# LegalAI 86 ·「智审 / LegalReview」API 交付文档

> 适用分支：`upgrade/legalai86-platform`（自 `main@5886e89` 切出）
> 本文档逐条对照后端源码核实（`backend/app/api/v1/*.py`、`backend/app/api/deps.py`、
> `backend/app/main.py`、`backend/app/core/config.py`、`backend/app/services/rate_limit.py`），
> **不编造端点或响应字段**；对未实现/未接线处显式标注。

---

## 1. 约定（Conventions）

### 1.1 Base URL 与环境

| 环境 | Base URL | 说明 |
| --- | --- | --- |
| 生产（合法） | `https://legalai86.com.cn` | 唯一合法生产域名；`/health` 挂根路径返回 200（`docs/LEGALAI86_AUDIT.md`）。 |
| API 根前缀 | `${BASE}/api/v1` | 由 `backend/app/api/v1/__init__.py` 的 `api_router = APIRouter(prefix="/api/v1")` 定义。 |

> **重要**：`legal86.com.cn` **无 DNS 解析**，与 `legalai86.com.cn` **不是同一域名**，
> 本文档**不得**暗示两者等价，也不得据此刻画为已接入生产。若需启用，须由运营方单独完成
> 备案与解析（列为待办，非本次执行项，详见 `docs/LEGALAI86_AUDIT.md`）。

交互式文档：`/docs`（Swagger UI）、`/redoc`（ReDoc）、OpenAPI JSON：`/api/v1/openapi.json`
（见 `backend/app/main.py` 的 `docs_url` / `redoc_url` / `openapi_url`）。

健康检查**不进** `/api/v1` 前缀（`backend/app/main.py` 中 `health_router.router` 单独
`include_router` 挂根路径，`backend/app/api/v1/health.py` 无 prefix）：

- `GET /health` — 存活探针（不查 DB），200。
- `GET /ready` — 就绪探针（含 `SELECT 1` 探活），200。

### 1.2 鉴权（JWT）

- 用户面端点鉴权头：`Authorization: Bearer <access_token>`。
- 依赖实现：`backend/app/api/deps.py`
  - `get_current_user` → `CorePrincipal`（本地 JWT 优先，Core `/auth/me` 兜底）；
  - `get_tenant_context` → `TenantContext`（user + org + 团队/超管标记，多租户隔离）；
  - `require_role(*roles)` → 角色守卫工厂（`submitter/reviewer/supervisor/admin/librarian`）。
- **约定（硬约束）**：用户面端点必须走 JWT（`get_current_user` → `CorePrincipal`），
  **不信任** `X-User-Id` 头。`backend/app/api/deps.py` 中保留的 `get_actor`（读
  `X-User-Id` / `X-User-Role`）为历史兼容；**部分旧模块仍在使用它**，已在第 3 节逐端点
  标注「鉴权方式」并列入待办。
- Refresh Token：优先通过 HttpOnly Cookie 下发（`lr_rt`，`Path=/api/v1/auth`，
  `SameSite=Lax`，生产强制 `Secure`；见 `backend/app/api/v1/auth.py`）；
  body 传 `refresh_token` 的旧模式保留兼容。

### 1.3 统一错误响应格式

全局异常处理器（`backend/app/main.py` → `app.exception_handler(AppError)`）输出统一
envelope（`backend/app/core/errors.py` 的 `error_response`）：

```json
{ "error": { "code": "auth_error", "message": "登录已失效，请重新登录", "trace_id": "<uuid>" } }
```

错误类型与 `code`（`backend/app/core/errors.py`）：

| 异常类 | `code` | HTTP |
| --- | --- | --- |
| `AuthError` | `auth_error` | 401 |
| `NotFoundError` | `not_found` | 404 |
| `ConflictError` | `conflict` | 409 |
| `ValidationError` | `validation_error` | 422 |
| `QuotaExceededError` | `quota_exceeded` | 429 |
| `RateLimitedError` | `rate_limited` | 429 |
| `FileTypeError` / `FileTooLargeError` | `file_type_error` / `file_too_large` | 422 |
| `SandboxError` | `sandbox_error` | 500 |
| `AgentError` | `agent_error.<agent>` | 500 |

各端点亦存在**内联** `AppError`（如 `DOCUMENT_NOT_FOUND`、`REPORT_NOT_READY`、
`UNSUPPORTED_FORMAT`、`USER_HAS_NO_ORG`、`channel_disabled`、`terms_required` 等），
`code` 与 HTTP 以源码为准（见第 3 节逐条说明）。

### 1.4 状态码总览

