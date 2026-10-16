# 认证系统升级 · 阶段 1 审计报告

> 审计日 2026-10-15 · 范围：backend（FastAPI + SQLAlchemy async + Postgres + Alembic 0008）/ frontend（Next.js 16 + React 19 + zustand + Tailwind v4）

## 结论先行

项目已存在一套完成度约 70% 的「M0 统一身份系统」骨架（0003 迁移），**不需要重写认证框架**，本次升级 = 补齐断点 + 打通前后端 + UI 重设计。核心断点是：**后端能力齐全但 API 层有缺口、前端完全没有接入新认证体系**（仍用旧邮箱密码 + localStorage token）。

## 已有能力（直接复用）

| 能力 | 位置 | 状态 |
| --- | --- | --- |
| users 表双凭证（email+phone 同表）+ email/phone_verified_at + failed_login_count/locked_until + onboarding + agreed_terms_at | models/user.py:47-106 | ✅ |
| Argon2id 优先 + bcrypt 兼容 + 登录时 opportunistic rehash | services/auth_service.py:62-132 | ✅ |
| JWT HS256 access(1h) + refresh(30d, jti) | services/auth_service.py:140-185 | ✅ |
| refresh token 持久化：sha256 落库 + 轮换(replaced_by 链) + 单会话撤销 + 全设备撤销 + 会话列表 | auth_service.py:496-620 | ✅ 服务层齐 |
| 验证码：secrets 6位 + bcrypt 落库 + 5min TTL + 5次错作废 + 60s冷却 + IP 5/10min + 日10条 | services/verification.py | ✅ |
| SMS/Email Provider 抽象（sms: mock；email: mock+smtp；aliyun/tencent 仅配置占位） | services/sms/、services/email/ | ✅ |
| 统一登录/注册：验证码通过 → login_or_register_by_identity（phone/email 同一 user_id） | auth_service.py:398-483 | ✅ |
| 防枚举：统一「邮箱或密码错误」文案 | auth_service.py:286-295 | ✅ |
| 身份/审计模型：oauth_identities、account_link_pending、user_login_events、user_events、rate_limit_buckets | models/identity.py | ✅ 模型已建 |
| 渠道开关配置 auth_sms/email/password/wechat..._enabled + 验证码阈值配置项 | core/config.py:88-141 | ✅ 配置在 |
| 业务资产全挂 user_id：user_plans/orders/payments/review_tasks/documents/user_feedback | models/* | ✅ |
| 现有测试：test_auth_api.py（注册/登录/me/401/重复邮箱）、test_verification.py（冷却/限流/过期/尝试次数） | tests/ | ✅ |

## 缺失能力（本次补齐）

1. **忘记/重置/修改密码端点**：purpose 白名单有 `reset_password` 但无 API
2. **绑定/换绑手机号/邮箱端点**：purpose 有 `bind_phone/bind_email/change_*` 但无 API
3. **会话管理端点**：`list_sessions/revoke_all_user_tokens` 服务已实现但无路由
4. **登录审计未落库**：`user_login_events` 模型存在但登录全流程 0 写入
5. **本地密码注册端点**：`/auth/register` 走 Core Strangler 外部服务；本地 `AuthService.register` 存在但 API 未用（双轨混乱）
6. **验证码阈值配置未接线**：config.py 有 `verification_*` 配置但 verification.py 用硬编码常量
7. ~~**users.phone 无唯一索引**~~（审计修正：0003 已建 `ux_users_phone_normalized` 唯一索引，无需处理）
8. **前端零接入**：无验证码 UI、无手机号登录、无 `/auth/sms/send` 等 6 个端点调用、无 redirect 参数处理
9. **前端 401 直接登出**：`refreshToken()` 已定义但无调用方，无静默续期
10. **用户中心 /account 不存在**；TopBar 无账户入口
11. **转化埋点缺失**：现有 12 事件白名单无 auth 类事件

## 安全问题

| # | 问题 | 级别 | 处置 |
| --- | --- | --- | --- |
| S1 | refresh token 由前端 JS 持有（localStorage）→ XSS 可窃取 30 天凭证 | 高 | refresh 改 HttpOnly Cookie，access(1h) 保留内存/localStorage |
| S2 | phone 无 unique 约束 | ~~高~~ | **审计修正**：0003 已建 `ux_users_phone_normalized` 部分唯一索引（regexp_replace 去掉 +86 前缀），DB 层唯一性已就位，无需迁移 |
| S3 | 登录无审计事件（无法回溯爆破/撞库） | 中 | 全登录端点写 user_login_events |
| S4 | proxy.ts 守卫依赖可伪造的 lr_token cookie（仅 UX 层，后端 JWT 校验兜底） | 低 | 改用后端下发的非凭证 hint cookie |
| S5 | access token 撤销粒度：logout 只撤 refresh，access 自然过期（≤1h） | 可接受 | 业界常规，refresh 撤销即阻断续期 |
| S6 | CSRF（引入 cookie 后）：SameSite=Lax + API 保持 Bearer 双模式 | 中 | Lax 下跨站 POST 不带 cookie；写操作仍要求 Authorization |
| S7 | 枚举：验证码发送响应统一成功（不暴露是否已注册）；防枚举文案已有 | 低 | 保持 + 新端点遵循 |
| S8 | 密码策略 min_length=8（NIST 建议单因素≥15 或验证码兜底） | 低 | 本系统验证码+密码双因素场景，保留 8 位下限 + 常见密码拒绝，不强制组合规则 |

## 用户体验问题

1. 登录后固定跳 /dashboard，丢弃 `?redirect=` 原意页面
2. 无登录方式选择；后端已支持的验证码登录不可见
3. 表单无 react-hook-form/zod，错误反馈靠裸 alert 文本
4. 无会话/设备管理 UI；无「退出所有设备」
5. 无忘记密码入口（死路）

## 数据兼容风险

- 旧用户（Core 双跑注册）凭证在 Core 服务、本地 users 表可能无记录 → **保留旧 `/auth/login` 路由不动**，前端登录失败时回退旧端点；本地注册走新端点
- 旧 bcrypt 哈希用户 → rehash 已自动处理 ✅
- phone 加唯一索引前需先查重（迁移内做去重断言，冲突则 FAIL LOUD 而非静默丢数据）

## 推荐改造方案（P0 范围）

1. 迁移 0009：`users.phone` 唯一索引 + 去重预检
2. 后端新增端点（auth.py 扩展）：`/auth/register/password`、`/auth/password/forgot|reset|change`、`/auth/account/bind`、`GET /auth/sessions`、`DELETE /auth/sessions/{id}`、`POST /auth/logout-all`；全部登录端点写 UserLoginEvent；refresh/logout 支持 HttpOnly Cookie（lr_rt，SameSite=Lax）；验证码阈值接配置
3. 前端：登录页（统一身份输入 → 密码/验证码分支）、注册页（邮箱密码本地注册 + 协议勾选 + 可选验证码）、api.ts 静默续期、redirect 还原、/account 用户中心（Profile/Security/Sessions/Billing）、TopBar 入口
4. 埋点：auth_page_view/signup_start/signup_success/login_success/login_failed/verification_sent/verification_success/verification_failed/password_reset_success
5. 暗色适配：登录/注册页按 prefers-color-scheme 适配（全站暗色不在本次范围）

**不做**（P2 预留）：OAuth 实装（模型/配置已预留）、Passkeys/TOTP、组织 SSO、全站暗色主题。
