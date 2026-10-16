# 认证系统升级 · 实施验收报告

> 阶段12 交付物 · 2026-10-16 · 分支工作区（未部署）
> 关联文档：[00_AUDIT.md](./00_AUDIT.md)（阶段1 审计报告，本报告的唯一规格来源）

## 1. 结论

P0 全部完成并通过测试；P1（用户中心 + 转化埋点）完成；P2（OAuth/Passkeys/SSO/TOTP）按任务书要求仅做能力预留，未实施。**生产部署等待用户确认**，本报告不含任何自动部署动作。

| 验证项 | 结果 |
| --- | --- |
| 后端全量 pytest | **435 passed, 27 skipped**（原 410 + 新增 25 个 auth_upgrade 测试） |
| 前端 `tsc --noEmit` | 0 错误 |
| 前端 `next build` | 成功，全部路由生成（含新增 /account、/forgot-password） |
| 数据库迁移 | **无需新迁移**：0003 已含 `ux_users_phone_normalized` 部分唯一索引；head 仍为 0008 |

## 2. 分阶段完成度

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| 1 审计 | 现有认证系统审计 + P0 方案 | ✅ 00_AUDIT.md（S2 修正：phone 唯一性已就位） |
| 2 登录/注册 UI | 统一标识符 + 密码/验证码分段 + 忘记密码 + AuthLayout + 深浅色 + a11y | ✅ |
| 3 身份模型 | 一个 User ID，email/phone 为凭证；0003 索引核实 | ✅（零迁移） |
| 5 后端 API | register/password、login/password（Core 回退）、login/verification、password/forgot|reset|change、account、bind、sessions、logout-all、login-methods | ✅ |
| 6 会话管理 | HttpOnly Cookie（lr_rt）+ Refresh 轮换/撤销 + 多设备管理 | ✅ |
| 7 用户中心 | /account 四区（资料/安全/偏好/套餐）+ TopBar 入口 | ✅ |
| 8 转化埋点 | 10 个 auth 事件前后端白名单对齐，表单接入 | ✅ |
| 9 安全防护 | 见 §5 核查表 | ✅（1 项 P2 已知改进） |
| 11 测试 | 后端 25 新测试 + 全量回归；前端类型 + 构建验证 | ✅ |
| 12 交付 | 本报告 | ✅ |

## 3. 后端改动清单

| 文件 | 变更 |
| --- | --- |
| `app/api/v1/auth.py` | 新增 12 个端点；refresh/logout 支持 Cookie 优先；全部登录端点写 `user_login_events` 审计（成功+失败，失败不阻断）；forgot 恒 200 防枚举 |
| `app/services/auth_service.py` | `authenticate_by_identifier`（@识别邮箱/手机号、统一错误文案、Argon2id 透明 rehash）、`set_password`、`change_password`、`revoke_session_by_id`（属主校验）、`revoke_other_user_tokens`、`bind_identity`、`find_by_email` |
| `app/services/verification.py` | TTL/冷却/限流参数接线 `config.verification_*`（实例属性 + 模块常量回退保持测试兼容） |
| `app/schemas/auth.py` | RefreshRequest.refresh_token 可选；新增 Password/Register/Login/Forgot/Reset/Change/Bind/Profile 等 10 个 Schema |
| `app/api/v1/analytics.py` | 事件白名单 +10（auth_page_view … onboarding_completed） |
| `tests/test_auth_upgrade.py` | 新增 25 测试：注册/登录/Core 回退/Cookie 轮换/防枚举/撤销/越权 404 等 |

关键行为约定：

- **Core Strangler 双跑**：本地 `/auth/login/password` 失败且 identifier 含 `@` 时回退 Core 登录（手机号不触发），Core 成功后取真实 principal；Core 模式不下发 refresh Cookie。
- **Cookie 会话**：`lr_rt`，`Path=/api/v1/auth`、`HttpOnly`、`SameSite=Lax`、生产 `Secure`；cookie 模式 refresh 响应体不回传 refresh_token（`""`）。
- **撤销闭环**：改密码→撤销其他全部会话；重置密码→撤销全部；登出→撤销当前；`DELETE /auth/sessions/{id}` 属主校验。

## 4. 前端改动清单