`200` 成功；`201` 创建；`204` 无内容（如删除 Golden Case）；`400/401/403/404/409/422`
客户端错误；`429` 限流/配额；`501` 未实现（`GET /auth/quota` 冻结）；
`503` 渠道未配置（如微信支付未配置 `wxpay_disabled`）。

### 1.5 Rate Limit（限流）

- 边缘限流中间件（`backend/app/main.py` `rate_limit_middleware`，`backend/app/services/rate_limit.py`）：
  按 **IP** 固定窗口，Redis `INCR + EXPIRE`；Redis 不可用时降级为进程内计数。
  阈值：`rate_limit_enabled`（默认 `True`）、`rate_limit_per_ip_per_min`（默认 `300`/分钟，
  `backend/app/core/config.py`）。超限返回 429 + `{"error":{"code":"rate_limited",...}}`。
- **豁免名单**（`rate_limit_exempt_paths`）：`/health`、`/docs`、`/redoc`、
  `/api/v1/openapi.json`、**`/api/v1/metrics/prometheus`**（Prometheus 抓取不参与限流）。
- 业务级限流：短信/邮箱验证码等由 `VerificationService` 内部频控（超限抛 `RateLimitedError`）。

### 1.6 分页

无统一分页 envelope，各模块自定，常见两种：

- `{ "total": N, "page": P, "page_size": S, "items": [...] }`（如 tasks、notifications、user-feedback）。
- 列表直返数组 + `page`/`page_size` 查询参数（如 legal、audit、eval）。
  `page ≥ 1`，`page_size` 上限各端点不同（常见 `le=100`，audit `le=200`）。
- `search` 使用 `limit`（默认 10，`le=20`）。

---

## 2. 模块状态总览（五态）

> 五态：**真正可用** / **部分完成** / **仅有界面** / **尚未开发** / **受外部依赖阻塞**。
> 状态依据源码 + `docs/CHANGELOG_LEGALAI86.md`；仅「后端已就绪但前端未接线」记「部分完成」。

| 模块（router） | 前缀 | 状态 | 备注 |
| --- | --- | --- | --- |
| auth | `/api/v1/auth` | 真正可用 | 部分入口受渠道开关（`auth_sms_enabled` 等）约束；`GET /auth/quota` 冻洁 501。 |
| account | `/api/v1/account` | 真正可用 | 账号安全中心，全部 JWT。 |
| documents | `/api/v1/documents` | 真正可用 | 上传 + 自动建任务 + 触发解析。 |
| legal | `/api/v1/legal` | 真正可用 | 法规库导入/查询/时效/RAG/引证核验；**未走 JWT**（用 `get_actor`）。 |
| research | `/api/v1/research` | 部分完成 | 后端就绪且 JWT；前端 `/research` 仍 `comingSoon`。 |
| contract | `/api/v1/contract` | 部分完成 | 后端就绪且 JWT；前端 `/contract` 仍 `comingSoon`。 |
| gov | `/api/v1/gov` | 部分完成 | 规则包查询可用；**审核报告/导出前端页面未接线**；规则包 `legal_review_status=pending_legal_review`。 |
| tasks | `/api/v1/tasks` | 真正可用 | JWT + 租户；含本次新增 `gov-report` / `gov-export` / `report/export`。 |
| eval | `/api/v1/eval` | 真正可用 | Golden Dataset + EvalRun；**未走 JWT**（用 `get_actor`）。 |
| feedback | `/api/v1/feedback` | 部分完成 | 提交需 `X-User-Id` 头（历史约定，非 JWT）。 |
| audit | `/api/v1/audit` | 真正可用 | 审计查询；**无鉴权**（仅 `get_db`）。 |
| metrics | `/api/v1/metrics` | 真正可用 | 指标快照 + Prometheus；**无鉴权**，`/prometheus` 豁免限流。 |
| notifications | `/api/v1/notifications` | 真正可用 | JWT。 |
| search | `/api/v1/search` | 真正可用 | JWT；ILIKE 聚合搜索。 |
| user-feedback | `/api/v1/user-feedback` | 真正可用 | JWT（不信任 `X-User-Id`）。 |
| admin-user-feedback | `/api/v1/admin/user-feedback` | 部分完成 | 角色由 `X-User-Role` 头判定（**非 JWT**，与约定不符）。 |
| billing | `/api/v1/billing` | 受外部依赖阻塞 | 定价/下单/查单可用；真实收款依赖微信/支付宝商户配置（`docs/PAYMENT_SETUP.md`）。 |
| analytics | `/api/v1/analytics` | 真正可用 | 埋点可选 JWT，不采信请求体身份。 |

---

## 3. 端点总表（按 router 分组）

