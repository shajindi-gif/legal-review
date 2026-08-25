# LegalAI 账号合并设计 (ACCOUNT_LINKING_DESIGN)

> 版本: v1.0  
> 日期: 2026-08-25  
> 目的: 当用户使用不同登录方式(手机 / 邮箱 / GitHub / Google / 微信)时, 安全地把他们合并到同一个 `User` 记录, 避免产生无法识别的重复账号。  
> 配套文档: `AUTH_SYSTEM_AUDIT.md` · `AUTH_ARCHITECTURE.md` · `AUTH_SECURITY_REVIEW.md`

---

## 0. 场景与目标

### 0.1 真实场景

1. 用户先在 LegalAI 用 `abc@gmail.com` + 密码注册。
2. 后来用 Google 登录, Google 返回 `abc@gmail.com` (verified)。
3. 必须合并到同一个 `User`, 而不是再开一个 `User`。
4. 同时, 攻击者拿到 `abc@gmail.com` 的未验证凭据, 绝不能借此劫持账户。

### 0.2 设计目标

- ✅ 同一个人用不同方式登录 → 同一 `user_id`
- ✅ 任何凭据都不能在未验证时自动绑定
- ✅ 用户对"哪个 provider 绑到了我的账号"有完全透明度
- ✅ 随时可解绑 (除非是该用户最后一个登录方式)
- ✅ 审计记录每次合并 / 解绑, 可追溯

---

## 1. 信任等级 (Trust Levels)

每个 identifier (手机/邮箱/provider account) 都有一个**信任等级**, 决定它能否触发自动合并。

| Level | 来源 | 含义 |
| --- | --- | --- |
| **T0 受信** | 已登录用户主动在受信任会话中提供 (例如已登录状态下添加手机) | 一定可信, 立即合并 |
| **T1 验证过** | 短信验证码 / 邮箱验证链接 / OAuth `email_verified=true` | 高度可信, 大多数场景可合并 |
| **T2 未验证** | 用户在注册时"声称"的邮箱, 或 OAuth 返回 `email_verified=false` | 不可信, **绝不**自动合并 |
| **T3 弱** | 第三方解析得到的邮箱 (如 GitHub profile 的 public email) | 不可信, 仅作为展示, 不作为合并依据 |

**核心原则**:

> **只有 T0 + T1 才能触发自动合并; T2/T3 一律要求二次确认或拒绝。**

---

## 2. 合并决策矩阵

下表是 OAuth callback / 短信注册时, 当目标 identifier 在系统已有 `User` 的情况下, 该怎么办。

| 已存在账号凭据 | 当前 OAuth 用户返回 | 自动行为 |
| --- | --- | --- |
| phone (verified) | phone (T0, 验证码校验通过) | 合并到已有 user, 记录 `account_linked` 事件 |
| email (verified) | email (T1, verified) | 合并到已有 user, 记录 `account_linked` 事件 |
| email (unverified) | email (T1, verified) | 合并, 但发送"安全通知邮件"到原 email 提醒 |
| phone (verified) | email (T1, verified) **不同邮箱** | 创建新 user (不合并) |
| email (verified) | phone (T0) **不同手机** | 创建新 user (不合并) |
| email (verified) | email (T2) | **不合并**, 进入 `pending_link`, 强制要求用户提供"原账号密码"或"原手机验证码"二次确认 |
| email (verified) | provider 已存在 | 直接登录该 user, 无需合并 |
| provider 已绑定其他 user | provider 相同, user 不同 | **拒绝** (一个 provider 账号只能绑一个 user) |

---

## 3. 合并流程 (详细)

### 3.1 OAuth 登录命中已有 user

```
callback 拿到 { provider_user_id, email, email_verified }
↓
1. 查 oauth_identities(provider, provider_user_id) → 命中
   → 直接登录, 跳 /onboarding 或 /dashboard

2. 未命中:
   查 users WHERE email = ? AND email_verified_at IS NOT NULL (T1)
   → 命中:
     ├─ 当前 OAuth 是 verified → 自动合并
     │   ├─ INSERT oauth_identities(user_id=existing, provider, provider_user_id, ...)
     │   ├─ 发邮件到 existing.email: "新设备/新方式登录" 安全通知
     │   ├─ 写 user_events(account_linked, provider=...)
     │   └─ 颁发 token, 跳 /dashboard
     │
     └─ 当前 OAuth 是 unverified → 进入 pending_link
         └─ 详见 §4

3. 未命中 (无 T1 email):
   → 创建新 user (status=active, role=user, email_verified_at=NULL 或 NOW 取决于 verified)
   → INSERT oauth_identities
   → onboarding_required=true
```

