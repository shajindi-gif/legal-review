# LegalAI Auth System Audit

> **审计时间**: 2026-08-25
> **审计范围**: `https://legalai86.com.cn` 当前生产系统
> **审计目的**: 在不破坏现有 LegalAI 核心功能的前提下,将系统从"Demo 账号登录"升级为生产级 SaaS 用户系统
> **核心原则**: 增量式升级 (additive),Alembic-only schema 变更,保留现有用户兼容,所有 secret 走环境变量

---

## 0. Executive Summary

**当前状态**: 系统已部署运行,核心 LegalAI Agent 审查链路完整可工作,Demo 用户 `demo@shajindi.com / Demo@2024` 可正常登录,4/4 关键端点(Home / Login / Login API / Audit Count)返回 200。

**认证短板**: 当前 Auth 是"demo 风格最小可用"实现,缺少:
- 手机号注册 / 手机验证码登录
- 邮箱验证 / 邮箱验证链接
- OAuth (微信 / GitHub / Google)
- 统一登录页(目前只支持邮箱+密码)
- 忘记密码流程
- 用户中心(无 /account 页面)
- Onboarding
- Rate limit / 失败保护 / 防枚举
- Refresh token rotation / 撤销
- Cookie HttpOnly/Secure 标记
- UTM 归因 / Event 埋点
- Admin 用户管理
- Argon2id

**本审计目标**: 明确上述缺口的当前实现位置、影响范围、是否可复用、是否需修改、是否破坏性、是否需新增。

---

## 1. 前端技术栈 (Frontend Stack)

| 项目 | 版本 | 备注 |
|---|---|---|
| 框架 | Next.js 16.3.2 | App Router + Route Group |
| UI | React 19.2.8 | Server Component + Client Component 混合 |
| 状态管理 | Zustand 5.0.15 | 唯一 store: `useAuthStore` |
| HTTP | axios 1.19.x | baseURL 来自 `NEXT_PUBLIC_API_URL` |
| 样式 | Tailwind CSS 4 + Radix UI Primitives | |
| 工具 | lucide-react / clsx / tailwind-merge | |
| 包管理 | pnpm 11.6.0 | monorepo: pnpm-workspace.yaml 存在 |
| 路由守卫 | `proxy.ts` (Next.js 16 middleware 重命名) + `AuthGuard.tsx` (客户端) | 双重保护 |
| TypeScript | 5.x | 严格模式 |

**路由结构**:
- 公开路由: `/`, `/login`, `/register`
- 受保护路由: `/dashboard`, `/upload`, `/review/:id`, `/report/:id`, `/admin`
- 路由组: `(auth)` `(app)` `(admin)`(Next.js convention,不参与 URL)

**关键前端文件**:
- `frontend/src/lib/auth.ts` — Zustand 鉴权 store (token + user + cookie sync)
- `frontend/src/lib/api.ts` — axios 客户端 + 鉴权拦截器 + login/register/fetchMe/refresh/logout/fetchQuota
- `frontend/src/proxy.ts` — Next.js 16 proxy.ts (路由层守卫, 读 `lr_token` cookie)
- `frontend/src/components/auth/AuthGuard.tsx` — 客户端 AuthGuard
- `frontend/src/components/auth/LoginForm.tsx` — 仅邮箱+密码登录
- `frontend/src/components/auth/RegisterForm.tsx` — 仅邮箱+密码注册
- `frontend/src/components/dashboard/TopBar.tsx` — 顶栏(可改造支持登录态切换)
- `frontend/src/components/dashboard/SideNav.tsx` — 侧栏
- `frontend/src/app/page.tsx` — 首页(已有"立即注册"+"登录控制台" CTA)
- `frontend/src/app/(auth)/login/page.tsx` — 登录页
- `frontend/src/app/(auth)/register/page.tsx` — 注册页

**可复用 (不破坏)**:
- 整体 UI 体系 (Radix + Tailwind) — 直接扩展新页面
- Zustand store 架构 — 扩展 `useAuthStore` 添加 phone/email/oauth 方法
- AuthGuard / proxy.ts — 沿用,扩展 protected 列表即可
- api.ts 的 axios 拦截器 — 沿用,扩展端点
- TopBar / SideNav — 改造添加"账户中心"入口与已登录/未登录分支

**需要新增**:
- 登录页改造:邮箱 Tab + 手机号 Tab + 第三方按钮 + 跳转注册
- 注册页改造:邮箱/手机号选项 + 验证码输入 + 协议勾选
- 新页面:`/forgot-password` `/reset-password?token=` `/account` `/account/security` `/onboarding` `/account/devices` `/account/binding`
- 移动端响应式:Next.js 已支持,需在组件层用 `md:` `sm:` Tailwind 断点

**安全风险 (前端)**:
1. `localStorage` 存 token:当前 `lib/auth.ts` 把 access_token 写入 `localStorage.lr_token`。这是已知 XSS 风险;生产级应迁移到 HttpOnly Secure SameSite=Lax Cookie。后端已允许 `allow_credentials=True` 的 CORS,可平滑切换。
2. 401 响应拦截器强制跳 `/login` — 没有带 `?next=`,丢上下文;需改造带 redirect。
3. proxy.ts 重定向参数是 `redirect`,LoginForm 暂未读取 — 需对齐。

---

## 2. 后端技术栈 (Backend Stack)

| 项目 | 版本 | 备注 |
|---|---|---|
| Web | FastAPI 0.110+ | async 全异步 |
| 服务 | uvicorn 0.27+ | 2 workers (Docker CMD) |
| ORM | SQLAlchemy 2.0.25+ async | 声明式 + Mapped[...] |
| 驱动 | asyncpg 0.29+ | |
| 校验 | Pydantic 2.6+ + pydantic-settings 2.1+ | |
| 迁移 | Alembic 1.13+ | 3 迁移已应用 |
| 向量 | pgvector 0.3+ | 1024 维 |
| 缓存 | redis[hiredis] 5+ | 已部署,目前未用于限流 |
| HTTP | httpx 0.27+ | LLM Gateway |
| Auth | pyjwt 2.8+ + bcrypt 4.1+ + email-validator 2+ | |
| 模板 | jinja2 / pyyaml | Prompt 渲染 |
| 日志 | structlog 24+ | 已接入 |
| 文件 | python-magic / Pillow / paddleocr / paddlepaddle / python-docx / pypdf | |
| PDF | weasyprint 60+ | 报告 PDF |
| Python | 3.11 (slim base) | |

