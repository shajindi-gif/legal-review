"""应用配置 - 基于 pydantic-settings 从环境变量加载。"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量 / .env 加载。"""

    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local"),
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

    # ---- 统一账号：多登录渠道开关（未配置真实服务前保持 False，前台不展示）----
    auth_sms_enabled: bool = False
    auth_email_enabled: bool = False
    auth_password_enabled: bool = True
    auth_wechat_enabled: bool = False
    auth_qq_enabled: bool = False
    auth_weibo_enabled: bool = False
    auth_xiaohongshu_enabled: bool = False  # 小红书开放平台无标准网站 OAuth 登录

    # ---- 验证码 ----
    verification_code_ttl_seconds: int = 300
    verification_code_max_attempts: int = 5
    verification_per_target_cooldown_seconds: int = 60
    verification_per_ip_window_seconds: int = 600
    verification_per_ip_max_sends: int = 5
    verification_per_target_daily_max: int = 10

    # ---- 短信（mock | aliyun | tencent）----
    sms_provider: str = "mock"
    expose_mock_sms_code: bool = False
    aliyun_sms_access_key_id: str = ""
    aliyun_sms_access_key_secret: str = ""
    aliyun_sms_sign_name: str = ""
    aliyun_sms_template_code: str = ""
    aliyun_sms_endpoint: str = "dysmsapi.aliyuncs.com"
    tencent_sms_secret_id: str = ""
    tencent_sms_secret_key: str = ""
    tencent_sms_sdk_app_id: str = ""
    tencent_sms_sign_name: str = ""
    tencent_sms_template_id: str = ""

    # ---- 邮件（mock | smtp）----
    email_provider: str = "mock"
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_addr: str = ""
    smtp_from_name: str = ""
    smtp_use_tls: bool = True

    # ---- OAuth（微信/QQ/微博；小红书无标准网站 OAuth）----
    oauth_wechat_app_id: str = ""
    oauth_wechat_app_secret: str = ""
    oauth_wechat_redirect_uri: str = ""
    oauth_qq_app_id: str = ""
    oauth_qq_app_secret: str = ""
    oauth_qq_redirect_uri: str = ""
    oauth_weibo_app_id: str = ""
    oauth_weibo_app_secret: str = ""
    oauth_weibo_redirect_uri: str = ""

    # ---- Refresh token 持久化（rotation + revoke）----
    refresh_token_ttl_days: int = 30

    # ---- Core Auth（Strangler 双跑，Phase 4 Pilot）----
    # CORE_API_URL / CORE_API_KEY 从 .env.local 注入，严禁硬编码、严禁提交 git
    core_api_url: str = "http://127.0.0.1:8200"
    core_api_key: str = ""

    # ---- Agent 硬约束（来自工程铁律）----
    max_iteration: int = 5
    min_confidence: float = 0.7
    max_hallucination_rate: float = 0.05

    # ---- 支付：公网回调基址（必须是已 ICP 备案的 HTTPS 地址，不带尾斜杠）----
    public_base_url: str = "https://legalai86.com.cn"

    # ---- 支付：微信支付 V3（Native / JSAPI / H5 三端分流）----
    # 全部从 .env.local 注入，严禁硬编码、严禁提交 git
    wxpay_enabled: bool = False
    wxpay_mchid: str = ""                  # 商户号 mchid
    wxpay_appid: str = ""                  # 公众号 / 应用 AppID（Native 下单需要）
    wxpay_appsecret: str = ""              # 公众号 AppSecret（JSAPI 静默 OAuth 换 openid）
    wxpay_api_v3_key: str = ""             # APIv3 密钥（回调解密 AES-256-GCM）
    wxpay_mch_serial_no: str = ""          # 商户 API 证书序列号（40 位十六进制，请求签名用）
    wxpay_mch_private_key: str = ""        # 商户 API 私钥（apiclient_key.pem 全文 PEM，请求签名用）
    wxpay_public_key: str = ""             # 微信支付公钥（验签回调，非商户 apiclient 证书）
    wxpay_public_key_id: str = ""          # 微信支付公钥 ID（PUB_KEY_ID_xxx，回调头 serial）
    wxpay_notify_path: str = "/api/v1/billing/wechat/notify"
    wxpay_oauth_redirect_url: str = ""     # JSAPI OAuth 回调地址（须在公众号网页授权域名下）

    # ---- 支付：支付宝（电脑网站 page.pay / 手机网站 wap.pay，RSA2）----
    alipay_enabled: bool = False
    alipay_app_id: str = ""                # 支付宝开放平台 APPID
    alipay_private_key: str = ""           # 应用私钥（RSA2，PEM 全文或纯 base64 体）
    alipay_public_key: str = ""            # 支付宝公钥（用于验签，非应用公钥）
    alipay_gateway: str = "https://openapi.alipay.com/gateway.do"
    alipay_notify_path: str = "/api/v1/billing/alipay/notify"
    alipay_return_url: str = ""            # 支付完成同步回跳地址（page/wap 的 return_url）

    # ---- API 边缘限流（per-IP 兜底，Redis 固定窗口，超限 429）----
    rate_limit_enabled: bool = True
    rate_limit_per_ip_per_min: int = 300  # 每 IP 每分钟最大请求数
    rate_limit_exempt_paths: str = "/health,/docs,/redoc,/api/v1/openapi.json"

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
    def rate_limit_exempt_path_set(self) -> set[str]:
        """解析限流豁免路径为去前导斜杠的 set（用于逐请求前缀/全量判断）。"""
        return {p.strip().strip("/") for p in self.rate_limit_exempt_paths.split(",") if p.strip()}

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
