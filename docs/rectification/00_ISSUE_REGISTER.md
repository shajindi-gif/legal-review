# 整改台账（Issue Register）

> 基线日 2026-10-17 · 依据：docs/auth-upgrade/01_IMPLEMENTATION_REPORT.md（最近一次完整验收报告）+ docs/commercialization/01_PRODUCT_AUDIT.md + 08_IMPLEMENTATION_REPORT.md
> 原则：每条问题必须有**代码证据**，不转抄文档结论。修复必须由测试证明，不以「代码已改」为完成标准。

## 1. 整改前基线（实测）

| 门禁 | 实测值 | 复现命令 |
| --- | --- | --- |
| 后端 pytest | **445 passed, 27 skipped, 0 failed** | `cd backend && .venv/bin/python -m pytest -q` |
| 后端覆盖率 | 73%（app 全量） | 同上（pytest addopts 含 --cov） |
| 前端 tsc | 0 错误 | `cd frontend && npx tsc --noEmit` |
| 前端 build | 成功，20 条路由 | `cd frontend && npx next build` |
| 生产站 | 未验证（访问生产需授权） | — |

环境修复记录：`backend/.venv` 原为空壳（仅 pip/setuptools），已补齐 curated 依赖（跳过 paddleocr/paddlepaddle/weasyprint —— 代码中为函数内延迟导入，不影响测试）。
`frontend/package.json` 无 typecheck/lint/test 脚本，门禁以 `npx tsc --noEmit` + `npx next build` 手动执行。

## 2. 未修复问题（整改对象）

### P0 —— 阻断真实用户闭环 / 收费能力

| ID | 问题 | 代码证据 | 业务影响 | 状态 |
| --- | --- | --- | --- | --- |
| R1-1 | 报告无导出（无 docx/pdf/打印入口） | `backend/app/api/v1/tasks.py` 仅 `GET /{task_id}/report` 返回 JSON；前端仅 ReportViewer 的 Markdown 下载，无可归档交付物 | 用户拿不到可归档交付物 → 「完整使用产品」不成立，续费动机缺失 | **已修复**：新增 `GET /tasks/{id}/report/export`（docx）+ 前端「导出 Word」按钮；`tests/test_report_export.py` 8 passed |
| R1-2 | 额度耗尽无升级引导（UpgradeDialog 组件不存在） | `upgrade_dialog_view`/`upgrade_click`/`quota_exhausted` 在 `analytics.py` 白名单内，全仓零上报点 | 付费转化断层，直接压低收入 | **已修复**：`UpgradeDialog` 挂到唯一「开始任务」入口 `NewReviewForm`，429/`quota_exceeded` 时上报并弹层 |
| R1-3 | `task_completed` 服务端埋点缺失 | 全仓仅 `payment/service.py:284` 写 AnalyticsEvent（order_paid） | 激活率不可测 → 无法证明收费能力 | **已修复**：`services/analytics_sink.py` + 工作流收尾写入（仅 `report_generation` 完成才计） |
| R1-4 | 合规字段空缺（统一社会信用代码/办公地址/公安备案号/政策生效日） | `frontend/src/lib/site.ts:11,12,16,23` 为空 | 页脚、协议、开票落款仍占位 | **阻塞：需运营方提供数据，代码无法代填** |

### P1 —— 影响核心业务 / 留存 / 获客