**关键后端文件**:
- `backend/app/main.py` — FastAPI 工厂 + CORS + trace_id 中间件 + 全局 AppError handler
- `backend/app/api/v1/__init__.py` — 路由聚合
- `backend/app/api/v1/auth.py` — 当前 5 个鉴权端点 (register/login/refresh/me/quota/logout)
- `backend/app/api/deps.py` — `get_db` / `get_current_user` / `require_role` 工厂 / `get_current_user_optional`
- `backend/app/services/auth_service.py` — bcrypt 哈希 + JWT 签发 + register/login/refresh
- `backend/app/models/user.py` — User / Organization / UserPlan / Order / Payment
- `backend/app/schemas/auth.py` — RegisterRequest / LoginRequest / TokenResponse / UserOut / QuotaStatus
- `backend/app/core/config.py` — pydantic-settings,`cors_origin_list` 已修复 (逗号分隔)
- `backend/app/core/constants.py` — UserRole(UserRole.SUBMITTER/REVIEWER/SUPERVISOR/ADMIN/LIBRARIAN)/UserStatus(ACTIVE/DISABLED/LOCKED) — **缺 SUSPENDED/DELETED,需扩展**
- `backend/app/core/errors.py` — AppError / AuthError(401) / ConflictError(409) / NotFoundError(404) / QuotaExceededError(429) / ValidationError(422)
- `backend/alembic/versions/0001_initial_schema.py` — 12 表 T01~T12 (含 users, organizations, user_plans 等)
- `backend/alembic/versions/0002_saas_user_subscription.py` — users.company + user_plans + orders + payments
- `backend/alembic/versions/c369d702b000_expand_documents_mime_type_to_128.py` — 文档 mime_type 扩列

**后端当前 5 个鉴权端点**:
- `POST /api/v1/auth/register` (201,body: email/password/company/real_name)
- `POST /api/v1/auth/login` (body: email/password)
- `POST /api/v1/auth/refresh` (body: refresh_token)
- `GET  /api/v1/auth/me` (Bearer)
- `GET  /api/v1/auth/quota` (Bearer)
- `POST /api/v1/auth/logout` (Bearer,目前仅审计,无 token 黑名单)

---

## 3. User Model 当前结构

**表**: `users` (T01)
```sql
id              UUID PK uuid_generate_v4()
username        VARCHAR(64) UNIQUE NOT NULL
real_name       VARCHAR(64) NOT NULL
email           VARCHAR(128) UNIQUE NULL
phone           VARCHAR(20)  NULL          -- 当前未标准化,+86 格式未统一
password_hash   VARCHAR(255) NOT NULL      -- bcrypt cost=12
role            VARCHAR(32) NOT NULL       -- submitter/reviewer/supervisor/admin/librarian
company         VARCHAR(128) NULL          -- Sprint 6 新增
organization_id UUID FK → organizations.id NULL
status          VARCHAR(16) NOT NULL DEFAULT 'active'  -- active/disabled/locked
last_login_at   TIMESTAMPTZ NULL
created_at      TIMESTAMPTZ NOT NULL
updated_at      TIMESTAMPTZ NOT NULL
deleted_at      TIMESTAMPTZ NULL           -- 软删除
```

**已发现缺口** (新增字段,需要 Alembic 迁移):
- `phone_verified_at` TIMESTAMPTZ NULL — 短信验证状态
- `email_verified_at` TIMESTAMPTZ NULL — 邮件验证状态
- `display_name` VARCHAR(64) NULL — 用户展示名(可与 real_name 区分)
- `avatar_url` VARCHAR(512) NULL — 头像
- `locale` VARCHAR(8) DEFAULT 'zh-CN' — 多语言
- `timezone` VARCHAR(32) DEFAULT 'Asia/Shanghai' — 时区
- `password_changed_at` TIMESTAMPTZ NULL — 密码最近修改时间
- `deactivated_at` TIMESTAMPTZ NULL — 软删除(注销)时间
- `onboarding_completed_at` TIMESTAMPTZ NULL — onboarding 完成时间
- `onboarding_role` VARCHAR(32) NULL — 身份 (企业法务/律师/政府/企业管理者/个人/其他)
- `onboarding_purpose` VARCHAR(32) NULL — 用途 (合同审查/法规检索/文件合法性审查/法律问答/政策分析/企业合规)
- `failed_login_count` INT DEFAULT 0 — 登录失败计数
- `locked_until` TIMESTAMPTZ NULL — 临时锁定到期时间

**索引补充**:
- `users.phone` 当前**无 UNIQUE 约束**,无索引 — 必须新增
- `users.email` 已有 UNIQUE — 复用
- 建议加 `idx_users_status`、`idx_users_deleted_at`(部分索引)

**绝不能修改**:
- `users.id` (UUID PK) — 业务方已写入引用
- `users.password_hash` 类型与现有哈希值 — bcrypt 字符串格式
- `users.created_at` / `users.updated_at` / `users.deleted_at` — 既有逻辑依赖
- 已有 `users.username` 唯一约束(在用,不可删)
- 已有 demo 用户 `demo@shajindi.com / Demo@2024` — 必须保留可登录

---

## 4. 当前 Auth 实现 (auth_service.py)

