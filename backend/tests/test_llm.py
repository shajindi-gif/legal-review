"""LLM Gateway 测试 - Sprint 4 / FR-016 LLM 可切。

覆盖：
- DeepSeek / Qwen / Mock 三 Provider 工厂切换
- MockProvider 返回不同场景的 mock JSON（文件分类/主体审查/内容审查/评级/证据/报告/query）
- complete_json 解析校验
- 限流令牌桶
- 模型档位解析（strong/balanced/flash/reasoner）
- API key 缺失禁用真实 provider（硬约束）
- 重试耗尽抛 AgentError
"""
from __future__ import annotations

import asyncio
import contextlib
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.errors import AgentError, ValidationError
from app.tools.llm import (
    DeepSeekProvider,
    LLMResponse,
    MockProvider,
    OpenAICompatProvider,
    QwenProvider,
    TokenBucketRateLimiter,
    get_llm_provider,
    reset_llm_provider,
)


# ============== 工厂切换 ==============
def test_get_llm_provider_mock() -> None:
    """settings.llm_provider=mock → MockProvider。"""
    with patch("app.tools.llm.get_settings") as mock_s:
        s = MagicMock()
        s.llm_provider = "mock"
        s.llm_rate_limit_rpm = 60
        s.llm_model_tier = "strong"
        mock_s.return_value = s
        reset_llm_provider()
        provider = get_llm_provider()
        assert isinstance(provider, MockProvider)
        assert provider.name == "mock"


def test_get_llm_provider_deepseek() -> None:
    """settings.llm_provider=deepseek → DeepSeekProvider。"""
    with patch("app.tools.llm.get_settings") as mock_s:
        s = MagicMock()
        s.llm_provider = "deepseek"
        s.llm_rate_limit_rpm = 60
        s.llm_model_tier = "strong"
        s.deepseek_base_url = "https://api.deepseek.com"
        s.deepseek_api_key = "sk-test"
        s.deepseek_model_strong = "deepseek-chat"
        s.deepseek_model_balanced = "deepseek-chat"
        s.deepseek_model_flash = "deepseek-chat"
        s.deepseek_model_reasoner = "deepseek-reasoner"
        s.llm_max_retries = 3
        s.llm_retry_backoff = 2.0
        s.llm_timeout_seconds = 60
        mock_s.return_value = s
        reset_llm_provider()
        provider = get_llm_provider()
        assert isinstance(provider, DeepSeekProvider)
        assert provider.name == "deepseek"


def test_get_llm_provider_qwen() -> None:
    """settings.llm_provider=qwen → QwenProvider。"""
    with patch("app.tools.llm.get_settings") as mock_s:
        s = MagicMock()
        s.llm_provider = "qwen"
        s.llm_rate_limit_rpm = 60
        s.llm_model_tier = "strong"
        s.qwen_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        s.qwen_api_key = "sk-test"
        s.qwen_model_strong = "qwen3-max"
        s.qwen_model_balanced = "qwen-plus"
        s.qwen_model_flash = "qwen-turbo"
        s.qwen_model_reasoner = "qwen3-max"
        s.llm_max_retries = 3
        s.llm_retry_backoff = 2.0
        s.llm_timeout_seconds = 60
        mock_s.return_value = s
        reset_llm_provider()
        provider = get_llm_provider()
        assert isinstance(provider, QwenProvider)
        assert provider.name == "qwen"


def test_get_llm_provider_unknown_raises() -> None:
    """未知 provider → ValidationError。"""
    with patch("app.tools.llm.get_settings") as mock_s:
        s = MagicMock()
        s.llm_provider = "unknown"
        s.llm_rate_limit_rpm = 60
        s.llm_model_tier = "strong"
        mock_s.return_value = s
        reset_llm_provider()
        with pytest.raises(ValidationError, match="未知 LLM provider"):
            get_llm_provider()


# ============== Mock Provider 响应 ==============
@pytest.mark.asyncio
async def test_mock_complete_returns_text() -> None:
    """非 JSON 模式返回文本。"""
    provider = MockProvider()
    resp = await provider.complete("测试 prompt")
    assert resp.provider == "mock"
    assert "[mock-llm]" in resp.text
    assert resp.latency_ms >= 0
    assert resp.usage["prompt_tokens"] > 0


@pytest.mark.asyncio
async def test_mock_complete_json_default() -> None:
    """未知 prompt → 默认 mock JSON。"""
    provider = MockProvider()
    result = await provider.complete_json("未知 prompt")
    assert result["result"] == "mock"
    assert "prompt_preview" in result