| 文件 | 变更 |
| --- | --- |
| `src/lib/api.ts` | `withCredentials` + 401 单飞静默续期（cookie 优先）+ `_retry` 重试；`errorMessage` 识别 `{error:{message}}` envelope；新增 14 个认证函数与类型 |
| `src/lib/auth.ts` | `lr_hint`（非凭证提示 cookie，供 proxy 守卫）+ 旧 `lr_token` cookie 双 path 清理 |
| `src/proxy.ts` | 守卫改读 `lr_hint`；PROTECTED 增加 `/account`；redirect 参数透传 |
| `src/components/auth/AuthLayout.tsx` | 新增：品牌区 + max-w-md 卡片容器 + 合规 footer + 深浅色 |
| `src/components/auth/LoginForm.tsx` | 重写：统一 identifier、密码/验证码分段（login-methods 开关）、60s 倒计时、redirect 还原（防开放重定向）、a11y、埋点 |
| `src/components/auth/RegisterForm.tsx` | 重写：本地密码注册、渐进选填字段、agreed_terms 合规勾选、signup_start/success 埋点 |
| `src/components/auth/ForgotPasswordForm.tsx` | 新增：两步重置（发码→验证码+新密码）、防枚举文案、重发倒计时 |
| `src/app/(auth)/login|register/page.tsx` | 改用 AuthLayout + Suspense 边界 |
| `src/app/(auth)/forgot-password/page.tsx` | 新增 |
| `src/app/(app)/account/page.tsx` + `src/components/account/AccountCenter.tsx` | 新增：四区用户中心（资料编辑/改密码/设备下线/退出所有设备/偏好展示/套餐入口） |
| `src/components/dashboard/TopBar.tsx` | 账户菜单新增「账户设置」；登出先调后端 `/auth/logout` 清 Cookie 再清本地态 |
| `src/lib/analytics.ts` | AnalyticsEventName +10 auth 事件 |

## 5. 安全核查表（阶段9）

| # | 检查项 | 结论 | 依据 |
| --- | --- | --- | --- |
| 1 | CSRF | ✅ | refresh Cookie `SameSite=Lax` 且限 `Path=/api/v1/auth`；跨站 POST 不携带；写操作凭 Bearer/body |
| 2 | Session Fixation | ✅ | 登录/刷新一律新发 token 对，refresh 服务端轮换 + replaced_by 链 |
| 3 | XSS | ✅ | 30d refresh token HttpOnly（JS 不可读）；localStorage 仅存 1h access token；CSP nonce 机制维持既有方案 |
| 4 | 防枚举 | ✅ | forgot 恒 200；登录失败统一「账号或密码错误」；审计 identifier 经 mask_email/mask_phone 脱敏 |
| 5 | 暴力破解 | ✅（1 项 P2） | 全局 per-IP 限流 300/min（`/auth/*` 不在豁免清单）；验证码 5 次错作废 + 60s 冷却 + IP/日上限。**P2 已知项**：密码登录未接线 `locked_until` 账户锁定（字段已备） |
| 6 | 开放重定向 | ✅ | 前端 `sanitizeRedirect` 仅允许站内路径（拒绝 `//`、换行）；后端无 redirect 端点 |
| 7 | 密码存储 | ✅ | Argon2id 优先，bcrypt 历史兼容，登录成功透明 rehash |
| 8 | JWT | ✅ | HS256，access 1h / refresh 30d(jti)，服务端持久化可撤销 |
| 9 | 越权 | ✅ | 会话撤销属主校验（非属主 404）；统一 `get_current_user` JWT 鉴权（不信任 X-User-Id） |
| 10 | 凭证下发 | ✅ | 生产 Cookie `Secure`；支付/密钥类配置不受本变更影响 |

## 6. 兼容性说明

- **历史用户**：Core 注册的用户邮箱密码登录走 Strangler 回退，无需迁移；手机号仅走本地身份。
- **旧客户端**：`/auth/refresh`、`/auth/logout` 仍接受 body 传 refresh_token；未带 cookie 的请求行为不变。
- **前端旧存储**：首次加载自动清理历史 `lr_token` cookie（/ 与 /api/v1/auth 两个 path）。
- **不删数据**：本次零迁移、零数据变更，users 表仅增列使用（0003 已建）。

## 7. 部署与回滚（待用户确认后执行）

本次变更**无数据库迁移**，部署顺序：

1. 后端：`docker compose build backend` → `compose up -d backend`（健康检查 `https://legalai86.com.cn/health`）。
2. 前端：先 `rm` 服务器上被移动/删除的旧路由文件（如有），再 `docker compose build frontend` → `up -d frontend`。
3. 验收：注册→登录→刷新→改密码→其他设备下线→登出全链路；忘记密码重置；埋点事件入库抽查。

回滚：镜像回退到上一版本 tag 即可（无 schema 变更，无需数据回滚）；旧前端 + 新后端组合兼容（body refresh 兼容保留）。

## 8. 遗留与 P2 路线

- 密码登录接线 `locked_until`（连续失败锁定）——字段与重置逻辑已就位，仅差计数器写入。
- `/account` 绑定/换绑手机号、邮箱 UI（后端 `/auth/account/bind` 已就绪）。
- locale/timezone 编辑、OAuth（微信/QQ/微博/小红书 开关已预留）、Passkeys、TOTP MFA。
- `onboarding_completed` 埋点待接入 onboarding 流程。