> 图例：**鉴权** 列 — `JWT` = `get_current_user`/`get_tenant_context`；`actor` = `get_actor`
> （读 `X-User-Id`/`X-User-Role`，非 JWT）；`无` = 未加鉴权依赖。
> **Method Path** 均为 `/api/v1` 前缀下（health 除外）；`{…}` 为路径参数。

### 3.1 auth（`backend/app/api/v1/auth.py`）

| Method | Path | 用途 | 鉴权 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- | --- |
| POST | `/auth/register` | 邮箱注册（Core provision-tenant） | 无 | body `RegisterRequest` | 201 `TokenResponse` |
| POST | `/auth/login` | 邮箱密码登录（Core） | 无 | body `LoginRequest` | `TokenResponse` |
| GET | `/auth/me` | 当前用户 | JWT | — | `UserOut` |
| POST | `/auth/register/password` | 本地邮箱密码注册 | 无 | body `PasswordRegisterRequest`（`agreed_terms=true`）；渠道开关 | 201 `VerificationLoginResponse` |
| POST | `/auth/login/password` | 统一密码登录（本地优先，Core 回退） | 无 | body `PasswordLoginRequest`（identifier=邮箱/手机） | `VerificationLoginResponse` |
| POST | `/auth/sms/send` | 发送短信验证码 | 无 | body `SmsSendRequest`；`auth_sms_enabled` | `SmsSendResponse` |
| POST | `/auth/email/send` | 发送邮箱验证码 | 无 | body `EmailSendRequest`；`auth_email_enabled` | `EmailSendResponse` |
| POST | `/auth/login/verification` | 验证码统一登录/注册 | 无 | body `VerificationLoginRequest`（channel=phone/email + code） | `VerificationLoginResponse` |
| POST | `/auth/login/phone` | 手机号+密码登录 | 无 | body `PhoneLoginRequest` | `VerificationLoginResponse` |
| POST | `/auth/refresh` | 刷新 Token（Cookie 优先） | Cookie/body | `RefreshRequest` | `TokenResponse` |
| POST | `/auth/logout` | 撤销当前 refresh token | Cookie/body | `LogoutRequest` | `{success:true}` |
| GET | `/auth/login-methods` | 登录方式开关 | 无 | — | `LoginMethodsResponse` |
| POST | `/auth/password/forgot` | 忘记密码（防枚举恒 200） | 无 | body `ForgotPasswordRequest` | `{success, message}` |
| POST | `/auth/password/reset` | 重置密码（撤销全部会话） | 无 | body `ResetPasswordRequest` | `{success, message}` |
| POST | `/auth/password/change` | 修改密码（保留当前会话） | JWT | body `ChangePasswordRequest` | `{success, revoked_other_sessions}` |
| GET | `/auth/account` | 用户中心资料 | JWT | — | `AccountProfileResponse` |
| PATCH | `/auth/account` | 更新资料（real_name/company） | JWT | body `UpdateProfileRequest` | `AccountProfileResponse` |
| POST | `/auth/account/bind` | 绑定/换绑手机或邮箱 | JWT | body `BindAccountRequest`（验证码） | `BindAccountResponse` |
| GET | `/auth/sessions` | 活跃会话列表 | JWT | — | `SessionListResponse` |
| DELETE | `/auth/sessions/{session_id}` | 撤销指定会话 | JWT | path `session_id` | `{success:true}` |
| POST | `/auth/logout-all` | 退出所有设备 | JWT | — | `{success, revoked}` |
| GET | `/auth/quota` | 配额状态 | 无 | — | **501**（冻结，`not_implemented`） |

### 3.2 account（`backend/app/api/v1/account.py`，全部 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| GET | `/account/identities` | 已绑定登录方式（脱敏） | — | `IdentitiesResponse` |
| POST | `/account/bind` | 绑定手机/邮箱（验证码 + 冲突检测） | body `BindIdentityRequest` | `BindIdentityResponse` |
| POST | `/account/unbind` | 解绑（禁解绑最后一种方式） | body `UnbindIdentityRequest` | `UnbindIdentityResponse` |
| GET | `/account/sessions` | 我的活跃会话 | — | `SessionListResponse` |
| POST | `/account/sessions/logout-all` | 退出其他所有会话 | — | `{success, revoked}` |

### 3.3 documents（`backend/app/api/v1/documents.py`）

| Method | Path | 用途 | 鉴权 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- | --- |
| POST | `/documents/upload` | 上传送审文件→建任务→触发解析 | JWT | `file`(multipart, ≤50MB, docx/pdf/png/jpg/jpeg/txt)；头 `X-Task-Title`、`X-Priority`；配额 | 201 `DocumentUploadResponse` |