```python
# 密码
def hash_password(plain: str) -> str:    # bcrypt cost=12
def verify_password(plain, hashed) -> bool:  # bcrypt.checkpw

# JWT
def create_access_token(user_id, role, tier='free') -> str:
    # payload: sub/role/tier/type=access/iat/exp
    # exp = now + jwt_access_ttl (默认 3600s)
def create_refresh_token(user_id) -> str:
    # payload: sub/type=refresh/iat/exp
    # exp = now + jwt_refresh_ttl (默认 604800s = 7天)
def decode_token(token) -> dict:
    # HS256, jwt.decode, AuthError on fail

# AuthService
async def register(email, password, company=None, real_name=None) -> User:
    # 1) email 唯一性预检
    # 2) username 取 email 本地部分,冲突追加 4 位 hex
    # 3) 创建 User + Free UserPlan + Personal Organization
    # 4) 自动 commit 后 issue_tokens
async def authenticate(email, password) -> User:
    # 1) 按 email 查 user
    # 2) verify_password
    # 3) status 必须 active
    # 4) 更新 last_login_at
def issue_tokens(user) -> dict:
    # 返回 access_token/refresh_token/token_type/expires_in
async def refresh_access(refresh_token) -> dict:
    # 1) decode → 必须 type=refresh
    # 2) 按 sub 查 user
    # 3) status 必须 active
    # 4) 重新签发 access + refresh (无 rotation 黑名单)
```

**可复用**:
- `bcrypt` 哈希 + `verify_password` 整体逻辑
- `create_access_token` / `create_refresh_token` / `decode_token` 签名逻辑(可加 `aud` `iss` 字段)
- `issue_tokens` 包装逻辑
- `AuthService` 类结构(扩展方法,不动现有 register/authenticate/refresh_access)

**需要修改 / 扩展**:
- 注册方法需支持 phone+code / phone+password 两种入口
- 登录方法需支持 phone+code / phone+password / email+password / oauth
- 需新增 logout_session / logout_all / list_sessions / revoke_session
- 需新增 send_code / verify_code
- 需新增 oauth_authorize_start / oauth_callback
- 需新增 change_password / forgot_password / reset_password
- 需新增 link_identity / unlink_identity(账户绑定)
- refresh_access 需要支持 rotation(写 refresh_token_versions 表)

**安全风险**:
1. `bcrypt.checkpw` 异常吞了 (ValueError, TypeError) → 返回 False,可接受
2. JWT 无 audience / issuer 校验 → 风险低(同 secret 即可伪造),后续加 aud/iss
3. Refresh token **无黑名单** → logout 无法真正撤销旧 token(只能用过期策略)
4. Login 错误信息**会泄露** "邮箱或密码错误"(统一文案可接受,但注册时 "邮箱 xxx 已注册" 是枚举点 — 需改 "若该邮箱已注册,我们已发送邮件" 防枚举)
5. **无失败计数锁定** → 暴力破解无保护
6. **无 IP / UA 审计** → 已有 `audit_records` 表,需在登录链路里强制写入
7. **无 UTM 归因** → 无法判断用户来源

---

## 5. JWT / Session 当前实现

**JWT 结构** (HS256):
```json
{
  "sub": "<user_uuid>",
  "role": "submitter",
  "tier": "free",
  "type": "access" | "refresh",
  "iat": 1700000000,
  "exp": 1700003600
}
```

**TTL 配置** (Settings):
- `jwt_secret: str = "change_me_in_production"` — **生产 .env 已用 64 hex 覆盖**
- `jwt_access_ttl: int = 3600` (1 小时) — 任务要求 15-30 分钟,**后续可调小,需保留 3600 兼容**
- `jwt_refresh_ttl: int = 604800` (7 天) — 任务要求 7-30 天,**在范围内**

**当前存储**:
- 后端:**无状态**,token 不存 DB(只在 AuditRecord 写一次 actor_id)
- 前端:`localStorage["lr_token"]` + `localStorage["lr_user"]` + 同步到 `document.cookie["lr_token"]`

**安全风险**:
1. **localStorage 存 token** — XSS 即可窃取,必须迁移到 HttpOnly Secure Cookie
2. **Cookie 缺 Secure / HttpOnly / SameSite** — 当前 `lib/auth.ts` 只设了 `samesite=lax`,**没设 Secure**(生产 HTTPS 必须有) **没设 HttpOnly**(JS 可读,被 XSS 偷)
3. **Refresh token 无 rotation / 无吊销** — 7 天内 token 永不过期除非自然到期
4. **同一 secret 跨多端使用** — HS256 单一密钥,建议升级 RS256(后续优化,本轮可保留 HS256)

**需要新增**:
- `refresh_tokens` 表(token hash / user_id / user_agent / ip / expires_at / revoked_at / replaced_by)
- `access_token_jti` (可选用 jti 字段实现黑名单)
- `user_sessions` 视图(把 refresh_token + UA + IP 暴露给用户中心"登录设备"页)

---

## 6. 当前 Login API

```
POST /api/v1/auth/register    201  {email, password, company?, real_name?}
POST /api/v1/auth/login       200  {email, password}
POST /api/v1/auth/refresh     200  {refresh_token}
GET  /api/v1/auth/me          200  Bearer
GET  /api/v1/auth/quota       200  Bearer
POST /api/v1/auth/logout      200  Bearer
```

**register 行为**: email 唯一、username 派生、bcrypt、status=active、自动创建 Free UserPlan、自动创建 Personal Organization、issue tokens。
**login 行为**: bcrypt 校验、status 检查、更新 last_login_at、issue tokens。
**refresh 行为**: 校验 type=refresh、查 user、状态 active、重新签发 (无 rotation,无吊销)。
**logout 行为**: 仅写 audit log,**不撤销 token**(客户端自清)。