| ID | 问题 | 代码证据 | 状态 |
| --- | --- | --- | --- |
| R2-1 | 账户锁定未接线：`failed_login_count` 从不递增、`locked_until` 从不写入 | `auth_service.py:655` 仅成功时清零 | **已修复**：失败累加 + 达阈值锁定 + 锁定期间拒绝正确密码 |
| R2-2 | 多租户隔离仅覆盖 tasks + documents，notifications/feedback 未接入 | `services/tenant.py` | **已修复**：notification / user_feedback 写入 organization_id，管理端按组织过滤 |
| R2-3 | SEO 基建为 0：无 sitemap.xml / robots.txt / 解决方案落地页 | `frontend/src/app` 无对应文件（`proxy.ts:75` 已预留豁免） | **已修复**：`app/sitemap.ts` + `app/robots.ts` + `/solutions/sifaju` |
| R2-4 | 首页 `page_view` 埋点缺失 | 无调用点 | **已修复**：`PageViewTracker` 挂载首页与方案页 |
| R2-5 | 定价页无对比表 / 折算月价 | 待改 | **已修复**：套餐能力对比表 + 季付/年付折算月价 |
| R2-6 | `/account` 无绑定/换绑手机号、邮箱 UI（后端 `/auth/account/bind` 已就绪） | 待改 | **本轮不做（非阻断）** |

### 已确认修复、无需返工（验收复核结论）

/pricing 公开化（`frontend/src/app/pricing/page.tsx` 已移出 (app) 组）· 额度文案对齐后端 `FREE_TRIAL_LIMIT=2` · 过时支付横幅已删 · 注册页协议勾选 · ICP 落款已填（沪ICP备2026045851号-4）· 首页 FAQ 已加 · 埋点最小集 14 事件已上线。

### 本轮明确不做（与 MVP 无关或依赖资质）

微信支付（需商户资质）· OAuth/Passkeys/TOTP（P2 预留）· Alertmanager · 全站暗色 · 首页案例区（无真实客户，做假案例违反诚实红线）。

## 3. 整改计划（最小开发成本）

| Sprint | 内容 | 交付门禁 |
| --- | --- | --- |
| R1（P0） | R1-1 报告 docx 导出（后端端点 + 前端下载入口）<br>R1-2 UpgradeDialog 额度耗尽引导<br>R1-3 埋点补全：前端 `quota_exhausted`/`upgrade_dialog_view`/`upgrade_click`/`page_view`，后端 `task_completed` | 新增测试全绿 + 全量回归无退化 |
| R2（P1） | R2-1 账户锁定接线（`failed_login_count`+`locked_until`）<br>R2-2 notifications/feedback 多租户隔离<br>R2-3 SEO：sitemap.xml + robots.txt + `/solutions/sifaju`<br>R2-4/R2-5 首页 page_view + 定价页对比表 | 同上 + build 成功 |
| R3 | 重跑原始验收测试（后端全量 pytest + tsc + build + e2e 链路），对比指标 | 出具对比报告 |

## 4. 约束与授权边界

- **生产部署**：R1/R2 整改完成后，用户已显式授权部署到 `legalai86.com.cn`（2026-10-21）；仍不得改动 DNS / 备案 / 域名绑定，不得变更生产支付配置。
- **数据库迁移**：如涉及，必须先提供 downgrade 回滚方案并单独说明。
- **不破坏既有功能**：每个 Sprint 结束跑全量回归，对比基线 445 passed 无退化。

## 5. 整改执行结果（逐任务，含测试证据）

### R1-1 报告 Word(docx) 导出 —— ✅ 已修复

改动：
- 新增 `backend/app/services/report_export.py`：`markdown_to_docx()` 纯本地 Markdown→docx 转换（标题/加粗/列表/表格/代码块/引用）。
- `backend/app/api/v1/tasks.py`：抽出 `_load_report()` 复用；新增 `GET /tasks/{task_id}/report/export?format=docx&filename=` 端点，复用 `_load_task` 鉴权与多租户可见性，返回 `StreamingResponse`（RFC 5987 中文文件名）。
- `frontend/src/lib/api.ts`：新增 `fetchReportDocx(taskId, filename)`。
- `frontend/src/components/review/ReportViewer.tsx`：新增「导出 Word」按钮（保留原 Markdown 导出）。
- `frontend/src/app/(app)/report/[id]/page.tsx`：传入 `taskId`。

