"""LLM Gateway - 多 Provider 统一接入层（Sprint 4 / FR-016 LLM 可切）。

设计原则：
1. 三 Provider：DeepSeek（V4 Pro/Flash）/ Qwen（Qwen3.7-Max/Plus/Turbo）/ Mock（测试）
2. 统一 OpenAI Chat Completions 兼容协议（DeepSeek & Qwen 均兼容）
3. 重试：指数退避 + 抖动（5xx / 超时 / 网络错误）
4. 限流：简单令牌桶（RPM 限制）
5. 结构化输出：JSON Mode（response_format=json_object）
6. 硬约束：未配置 API key 时禁用真实 provider，强制回退 mock

模型档位映射（来自 settings + registry.yaml model_tier）：
- strong：旗舰（deepseek-v4-pro / qwen3.7-max）
- balanced：速度优先（deepseek-v4-flash / qwen-plus）
- flash：轻量便宜（deepseek-v4-flash / qwen-turbo）
- reasoner：带推理链（deepseek-v4-pro / qwen3.7-max）

注：旧 deepseek-chat / deepseek-reasoner 已于 2026-07-24 强制熔断停用；
    qwen3-max 升级为 qwen3.7-max（MoE，Agent 时代旗舰）。
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.errors import AgentError, ValidationError
from app.core.logging import get_logger

logger = get_logger("tools.llm")

# ============== 模型档位 ==============
VALID_TIERS = ("strong", "balanced", "flash", "reasoner")


# ============== 响应数据结构 ==============
@dataclass
class LLMResponse:
    """LLM 统一响应。"""

    text: str
    model: str
    provider: str
    usage: dict[str, int]  # prompt_tokens / completion_tokens / total_tokens
    latency_ms: int
    raw_response: dict[str, Any] = field(default_factory=dict)


# ============== Provider 抽象 ==============
class LLMProvider:
    """LLM Provider 抽象基类。"""

    @property
    def name(self) -> str:
        raise NotImplementedError

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
        trace_id: str | None = None,
    ) -> LLMResponse:
        raise NotImplementedError

    async def complete_json(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        trace_id: str | None = None,
        tier: str | None = None,
    ) -> dict[str, Any]:
        """结构化输出：JSON Mode + 解析校验。

        Args:
            tier: 模型档位（strong/balanced/flash/reasoner），由 PromptManager 传入；
                  OpenAICompatProvider 会按 tier 映射到具体 model_name。
        """
        resp = await self.complete(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            json_mode=True,
            trace_id=trace_id,
            tier=tier,
        )
        try:
            return json.loads(resp.text)
        except json.JSONDecodeError as e:
            raise AgentError(
                "llm",
                f"LLM 输出非合法 JSON: {e}。原始输出前 200 字: {resp.text[:200]}",
                trace_id=trace_id,
            ) from e


# ============== 令牌桶限流 ==============
class TokenBucketRateLimiter:
    """简单令牌桶限流（按 RPM 限制）。

    异步安全：单进程内共享。多进程需走 Redis（Sprint 后续）。
    """

    def __init__(self, rpm: int) -> None:
        self._rpm = max(1, rpm)
        # 计算每秒补充的令牌数（rpm / 60）
        self._refill_per_sec = self._rpm / 60.0
        self._capacity = float(self._rpm)
        self._tokens = float(self._rpm)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """获取一个令牌（无则等待）。"""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._last_refill = now

            # 补充令牌
            self._tokens = min(self._capacity, self._tokens + elapsed * self._refill_per_sec)

            if self._tokens < 1.0:
                # 需要等待
                wait = (1.0 - self._tokens) / self._refill_per_sec
                logger.debug("rate_limit_wait", wait_s=round(wait, 2))
                await asyncio.sleep(wait)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0


# ============== OpenAI 兼容 Provider 基类 ==============
class OpenAICompatProvider(LLMProvider):
    """OpenAI Chat Completions 兼容协议 Provider 基类。

    DeepSeek 和 Qwen 都兼容此协议。
    子类只需提供 base_url / api_key / 默认 model。
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        provider_name: str,
        default_model: str,
        tier_models: dict[str, str],
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._provider_name = provider_name
        self._default_model = default_model
        self._tier_models = tier_models
        self._settings = get_settings()
        self._limiter = TokenBucketRateLimiter(self._settings.llm_rate_limit_rpm)

    @property
    def name(self) -> str:
        return self._provider_name

    def _resolve_model(self, model: str | None, tier: str | None = None) -> str:
        """解析实际调用的模型名。

        优先级：显式传入 model > tier 映射 > default_model
        """
        if model:
            return model
        if tier and tier in self._tier_models:
            return self._tier_models[tier]
        return self._default_model

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
        trace_id: str | None = None,
        tier: str | None = None,
    ) -> LLMResponse:
        """调用 LLM（含重试 + 限流）。"""
        if not self._api_key:
            raise ValidationError(
                f"LLM provider={self._provider_name} 未配置 API key，"
                f"请在 .env 设置对应 *_API_KEY（硬约束：未配置禁用真实 provider）"
            )

        resolved_model = self._resolve_model(model, tier)
        start = time.monotonic()

        # 限流
        await self._limiter.acquire()

        # 构造请求
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        # 重试循环
        max_retries = self._settings.llm_max_retries
        backoff = self._settings.llm_retry_backoff
        timeout = self._settings.llm_timeout_seconds

        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)

                # 5xx 重试
                if resp.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"HTTP {resp.status_code}", request=resp.request, response=resp
                    )

                # 4xx 不重试（除 429）
                if resp.status_code == 429:
                    raise httpx.HTTPStatusError(
                        "HTTP 429 Too Many Requests",
                        request=resp.request,
                        response=resp,
                    )
                if resp.status_code >= 400:
                    body = resp.text[:500]
                    raise ValidationError(
                        f"LLM API 调用失败 {self._provider_name} "
                        f"HTTP {resp.status_code}: {body}"
                    )

                data = resp.json()
                latency_ms = int((time.monotonic() - start) * 1000)

                text = ""
                choices = data.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    text = msg.get("content", "")

                usage = data.get("usage", {})

                logger.info(
                    "llm_complete_done",
                    provider=self._provider_name,
                    model=resolved_model,
                    latency_ms=latency_ms,
                    prompt_tokens=usage.get("prompt_tokens", 0),
                    completion_tokens=usage.get("completion_tokens", 0),
                    attempt=attempt,
                    trace_id=trace_id,
                )

                return LLMResponse(
                    text=text,
                    model=resolved_model,
                    provider=self._provider_name,
                    usage={
                        "prompt_tokens": usage.get("prompt_tokens", 0),
                        "completion_tokens": usage.get("completion_tokens", 0),
                        "total_tokens": usage.get("total_tokens", 0),
                    },
                    latency_ms=latency_ms,
                    raw_response=data,
                )

            except (httpx.HTTPStatusError, httpx.TimeoutException, httpx.NetworkError) as e:
                last_error = e
                if attempt < max_retries:
                    wait = backoff * (2 ** (attempt - 1))
                    # 抖动：避免重试雷同
                    import random
                    jitter = random.uniform(0, 0.5)
                    logger.warning(
                        "llm_retry",
                        provider=self._provider_name,
                        attempt=attempt,
                        max_retries=max_retries,
                        wait_s=round(wait + jitter, 2),
                        error=str(e),
                        trace_id=trace_id,
                    )
                    await asyncio.sleep(wait + jitter)
                else:
                    logger.error(
                        "llm_exhausted_retries",
                        provider=self._provider_name,
                        attempts=attempt,
                        error=str(e),
                        trace_id=trace_id,
                    )

        # 重试耗尽
        raise AgentError(
            "llm",
            f"LLM 调用失败（已重试 {max_retries} 次）：{last_error}",
            trace_id=trace_id,
        ) from last_error