**新增需求** (按 45 节规范):
```
POST /api/v1/auth/register/phone      201  {phone, code, password, agreements}
POST /api/v1/auth/register/email      201  {email, password}
                                       -> 发验证邮件(若 EmailProvider 配置)
POST /api/v1/auth/sms/send            200  {phone, purpose}
POST /api/v1/auth/sms/verify          200  {phone, code, purpose}
POST /api/v1/auth/login/password      200  {email, password}  -- 旧 login 改名
POST /api/v1/auth/login/phone         200  {phone, password}  -- 新增
POST /api/v1/auth/login/sms           200  {phone, code}      -- 新增
POST /api/v1/auth/token/refresh       200  {refresh_token}    -- 旧 refresh 改名
POST /api/v1/auth/logout              200  Bearer  -- 撤销当前 session
POST /api/v1/auth/logout-all          200  Bearer  -- 撤销所有 session
POST /api/v1/auth/password/forgot     200  {account, method: phone|email}
POST /api/v1/auth/password/reset      200  {token, new_password}  -- email 流程
POST /api/v1/auth/password/reset-sms  200  {phone, code, new_password}  -- sms 流程
GET  /api/v1/auth/oauth/{provider}           -- 跳转 provider
GET  /api/v1/auth/oauth/{provider}/callback  -- 回调
GET  /api/v1/users/me                       -- 同 /auth/me
PATCH /api/v1/users/me                      -- 更新 display_name/avatar
GET  /api/v1/users/me/identities            -- 列出所有已绑定方式
POST /api/v1/users/me/identities/{provider} -- 绑定(需验证)
DELETE /api/v1/users/me/identities/{provider} -- 解绑
GET  /api/v1/users/me/sessions              -- 登录设备
DELETE /api/v1/users/me/sessions/{sid}      -- 踢出
POST /api/v1/users/me/deactivate            -- 注销(soft delete)
POST /api/v1/auth/onboarding/complete       -- 保存 onboarding
GET  /api/v1/admin/users                    -- 管理员
PATCH /api/v1/admin/users/{id}/status       -- 启用/禁用
```

**保留现有端点不破坏**:
- `/auth/register` `/auth/login` `/auth/refresh` 仍可用,内部委托到新的 service 方法
- 前端 api.ts 同步扩展(`login(email, password)` 保留,新增 `loginWithPhone`)

---

## 7. 当前 Demo 用户逻辑

**Demo 用户**:`demo@shajindi.com` / `Demo@2024` / role=submitter / status=active
- 通过 `backend/scripts/seed_users_orgs.py` 流程的扩展(手动 register API)创建
- 业务上等价于普通 Free 用户
- **必须保留可登录**(系统启动期间不能被禁用)

**scripts/seed_users_orgs.py 现状**:
- 创建 `system` 用户 + `系统默认送审单位` 组织作为兜底(供 documents.upload header 缺失时使用)
- **不创建** demo 用户(那是手动 register)

**改进点**:
- 不删除 demo 用户
- 新增"系统初始化"脚本入口可创建 super_admin / 内部 admin / 内部 demo 三个固定账号
- 生产 .env 增加 `DEMO_ENABLED=false` 控制,关闭时 demo 用户自动 disabled(但不删)

---

## 8. PostgreSQL 用户相关表

**T01 users** — 已在 Section 3 详述
**T02 organizations** — name/type/parent_id/region_code/status,已有
**T13 user_plans** — user_id/tier/status/quota_daily/used_today/quota_reset_date/period_days/started_at/expires_at/cancelled_at
**T14 orders** — user_id/plan_tier/amount_cny/period_days/status/payment_channel/payment_no/paid_at/note
**T15 payments** — order_id/user_id/amount_cny/status/channel/channel_trade_no/paid_at/raw_callback/note
**T08 audit_records** — 已有 trace_id/actor_id/actor_role/action/target_type/target_id/before_value/after_value/ip_address/user_agent/created_at
**T01 timestamps** — created_at/updated_at (TimestampMixin)

**需新增的表** (Alembic 0003):
- `oauth_identities` (id, user_id, provider, provider_user_id UNIQUE with provider, provider_email, access_token_encrypted, refresh_token_encrypted, scope, created_at, updated_at)
- `verification_codes` (id, target, channel, purpose, code_hash, expires_at, attempt_count, used_at, created_at) — phone/email 共用
- `refresh_tokens` (id, user_id, token_hash, user_agent, ip_address, expires_at, revoked_at, replaced_by, created_at)
- `user_login_events` (id, user_id, ip_address, user_agent, login_method, success, failure_reason, created_at)
- `user_acquisition_sources` (id, user_id, utm_source, utm_medium, utm_campaign, utm_content, utm_term, referrer, landing_page, created_at)
- `user_events` (id, user_id, event_name, properties JSONB, ip, ua, created_at) — 埋点
- `rate_limit_buckets` (id, key, count, window_start) — Redis 失败时兜底(主用 Redis)

**T01 users 增量字段** (Alembic 0003):
- phone_verified_at, email_verified_at, display_name, avatar_url, locale, timezone, password_changed_at, deactivated_at, onboarding_completed_at, onboarding_role, onboarding_purpose, failed_login_count, locked_until
- 新增 `idx_users_phone` 部分索引 (WHERE phone IS NOT NULL)
- 新增 unique constraint on `phone` **WHEN NULL** (PostgreSQL 用 `UNIQUE NULLS DISTINCT` 语义需在 app 层兜底;建议 phone 不为空时做 UNIQUE,**不强制 phone NOT NULL**)

---

## 9. Alembic 迁移状态

| Revision | 描述 | 状态 |
|---|---|---|
| `0001` | initial_schema (12 表) | ✅ 已应用 |
| `0002` | saas_user_subscription (users.company + user_plans + orders + payments) | ✅ 已应用 |
| `c369d702b000` | expand documents.mime_type to 128 | ✅ 已应用 |

**未来迁移**:
- `0003_auth_saas_identity` — 增量修改 users + 新增 oauth_identities/verification_codes/refresh_tokens/user_login_events/user_acquisition_sources/user_events/rate_limit_buckets + 新增 idx_users_phone

**迁移铁律**:
- 禁止 DROP DATABASE / DROP TABLE
- 禁止 reset database
- 只能 ADD COLUMN / ADD TABLE / CREATE INDEX
- 必须保留 demo 用户可登录

---

## 10. Nginx 路由

**文件**: `deploy/nginx/conf.d/legalai86.com.cn.conf`