测试证据（新增 `backend/tests/test_report_export.py`，8 passed）：
| 用例 | 断言 | 结果 |
| --- | --- | --- |
| markdown_to_docx_returns_valid_docx | PK 签名 + python-docx 可重开 + 标题/正文可还原 | ✅ |
| markdown_to_docx_preserves_bold | `**加粗**` → bold run | ✅ |
| markdown_to_docx_renders_table | 管道表格 → Word 表格（表头加粗） | ✅ |
| markdown_to_docx_empty_markdown | 空输入不报错，含标题 | ✅ |
| export_endpoint_returns_docx | 200 + docx Content-Type + attachment header + PK | ✅ |
| export_endpoint_custom_filename | `filename` 生效，UTF-8 编码写入 header | ✅ |
| export_endpoint_report_not_ready_404 | 报告缺失 → 404 | ✅ |
| export_endpoint_invalid_format_422 | `format=pdf` → 422 | ✅ |

回归门禁（R1-1 完成后）：
- 后端全量：`453 passed, 27 skipped, 0 failed`（基线 445 passed → +8 新增，无退化）
- 前端：`npx tsc --noEmit` 0 错误；`npx next build` 成功（20 条路由不变）

### R1-2 额度耗尽升级引导 —— ✅ 已修复

改动：
- `frontend/src/lib/api.ts`：`createReview()` 抛出携带 `code` / `status` 的 Error（此前只保留文案，前端无法识别 429）。
- `frontend/src/components/review/NewReviewForm.tsx`：捕获 `quota_exceeded` / 429 → `track("quota_exhausted", {source:"upload"})` + 打开 `UpgradeDialog`（弹层打开上报 `upgrade_dialog_view`，点击 CTA 上报 `upgrade_click` 后跳 `/pricing`）。
- 该组件是 `/upload`、`/documents`、⌘N 复用的唯一「开始任务」入口，因此漏斗起点覆盖全部主路径。

### R1-3 task_completed 服务端埋点 —— ✅ 已修复

改动：
- `backend/app/services/analytics_sink.py`：`build_task_completed_event()` 仅当 `report_generation` 在已完成节点集合中才返回事件（未产出报告不计入激活）。
- `backend/app/agent/nodes.py`：工作流成功收尾后，用独立 session 写入事件；写入失败仅 `warning` 日志，不影响任务状态。

测试证据（`tests/test_lockout_and_analytics.py`）：
| 用例 | 断言 | 结果 |
| --- | --- | --- |
| task_completed_event_requires_report_generation | 无 `report_generation` → None | ✅ |
| task_completed_event_properties | event=task_completed、task_id 字符串化、nodes_completed=2、human_review=True | ✅ |

### R2-1 账户锁定接线 —— ✅ 已修复

改动：
- `backend/app/core/constants.py`：`MAX_FAILED_LOGIN_ATTEMPTS=5`、`FAILED_LOGIN_LOCKOUT_MINUTES=15`。
- `backend/app/services/auth_service.py`：`authenticate_by_identifier()` 在密码校验前检查 `locked_until`（`_as_utc` 兼容 naive datetime）；密码错误调用 `_register_failed_login()` 累加计数，达阈值写入锁定到期时间；登录成功清零计数与锁定；落库失败 best-effort 不影响对外响应。

测试证据（`tests/test_lockout_and_analytics.py`，5 个用例全绿）：失败累加、达阈值锁定、锁定期间正确密码亦拒绝、锁定到期后成功并清零、flush 异常不改变错误文案。

### R2-2 notifications / feedback 多租户隔离 —— ✅ 已修复（含线上真实 Bug）

关键发现：迁移 0006 将 `notifications.organization_id` 设为 `NOT NULL`，但 `NotificationService.create()` 从未写入该列 → 每次插入都违反约束，被 notifier 的 try/except 静默回滚，**线上通知中心实际一直为空**。`user_feedback` 同病（提交反馈会 500）。