# ============== DeepSeek Provider ==============
class DeepSeekProvider(OpenAICompatProvider):
    """DeepSeek V4 系列 Provider（Pro / Flash 双档，2026-07 上线）。

    模型档位：
    - strong: deepseek-v4-pro（旗舰 Pro，支持推理链）
    - balanced: deepseek-v4-flash
    - flash: deepseek-v4-flash
    - reasoner: deepseek-v4-pro

    注：旧 deepseek-chat / deepseek-reasoner 已于 2026-07-24 15:59 UTC 强制熔断停用。
    """

    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            base_url=s.deepseek_base_url,
            api_key=s.deepseek_api_key,
            provider_name="deepseek",
            default_model=s.deepseek_model_strong,
            tier_models={
                "strong": s.deepseek_model_strong,
                "balanced": s.deepseek_model_balanced,
                "flash": s.deepseek_model_flash,
                "reasoner": s.deepseek_model_reasoner,
            },
        )


# ============== Qwen Provider ==============
class QwenProvider(OpenAICompatProvider):
    """Qwen 通义千问 Provider（DashScope 兼容 OpenAI 协议）。

    模型档位（2026 年 Qwen3.7-Max 旗舰 MoE 上线）：
    - strong: qwen3.7-max（旗舰 Max，MoE 推理）
    - balanced: qwen-plus（速度优先）
    - flash: qwen-turbo（轻量便宜）
    - reasoner: qwen3.7-max
    """

    def __init__(self) -> None:
        s = get_settings()
        super().__init__(
            base_url=s.qwen_base_url,
            api_key=s.qwen_api_key,
            provider_name="qwen",
            default_model=s.qwen_model_strong,
            tier_models={
                "strong": s.qwen_model_strong,
                "balanced": s.qwen_model_balanced,
                "flash": s.qwen_model_flash,
                "reasoner": s.qwen_model_reasoner,
            },
        )