**当前 80 端口**:
- `/.well-known/acme-challenge/` → certbot 静态目录
- 其他 → 301 跳 https

**443 端口**:
- TLS: 腾讯云免费证书 (`/etc/nginx/ssl/legalai86.com.cn_bundle.crt` + `.key`)
- 协议: TLSv1.2 + TLSv1.3
- 安全头: HSTS (max-age=31536000; includeSubDomains) / X-Content-Type-Options / X-Frame-Options SAMEORIGIN / Referrer-Policy
- `/api/` → `proxy_pass http://backend:8000` (SSE timeout 300s, proxy_buffering off)
- `/` → `proxy_pass http://frontend:3081` (WebSocket upgrade headers)

**X-Forwarded-For 已透传** — `request.client.host` 拿真实 IP。

**新增路由** (前端路径):
- `/login` `/register` `/forgot-password` `/reset-password` `/account` `/account/security` `/account/devices` `/account/binding` `/onboarding` — 全部走 frontend:3081,无需改 nginx

**新增 API**:
- `/api/v1/auth/...` `/api/v1/users/...` `/api/v1/admin/...` — 已走 `/api/` 通用 proxy

**不需修改**:
- nginx 主配置
- certbot 自动续期逻辑

---

## 11. Docker Compose

**文件**: `deploy/docker-compose.prod.yml`

**5 服务**:
- `legal-pg` (pgvector/pgvector:pg16)
- `legal-redis` (redis:7-alpine, appendonly)
- `legal-backend` (python:3.11-slim)
- `legal-frontend` (node:22 实际 base)
- `legal-nginx` (nginx:1.27)

**挂载卷**:
- `legal_pg_data` — **绝不能删**
- `legal_redis_data` — 可保留
- `legal_backend_sandbox` — 文件沙箱
- `legal_backend_uploads` — 上传文件
- `legal_certbot_conf` / `legal_certbot_www` — 证书

**网络**: `appnet` (bridge),5 容器互通

**前端容器内 BACKEND_URL** = `http://backend:8000` — 通过 Next.js rewrites 转发 /api

**新增环境变量** (backend 容器):
```env
SMS_PROVIDER=mock                       # mock|tencent|aliyun
TENCENT_SMS_SECRET_ID=
TENCENT_SMS_SECRET_KEY=
TENCENT_SMS_APP_ID=
TENCENT_SMS_SIGN_NAME=
TENCENT_SMS_TEMPLATE_ID=

EMAIL_PROVIDER=mock                     # mock|smtp
SMTP_HOST=
SMTP_PORT=587
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_USE_TLS=true
EMAIL_FROM=noreply@legalai86.com.cn

GITHUB_CLIENT_ID=
GITHUB_CLIENT_SECRET=
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
WECHAT_APP_ID=
WECHAT_APP_SECRET=

WECHAT_LOGIN_ENABLED=false              # 默认 false
GOOGLE_LOGIN_ENABLED=false              # 默认 false
GITHUB_LOGIN_ENABLED=true               # 默认 true

CAPTCHA_ENABLED=false                   # 暂时关闭
CAPTCHA_PROVIDER=turnstile               # turnstile|hcaptcha|recaptcha|tencent
CAPTCHA_SITE_KEY=
CAPTCHA_SECRET_KEY=

# Token 加密(OAuth token 落库用)
OAUTH_TOKEN_ENC_KEY=                    # Fernet key(32 url-safe base64)

# Rate limit
RATE_LIMIT_ENABLED=true
RATE_LIMIT_RPM=60

# CORS 扩展(已有逗号分隔)
CORS_ORIGINS=https://legalai86.com.cn,https://www.legalai86.com.cn
```

---

## 12. .env 配置 (当前)

**backend/.env.example** 包含:
- APP / DB / REDIS / LLM / Embedding / JWT / Agent / CORS — 完整
- **缺**:SMS / Email / OAuth / Captcha / Cookie 加密 key

**deploy/.env.example** 包含:
- POSTGRES_PASSWORD / JWT_SECRET / LLM_PROVIDER / DEEPSEEK_API_KEY / QWEN_API_KEY / CORS_ORIGINS — 6 个变量
- **缺**:SMS / Email / OAuth / Captcha

**生产 .env (服务器 /opt/legal-review/deploy/.env)**:
- 已设 POSTGRES_PASSWORD / JWT_SECRET(64hex) / LLM_PROVIDER=mock / CORS_ORIGINS
- 新增项需追加,deploy.sh 已实现幂等补齐(可改 deploy.sh 自动追加缺省项)

**安全铁律**:生产 .env 不得 commit Git。当前 .gitignore 已排除 backend/.env 与 deploy/.env

---

## 13. 当前 RBAC / Tenant / SaaS

**Role** (UserRole StrEnum):
- submitter / reviewer / supervisor / admin / librarian

**Status** (UserStatus StrEnum):
- active / disabled / **locked**

**任务要求新增**:
- `suspended` (临时封禁,区别于 disabled)
- `deleted` (软删除,已通过 deleted_at 实现,只需在状态枚举中明确)

**Tenant (Organization)**:
- Organization 已有 type (county_dept/township/street/public_inst/state_owned/personal)
- 注册时自动创建 PERSONAL org
- **不需要改** Organization 表结构

**SaaS 套餐**:
- user_plans 已有 (free/pro/enterprise)
- orders + payments 已有
- **不需要改** SaaS 层

**RBAC 守卫**:
- `require_role(*roles)` 工厂已在 `app/api/deps.py:111-123`
- 当前用法示例:`current_user: User = Depends(require_role("admin"))`
- **复用** — 扩展 `require_role` 为 `require_admin` / `require_super_admin` 即可
- **关键安全**:严禁普通用户通过 API 修改 `role` 字段,需在 schema 层禁 `role` update 字段(已自然不暴露)

---

## 14. 当前登录态在前端如何保存