改动：
- `services/notification.py`：`create()` 新增 `organization_id` 参数；未显式传入时按收件人 `User.organization_id` 推导。
- `services/notifier.py` + `agent/nodes.py`：节点通知透传任务所属组织。
- `services/user_feedback.py` + `api/v1/user_feedback.py`：提交时写入组织；`list_for_admin()` / `summary()` 支持组织过滤。
- `api/v1/admin_user_feedback.py`：admin / super_admin 全量，其余（supervisor）限本组织。

测试证据：`notification_create_derives_organization_id`、`notification_create_prefers_explicit_organization_id` 全绿。

### R2-3 SEO 基建 —— ✅ 已修复

- `frontend/src/app/sitemap.ts`：公开页（/、/pricing、/solutions/sifaju、/privacy、/terms、/cookies）。
- `frontend/src/app/robots.ts`：放行公开页，屏蔽 /api、/dashboard、/review、/admin 等登录后路径，并声明 sitemap 地址。
- `frontend/src/app/solutions/sifaju/page.tsx`：司法局规范性文件合法性审核方案落地页（含 metadata/canonical/OG、三查能力、地域分层规则包、四类判定口径、FAQ、CTA）。`proxy.ts` matcher 已排除 sitemap.xml / robots.txt，未被登录守卫拦截。

### R2-4 / R2-5 埋点与定价页 —— ✅ 已修复

- `PageViewTracker` 挂载首页（`page="home"`）与方案页（`page="solutions/sifaju"`），每次挂载上报一次 `page_view`。
- 定价页新增套餐能力对比表（7 项），季付/年付显示折算月价；对比表只列产品真实具备能力，未编造指标。

### 安全偏差整改（鉴权）—— ✅ 已修复

代码证据：`api/v1/feedback.py`、`eval.py`、`legal.py`、`admin_user_feedback.py` 此前通过 `get_actor` 读取 `X-User-Id` / `X-User-Role` 请求头自报身份。

改动：
- 四个模块全部改为 `Depends(get_current_user)`（管理端用 `require_role("admin","supervisor")`），actor 取 JWT 主体的 `id` / `role`，IP 取 `deps.client_ip(request)`。
- `frontend/src/lib/api.ts`：删除请求拦截器里的 `X-User-Id` / `X-User-Role` 注入。
- 测试同步改写：`test_feedback_api.py` / `test_eval_api.py` / `test_legal_api.py` 由 override `get_actor` 改为 override `get_current_user` 并注入 `CorePrincipal`；新增「带 X-User-Id 但无 JWT → 401」用例。

### 前端 SSE 假端点移除 —— ✅ 已修复

代码证据：`frontend/src/lib/sse.ts` 指向 `GET /api/v1/tasks/{id}/stream`，后端全仓无该端点 → 每次进入审查页都显示「实时连接中断」错误横幅。

处理：删除 `sse.ts`，审查页移除 SSE 订阅与仅由 SSE 填充的「修改建议」面板；进度继续由 `/tasks/{id}/status` 3 秒轮询驱动（该轮询原本即存在）。

### 回归门禁（本轮全部整改完成后）

| 门禁 | 实测 | 命令 |
| --- | --- | --- |
| ruff | All checks passed | `.venv/bin/python -m ruff check app tests` |
| mypy（项目配置，111 文件） | Success: no issues found | `.venv/bin/python -m mypy app` |
| pytest | **551 passed, 27 skipped, 0 failed** | `.venv/bin/python -m pytest -q --no-cov` |
| tsc | 0 错误 | `npx tsc --noEmit` |
| next build | 成功，新增 `/robots.txt`、`/sitemap.xml`、`/solutions/sifaju` | `npx next build` |

### R1-4 合规字段 —— ⛔ 阻塞（如实标注）

`frontend/src/lib/site.ts` 的 `unifiedSocialCreditCode` / `officeAddress` / `icpSecurityRecord` / `policyEffectiveDate` 仍为空。
代码无法代填：这些是经营主体与备案的法定信息，需运营方提供原始凭证后填入，否则等于编造。