失败：空文件 `400`；文件类型/大小 `file_type_error`/`file_too_large`(422)；
配额超限 `quota_exceeded`(429)；未挂靠组织 `USER_HAS_NO_ORG`(400)。

### 3.4 legal（`backend/app/api/v1/legal.py`；鉴权为 `get_actor`，非 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| POST | `/legal/import` | 批量导入法规（切分+embedding） | body `LegalLibraryImportRequest` | 200 `LegalLibraryImportResponse` |
| POST | `/legal/laws` | 导入单部法规 | body `LegalDocumentCreate` | 201 `LegalDocumentRead` |
| GET | `/legal/laws` | 法规列表 | Query `law_type`/`law_level`/`status`/`keyword`/`page`/`page_size`(≤100) | `list[LegalDocumentRead]` |
| GET | `/legal/laws/{law_id}` | 法规详情（含条款数） | path `law_id` | `LegalDocumentRead` |
| GET | `/legal/laws/{law_id}/validity` | 法规时效性检查 | path `law_id` | `LawTimeValidity` |
| POST | `/legal/laws/{law_id}/status` | 状态变更（可建修订链） | Query `new_status`、`replaced_by_law_id` | `LegalDocumentRead` |
| POST | `/legal/search` | RAG 混合检索 | body `RAGSearchRequest` | `RAGSearchResponse` |
| POST | `/legal/citations/verify` | 单条法律依据核验 | body `CitationClaim` | `CitationVerificationResult` |
| POST | `/legal/citations/verify-batch` | 批量核验 | body `CitationBatchRequest` | `CitationBatchResponse` |

### 3.5 research（`backend/app/api/v1/research.py`，全部 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| POST | `/research/sessions` | 执行一次法律研究（结构化 8 段 + 引证核验） | body `ResearchRequest` | 201 `ResearchSessionRead` |
| GET | `/research/sessions` | 研究会话列表 | Query `page`/`page_size`(≤100) | `ResearchSessionListResponse` |
| GET | `/research/sessions/{session_id}` | 会话详情 | path `session_id` | `ResearchSessionRead` |

### 3.6 contract（`backend/app/api/v1/contract.py`，全部 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| POST | `/contract/reviews` | 上传合同文件并审查 | `file`(multipart, ≤50MB, docx/pdf/txt)；Form `stance`/`contract_type`/`project_id` | 201 `ContractReviewRead` |
| POST | `/contract/reviews/text` | 纯文本合同审查 | body `ContractReviewRequest` | 201 `ContractReviewRead` |
| GET | `/contract/reviews` | 合同审查列表 | Query `page`/`page_size`(≤100) | `ContractReviewListResponse` |
| GET | `/contract/reviews/{review_id}` | 审查详情（findings+redline+依据核验） | path `review_id` | `ContractReviewRead` |

失败：扫描版 PDF `OCR_REQUIRED`(422)；类型/大小 `file_type_error`/`file_too_large`(422)。

### 3.7 gov（`backend/app/api/v1/gov.py`，全部 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| GET | `/gov/rule-packs` | 列出全部审核规则包 | — | `list[GovRulePackRead]` |
| GET | `/gov/rule-packs/resolve` | 按地区解析适用规则包 | Query `region`（如 `上海市徐汇区`；缺省仅国家通用） | `list[GovRulePackRead]` |
| GET | `/gov/rule-packs/{pack_id}` | 单个规则包详情（含全部规则） | path `pack_id` | `GovRulePackRead` |

已内置规则包（`backend/app/gov_rules/registry.yaml`）：`national_general`（国家通用，scope=national）、
`shanghai`（上海市，municipality）、`xuhui`（徐汇区，district）。选择逻辑：
国家通用恒选 + 地方包 `region` 为 region 子串时命中（`resolve_for_region`）。

### 3.8 tasks（`backend/app/api/v1/tasks.py`，JWT + 租户 `get_tenant_context`）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| GET | `/tasks` | 任务列表（多租户过滤） | Query `page`(≥1)/`page_size`(≤100)/`status` | `TaskListResponse` |
| GET | `/tasks/{task_id}` | 任务详情 | path `task_id` | `TaskRead` |
| GET | `/tasks/{task_id}/status` | 状态与进度 | path `task_id` | `TaskStatusResponse` |
| GET | `/tasks/{task_id}/documents` | 任务下文件列表 | path `task_id` | `list[DocumentRead]` |
| GET | `/tasks/{task_id}/documents/{document_id}` | 单文件（含 `parsed_json`） | path 双参 | `DocumentRead` |
| GET | `/tasks/{task_id}/report` | 最终报告（markdown+risks+evidences） | path `task_id` | `dict` |
| GET | **`/tasks/{task_id}/report/export`** | **导出审查意见书 DOCX（本次新增）** | Query `format`(仅 `docx`)、`filename` | DOCX 附件流 |
| GET | **`/tasks/{task_id}/gov-report`** | **规范性文件合法性审核报告，10 段（本次新增）** | Query `region` | `GovReviewReport` |
| GET | **`/tasks/{task_id}/gov-export`** | **导出交付物：意见书/报告/条款清单（本次新增）** | Query `format`(`docx`\|`pdf`\|`xlsx`)、`region`、`filename` | 附件流（DOCX/PDF/XLSX） |

