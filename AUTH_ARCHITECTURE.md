# LegalAI 统一身份系统架构 (AUTH_ARCHITECTURE)

> 版本: v1.0  
> 日期: 2026-08-25  
> 范围: 把当前 "Demo 登录" 升级为生产级 SaaS 身份系统  
> 配套文档: `AUTH_SYSTEM_AUDIT.md` · `ACCOUNT_LINKING_DESIGN.md` · `AUTH_SECURITY_REVIEW.md`

---

## 0. 设计目标

把 `https://legalai86.com.cn` 从"仅 Demo 账号可用"升级为:

> **任何陌生用户都可以在零开发者介入的情况下,完成注册 → 验证 → 登录 → 长期使用 LegalAI 的全部核心功能。**

设计原则:

1. **增量优先**: 不重写, 在已有 12 张业务表 + JWT + bcrypt 之上做增量。
2. **统一身份 (Unified Identity)**: 一个 `User` 可以同时绑定手机、邮箱、密码、微信、GitHub、Google, 全部汇入同一 `user_id`。
3. **可插拔 Provider**: SMS / Email / OAuth / Captcha 全部走接口 + Adapter, 通过 env 切换。
4. **生产级安全**: Token rotation、Cookie HttpOnly+Secure+SameSite, 防枚举、防爆破、防重放。
5. **可观测**: 结构化日志、登录事件、UTM 归因、行为埋点全部入库。
6. **可灰度**: 所有新功能通过 `*_ENABLED` 与 `*_PROVIDER` 开关控制, 默认不影响线上已有用户。

---

## 1. 顶层架构图

```
                    ┌─────────────────────────────────────────────┐
                    │           Client (Browser / Mobile)         │
                    │  Next.js 16 · React 19 · Zustand · axios     │
                    │  Cookie: lr_token (HttpOnly Secure)         │
                    └────────────────┬────────────────────────────┘
                                     │  HTTPS
                                     ▼
   ┌────────────────────────────────────────────────────────────────┐
   │                    Nginx (Tencent SSL · HSTS)                  │
   │        /          →  frontend:3081                              │
   │        /api/      →  backend:8000 (uvicorn workers=2)          │
   └────────────────┬───────────────────────────────────────────────┘
                    │
                    ▼
   ┌────────────────────────────────────────────────────────────────┐
   │                       FastAPI (Backend)                       │
   │                                                                │
   │   ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
   │   │  Auth    │  │  Users   │  │ Account  │  │   Onboarding │  │
   │   │ Router   │  │  Router  │  │  Router  │  │   Router     │  │
   │   └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────┬───────┘  │
   │        │             │              │              │          │
   │   ┌────▼─────────────▼──────────────▼──────────────▼───────┐  │
   │   │              AuthService (unified identity)           │  │
   │   │  · register_phone / register_email                    │  │
   │   │  · login_password / login_sms                         │  │
   │   │  · refresh_token / rotate / revoke                    │  │
   │   │  · bind_identity / unlink_identity / link_account     │  │
   │   │  · forgot_password / reset_password                   │  │
   │   │  · onboarding_complete / soft_delete                  │  │
   │   └────┬──────────┬───────────┬────────────┬──────────────┘  │
   │        │          │           │            │                 │
   │   ┌────▼───┐ ┌────▼────┐ ┌────▼────┐ ┌────▼──────────┐       │
   │   │ SMS    │ │ Email   │ │ OAuth   │ │  RateLimit /  │       │
   │   │Adapter │ │ Adapter │ │ Adapter │ │  Audit / Log  │       │
   │   └───┬────┘ └────┬────┘ └────┬────┘ └───────┬───────┘       │
   │       │           │          │               │               │
   │   ┌───▼───────────▼──────────▼───────────────▼────────────┐  │
   │   │       SQLAlchemy 2.0 async  ·  PostgreSQL 16          │  │
   │   │       + pgvector  ·  redis (rate limit, session)      │  │
   │   └──────────────────────────────────────────────────────┘  │
   └────────────────────────────────────────────────────────────────┘
```

---

## 2. 核心数据模型 (增量)

完整 SQL 见 Alembic 0003 migration, 这里只描述关键字段。

### 2.1 `users` (扩展已有)