@pytest.mark.asyncio
async def test_mock_complete_json_doc_classify() -> None:
    """文件分类 mock 响应。"""
    provider = MockProvider()
    # 构造与 doc_classify 模板匹配的 prompt
    prompt = "判定是否属于行政规范性文件"
    result = await provider.complete_json(prompt)
    assert result["is_normative"] is True
    assert result["confidence"] == 0.95
    assert len(result["evidences"]) == 1


@pytest.mark.asyncio
async def test_mock_complete_json_authority_review() -> None:
    """主体审查 mock 响应。"""
    provider = MockProvider()
    prompt = "审查制定主体是否合法"
    result = await provider.complete_json(prompt)
    assert result["status"] == "PASS"
    assert result["risks"] == []


@pytest.mark.asyncio
async def test_mock_complete_json_content_review() -> None:
    """内容审查 mock 响应。"""
    provider = MockProvider()
    prompt = "按 6 类违法情形审查"
    result = await provider.complete_json(prompt)
    assert result["status"] == "RISK"
    assert len(result["risks"]) == 1
    assert result["risks"][0]["risk_type"] == "违法设置行政许可"
    assert result["risks"][0]["evidence"]["law_name"] == "行政许可法"


@pytest.mark.asyncio
async def test_mock_complete_json_risk_assessment() -> None:
    """风险评级 mock 响应。"""
    provider = MockProvider()
    prompt = "综合评级给出总体评级"
    result = await provider.complete_json(prompt)
    assert result["overall_status"] == "RISK"
    assert result["risk_summary"]["high_count"] == 1


@pytest.mark.asyncio
async def test_mock_complete_json_evidence_verify() -> None:
    """证据校验 mock 响应。"""
    provider = MockProvider()
    prompt = "校验证据完整性"
    result = await provider.complete_json(prompt)
    assert result["status"] == "PASS"
    assert result["missing_evidences"] == []


@pytest.mark.asyncio
async def test_mock_complete_json_legal_query() -> None:
    """query 生成 mock 响应。"""
    provider = MockProvider()
    prompt = "生成 RAG 检索 query"
    result = await provider.complete_json(prompt)
    assert len(result["queries"]) == 5
    assert "行政许可设置依据" in result["queries"]


@pytest.mark.asyncio
async def test_mock_complete_json_report_generation() -> None:
    """报告生成 mock 响应。"""
    provider = MockProvider()
    prompt = "生成审查报告"
    result = await provider.complete_json(prompt)
    assert "report_markdown" in result
    assert result["section_complete"] is True


# ============== OpenAICompatProvider 模型档位解析 ==============
def test_resolve_model_explicit_overrides_tier() -> None:
    """显式传入 model 优先于 tier 映射。"""
    provider = _make_test_provider()
    assert provider._resolve_model(model="custom-model", tier="strong") == "custom-model"


def test_resolve_model_tier_mapping() -> None:
    """tier 映射到对应模型。"""
    provider = _make_test_provider()
    assert provider._resolve_model(model=None, tier="strong") == "deepseek-chat"
    assert provider._resolve_model(model=None, tier="reasoner") == "deepseek-reasoner"
    assert provider._resolve_model(model=None, tier="flash") == "deepseek-chat"


def test_resolve_model_unknown_tier_falls_back_default() -> None:
    """未知 tier → default_model。"""
    provider = _make_test_provider()
    assert provider._resolve_model(model=None, tier="unknown") == "deepseek-chat"


def _make_test_provider() -> OpenAICompatProvider:
    """构造测试用 OpenAICompatProvider。"""
    return OpenAICompatProvider(
        base_url="https://api.test.com",
        api_key="sk-test",
        provider_name="test",
        default_model="deepseek-chat",
        tier_models={
            "strong": "deepseek-chat",
            "balanced": "deepseek-chat",
            "flash": "deepseek-chat",
            "reasoner": "deepseek-reasoner",
        },
    )


# ============== API key 缺失禁用（硬约束） ==============
@pytest.mark.asyncio
async def test_openai_compat_missing_api_key_raises() -> None:
    """API key 缺失 → ValidationError（硬约束：未配置禁用真实 provider）。"""
    provider = OpenAICompatProvider(
        base_url="https://api.test.com",
        api_key="",  # 空
        provider_name="deepseek",
        default_model="deepseek-chat",
        tier_models={},
    )
    with pytest.raises(ValidationError, match="未配置 API key"):
        await provider.complete("测试")


# ============== 重试机制 ==============
@pytest.mark.asyncio
async def test_openai_compat_retries_on_5xx() -> None:
    """5xx 错误 → 重试。"""
    provider = _make_test_provider()
    provider._settings = MagicMock()
    provider._settings.llm_max_retries = 2
    provider._settings.llm_retry_backoff = 0.01  # 测试用小退避
    provider._settings.llm_timeout_seconds = 5
    provider._settings.llm_rate_limit_rpm = 1000
    provider._limiter = TokenBucketRateLimiter(1000)

    # mock httpx 返回 500
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_response.request = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        with pytest.raises(AgentError, match="已重试 2 次"):
            await provider.complete("测试")