- 租户可见性（`_load_task`）：`supervisor`/`admin` 看全部；团队组织看同 `organization_id`；
  personal 组织仅看 `submitter_id` 自己的；`super_admin` 跨租户。不可见时按
  `NotFoundError`(404) 处理（不泄露存在性）。
- `/report` 与 `/report/export` 依赖 `report_generation` 节点的 `ReviewResult`；
  未生成时 `REPORT_NOT_READY`(404)。`report` 返回字段：
  `task_id`、`status`、`report_markdown`、`risks`、`evidences`。
- `/report/export` 非 `docx` → `UNSUPPORTED_FORMAT`(422)；文件名为
  `filename`/任务标题 + `.docx`（RFC 5987 `filename*` 支持中文）。
- `/gov-export` 仅接受 `docx`/`pdf`/`xlsx`（`backend/app/services/gov_export.py` 的
  `EXPORT_FORMATS`），否则 `UNSUPPORTED_FORMAT`(422)；默认文件名分别为
  「规范性文件合法性审核意见书」/「规范性文件审核报告」/「条款问题清单」。

### 3.9 eval（`backend/app/api/v1/eval.py`；鉴权为 `get_actor`，非 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| POST | `/eval/golden/cases` | 新增单条 Golden Case | body `GoldenCaseCreate` | 201 `GoldenCaseRead` |
| POST | `/eval/golden/import` | 批量导入（容错） | body `GoldenBatchImportRequest` | 200 `GoldenBatchImportResponse` |
| GET | `/eval/golden/cases` | 列表 | Query `category` | `list[GoldenCaseRead]` |
| GET | `/eval/golden/cases/{case_id}` | 单条 | path `case_id` | `GoldenCaseRead` |
| DELETE | `/eval/golden/cases/{case_id}` | 删除 | path `case_id` | 204 |
| GET | `/eval/golden/count` | 总数 | — | `{total}` |
| POST | `/eval/runs` | 触发评测运行（6 指标 + overall_pass） | body `EvalRunCreate` | 201 `EvalRunRead` |
| GET | `/eval/runs` | 运行历史 | Query `limit`(≤100) | `list[EvalRunRead]` |
| GET | `/eval/runs/{run_id}` | 单次运行 | path `run_id` | `EvalRunRead` |

### 3.10 feedback（`backend/app/api/v1/feedback.py`；`get_actor`，非 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| POST | `/feedback/tasks/{task_id}` | 提交人工反馈 | path `task_id`；body `FeedbackCreate`；**需 `X-User-Id`** | 201 `FeedbackRead` |
| GET | `/feedback/tasks/{task_id}` | 任务全部反馈 | path `task_id` | `list[FeedbackRead]` |
| GET | `/feedback/unincorporated` | 未吸收反馈（待优化） | Query `limit`(≤500) | `list[FeedbackRead]` |
| GET | `/feedback/batch-review` | 周期 Batch 复盘 | — | `FeedbackBatchReviewResponse` |
| POST | `/feedback/cases/{case_id}/incorporate` | 标记已吸收 | path `case_id`；Query `prompt_version_after` | 200 `FeedbackRead` |

缺少 `X-User-Id` 时 `POST /feedback/tasks/{task_id}` 报 `validation_error`(422)。

### 3.11 audit（`backend/app/api/v1/audit.py`；**无鉴权**，仅 `get_db`）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| GET | `/audit/records` | 审计日志查询 | Query `trace_id`/`action`/`target_type`/`actor_id`/`start_time`/`end_time`/`page`/`page_size`(≤200) | `list[AuditRecordRead]` |
| GET | `/audit/trace/{trace_id}` | 按 trace 全链路 | path `trace_id` | `list[AuditRecordRead]` |
| GET | `/audit/records/{record_id}` | 单条记录 | path `record_id` | `AuditRecordRead` |
| GET | `/audit/count` | 总数 | — | `{total}` |