### 3.2 短信登录命中已有 user

```
input: phone, code
↓
verify_code(code) → OK
↓
查 users WHERE phone = '+86...' (T0, 因为验证码刚验证过)
├─ 命中 → 颁发 token
└─ 未命中 → 走"手机号注册"路径, 但跳过密码设置 (用 sms-only 账户)
```

### 3.3 OAuth 登录携带 phone, 但 phone 已绑其他 user

```
callback 拿到 { provider_user_id, phone? }
注: 大部分 OAuth provider 不返回 phone, 这里主要指 "用户主动补充" 场景
↓
如果 phone 已绑 user_A, 当前 OAuth 即将绑 user_B:
→ 拒绝, 返回 409 PHONE_CONFLICT
→ 提示: "该手机号已绑其他账号, 请先解绑"
```

---

## 4. Pending Link (待合并队列)

当自动合并不可行 (例如 OAuth email 是 T2, 但有相同 T1 email 存在), 不能贸然合并, 也不能简单拒绝。

**解决: Pending Link 队列**

```sql
CREATE TABLE account_link_pending (
    id                BIGSERIAL PRIMARY KEY,
    existing_user_id  BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    new_provider      VARCHAR(16) NOT NULL,
    new_provider_user_id VARCHAR(128) NOT NULL,
    new_email         VARCHAR(255) NULL,
    new_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    state             VARCHAR(32) NOT NULL,        -- waiting_confirm / confirmed / expired / rejected
    confirm_token     UUID NOT NULL DEFAULT gen_random_uuid(),
    expires_at        TIMESTAMPTZ NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

**用户路径**:

```
OAuth callback → 检测冲突 → 不自动合并
  → 创建 account_link_pending(..., state='waiting_confirm', expires_at = NOW() + 1h)
  → 给 existing_user 邮箱发邮件: "有人尝试用 [provider] 登录您的账号, 若是您本人, 请点击下方确认"
  → 给当前 session 一个临时 pending_token, 但不颁发完整 token
  → 302 → /account/pending-link?token=<confirm_token>
  
页面选项:
  A. 输入原账号密码 → 校验通过 → 合并, 跳 /dashboard
  B. 用原手机收验证码 → 校验通过 → 合并, 跳 /dashboard  
  C. "不是我" → 拒绝合并, 把 attempt 写 security log, 跳 /login
  
合并成功后:
  → 写 user_events(account_linked, provider=..., via='password_confirm' | 'sms_confirm')
  → 通知原 email: "[Security] 您的 LegalAI 账号已通过 [provider] 登录"
```

---

## 5. 用户主动 Bind / Unbind

### 5.1 Bind (用户已登录, 主动添加新方式)

用户在 `/account/security` 点击"绑定 GitHub"等按钮:

```
[1] 前端: 点击 "绑定 GitHub"
    → GET /api/v1/auth/oauth/github?flow=bind&csrf=...
    → 后端检查 session 已登录, 写 state cookie (with user_id)
    → 302 → GitHub

[2] GitHub callback
    → 验证 state
    → 拿 access_token + userinfo
    → 查 oauth_identities(provider, provider_user_id)
       命中 (绑到其他 user) → 409 IDENTITY_CONFLICT
       未命中 → INSERT
    → 写 user_events(account_linked, via=manual_bind)
    → 跳 /account/security?linked=github
```

**Bind 路径绕开所有合并决策**, 因为是 T0 (已登录会话)。

### 5.2 Unbind

```
DELETE /api/v1/users/me/identities/{provider}
↓
查 user 当前的 active_login_methods 数量
├─ = 1 且正好是这个 provider → 403 CANNOT_UNBIND_LAST
└─ > 1 → DELETE oauth_identities row + revoke 相关 refresh_tokens
        → 写 user_events(account_unlinked)
        → 200 OK