# ============== Mock Provider（测试用） ==============
class MockProvider(LLMProvider):
    """Mock LLM Provider - 测试 / CI 用。

    返回确定性 JSON，避免真实 API 调用。
    根据 prompt 关键词返回不同模板（覆盖测试场景）。
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def name(self) -> str:
        return "mock"

    async def complete(
        self,
        prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        json_mode: bool = False,
        trace_id: str | None = None,
        tier: str | None = None,
    ) -> LLMResponse:
        start = time.monotonic()

        # 根据 prompt 关键词返回不同 mock 响应
        text = self._mock_response(prompt, json_mode=json_mode)

        latency_ms = int((time.monotonic() - start) * 1000)
        return LLMResponse(
            text=text,
            model=model or "mock-model",
            provider="mock",
            usage={
                "prompt_tokens": len(prompt) // 4,
                "completion_tokens": len(text) // 4,
                "total_tokens": (len(prompt) + len(text)) // 4,
            },
            latency_ms=latency_ms,
            raw_response={"mock": True},
        )

    def _mock_response(self, prompt: str, *, json_mode: bool) -> str:
        """根据 prompt 关键词返回 mock 响应。"""
        # 非 JSON 模式：直接返回文本
        if not json_mode:
            return f"[mock-llm] {prompt[:200]}"

        # JSON 模式：按 prompt 关键词返回对应 mock 结构
        mock_data = self._mock_json(prompt)
        return json.dumps(mock_data, ensure_ascii=False)

    @staticmethod
    def _mock_json(prompt: str) -> dict[str, Any]:
        """按 prompt 关键词返回对应 mock JSON 结构。"""

        # 文件分类
        if "是否属于" in prompt and "行政规范性文件" in prompt:
            return {
                "is_normative": True,
                "confidence": 0.95,
                "reasoning": "文件涉及公民权利义务且具有普遍约束力",
                "evidences": [
                    {
                        "law_name": "行政规范性文件制定程序规定",
                        "article": "第三条",
                        "original_text": "本规定所称行政规范性文件...",
                        "explanation": "符合 4 要素",
                    }
                ],
            }

        # 主体审查
        if "制定主体是否合法" in prompt:
            return {
                "status": "PASS",
                "risks": [],
                "evidences": [
                    {
                        "law_name": "地方组织法",
                        "article": "第七十六条",
                        "original_text": "县级人民政府有权制定...",
                        "explanation": "主体合法",
                    }
                ],
                "confidence": 0.95,
                "reasoning": "制定主体在法定清单内",
            }

        # 内容审查
        if "6 类违法情形" in prompt:
            return {
                "status": "RISK",
                "risks": [
                    {
                        "dimension": "content",
                        "risk_type": "违法设置行政许可",
                        "severity": "high",
                        "paragraph_anchor": "#p3",
                        "evidence": {
                            "law_name": "行政许可法",
                            "article": "第十五条",
                            "original_text": "本法所称行政许可...",
                            "explanation": "文件增设了行政许可",
                        },
                        "confidence": 0.85,
                        "suggestion": "删除增设行政许可的条款",
                    }
                ],
                "evidences": [],
                "confidence": 0.85,
                "reasoning": "发现 1 处违法设置行政许可",
            }

        # 风险评级
        if "总体评级" in prompt:
            return {
                "overall_status": "RISK",
                "risk_summary": {
                    "critical_count": 0,
                    "high_count": 1,
                    "medium_count": 0,
                    "low_count": 0,
                    "dimensions_hit": ["content"],
                },
                "top_risks": [],
                "confidence": 0.85,
                "reasoning": "存在 1 处 high 风险",
            }

        # 证据校验
        if "证据完整性" in prompt:
            return {
                "status": "PASS",
                "missing_evidences": [],
                "duplicated_risks": [],
                "low_confidence_risks": [],
                "confidence": 1.0,
                "reasoning": "证据完整",
            }

        # query 生成
        if "RAG 检索 query" in prompt:
            return {
                "queries": [
                    "行政规范性文件制定主体权限",
                    "行政许可设置依据",
                    "行政处罚设定权限",
                    "行政强制措施依据",
                    "优化营商环境 限制公平竞争",
                ],
            }

        # 报告生成
        if "审查报告" in prompt:
            return {
                "report_markdown": "# 审查报告\n\n## 一、文件基本情况\n...",
                "evidence_count": 3,
                "section_complete": True,
                "confidence": 1.0,
            }

        # 默认响应
        return {"result": "mock", "prompt_preview": prompt[:200]}


# ============== 工厂 ==============
_provider: LLMProvider | None = None


def get_llm_provider() -> LLMProvider:
    """获取全局 LLM Provider 单例（按 settings.llm_provider）。"""
    global _provider
    if _provider is None:
        s = get_settings()
        if s.llm_provider == "deepseek":
            _provider = DeepSeekProvider()
        elif s.llm_provider == "qwen":
            _provider = QwenProvider()
        elif s.llm_provider == "mock":
            _provider = MockProvider()
        else:
            raise ValidationError(
                f"未知 LLM provider: {s.llm_provider}（支持 deepseek|qwen|mock）"
            )
        logger.info(
            "llm_provider_initialized",
            provider=_provider.name,
            tier_default=s.llm_model_tier,
        )
    return _provider


def reset_llm_provider() -> None:
    """重置单例（测试用）。"""
    global _provider
    _provider = None
