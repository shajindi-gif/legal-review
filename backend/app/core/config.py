"""应用配置 - 基于 pydantic-settings 从环境变量加载。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 加载。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ---- 应用 ----
    app_name: str = "行政规范性文件智能合法性审查 Agent 系统"
    app_version: str = "0.1.0"
    debug: bool = False
    environment: str = Field(default="local")  # local|ci|staging|prod

    # ---- 数据库 ----
    database_url: str = Field(
        default="postgresql+asyncpg://legal:legal_dev_pass@localhost:5432/legal_review"
    )
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_recycle: int = 3600

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- 文件沙箱 ----
    sandbox_root: str = "./_sandbox"
    sandbox_max_file_mb: int = 50
    sandbox_allowed_extensions: str = "docx,pdf,png,jpg,jpeg,txt"

    # ---- LLM Gateway ----
    # Provider 切换：deepseek|qwen|mock（测试用 mock，避免真实 API 调用）
    llm_provider: str = "deepseek"  # deepseek|qwen|mock
    # 模型档位：strong（旗舰）| balanced（速度优先）| flash（轻量便宜）| reasoner（带推理链）
    llm_model_tier: str = "strong"  # strong|balanced|flash|reasoner

    # ---- DeepSeek（V4 系列 Pro/Flash 双档，2026-07 上线；
    #      旧 deepseek-chat / deepseek-reasoner 已停用熔断）----
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    # strong=deepseek-v4-pro(旗舰 Pro) / balanced=deepseek-v4-flash
    # flash=deepseek-v4-flash / reasoner=deepseek-v4-pro
    deepseek_model_strong: str = "deepseek-v4-pro"
    deepseek_model_balanced: str = "deepseek-v4-flash"
    deepseek_model_flash: str = "deepseek-v4-flash"
    deepseek_model_reasoner: str = "deepseek-v4-pro"

    # ---- Qwen（Qwen3.7-Max 旗舰 MoE，2026 年；
    #      Qwen-Plus/Turbo 中轻档，两三代以内）----
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    # strong=qwen3.7-max(旗舰 Max) / balanced=qwen-plus
    # flash=qwen-turbo / reasoner=qwen3.7-max
    qwen_model_strong: str = "qwen3.7-max"
    qwen_model_balanced: str = "qwen-plus"
    qwen_model_flash: str = "qwen-turbo"
    qwen_model_reasoner: str = "qwen3.7-max"

    # ---- LLM Gateway 控制：超时 / 重试 / 限流 ----
    llm_timeout_seconds: int = 60
    llm_max_retries: int = 3
    llm_retry_backoff: float = 2.0  # 指数退避基数（秒）
    llm_rate_limit_rpm: int = 60  # 每分钟最大请求数

    # ---- Embedding（多后端可切，独立于 LLM）----
    embedding_backend: str = ""  # local|api|mock；空则 debug=mock 否则 local
    embedding_provider: str = "mock"  # mock|bge-m3-local|dashscope
    embedding_model: str = "bge-m3"
    embedding_dim: int = 1024
    dashscope_api_key: str = ""  # Embedding 用 DashScope API 时填

    # ---- 鉴权 ----
    jwt_secret: str = "change_me_in_production"
    jwt_access_ttl: int = 3600
    jwt_refresh_ttl: int = 604800

    # ---- Agent 硬约束（来自工程铁律）----
    max_iteration: int = 5
    min_confidence: float = 0.7
    max_hallucination_rate: float = 0.05

    # ---- CORS ----
    # 逗号分隔字符串(pydantic-settings 对 list 类型要求 JSON 数组,
    # 改用 str 存储 + property 返回 list,兼容 .env 逗号格式)
    cors_origins: str = ""

    _default_cors_origins: list[str] = [
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3080", "http://127.0.0.1:3080",
        "https://legalai86.com.cn", "https://www.legalai86.com.cn",
    ]

    @property
    def cors_origin_list(self) -> list[str]:
        """解析 cors_origins 字符串为 list,空则返回默认值。"""
        if not self.cors_origins:
            return self._default_cors_origins
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def sandbox_path(self) -> Path:
        """沙箱根目录绝对路径。"""
        p = Path(self.sandbox_root).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def allowed_extensions_set(self) -> set[str]:
        """允许上传的扩展名集合。"""
        return {ext.strip().lower() for ext in self.sandbox_allowed_extensions.split(",")}


@lru_cache
def get_settings() -> Settings:
    """单例配置，避免重复 IO。"""
    return Settings()