### 3.12 metrics（`backend/app/api/v1/metrics.py`；**无鉴权**）

| Method | Path | 用途 | 返回 |
| --- | --- | --- | --- |
| GET | `/metrics` | 指标快照 | JSON `dict` |
| GET | `/metrics/nodes` | 节点级指标 | JSON `dict` |
| GET | `/metrics/prometheus` | Prometheus 文本（**限流豁免**） | `text/plain; version=0.0.4` |
| POST | `/metrics/reset` | 重置采集器（测试/排障） | `{status:"ok"}` |

> `POST /metrics/reset` 源码注释要求「生产需管理员鉴权后调用」，当前**未加鉴权**，属待办。

### 3.13 notifications（`backend/app/api/v1/notifications.py`，全部 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| GET | `/notifications` | 通知列表（分页 + 未读数） | Query `page`/`page_size`(≤100)/`only_unread` | `NotificationListResponse` |
| GET | `/notifications/unread-count` | 仅未读数（30s 轮询） | — | `NotificationUnreadCount` |
| POST | `/notifications/{notif_id}/read` | 标记单条已读 | path `notif_id` | 200 `NotificationRead` |
| POST | `/notifications/read-all` | 全部已读 | — | `NotificationUnreadCount` |

### 3.14 search（`backend/app/api/v1/search.py`，JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| GET | `/search` | ⌘K 全局搜索（tasks/documents/reports） | Query `q`(≤64)/`limit`(≤20) | `SearchResponse` |

### 3.15 user-feedback（`backend/app/api/v1/user_feedback.py`，全部 JWT）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| POST | `/user-feedback` | 提交用户反馈 | body `UserFeedbackCreate` | 201 `UserFeedbackRead` |
| GET | `/user-feedback/summary` | 本人反馈概览 | — | `UserFeedbackSummary` |
| GET | `/user-feedback` | 本人反馈列表 | Query `status`/`target_kind`/`page`/`page_size`(≤100) | `UserFeedbackListResponse` |
| GET | `/user-feedback/{feedback_id}` | 单条详情（仅本人） | path `feedback_id` | `UserFeedbackRead` |
| PATCH | `/user-feedback/{feedback_id}` | 用户关闭（已读） | path；body `UserFeedbackUpdate` | `UserFeedbackRead` |

### 3.16 admin-user-feedback（`backend/app/api/v1/admin_user_feedback.py`；`get_actor` + `X-User-Role` 角色校验）

| Method | Path | 用途 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- |
| GET | `/admin/user-feedback` | 全量分页查询 | Query `status`/`target_kind`/`page`/`page_size`(≤200) | `UserFeedbackListResponse` |
| GET | `/admin/user-feedback/summary` | 概览统计 | — | JSON `dict` |
| PATCH | `/admin/user-feedback/{feedback_id}` | 更新 `status`/`admin_reply` | path；body `AdminFeedbackUpdate` | `UserFeedbackRead` |

角色仅 `admin`/`supervisor` 可访问（`_require_admin`），否则 `AuthError`(401)。

### 3.17 billing（`backend/app/api/v1/billing.py`）

| Method | Path | 用途 | 鉴权 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- | --- |
| GET | `/billing/pricing` | 套餐定价 | 无 | — | `list[PricingItem]` |
| POST | `/billing/orders` | 创建支付订单 | JWT | body `CreateOrderRequest` | `CreateOrderResponse` |
| GET | `/billing/orders/{order_id}` | 查询订单（主动查单补偿/超时关单） | JWT | path `order_id` | `OrderStatusResponse` |
| POST | `/billing/orders/{order_id}/refund` | 申请退款（本人/管理员） | JWT | path；body `RefundRequest` | `RefundResponse` |
| POST | `/billing/wechat/notify` | 微信支付回调（幂等） | 无（验签） | 原始 body | `{code,message}` |
| POST | `/billing/alipay/notify` | 支付宝异步通知 | 无（验签） | form-data | `"success"\|"fail"` |
| GET | `/billing/orders` | 当前用户订单列表 | JWT | Query `limit` | `list[dict]` |
| GET | `/billing/wechat/oauth/url` | 微信 JSAPI 静默授权地址 | JWT | Query `state` | `{url}` |
| GET | `/billing/wechat/oauth/callback` | 微信 OAuth 回调（换 openid 后回跳） | 无 | Query `code`/`state` | 302 重定向 |

未配置微信支付时：`wechat_notify` 返回 `{code:"FAIL"}`；`oauth/url` 抛 `wxpay_disabled`(503)。

### 3.18 analytics（`backend/app/api/v1/analytics.py`）