```sql
ALTER TABLE users
    -- 展示信息
    ADD COLUMN display_name       VARCHAR(64)  NULL,  -- 昵称 (默认 real_name)
    ADD COLUMN avatar_url         TEXT         NULL,
    ADD COLUMN locale            VARCHAR(16)  NOT NULL DEFAULT 'zh-CN',
    ADD COLUMN timezone          VARCHAR(64)  NOT NULL DEFAULT 'Asia/Shanghai',

    -- 验证状态
    ADD COLUMN email_verified_at  TIMESTAMPTZ  NULL,
    ADD COLUMN phone_verified_at  TIMESTAMPTZ  NULL,
    -- phone 已经存在, 但加 UNIQUE 索引 (在 0003 加)

    -- 安全相关
    ADD COLUMN password_changed_at    TIMESTAMPTZ  NULL,
    ADD COLUMN failed_login_count     INT          NOT NULL DEFAULT 0,
    ADD COLUMN locked_until           TIMESTAMPTZ  NULL,

    -- 软删除
    ADD COLUMN deactivated_at     TIMESTAMPTZ  NULL,
    ADD COLUMN deactivation_reason VARCHAR(64) NULL,

    -- Onboarding
    ADD COLUMN onboarding_role    VARCHAR(32)  NULL,   -- legal_counsel / lawyer / gov / biz_owner / individual / other
    ADD COLUMN onboarding_purposes JSONB       NULL,   -- ["contract_review","legal_qa",...]
    ADD COLUMN onboarding_completed_at TIMESTAMPTZ NULL;
```

**phone UNIQUE 索引** (部分索引, 跳过 NULL):

```sql
CREATE UNIQUE INDEX ux_users_phone_normalized
    ON users ((regexp_replace(phone, '^\+?86', '')))
    WHERE phone IS NOT NULL;
```

> 内层存储统一为 `+8613800138000`, 索引也按去掉 `+86` 的纯号生成, 杜绝空格/横线导致重复。

### 2.2 `oauth_identities` (新表)

```sql
CREATE TABLE oauth_identities (
    id                 BIGSERIAL PRIMARY KEY,
    user_id            BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    provider           VARCHAR(16) NOT NULL,           -- wechat / github / google
    provider_user_id   VARCHAR(128) NOT NULL,          -- openid / sub / id
    provider_email     VARCHAR(255) NULL,              -- 来自 provider, 不一定 verified
    provider_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    access_token_enc   BYTEA NULL,                     -- Fernet 对称加密
    refresh_token_enc  BYTEA NULL,
    scope              TEXT NULL,
    raw_profile        JSONB NULL,                     -- 仅保留必要字段, 不存 token
    created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT uq_oauth_provider_user UNIQUE (provider, provider_user_id)
);

CREATE INDEX ix_oauth_user ON oauth_identities(user_id);
```

### 2.3 `verification_codes` (新表)

```sql
CREATE TABLE verification_codes (
    id              BIGSERIAL PRIMARY KEY,
    target          VARCHAR(64) NOT NULL,        -- +8613800138000 或 email
    channel         VARCHAR(16) NOT NULL,        -- sms / email
    purpose         VARCHAR(32) NOT NULL,        -- register / login / reset_password / bind_phone / change_phone / verify_email
    code_hash       VARCHAR(128) NOT NULL,       -- bcrypt(code, cost=10) 落库
    expires_at      TIMESTAMPTZ NOT NULL,
    attempt_count   INT NOT NULL DEFAULT 0,
    max_attempts    INT NOT NULL DEFAULT 5,
    used_at         TIMESTAMPTZ NULL,
    ip_address      INET NULL,
    user_agent      TEXT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_vc_target_purpose ON verification_codes(target, purpose, created_at DESC);
```

> 不存明文, 校验时 `bcrypt.checkpw` 比对; 5 次错误直接作废整行 (`used_at = NOW()`)。

### 2.4 `refresh_tokens` (新表)

```sql
CREATE TABLE refresh_tokens (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash      CHAR(64) NOT NULL UNIQUE,     -- sha256(refresh_token)
    issued_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at      TIMESTAMPTZ NOT NULL,
    revoked_at      TIMESTAMPTZ NULL,
    replaced_by_id  UUID NULL REFERENCES refresh_tokens(id),
    user_agent      TEXT NULL,
    ip_address      INET NULL,
    device_id       VARCHAR(128) NULL
);

CREATE INDEX ix_rt_user ON refresh_tokens(user_id);
CREATE INDEX ix_rt_hash ON refresh_tokens(token_hash);
```

- **Rotation**: refresh 时生成新 token, 把旧 `replaced_by_id` 指向新行, 旧行 `revoked_at = NOW()`。
- **Reuse detection**: 命中已 `revoked_at IS NOT NULL` 的 token → 整链作废 (refresh_token_reuse_attack)。