```ts
// frontend/src/lib/auth.ts
TOKEN_KEY = "lr_token"
USER_KEY = "lr_user"
localStorage[TOKEN_KEY] = access_token
localStorage[USER_KEY] = JSON.stringify(user)
// 同步到 cookie
document.cookie = `lr_token=${token}; path=/; max-age=${60*60*24*7}; samesite=lax`;
```

**问题**:
- localStorage 存 token → XSS 偷取
- cookie 没 Secure / HttpOnly → JS 可读 / HTTPS 下也明文
- 7 天 max-age 与 refresh_token TTL 对齐

**升级目标**:
- 改用 HttpOnly Secure SameSite=Lax cookie(由后端 Set-Cookie,前端不再存)
- 保留 `lr_user` (非敏感) 在 localStorage 供 UI 用
- access_token 15 分钟,refresh_token 7-30 天
- cookie 命名:`__Host-lr_at`(access)+ `__Host-lr_rt`(refresh)

**注意 Next.js 16 同源**:
- 前端 `https://legalai86.com.cn` 访问 `/api/...` 通过 Next.js rewrite 转到后端 `http://backend:8000`
- cookie 域名需设为 `legalai86.com.cn`(不设 domain,默认当前 host)
- 后端若直接返 Set-Cookie,Next.js 需透传(用 `proxy_pass` 已透传,nginx 也透传)

---

## 15. 当前密码 hash 算法

**算法**: bcrypt (cost=12)
**库**: `bcrypt>=4.1.0`
**存储格式**: `$2b$12$...`(标准 bcrypt)

```python
def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")
```

**任务建议**: 优先 Argon2id,允许沿用 bcrypt(本系统已稳定)。

**升级策略**:
- **不强制迁移**现有用户
- 新用户/修改密码时,默认用 Argon2id(`argon2-cffi`)
- login 时先检测 hash 前缀:`$argon2id$` → argon2 verify,`$2b$` → bcrypt verify
- 探测式升级:用户用 bcrypt 哈希成功登录后,**异步**用 argon2id 重哈希并落库(opportunistic rehash)
- 提供 `PasswordHasher` 抽象,统一入口

**最低密码要求**: 8 位(min_length=8,已实现)

---

## 16. CORS / CSRF / Cookie 配置

**CORS** (main.py):
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- `cors_origin_list` 逗号分隔,生产 .env 含 `https://legalai86.com.cn,https://www.legalai86.com.cn` ✅
- `allow_credentials=True` — 允许 cookie 跨源(同源时不需要,但保留 OK)

**CSRF**:
- 当前**无 CSRF token** — SameSite=Lax Cookie + Authorization Bearer header 双保险基本够用
- 升级为 SameSite=Lax HttpOnly cookie 后,需要在 OAuth callback / 表单 POST 加 `X-Requested-With` header 或 CSRF token

**Cookie 安全**:
- 当前 `document.cookie` JS 写入,**无 HttpOnly 无 Secure** — **必须升级**
- 生产 HTTPS,cookie 必须 Secure=true
- 新方案:后端 Set-Cookie `__Host-lr_at` + `__Host-lr_rt`,属性 `Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=...`

**安全头** (nginx 已配):
- HSTS max-age=31536000 ✅
- X-Content-Type-Options nosniff ✅
- X-Frame-Options SAMEORIGIN ✅
- Referrer-Policy strict-origin-when-cross-origin ✅
- **建议追加**: Content-Security-Policy(防 XSS)

---

## 17. 当前页面

| 路径 | 状态 | 备注 |
|---|---|---|
| `/` | 200,公开 | 首页 + Hero + Features + Plans + Footer(已有"立即注册"+"登录控制台") |
| `/login` | 200,公开 | 简单居中卡片,只支持邮箱+密码 |
| `/register` | 200,公开 | 邮箱+密码+姓名+公司,**无协议勾选** |
| `/dashboard` | 受保护 | 已登录用户主页 |
| `/upload` | 受保护 | 文件上传 |
| `/review/[id]` | 受保护 | 审查详情 |
| `/report/[id]` | 受保护 | 报告 |
| `/admin` | 受保护(admin role) | 简单管理页(占位) |
| `/account` | **不存在** | 需新建 |
| `/forgot-password` | **不存在** | 需新建 |
| `/reset-password` | **不存在** | 需新建 |
| `/onboarding` | **不存在** | 需新建 |

**TopBar 改造**:
- 未登录:显示 "登录" + "免费注册"
- 已登录:显示 Avatar + 用户名(下拉菜单:LegalAI/账户设置/退出登录)

**移动端**:
- 当前未做移动端针对性优化
- 升级时所有新页面必须 mobile-first,断点 `md:`

---

## 18. 审计结论:可复用 / 需修改 / 需新增

### 18.1 可复用 (不要动)

| 模块 | 文件 | 原因 |
|---|---|---|
| bcrypt 哈希 | `auth_service.py:33-44` | 业务稳定,沿用 + 探测式升级 Argon2id |
| JWT 签发 / 解码 | `auth_service.py:49-95` | 结构稳定,加 aud/iss 可选 |
| `User` / `Organization` / `UserPlan` / `Order` / `Payment` 模型 | `models/user.py` | 已在 Sprint 6 稳定 |
| `require_role` 工厂 | `api/deps.py:111-123` | 扩展即可 |
| `get_current_user` | `api/deps.py:61-92` | 升级时 status 检查加 suspended/deleted |
| `AuditService` | `services/audit.py` | 已记录 actor/role/target/ip/ua,扩展 action 即可 |
| `pydantic-settings` 配置体系 | `core/config.py` | 增量加新变量 |
| `AppError` 体系 | `core/errors.py` | 扩展 `RateLimitedError` `EmailSendError` `OAuthError` |
| nginx 路由 + HTTPS | `deploy/nginx/conf.d/` | 不动 |
| Alembic 链路 | `alembic/env.py` | 不动 |
| 前端 UI 组件库 | `components/ui/*` | 沿用 |
| 演示用户 `demo@shajindi.com` | 数据库 | 不动 |

### 18.2 需要修改 (增量)