```

`active_login_methods` 计算:

```python
def get_active_methods(user: User) -> list[str]:
    methods = []
    if user.password_hash: methods.append("password")
    if user.phone_verified_at: methods.append("sms_code")
    if user.email_verified_at: methods.append("email_link")
    for ident in user.oauth_identities:
        if ident.provider in ("github","google","wechat"):
            methods.append(f"oauth:{ident.provider}")
    return methods
```

---

## 6. 解绑保护 (Safety Rules)

| 情况 | 行为 |
| --- | --- |
| 用户有 1 个登录方式 | 拒绝解绑, 引导用户先添加另一种方式 |
| 用户尝试解绑 password 但有其他方式 | 允许, 同时 reset password 后强制用新方式登录 |
| 用户解绑 phone 但有其他方式 | 允许, SMS 登录不再可用 |
| 用户解绑 email (verified) 但已用于 password reset | 允许, 但提示"将无法通过邮件找回密码" |
| 用户尝试解绑 super_admin 的最后一个方法 | 拒绝 + 写 security alert (这种行为可疑) |

---

## 7. 审计与通知

### 7.1 每次合并/解绑的审计

`AuditRecord`:

```python
{
  "action": "account.linked" | "account.unlinked" | "account.merge_rejected" | "account.pending",
  "actor_id": <acting_user_id>,            # 自动合并场景为 existing_user_id
  "target_type": "user",
  "target_id": <existing_user_id>,
  "after_value": {
    "provider": "github",
    "via": "auto_merge" | "manual_bind" | "password_confirm" | "sms_confirm",
    "ip": "1.2.3.4",
    "user_agent": "..."
  }
}
```

### 7.2 用户通知

任何合并发生, 立刻发邮件到已验证邮箱:

```
Subject: [LegalAI Security] 您的账号新增了一种登录方式
Body:
  我们检测到您的账号新增了一种登录方式:
  
  方式: GitHub
  时间: 2026-08-25 12:34 UTC+8
  IP:   1.2.3.4
  
  如果这不是您本人的操作, 请立即:
  1. 访问 https://legalai86.com.cn/account/security
  2. 解绑该方式
  3. 修改密码
```

---

## 8. 边界场景与决策

| 场景 | 决策 |
| --- | --- |
| OAuth 返回 email 为 NULL | 当作"无法合并", 创建新 user, 提示补填 |
| OAuth email 与已存在 user 相同但 verified 状态不同 | 优先信任 existing 的 verified 状态; 新 OAuth 不带 verified 时进入 pending |
| 用户用 GitHub A 登录, 后来用 GitHub B 登录且 email 相同 | 走普通流程, GitHub B 创建新 user, 因为 provider_user_id 不同 |
| 一个 user 有 3 个 OAuth identity, 删 user (软删除) | oauth_identities 级联, 不影响 |
| 用户修改 OAuth 邮箱 | 不自动更新 user.email, 必须走"绑定新邮箱"流程单独验证 |
| 手机号格式变化 (携号转网) | 不支持, 引导用户用原 provider 登录后修改手机 |

---

## 9. 关键代码骨架

```python
# app/services/identity_service.py

class IdentityService:
    async def link_or_create(
        self,
        *,
        provider: str,
        provider_user_id: str,
        provider_email: str | None,
        provider_email_verified: bool,
        phone: str | None = None,           # 短信登录场景
        phone_verified: bool = False,
        request: Request,
    ) -> tuple[User, bool]:                # (user, is_new)
        # 1. 已有 oauth identity?
        existing = await self._find_oauth(provider, provider_user_id)
        if existing:
            return existing.user, False

        # 2. 已有 phone?
        if phone and phone_verified:
            user = await self._find_user_by_phone(phone)
            if user:
                await self._create_oauth_identity(user, provider, provider_user_id, provider_email, provider_email_verified)
                await self._notify_security(user, "linked", provider, request)
                await self._event(user, "account_linked", {"provider": provider, "via": "auto_phone_match"})
                return user, False

        # 3. 已有 email (verified)?
        if provider_email and provider_email_verified:
            user = await self._find_verified_user_by_email(provider_email)
            if user:
                await self._create_oauth_identity(user, provider, provider_user_id, provider_email, True)
                await self._notify_security(user, "linked", provider, request)
                await self._event(user, "account_linked", {"provider": provider, "via": "auto_email_match"})
                return user, False

        # 4. email 存在但 unverified → pending
        if provider_email:
            user = await self._find_any_user_by_email(provider_email)
            if user:
                pending = await self._create_pending_link(user, provider, provider_user_id, provider_email, provider_email_verified)
                await self._send_pending_email(user, pending)
                raise PendingLinkRequired(pending.confirm_token)

        # 5. 创建新 user
        new_user = await self._create_user_from_identity(
            provider=provider,
            provider_email=provider_email,
            provider_email_verified=provider_email_verified,
            phone=phone,
        )
        await self._create_oauth_identity(new_user, provider, provider_user_id, provider_email, provider_email_verified)
        await self._event(new_user, "signup_completed", {"method": f"oauth:{provider}"})
        return new_user, True