### 2.5 `user_login_events` (新表)

```sql
CREATE TABLE user_login_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
    identifier      VARCHAR(128) NULL,           -- 输入的 phone/email (用于 failed 场景)
    login_method    VARCHAR(32) NOT NULL,        -- password / sms / oauth:github / oauth:wechat ...
    success         BOOLEAN NOT NULL,
    failure_reason  VARCHAR(64) NULL,            -- invalid_password / invalid_code / locked / not_found / rate_limited
    ip_address      INET NULL,
    user_agent      TEXT NULL,
    device_id       VARCHAR(128) NULL,
    trace_id        VARCHAR(64) NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_login_user_time ON user_login_events(user_id, created_at DESC);
CREATE INDEX ix_login_ip_time ON user_login_events(ip_address, created_at DESC);
```

### 2.6 `user_acquisition_sources` (新表)

```sql
CREATE TABLE user_acquisition_sources (
    user_id         BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    utm_source      VARCHAR(64) NULL,
    utm_medium      VARCHAR(64) NULL,
    utm_campaign    VARCHAR(128) NULL,
    utm_content     VARCHAR(128) NULL,
    utm_term        VARCHAR(128) NULL,
    referrer        TEXT NULL,
    landing_page    TEXT NULL,
    first_seen_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

### 2.7 `user_events` (新表, 通用埋点)

```sql
CREATE TABLE user_events (
    id              BIGSERIAL PRIMARY KEY,
    user_id         BIGINT NULL REFERENCES users(id) ON DELETE SET NULL,
    anonymous_id    VARCHAR(64) NULL,           -- 未登录用户的 cookie id
    event_name      VARCHAR(64) NOT NULL,       -- page_view / signup_started / login_success ...
    properties      JSONB NULL,
    ip_address      INET NULL,
    user_agent      TEXT NULL,
    trace_id        VARCHAR(64) NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX ix_event_name_time ON user_events(event_name, created_at DESC);
CREATE INDEX ix_event_user_time ON user_events(user_id, created_at DESC);
```

---

## 3. Provider 抽象层

### 3.1 SMS Provider

```python
# app/services/sms/base.py
class SMSProvider(Protocol):
    name: str
    async def send_code(self, *, phone: str, code: str, purpose: str, ttl_seconds: int) -> SMSResult: ...

# app/services/sms/mock_provider.py
class MockSMSProvider:
    """开发环境使用, 验证码直接打印到日志, 可选 redis pub 给前端调试面板。"""
    async def send_code(...): log.info("[MOCK SMS] phone=%s code=%s", phone, code)

# app/services/sms/tencent_provider.py
class TencentSMSProvider:
    """腾讯云 SecretId/SecretKey 走 SDK 或 HTTPS 签名。"""
    ...

# app/services/sms/aliyun_provider.py
class AliyunSMSProvider: ...

# app/services/sms/factory.py
def get_sms_provider() -> SMSProvider:
    name = settings.sms_provider
    if name == "mock": return MockSMSProvider()
    if name == "tencent": return TencentSMSProvider(...)
    if name == "aliyun": return AliyunSMSProvider(...)
    raise RuntimeError(f"unknown SMS_PROVIDER={name}")
```

### 3.2 Email Provider

```python
class EmailProvider(Protocol):
    name: str
    async def send(self, *, to: str, subject: str, html: str, text: str) -> EmailResult: ...

class MockEmailProvider: ...        # 落到日志
class SMTPEmailProvider: ...        # 通用 SMTP (阿里云邮件推送 / 自建 / Mailgun)
class SESEmailProvider: ...         # 未来 AWS SES
```

### 3.3 OAuth Provider

```python
class OAuthProvider(Protocol):
    name: str                           # "github" / "google" / "wechat"
    enabled: bool
    def authorize_url(self, *, state: str, redirect_uri: str) -> str: ...
    async def exchange_code(self, *, code: str, redirect_uri: str) -> OAuthTokens: ...
    async def fetch_userinfo(self, *, access_token: str) -> OAuthUserInfo: ...

class GitHubOAuthProvider: ...
class GoogleOAuthProvider: ...
class WeChatOAuthProvider:
    """微信开放平台 网站应用 scope= snsapi_login; 公众号走 snsapi_userinfo 单独 adapter。"""
    ...
```

### 3.4 Captcha Provider

```python
class CaptchaProvider(Protocol):
    enabled: bool
    async def verify(self, *, token: str, ip: str) -> bool: ...

class TurnstileCaptcha: ...
class HCaptcha: ...
class TencentCaptcha: ...
class NoopCaptcha: ...   # CAPTCHA_ENABLED=false
```

---

## 4. 密码体系

### 4.1 算法策略

- **首选**: `argon2-cffi` Argon2id (time_cost=2, memory_cost=64MB, parallelism=2)
- **兼容**: 已有的 `bcrypt` cost=12 哈希保留
- **存储格式**: `$argon2id$v=19$m=65536,t=2,p=2$...` 或 `$2b$12$...`
- **校验**: `pwdlib` 或自写 `identify_hasher` 识别前缀; 命中 bcrypt 时 `bcrypt.checkpw`, 命中 argon2 时 `PasswordHasher().verify`
- **升级**: 登录成功后若 hash 是 bcrypt, 异步 task 用新 Argon2id 重哈希, 透明升级

```python
def hash_password(plain: str) -> str:
    if settings.password_hasher == "argon2id":
        return argon2_hasher.hash(plain)
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()

def verify_password(plain: str, hashed: str) -> bool:
    if hashed.startswith("$argon2id$"):
        try:
            return argon2_hasher.verify(hashed, plain)
        except VerifyMismatchError:
            return False
    if hashed.startswith("$2"):
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    return False
```

### 4.2 密码规则

| 维度 | 规则 |
| --- | --- |
| 最短 | 8 字符 |
| 最长 | 128 字符 |
| 必须 | 字母 + 数字 (建议而非强制, 不影响转化) |
| 不允许 | 纯数字 / 纯字母 / 包含用户手机号或邮箱本地部分 |
| 爆破保护 | `failed_login_count >= 5` → `locked_until = NOW() + 15min` |
| 弱密码黑名单 | 暂不接入; 后续接 12306 公开弱密码库 |

---

## 5. JWT 与 Session 体系

### 5.1 Token 结构

**Access Token** (HS256, 15 分钟)

```json
{
  "sub": "123",
  "role": "user",
  "tier": "free",
  "type": "access",
  "iat": 1756100000,
  "exp": 1756100900,
  "jti": "uuid-v4"
}
```

**Refresh Token** (HS256, 30 天, 但在 DB 有 `refresh_tokens` 行, 支持 revoke)

```json
{
  "sub": "123",
  "type": "refresh",
  "iat": 1756100000,
  "exp": 1758692000,
  "jti": "uuid-v4",
  "sid": "uuid-v4"            // refresh_tokens.id
}
```

### 5.2 颁发流程

```
POST /api/v1/auth/login/password
  → AuthService.authenticate(...)
  → 成功 → create_refresh_token + insert refresh_tokens row
  → create_access_token (15min)
  → Set-Cookie: lr_token=<access>; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=900
  → Set-Cookie: lr_refresh=<refresh>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=2592000
  → response body 也带 token (兼容老前端)
```

### 5.3 Rotation

```
POST /api/v1/auth/token/refresh
  body: { refresh_token }
  → 查 refresh_tokens.token_hash
  → 不存在 / 已 revoked → 401
  → 过期 → 401
  → 命中 reused (revoked_at 不空但 iat 在过去) → 撤销整链 (被攻击嫌疑)
  → 标记旧行 revoked_at = NOW() + replaced_by_id = new_id
  → 插入新行 + 颁发新 access
```

### 5.4 Logout

```
POST /api/v1/auth/logout      → 撤销当前 refresh
POST /api/v1/auth/logout/all  → 撤销该 user 全部 refresh
DELETE /api/v1/users/me/sessions/{id} → 撤销指定 session
```

前端同步清掉 cookie + localStorage 中残留字段。

---

## 6. Cookie 安全

```python
response.set_cookie(
    key="lr_token",
    value=access_token,
    max_age=900,
    path="/",
    httponly=True,
    secure=True,            # 生产 true,  本地 false
    samesite="lax",         # 顶层跳转可用, 跨站 POST 拒绝
)
response.set_cookie(
    key="lr_refresh",
    value=refresh_token,
    max_age=2592000,
    path="/api/v1/auth",    # 仅 auth 接口可读
    httponly=True,
    secure=True,
    samesite="strict",
)
```

- 浏览器 JS 永远拿不到 `lr_token` / `lr_refresh`
- 前端 axios 通过 cookie 自动带 `lr_token`, **不** 也不需要 Authorization header
- 老的 `lr_token` localStorage 在前端 store 里删除, 兼容期保留清空逻辑

---

## 7. 注册流程详细

### 7.1 手机号注册

```
[1] POST /api/v1/auth/sms/send
    body: { phone: "+8613800138000", purpose: "register" }
    ├─ normalize: 13800138000 → +8613800138000
    ├─ rate limit: 60s/phone, 5/10min/ip, 10/day/phone
    ├─ 6 位 code 写入 verification_codes (bcrypt hash)
    ├─ MockSMSProvider.send_code(...) 或 Tencent
    └─ return { ttl_seconds: 300, sent: true }

[2] POST /api/v1/auth/register/phone
    body: { phone, code, password, agree_terms, agree_privacy, utm? }
    ├─ 校验验证码 (5 次错误作废, 5 分钟过期, 单次使用)
    ├─ 查 users.phone 是否已存在 → 409
    ├─ 创建 user (status=active, role=user, phone_verified_at=NOW, password=Argon2id)
    ├─ 颁发 token + Set-Cookie
    ├─ 写 user_login_events(success=true, login_method=sms_register)
    ├─ 写 user_acquisition_sources (utm_*)
    └─ return { user, access_token, refresh_token, onboarding_required: true }
```

### 7.2 邮箱注册

```
[1] POST /api/v1/auth/register/email
    body: { email, password, agree_terms, agree_privacy, utm? }
    ├─ 查 users.email 是否已存在 → 409
    ├─ 创建 user (email_verified_at=NULL, role=user)
    ├─ 颁发 token (限制 onboarding_required=true 但允许使用受限接口)
    ├─ EmailProvider.send(verify_link=<JWT verify email link, 24h>)
    └─ return { user, access_token, refresh_token, onboarding_required: true }

[2] GET /api/v1/auth/email/verify?token=...
    → 校验 token → 置 email_verified_at = NOW
    → 跳回 /account?verified=1
```

### 7.3 同意条款

注册请求必须带 `agree_terms=true` AND `agree_privacy=true`, 否则 422。后端只存 `agreed_terms_at = NOW()`, 真实条款 URL 放前端 `/legal/terms` `/legal/privacy`。

---

## 8. 登录流程详细

### 8.1 密码登录

```
POST /api/v1/auth/login/password
body: { identifier: "<email or phone>", password, captcha_token? }
├─ 识别: 是 email 还是 phone (含 +86)
├─ rate limit: 5/min/ip, 5 失败后 15min 锁
├─ bcrypt/argon2 校验
├─ 失败: failed_login_count++, 超过阈值 → locked_until = NOW + 15min, 写 login_events
├─ 成功: 清零 failed_login_count, 更新 last_login_at, 颁发 token
└─ Set-Cookie + 写 login_events
```

> 失败一律返回 `AuthError("invalid_credentials")`, 绝不说"该手机号不存在"。

### 8.2 短信验证码登录

```
POST /api/v1/auth/login/sms
body: { phone, code }
├─ 调 verify_code 内部函数
├─ 命中 → 查 user, 不存在 → 自动 register (mobile-only account, status=active, role=user)
├─ 颁发 token
└─ 写 login_events
```

> 这种"无密码登录"自动建账户的设计在中国 SaaS 普遍采用, 转化率最高。

### 8.3 OAuth 登录

```
GET /api/v1/auth/oauth/{provider}
  → 生成 state (CSRF 防护) + nonce
  → state 写 redis 5min
  → 302 → provider.authorize_url(...)
  
GET /api/v1/auth/oauth/{provider}/callback?code=...&state=...
  → 校验 state
  → exchange_code → access_token
  → fetch_userinfo → { provider_user_id, email, email_verified, name, avatar }
  → 查 oauth_identities(provider, provider_user_id)
     存在: 登录该 user
     不存在: 走 Account Linking (见 ACCOUNT_LINKING_DESIGN.md)
  → 颁发 token
  → Set-Cookie + 302 → /onboarding 或 /dashboard
```

---

## 9. 路由命名 (保留已有, 增量新增)

保留: `/api/v1/auth/register` `/api/v1/auth/login` `/api/v1/auth/refresh` `/api/v1/auth/me` `/api/v1/auth/logout`

新增:

```
POST   /api/v1/auth/sms/send
POST   /api/v1/auth/sms/verify
POST   /api/v1/auth/register/phone
POST   /api/v1/auth/register/email
GET    /api/v1/auth/email/verify
POST   /api/v1/auth/login/password
POST   /api/v1/auth/login/sms
POST   /api/v1/auth/token/refresh
POST   /api/v1/auth/logout
POST   /api/v1/auth/logout/all
POST   /api/v1/auth/password/forgot
POST   /api/v1/auth/password/reset

GET    /api/v1/auth/oauth/{provider}
GET    /api/v1/auth/oauth/{provider}/callback

GET    /api/v1/users/me
PATCH  /api/v1/users/me
POST   /api/v1/users/me/password
POST   /api/v1/users/me/onboarding
DELETE /api/v1/users/me                  (soft delete)

GET    /api/v1/users/me/identities
DELETE /api/v1/users/me/identities/{provider}    (POST 留作 bind)
POST   /api/v1/users/me/identities/{provider}/bind

GET    /api/v1/users/me/sessions
DELETE /api/v1/users/me/sessions/{session_id}

GET    /api/v1/admin/users               (admin only)
GET    /api/v1/admin/users/{id}
PATCH  /api/v1/admin/users/{id}/status   (active / suspended / disabled)
```

---

## 10. RBAC 扩展

已有 `UserRole`: `submitter / reviewer / supervisor / admin / librarian`, 不动。

新增 SaaS 层抽象:

```python
class SaaSRole(str, Enum):
    USER = "user"             # 普通注册用户 (默认)
    ADMIN = "admin"           # 后台管理员
    SUPER_ADMIN = "super_admin"  # 系统超级管理员 (1-2 人)
```

User 增加 `is_super_admin: bool` 字段 (默认 false, 手工置 true)。`require_role` 已有, 新增:

```python
def require_saas_role(*roles: SaaSRole):
    def dep(current_user: User = Depends(get_current_user)) -> User:
        if current_user.is_super_admin: return current_user
        if current_user.role in roles: return current_user
        raise PermissionError(...)
    return dep
```

前端 `TopBar` 在 `is_super_admin || role in [admin]` 时显示 "管理后台" 入口。

---

## 11. 限流策略

基于 Redis, 通用中间件:

```python
class RateLimiter:
    def __init__(self, key: str, max: int, window_seconds: int):
        self.key, self.max, self.window = key, max, window_seconds
    async def check(self, redis): ...
```

| 场景 | 限制 |
| --- | --- |
| `POST /sms/send` (per phone) | 1 / 60s |
| `POST /sms/send` (per ip) | 5 / 10min |
| `POST /sms/send` (per phone per day) | 10 |
| `POST /register/*` (per ip) | 10 / hour |
| `POST /login/*` (per ip) | 20 / hour |
| `POST /login/*` (per identifier, 5 失败) | 锁定 15min |
| `POST /forgot-password` (per email) | 3 / hour |
| `POST /token/refresh` (per user) | 60 / hour |
| `GET /oauth/*` (per ip) | 30 / hour |

失败统一返回 `429 RateLimitedError`, 文案统一 "请求过于频繁, 请稍后再试"。

---

## 12. 事件埋点 (服务端)

| 事件名 | 触发点 | properties |
| --- | --- | --- |
| `page_view` | (前端) | path, referrer |
| `signup_started` | `POST /register/*` 第一步 | phone_prefix or email_domain |
| `verification_code_sent` | `POST /sms/send` 成功 | purpose, channel |
| `signup_completed` | user 创建成功 | method (phone/email/oauth) |
| `login_started` | `POST /login/*` 入口 | method |
| `login_success` | token 颁发 | method, is_new_user |
| `login_failed` | AuthError 抛出 | method, reason |
| `oauth_started` | `GET /oauth/{provider}` 302 前 | provider |
| `oauth_completed` | callback 成功 | provider, is_new_user |
| `onboarding_started` | 用户首次访问 /onboarding | - |
| `onboarding_completed` | `POST /users/me/onboarding` | role, purposes |
| `logout` | `POST /logout` | scope (self/all) |
| `account_linked` | 新 OAuth identity 关联到 user | provider |
| `account_unlinked` | 解绑 | provider |
| `password_reset_requested` | `POST /password/forgot` | channel |
| `password_reset_completed` | `POST /password/reset` | method |

实现: 同步写 `user_events` + `structlog.info` 双轨; 后续可挂异步 worker 转发到 PostHog / Mixpanel / GA4。

---

## 13. UTM 归因

`/login` 与 `/register` 页面渲染时从 `localStorage` 或 cookie 读 `utm_*` `referrer` `landing_page`, 在注册请求 body 一起带上。后端写入 `user_acquisition_sources`。

落地:

```js
// 前端 utmCapture.ts (挂在 layout)
const params = new URLSearchParams(location.search);
for (const k of ["utm_source","utm_medium","utm_campaign","utm_content","utm_term"]) {
    const v = params.get(k);
    if (v) localStorage.setItem(`lr_utm_${k}`, v);
}
if (document.referrer) localStorage.setItem("lr_referrer", document.referrer);
localStorage.setItem("lr_landing", location.pathname);
```

注册时 `api.register(..., utm: getStoredUtm())` 一起带过来。

---

## 14. Onboarding

新用户首次登录 (任意方式) → 服务端在 `TokenResponse` 多返 `onboarding_required: true`, 前端 `AuthGuard` 看到后 `router.replace("/onboarding?next=" + encodeURIComponent(originalPath))`。

`/onboarding` 流程:

```
[1] 选择身份 (单选)
    ☐ 企业法务
    ☐ 律师
    ☐ 政府工作人员
    ☐ 企业管理者
    ☐ 个人用户
    ☐ 其他

[2] 选择用途 (多选, 至少 1)
    ☐ 合同审查
    ☐ 法规检索
    ☐ 文件合法性审查
    ☐ 法律问答
    ☐ 政策分析
    ☐ 企业合规

[3] 提交
    POST /api/v1/users/me/onboarding
    body: { role, purposes: [...] }
    → 写 user.onboarding_role + user.onboarding_purposes
    → 写 user_events("onboarding_completed")
    → 跳 /dashboard
```

允许用户跳过 (写 `onboarding_completed_at = NULL` 但不强制, 再次进入 dashboard 时 header 显示提示 banner)。

---

## 15. 用户中心 `/account`

后端 `GET /api/v1/users/me` 扩展返回:

```json
{
  "id": 123,
  "display_name": "张三",
  "email": "zhang@example.com",
  "email_verified": true,
  "phone": "+8613800138000",
  "phone_verified": true,
  "avatar_url": null,
  "role": "user",
  "is_super_admin": false,
  "status": "active",
  "created_at": "2026-08-01T10:00:00Z",
  "last_login_at": "2026-08-25T12:34:56Z",
  "onboarding_completed": true,
  "identities": [
    { "provider": "github", "linked": true,  "linked_at": "..." },
    { "provider": "google", "linked": false },
    { "provider": "wechat", "linked": false }
  ],
  "active_login_methods": ["phone_password", "sms_code", "github"]
}
```

前端 `/account` 三个 Tab:

1. **基本资料** — 头像 / 昵称 / 邮箱 / 手机号 / 注册时间
2. **账户安全** — 修改密码 / 绑定手机 / 更换手机 / 绑定邮箱 / 第三方账号 / 登录设备
3. **注销账户** — 二次确认, 软删除 `deactivated_at = NOW()`

---

## 16. 后台 Admin

`/admin` 已有 (来自 `(admin)/admin/page.tsx`), 改造为:

- 列表: GET `/api/v1/admin/users?page=1&size=20&q=...&status=...`
- 搜索: phone/email/username/display_name 模糊
- 详情: 展示但不展示 `password_hash` / 完整 OAuth token
- 操作: 禁用 / 恢复 / 强制下线 (撤销 refresh)
- 审计: 所有 admin 操作走 `AuditRecord`

---

## 17. 部署环境变量 (汇总)

完整 `.env.example` 见仓库, 核心新增:

```env
# Auth
APP_ENV=production
JWT_SECRET=<openssl rand -hex 64>
JWT_ACCESS_TTL_MIN=15
JWT_REFRESH_TTL_DAYS=30
PASSWORD_HASHER=argon2id            # argon2id | bcrypt
OAUTH_TOKEN_ENC_KEY=<Fernet key>    # 用于加密 oauth_identities 的 access/refresh

# SMS
SMS_PROVIDER=mock                   # mock | tencent | aliyun
TENCENT_SMS_SECRET_ID=
TENCENT_SMS_SECRET_KEY=
TENCENT_SMS_APP_ID=
TENCENT_SMS_SIGN_NAME=法律智能
TENCENT_SMS_TEMPLATE_ID=              # 单模板 6 位数字

# Email
EMAIL_PROVIDER=mock
SMTP_HOST=smtp.exmail.qq.com
SMTP_PORT=465
SMTP_USERNAME=
SMTP_PASSWORD=

# OAuth
GITHUB_LOGIN_ENABLED=true
GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GITHUB_REDIRECT_URI=https://legalai86.com.cn/api/v1/auth/oauth/github/callback

GOOGLE_LOGIN_ENABLED=false
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=https://legalai86.com.cn/api/v1/auth/oauth/google/callback

WECHAT_LOGIN_ENABLED=false
WECHAT_APP_ID=
WECHAT_APP_SECRET=
WECHAT_REDIRECT_URI=https://legalai86.com.cn/api/v1/auth/oauth/wechat/callback

# Captcha
CAPTCHA_ENABLED=false
TURNSTILE_SITE_KEY=
TURNSTILE_SECRET_KEY=

# Rate Limit
RATE_LIMIT_ENABLED=true
```

---

## 18. 实施顺序 (M0 → M5)

| Milestone | 范围 | 风险 |
| --- | --- | --- |
| M0 | 0003 migration + 13 列扩展 + 6 新表 + bcrypt 兼容 | 数据库 |
| M1 | Argon2id + SMS Mock + 手机号注册 + 验证码风控 | 短信 |
| M2 | 邮箱注册 + SMTP Mock + verify email | 邮件 |
| M3 | 密码 / SMS code 登录 + Cookie 切换 + refresh rotation | 登录 |
| M4 | GitHub OAuth (默认开) + Google / WeChat 框架 (默认关) | OAuth |
| M5 | 用户中心 + Onboarding + Admin + 限流 + 埋点 + 文档 | 全栈 |

每个 Milestone 结束做一次 `docker compose build` + `alembic upgrade head` + 线上 smoke test。

---

## 19. 兼容性承诺

1. **旧 demo 用户继续可用** — `email` + `bcrypt` 路径保持不变, 仅新增能力。
2. **旧 token 兼容** — 旧 access/refresh token 1 周内继续被接受, 1 周后强切。
3. **旧 API 保留** — `/api/v1/auth/login` 仍能用, 但内部走新服务。
4. **旧前端组件** — `LoginForm` / `RegisterForm` 重写但保留导出, 不影响外部 import。

---

## 20. 与已有架构的关系

| 已有 | 关系 |
| --- | --- |
| `User` 模型 | 扩展, 不替换 |
| `Organization` (PERSONAL) | 沿用, 注册时自动建 personal org + free plan |
| `UserPlan` | 沿用 |
| `Order` / `Payment` | 沿用 (本轮不接支付, 仅占位) |
| `AuditRecord` | 沿用, 扩展 action 枚举 |
| `AuthService` | 拆为 `AuthService` + `IdentityService` + `OAuthService` + `TokenService` |
| `get_current_user` (deps) | 行为不变, 内部改用 `TokenService` |
| `LoginForm` / `RegisterForm` | 重写, 但保持 `props` 一致 |

---

## 21. 风险与回滚

| 风险 | 缓解 | 回滚 |
| --- | --- | --- |
| 0003 migration 在生产失败 | 提前在 staging 跑; 锁定 transaction | `alembic downgrade -1` |
| Cookie 切 HttpOnly 引发老浏览器异常 | 双轨期保留 localStorage 路径 | 退回旧 Set-Cookie |
| SMS 触发腾讯云审核 | 默认 mock, 真要切时再申请 | env 改回 `mock` |
| GitHub OAuth 回调 404 | 上线前用 `ngrok` 验证 | `GITHUB_LOGIN_ENABLED=false` |
| Refresh token reuse 误伤 | 误判条件严 (revoked_at != null 且 iat 早于 NOW-1h) 才整链撤销 | 关闭 rotation, 改为单 refresh |

---

## 22. 验收标准 (与 45 节 spec 对齐)

- ✅ 新手机用户无需开发者介入完成: 首页 → 注册 → 验证码 → 登录 → onboarding → dashboard → 退出 → 重新登录
- ✅ 旧 demo 用户 (`demo@shajindi.com`) 继续可用
- ✅ GitHub 登录可用 (默认开启)
- ✅ Google / 微信默认关闭, 后端能力就绪
- ✅ Cookie HttpOnly + Secure + SameSite=Lax
- ✅ Refresh token rotation + reuse detection
- ✅ 防枚举 (统一 invalid_credentials)
- ✅ Rate limit 在关键接口生效
- ✅ 6 份设计 / 测试 / 部署文档就绪
- ✅ 自动化测试 + E2E + 线上 smoke 全过

---

## 23. 后续阶段 (本轮不实现)

明确**不**纳入本轮:

- 复杂组织管理 (多租户 / 角色矩阵)
- 复杂 CRM / 营销自动化
- 支付 / 订阅商业化
- 企业 SSO / SAML / LDAP
- 复杂 ABAC

下轮重点: 商业化 / 多租户 / 团队协作 / 微信小程序 / 公众号登录。

---

> 详细设计已就绪, 下一步进入 **Todo #3: Alembic 0003 migration 落地**。