| Method | Path | 用途 | 鉴权 | 关键参数 | 返回 |
| --- | --- | --- | --- | --- | --- |
| POST | `/analytics/events` | 接收埋点（单条或批量 ≤50） | 可选 JWT | body `AnalyticsEventIn` 或 `AnalyticsBatchIn`（事件白名单） | `{accepted}` |

`user_id` 仅从 Bearer JWT 解析，**绝不采信请求体身份字段**；不落 IP 原文（仅 sha256 截断）。

---

## 4. 关键端点示例

### 4.1 上传送审文件

```bash
curl -X POST "https://legalai86.com.cn/api/v1/documents/upload" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-Task-Title: 上海市某规范性文件合法性审查" \
  -H "X-Priority: normal" \
  -F "file=@./送审文件.docx"
```

201 响应（`DocumentUploadResponse`，见 `backend/app/schemas/document.py`）：

```json
{
  "task_id": "…uuid…",
  "trace_id": "…uuid…",
  "document_id": "…uuid…",
  "original_name": "送审文件.docx",
  "file_type": "docx",
  "file_size": 123456,
  "file_hash": "…sha256…",
  "storage_path": "…沙箱相对路径…",
  "parse_status": "parsing",
  "status": "parsing"
}
```

### 4.2 查询任务状态

```bash
curl "https://legalai86.com.cn/api/v1/tasks/$TASK_ID/status" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`TaskStatusResponse`：`task_id`、`trace_id`、`status`、`current_node`、`progress`(0.0~1.0)、
`iteration`、`max_iteration`（`estimated_remaining_sec` 可选，源码未赋值）。

### 4.3 取最终报告（markdown）

```bash
curl "https://legalai86.com.cn/api/v1/tasks/$TASK_ID/report" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

返回：`{task_id, status, report_markdown, risks, evidences}`；未到 `report_generation`
节点 → 404 `REPORT_NOT_READY`。

### 4.4 导出审查意见书 DOCX（本次新增）

```bash
curl -OJ "https://legalai86.com.cn/api/v1/tasks/$TASK_ID/report/export?format=docx&filename=审查意见书" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

非 `docx` → 422 `UNSUPPORTED_FORMAT`；响应带 `Content-Disposition: attachment; filename*=UTF-8''…`。

### 4.5 取规范性文件合法性审核报告（10 段，本次新增）

```bash
curl "https://legalai86.com.cn/api/v1/tasks/$TASK_ID/gov-report?region=上海市徐汇区" \
  -H "Authorization: Bearer $ACCESS_TOKEN"