```

```python
# app/services/token_service.py

class TokenService:
    async def issue(self, user: User, request: Request) -> Tokens:
        access = create_access_token(...)
        refresh, jti = create_refresh_token(sid=...)
        await self._store_refresh(user, jti, request)
        return Tokens(access=access, refresh=refresh, ...)

    async def refresh(self, refresh_token: str) -> Tokens:
        payload = decode(refresh_token)
        row = await self._load_refresh(payload["sid"])
        if not row: raise TokenRevokedError()
        if row.revoked_at: 
            # reuse detection: 撤销整链
            await self._revoke_chain(row.user_id)
            raise TokenRevokedError("reuse_detected")
        if row.expires_at < now(): raise TokenExpiredError()
        # rotate
        new_refresh, new_jti = create_refresh_token(...)
        await self._rotate(row, new_jti)
        new_access = create_access_token(user_id=row.user_id)
        return Tokens(...)
```

---

## 10. 测试用例 (必过)

### 10.1 合并

- ✅ 已存在 email 用户, 用 Google (verified email 相同) 登录 → 合并, 同一 user
- ✅ 已存在 email 用户, 用 Google (unverified email 相同) 登录 → pending
- ✅ pending 链接, 用户在 1h 内输入原密码 → 合并
- ✅ pending 链接, 超过 1h → 拒绝
- ✅ pending 链接, 用户点"不是我" → 拒绝 + security log

### 10.2 Bind

- ✅ 已登录用户 bind GitHub → 成功
- ✅ 未登录用户尝试 bind → 401
- ✅ Bind 已被其他 user 绑的 GitHub → 409
- ✅ Bind 成功后调用 /me/identities → 看到新 provider

### 10.3 Unbind

- ✅ 用户有 password + GitHub, 解绑 GitHub → 成功
- ✅ 用户只有 password, 解绑 password → 403
- ✅ 解绑后, 用 GitHub 登录失败 (provider 未绑)
- ✅ 解绑后, /me/identities 不含该 provider

### 10.4 通知

- ✅ 合并后, 原 email 收到安全通知 (mock 模式验证日志)
- ✅ 合并后, user_events 含 account_linked
- ✅ 合并后, AuditRecord 含 action=account.linked

### 10.5 Reuse Detection

- ✅ Refresh token A 被使用 → 撤销 A
- ✅ 再用 A → 撤销该 user 全部 refresh
- ✅ 再用 B (chain) → 同样撤销全部

---

## 11. 配置项汇总

```env
# Pending Link
PENDING_LINK_TTL_HOURS=1

# Auto Merge
AUTO_MERGE_ON_VERIFIED_EMAIL=true
AUTO_MERGE_ON_VERIFIED_PHONE=true

# Notification
SECURITY_NOTIFY_ON_MERGE=true
```

---

## 12. 不做的事

- 不做"凭手机号模糊匹配邮箱"等弱匹配
- 不做"凭 IP / device fingerprint 合并"
- 不做"silent merge" (合并前一定有通知)
- 不支持跨手机号合并 (中国移动携号转网不在本轮范围)
- 不做 OAuth provider 的 email 自动同步 (用户改 GitHub email 不会自动改 LegalAI email)

---

## 13. 与其他文档的关系

- 详细 API 见 `AUTH_ARCHITECTURE.md` §9
- 加密 token 存储见 `AUTH_SECURITY_REVIEW.md` §5
- 端到端测试脚本见 `AUTH_E2E_TEST_REPORT.md`