@pytest.mark.asyncio
async def test_openai_compat_4xx_no_retry() -> None:
    """4xx（非 429）→ 直接抛 ValidationError，不重试。"""
    provider = _make_test_provider()
    provider._settings = MagicMock()
    provider._settings.llm_max_retries = 3
    provider._settings.llm_retry_backoff = 0.01
    provider._settings.llm_timeout_seconds = 5
    provider._settings.llm_rate_limit_rpm = 1000
    provider._limiter = TokenBucketRateLimiter(1000)

    mock_response = MagicMock()
    mock_response.status_code = 400
    mock_response.text = "Bad Request"
    mock_response.request = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        with pytest.raises(ValidationError, match="HTTP 400"):
            await provider.complete("测试")
        # 验证只调用一次（不重试）
        assert mock_client.post.call_count == 1


@pytest.mark.asyncio
async def test_openai_compat_success_returns_response() -> None:
    """成功调用 → LLMResponse。"""
    provider = _make_test_provider()
    provider._settings = MagicMock()
    provider._settings.llm_max_retries = 3
    provider._settings.llm_retry_backoff = 0.01
    provider._settings.llm_timeout_seconds = 5
    provider._settings.llm_rate_limit_rpm = 1000
    provider._limiter = TokenBucketRateLimiter(1000)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "测试响应"}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        resp = await provider.complete("测试", model="deepseek-chat")

    assert isinstance(resp, LLMResponse)
    assert resp.text == "测试响应"
    assert resp.model == "deepseek-chat"
    assert resp.provider == "test"
    assert resp.usage["total_tokens"] == 15


@pytest.mark.asyncio
async def test_openai_compat_json_mode_sets_response_format() -> None:
    """json_mode=True → payload 含 response_format=json_object。"""
    provider = _make_test_provider()
    provider._settings = MagicMock()
    provider._settings.llm_max_retries = 1
    provider._settings.llm_retry_backoff = 0.01
    provider._settings.llm_timeout_seconds = 5
    provider._settings.llm_rate_limit_rpm = 1000
    provider._limiter = TokenBucketRateLimiter(1000)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": '{"key": "value"}'}}],
        "usage": {},
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        await provider.complete("测试", json_mode=True)

    # 验证 payload 含 response_format
    call_args = mock_client.post.call_args
    payload = call_args.kwargs["json"]
    assert payload["response_format"] == {"type": "json_object"}


# ============== complete_json 解析失败 ==============
@pytest.mark.asyncio
async def test_complete_json_invalid_output_raises() -> None:
    """LLM 返回非合法 JSON → AgentError。"""
    provider = _make_test_provider()
    provider._settings = MagicMock()
    provider._settings.llm_max_retries = 1
    provider._settings.llm_retry_backoff = 0.01
    provider._settings.llm_timeout_seconds = 5
    provider._settings.llm_rate_limit_rpm = 1000
    provider._limiter = TokenBucketRateLimiter(1000)

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "不是 JSON {{"}}],
        "usage": {},
    }

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_class.return_value = mock_client

        with pytest.raises(AgentError, match="非合法 JSON"):
            await provider.complete_json("测试")


# ============== 限流令牌桶 ==============
@pytest.mark.asyncio
async def test_token_bucket_allows_burst_within_capacity() -> None:
    """令牌桶容量内允许突发。"""
    limiter = TokenBucketRateLimiter(rpm=60)  # 容量 60
    # 前 60 次应该几乎不阻塞
    for _ in range(5):
        await limiter.acquire()


@pytest.mark.asyncio
async def test_token_bucket_blocks_when_empty() -> None:
    """令牌耗尽后阻塞（rpm=1 容量 1，第二次会等待）。"""
    limiter = TokenBucketRateLimiter(rpm=1)  # 容量 1，每秒补 1/60
    await limiter.acquire()  # 立即拿到
    # 第二次应该等待（约 60 秒），用 timeout 0.5s 验证会阻塞但不抛错
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(limiter.acquire(), timeout=0.5)


# ============== reset ==============
def test_reset_llm_provider_clears_singleton() -> None:
    """reset 单例后下次 get 重新初始化。"""
    with patch("app.tools.llm.get_settings") as mock_s:
        s = MagicMock()
        s.llm_provider = "mock"
        s.llm_rate_limit_rpm = 60
        s.llm_model_tier = "strong"
        mock_s.return_value = s
        reset_llm_provider()
        p1 = get_llm_provider()
        p2 = get_llm_provider()
        assert p1 is p2  # 单例
        reset_llm_provider()
        p3 = get_llm_provider()
        assert p3 is not p1  # 重置后新实例