```

`GovReviewReport`（`backend/app/schemas/gov_review.py`）关键字段：
`task_id`、`generated_at`、`region`、`conclusion`(+`conclusion_label`)、`overall_risk`、
`risk_counts`、`findings_count`、`pack_ids`、`pack_review_status`、`disclaimer`，
以及固定 10 段：`basic_info` / `review_scope` / `review_basis` / `findings` /
`clause_locations` / `risk_levels` / `suggestions` / `missing_materials` /
`pending_human_review` / `opinion_draft`。
审核维度 A~J、风险 5 档、结论 4 类（`GovReviewConclusion`）；
报告中恒附免责声明（AI 辅助结果，非法定正式结论）。
`region` 缺省时取任务元数据 `metadata_.region`；规则包解析见 `GET /gov/rule-packs/resolve`。

### 4.6 导出规范性文件审核交付物（本次新增）

```bash
# 意见书 DOCX
curl -OJ "…/api/v1/tasks/$TASK_ID/gov-export?format=docx&region=上海市徐汇区" -H "Authorization: Bearer $TOKEN"
# 审核报告 PDF
curl -OJ "…/api/v1/tasks/$TASK_ID/gov-export?format=pdf&region=上海市徐汇区"  -H "Authorization: Bearer $TOKEN"
# 条款问题清单 XLSX
curl -OJ "…/api/v1/tasks/$TASK_ID/gov-export?format=xlsx&region=上海市徐汇区" -H "Authorization: Bearer $TOKEN"
```

支持格式由 `backend/app/services/gov_export.py` 的 `EXPORT_FORMATS = ("docx","pdf","xlsx")`
限定；PDF 走 weasyprint（CJK 字体回退），XLSX 走 openpyxl（两表：条款问题清单 + 材料缺失清单）。

---

## 5. API 变更（本次升级 `upgrade/legalai86-platform` 新增/修改）

对照 `git diff origin/main...HEAD`（`backend/app/api/v1`）：

**新增端点**

- `GET /gov/rule-packs`、`GET /gov/rule-packs/resolve`、`GET /gov/rule-packs/{pack_id}`
  （新增文件 `backend/app/api/v1/gov.py`，随 `api_router` 在 `metrics` 前后顺序注册）。
- `GET /tasks/{task_id}/gov-report`（`GovReviewReport`）。
- `GET /tasks/{task_id}/gov-export`（`docx`/`pdf`/`xlsx`）。
- `GET /tasks/{task_id}/report/export`（通用审查意见书 DOCX，复用 `report_export`）。

**新增后端支撑（非端点，但属本次交付）**

- `backend/app/services/gov_rules.py`（规则包管理 `GovRulePackManager`）+
  `backend/app/gov_rules/{registry,national,shanghai,xuhui}.yaml`。
- `backend/app/services/gov_review_report.py`（确定性、**不调 LLM**，组装 10 段报告）。
- `backend/app/services/gov_export.py`（DOCX/PDF/XLSX 渲染）。
- `backend/app/schemas/gov_review.py`（A~J 维度、5 档风险、4 类结论、10 段模型 + 免责声明）。
- `backend/app/api/v1/research.py`、`contract.py`（PHASE 1-3/1-4 新增模块路由）。
- `backend/app/core/constants.py` 新增枚举：`GovReviewDimension`、`GovRiskLevel`、
  `GovReviewConclusion`、`GovRuleReviewStatus`、`ProjectType`、`ReviewStance`、
  `ContractRiskLevel`、`ResearchStatus`、`LegalSourceType`、`SourceAuthorizationStatus` 等。

**未改动的既有契约**：`auth`、`account`、`documents`、`tasks`（除新增 3 条）、`eval`、
`feedback`、`audit`、`metrics`、`notifications`、`search`、`user-feedback`、
`admin_user_feedback`、`billing`、`analytics` 端点路径与响应模型保持稳定（`include_router`
顺序见 `backend/app/api/v1/__init__.py`）。

**硬约束遵守**：本次升级**未删除/弱化既有 LangGraph 11 节点工作流**，
**未修改任何既有 Prompt**，gov 增强以确定性数据层叠加（见 `docs/CHANGELOG_LEGALAI86.md`）。

---

## 6. 未完成与待办（含前端未接线端点）

1. **前端未接线（后端已就绪）**
   - `GET /tasks/{id}/gov-report`、`GET /tasks/{id}/gov-export`：前端页面**未接线**
     （`docs/CHANGELOG_LEGALAI86.md` 「未完成项」）。
   - `GET /research/sessions*`、`POST /contract/reviews*`：后端就绪，前端 `/research`、
     `/contract` 仍标 `comingSoon`（`frontend/src/lib/nav.ts`）。
   - `GET /legal/*`、`GET /eval/*`、`GET|POST /feedback/*`：后端可用，前端未逐一接线（同上）。

2. **前端已引用但后端未实现的端点**
   - `GET /api/v1/tasks/{id}/stream`（SSE）：`frontend/src/lib/sse.ts` 引用，源码注释明确
     「后端目前未提供 SSE 端点（由 `/api/v1/tasks/{id}/status` 轮询兜底）」。
     **当前未实现**，前端已降级为轮询。

3. **鉴权约定偏离（用户面应走 JWT，实际仍用头/无鉴权）**
   - 仍用 `get_actor`（`X-User-Id`/`X-User-Role`）：`legal`、`eval`、`feedback`、
     `admin_user_feedback`。
   - 无鉴权：`audit`、`metrics`（含 `POST /metrics/reset`）。
   - 建议后续统一收敛到 `get_current_user`；在收敛前，这些端点在网关状态可被直连，
     须以网络层（Nginx/内网）限制访问。

4. **功能冻结/外部依赖**
   - `GET /auth/quota`：冻结（501 `not_implemented`），待包月/配额模块接入。
   - 规则包：`legal_review_status = pending_legal_review`、`law_basis_article`/`effective_date`
     待逐条核实并**送法律专业人员审核**后方可上线（`backend/app/gov_rules/registry.yaml`）。
   - `billing`：真实收款依赖微信/支付宝商户号与回调域名配置（`docs/PAYMENT_SETUP.md`）。

5. **域名/合规待办**
   - `legal86.com.cn` 无 DNS 解析、**与 `legalai86.com.cn` 非同一域名**；未做任何
     DNS/备案/绑定变更，须由运营方单独完成后方可接入（`docs/LEGALAI86_AUDIT.md`）。

6. **技术债**
   - CI 缺前端 typecheck/lint 与 E2E；`analytics_events` 等历史索引漂移待单独迁移清理
     （`docs/CHANGELOG_LEGALAI86.md`）。