| 文件 | 修改 |
|---|---|
| `models/user.py` | 增量加新字段(phone_verified_at / email_verified_at / display_name / ...),不删旧字段 |
| `models/__init__.py` | 导入新增的 `OAuthIdentity` / `VerificationCode` / `RefreshToken` / `LoginEvent` / `AcquisitionSource` / `UserEvent` |
| `core/constants.py` | `UserStatus` 增 `suspended` `deleted`;新增 `OAuthProvider` 枚举;新增 `VerificationPurpose` 枚举;新增 `LoginMethod` 枚举 |
| `core/config.py` | 增量加新环境变量 |
| `services/auth_service.py` | 扩展方法(register_phone / register_email_with_verification / send_code / verify_code / login_phone / login_sms / login_email / change_password / forgot_password / reset_password / oauth_authorize / oauth_callback / link_identity / unlink_identity / list_sessions / revoke_session / deactivate_account) |
| `api/v1/auth.py` | 新增 P0 端点,保留旧端点作 alias |
| `api/v1/__init__.py` | 新增 users router / admin router |
| `api/deps.py` | `get_current_user_optional` 已存在;`require_admin` / `require_super_admin` 工厂 |
| `lib/auth.ts` (frontend) | 改用 cookie-only 模式(localStorage 存 user,cookie 自动由后端 Set-Cookie) |
| `lib/api.ts` (frontend) | 扩展 sendCode / verifyCode / loginWithPhone / loginWithSms / registerPhone / registerEmail / forgotPassword / resetPassword / fetchMeIdentities / linkIdentity / unlinkIdentity / fetchSessions / revokeSession / fetchOnboarding / completeOnboarding |
| `proxy.ts` (frontend) | 扩展 protected 列表;redirect 参数对齐 `?next=` |
| `AuthGuard.tsx` (frontend) | 读取 `?next=` 回跳 |
| `next.config.mjs` (frontend) | 不动 |
| `core/errors.py` | 增 `RateLimitedError(429)` `EmailSendError(500)` `OAuthError(400)` `TokenRevokedError(401)` |

### 18.3 需新增 (新文件 / 新表)

**后端**:
- `app/services/sms/base.py` `mock_provider.py` `tencent_provider.py` `factory.py`
- `app/services/email/base.py` `mock_provider.py` `smtp_provider.py` `factory.py`
- `app/services/oauth/base.py` `github.py` `google.py` `wechat.py` `factory.py`
- `app/services/captcha/base.py` `mock_provider.py` `turnstile_provider.py` `factory.py`
- `app/services/rate_limit.py` — Redis 限流
- `app/services/password_hasher.py` — argon2id / bcrypt 双算法
- `app/services/identity.py` — Account Linking 逻辑
- `app/services/audit_auth.py` — 鉴权专项结构化日志
- `app/api/v1/users.py` — `/api/v1/users/*`
- `app/api/v1/admin.py` — `/api/v1/admin/*`
- `alembic/versions/0003_auth_saas_identity.py` — 增量迁移

**前端**:
- `app/(auth)/forgot-password/page.tsx`
- `app/(auth)/reset-password/page.tsx`
- `app/account/page.tsx`(默认 tab profile)
- `app/account/security/page.tsx`
- `app/account/devices/page.tsx`
- `app/account/binding/page.tsx`
- `app/onboarding/page.tsx`
- `components/auth/PhoneLoginForm.tsx`
- `components/auth/EmailLoginForm.tsx`
- `components/auth/SmsCodeInput.tsx`
- `components/auth/PhoneRegisterForm.tsx`
- `components/auth/EmailRegisterForm.tsx`
- `components/auth/ForgotPasswordForm.tsx`
- `components/auth/ResetPasswordForm.tsx`
- `components/auth/OnboardingFlow.tsx`
- `components/auth/OAuthButton.tsx`
- `components/auth/IdentityBindingList.tsx`
- `components/auth/SessionList.tsx`
- `components/dashboard/UserMenu.tsx`(TopBar 头像下拉)
- `components/auth/PhoneInput.tsx`(中国 +86 格式化)
- `components/auth/CaptchaWidget.tsx`(后期接入)

**测试**:
- `tests/test_auth_register_phone.py`
- `tests/test_auth_login_sms.py`
- `tests/test_auth_oauth.py`
- `tests/test_auth_account_linking.py`
- `tests/test_auth_password_reset.py`
- `tests/test_auth_sessions.py`
- `tests/test_auth_rate_limit.py`
- `tests/test_auth_admin.py`
- `e2e/test_new_user_journey.py`(Playwright 或 httpx E2E)

**文档**:
- `AUTH_SYSTEM_AUDIT.md`(本文)
- `AUTH_ARCHITECTURE.md`
- `ACCOUNT_LINKING_DESIGN.md`
- `AUTH_SECURITY_REVIEW.md`
- `AUTH_DEPLOYMENT_REPORT.md`
- `AUTH_E2E_TEST_REPORT.md`

---

## 19. 安全风险汇总 (P0 上线前必修)

| # | 风险 | 等级 | 修复方案 |
|---|---|---|---|
| 1 | localStorage 存 access_token | 高 | 迁移到 HttpOnly Secure cookie |
| 2 | Cookie 缺 Secure / HttpOnly | 高 | 后端 Set-Cookie 时强制 |
| 3 | 无失败计数 / 锁定 | 高 | failed_login_count + locked_until |
| 4 | 无 IP / 单号 / 验证码发送频控 | 高 | Redis rate_limit |
| 5 | 注册时 "邮箱已注册" 泄露 | 中 | 改 "若该邮箱可注册,我们已发送邮件" |
| 6 | 验证码无尝试次数限制 | 中 | verification_codes.attempt_count 上限 5 |
| 7 | Refresh token 无 rotation / 撤销 | 中 | refresh_tokens 表 + replaced_by |
| 8 | 无 UTM 归因 | 中 | user_acquisition_sources 表 |
| 9 | 无 Event 埋点 | 中 | user_events 表 |
| 10 | 注销账号无路径 | 中 | soft delete + deactivated_at |
| 11 | Admin 无 UI | 中 | /admin/users 列表 + 状态切换 |
| 12 | 无 Account Linking 安全策略 | 中 | verified_email 才允许自动 link |
| 13 | OAuth token 落库明文 | 中 | Fernet 加密 access/refresh token |
| 14 | 无 CSRF token | 低 | SameSite=Lax + Authorization header 双保险可接受;或加 csrf_token |
| 15 | 无 CSP | 低 | 追加 Content-Security-Policy 头 |

---

## 20. 不能动的代码 (Frozen Areas)

**绝对不能修改**:
- `alembic/versions/0001_initial_schema.py` 升级逻辑(已应用)
- `alembic/versions/0002_saas_user_subscription.py` 升级逻辑
- `alembic/versions/c369d702b000_expand_documents_mime_type_to_128.py` 升级逻辑
- `users.id` (UUID PK) 已有引用
- `users.password_hash` 现有值(只能追加新算法逻辑,不能改既有 hash 字符串)
- `organizations` 表结构
- `user_plans` / `orders` / `payments` 表结构
- `documents` / `review_tasks` / `legal_documents` / `legal_clauses` / `review_results` / `agent_logs` / `audit_records` / `feedback_cases` / `prompts` / `golden_dataset` / `eval_runs` 已有 12 张表
- Demo 用户 `demo@shajindi.com` 的 row(允许改 status 但不允许删除)
- 9 个 Agent 的 graph / nodes / harness
- 现有 `submitReview` 流程(documents → review_tasks 链路)
- `proxy_pass` 到 `backend:8000` 的 nginx 路由

**可以新增 / 增量修改**:
- users 表追加新列(ALTER TABLE ADD COLUMN)
- 新建 6+ 张表
- 新建 endpoint
- 新建 service / provider
- 新建前端页面
- 替换 auth_service.py 内部实现(但保持 issue_tokens / verify_password / decode_token 公共 API 不变或做向后兼容)

---

## 21. 增量迁移计划 (Alembic 0003 草案)

```python
# 0003_auth_saas_identity.py
revision = "0003"
down_revision = "0002"

def upgrade():
    # 1) users 表加列
    op.add_column("users", sa.Column("phone_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.String(64), nullable=True))
    op.add_column("users", sa.Column("avatar_url", sa.String(512), nullable=True))
    op.add_column("users", sa.Column("locale", sa.String(8), nullable=True, server_default="zh-CN"))
    op.add_column("users", sa.Column("timezone", sa.String(32), nullable=True, server_default="Asia/Shanghai"))
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("onboarding_completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("onboarding_role", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("onboarding_purpose", sa.String(32), nullable=True))
    op.add_column("users", sa.Column("failed_login_count", sa.Integer, nullable=False, server_default="0"))
    op.add_column("users", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))
    
    # 2) users 表加索引
    op.create_index("idx_users_phone_partial", "users", ["phone"], 
                    postgresql_where=sa.text("phone IS NOT NULL AND deleted_at IS NULL"))
    op.create_index("idx_users_status", "users", ["status"],
                    postgresql_where=sa.text("deleted_at IS NULL"))
    
    # 3) oauth_identities
    op.create_table("oauth_identities", ...)
    op.create_unique_constraint("uq_oauth_provider_user", "oauth_identities", ["provider", "provider_user_id"])
    
    # 4) verification_codes
    op.create_table("verification_codes", ...)
    op.create_index("idx_vc_target_purpose", "verification_codes", ["target", "purpose", "created_at"])
    
    # 5) refresh_tokens
    op.create_table("refresh_tokens", ...)
    op.create_index("idx_rt_user", "refresh_tokens", ["user_id", "expires_at"])
    
    # 6) user_login_events
    op.create_table("user_login_events", ...)
    op.create_index("idx_ule_user", "user_login_events", ["user_id", "created_at"])
    
    # 7) user_acquisition_sources
    op.create_table("user_acquisition_sources", ...)
    
    # 8) user_events
    op.create_table("user_events", ...)
    op.create_index("idx_ue_user", "user_events", ["user_id", "event_name", "created_at"])
    
    # 9) rate_limit_buckets(可选,Redis 主用)
    op.create_table("rate_limit_buckets", ...)
```

---

## 22. 验收标准 (P0 阶段)

完成所有 P0 任务后,**全新手机号用户**能完成:
1. 访问 `https://legalai86.com.cn` 看到 "立即免费使用" + "登录" CTA
2. 点 "立即免费使用" → `/register` → 选 "手机号注册" tab
3. 输入 +86 手机号 → 点 "发送验证码" → 60s 内收到(开发用 mock,生产用腾讯云)
4. 输入 6 位验证码 + 设置 8+ 位密码 + 勾选协议 → 提交
5. 自动登录 → 跳转 `/onboarding`(身份 + 用途)→ 完成 → 跳 `/dashboard`
6. 上传一份审查文件 → 看到 11 节点进度 → 拿到报告
7. 进入 `/account` → 看到资料 + 安全 + 设备 + 绑定
8. 点 "退出登录" → 回到 `/login`
9. 再次用手机号+密码登录 → 进入 dashboard

**E2E 用全新用户跑通即视为通过**。

---

## 23. 审计签名

- 审计执行:Production Auth Audit
- 审计结论:**可以开始增量升级**
- **关键决策**:
  - 保留 bcrypt,**探测式升级** Argon2id
  - 保留 demo 用户,**不删除**
  - 保留所有现有 API,**新增端点**
  - Cookie 升级为 HttpOnly Secure,前端 localStorage 移除 token(仅保留 user)
  - OAuth 默认禁用(微信/Google),GitHub 默认启用
  - SMS 优先 Mock,生产环境通过 `SMS_PROVIDER=tencent` 切换
  - Onboarding 完成后才进入 dashboard,可选 skip

---

> 审计完成。下一步进入 Section 3-17:设计统一身份系统架构。
