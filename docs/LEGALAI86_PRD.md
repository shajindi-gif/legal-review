# LegalAI 86 /「智审 · LegalReview」产品需求文档（PRD）

> 定位：**AI-Native Legal Workspace for China** —— 对标 Legora 的一体化法律智能工作台。
> 本文基于仓库真实代码（前端导航、后端 services/api/models、PHASE 0 审计）撰写；
> 所有"状态"结论均可回溯到代码路径与文档，**不含未实现的编造能力**。
> 项目主体：上海衍策引擎人工智能科技有限公司 · 品牌「智审 · LegalReview」。
> 升级分支：`upgrade/legalai86-platform`（自 `main@5886e89` 切出）。
> 基线变更日志：`docs/CHANGELOG_LEGALAI86.md`；审计报告：`docs/LEGALAI86_AUDIT.md`。

---

## 0. 文档元信息

| 项 | 值 | 来源 |
|---|---|---|
| 产品名称 | LegalAI 86 /「智审 · LegalReview」 | 项目记忆 |
| 合法生产域名 | `https://legalai86.com.cn`（`/health` 挂根路径返回 200） | `docs/LEGALAI86_AUDIT.md` §0.1 |
| 未接入域名 | `legal86.com.cn`（**无 DNS 解析**，与前者不是同一域名） | 同上 |
| 前端 | Next.js 16.3.2 / React 19.2.8 / TypeScript 5 / Tailwind v4 / TanStack Query 5 / Zustand 5 | `frontend/package.json`、`docs/LEGALAI86_AUDIT.md` §1 |
| 后端 | FastAPI + SQLAlchemy 2 (async) + asyncpg + Alembic + pgvector + Redis + LangGraph | `backend/app`、`docs/LEGALAI86_AUDIT.md` §1 |
| 已验收测试基线 | 后端 `ruff` + `mypy(strict)` 全绿；`pytest tests/ -q --no-cov` → **543 passed / 27 skipped**；前端 PHASE 1-6 `npx tsc --noEmit` + `pnpm build` 通过 | 项目记忆 / `docs/CHANGELOG_LEGALAI86.md` |

> 说明：本文不引用除上述以外的任何测试/性能指标；未逐项验证的内容一律标注状态或"待核实"。

---

## 1. 产品定位与对标

### 1.1 一句话定位

把「法规检索 → 依据核验 → 合同审查 → 规范性文件合法性审核 → 报告与交付物导出」收敛进一个**按角色显隐的 11 模块三栏工作台**，每个 AI 结论都**带可核验的引证溯源**，杜绝编造。

### 1.2 对标 Legora 的差异点

| 维度 | Legora（参照） | LegalAI 86 现状（真实代码） |
|---|---|---|
| 工作台形态 | AI-Native 三栏（左导航/中内容/右 AI+引证） | 已落地三栏：`frontend/src/components/dashboard/ContextPanel.tsx`（第三栏，宽 320px，桌面可开合/移动隐藏）、`AppShell.tsx`、`TopBar.tsx`（`data-testid="context-panel-toggle"`） |
| 导航 | 模块化一级导航 | `frontend/src/lib/nav.ts` 定义 **11 个一级模块单一事实源**，含 `roles` 角色白名单与 `comingSoon` 角标 |
| 引证可核验 | Citation-first | `backend/app/services/citation_verifier.py`（名称/条款号/原文/时效四要素确定性核验）+ `legal_documents.source_url` 支持前端点击跳转 |
| 合同审查 | Redline | `backend/app/services/contract_review.py` 输出 `findings` + `redline`（**对照修改视图，不伪装 Word 原生修订**） |
| 中国本地化 | —— | 规范性文件合法性审核（A~J 十维度、国家/上海/徐汇分层规则包）、四档 LLM（DeepSeek V4 / Qwen3.7-Max）、支付宝真实支付闭环 |

### 1.3 产品原则（硬约束）

1. **引证可核验优先**：无法核验时统一返回"暂未找到可核验的权威依据，需要人工复核"（`backend/app/services/citation_verifier.py` 的 `CANNOT_VERIFY_MESSAGE`）。
2. **不展示假入口**：未真正实现的模块置 `comingSoon: true`，不可点击、显示「即将」角标（`frontend/src/lib/nav.ts` 注释）。
3. **不编造条号/日期**：规范性审核规则包 `law_basis_article`/`effective_date` 未核实前保持 `null`（`backend/app/gov_rules/*.yaml`）。
4. **不绕访问控制**：数据源在未逐源核实 `robots.txt`/使用条款前 `authorization_status` 保持 `unknown`（`backend/app/models/legal.py` 的 `SourceAuthorizationStatus`）。
5. **AI 结果为辅助**：所有输出均附免责声明（`backend/app/schemas/gov_review.py` 的 `DISCLAIMER`）。

---

## 2. 目标用户与角色

角色枚举集中于 `backend/app/core/constants.py`（`UserRole`），权限上下文由 `backend/app/api/deps.py`（`get_current_user` / `require_role` / `get_tenant_context`）与 `backend/app/services/tenant.py` 承载。

| 角色 | 枚举值 | 职责 | 来源 |
|---|---|---|---|
| 送审人 | `submitter` | 上传送审文件、发起审查任务 | `constants.UserRole.SUBMITTER` |
| 审查员/律师 | `reviewer` | 审查结果复核、合同审查、法律文书 | `constants.UserRole.REVIEWER`（`nav.ts` 中合同/文书/项目模块角色白名单） |
| 审查主管 | `supervisor` | 任务分派、全局查看 | `constants.UserRole.SUPERVISOR`（`search.py` 的 `_can_view_all`） |
| 系统管理员 | `admin` | 管理后台、用户反馈处理 | `constants.UserRole.ADMIN` |
| 法规库管理员 | `librarian` | 法规库维护 | `constants.UserRole.LIBRARIAN` |
| 超级管理员 | `is_super_admin=true` | 手工置位，**禁止 API 修改** | `backend/app/models/user.py`（`is_super_admin`） |

**角色显隐规则**（`frontend/src/lib/nav.ts`）：
- 缺省 `roles` = 全部角色可见；
- `合同审查` / `法律文书` / `项目与团队` 仅对 `reviewer`/`supervisor`/`admin` 可见。

> 说明：PHASE 0 审计（`docs/LEGALAI86_AUDIT.md` §1 第 5/6 项）判定权限控制为 **PARTIAL** —— 已有角色级 RBAC 与 `organization_id` 多租户隔离，**尚缺**细粒度 `permissions` 表与 `organization_members` 成员关系表。

---

## 3. 三大核心流程闭环

### 3.1 法律检索 + 引用核验（Legal Research）

**目标**：给定问题，产出结构化回答，且每条法律依据都可核验、可点击溯源。

- 编排服务：`backend/app/services/legal_research.py`（`LegalResearchService.create_session`）
  1. RAG 召回相关条款（唯可引用依据，`backend/app/tools/rag.py`；失败降级不阻塞并提示人工复核）；
  2. 版本化 Prompt `legal_research@v1.0.0`（`backend/app/agent/prompts/legal_research/v1.0.0.yaml`，`model_tier: strong`）；
  3. 固定 **8 段**回答模板：`backend/app/schemas/research.py`（`RESEARCH_SECTION_TITLES`）——【问题】【适用法域及时间】【结论】【法律依据】【分析】【适用条件与例外】【风险及待核实事项】【官方来源】；
  4. 逐条引证走 `CitationVerifier` 核验，回填 `source_url` 供前端点击跳转；
  5. 持久化 `research_sessions`（`backend/app/models/research.py`）。
- 核验引擎：`backend/app/services/citation_verifier.py` —— 名称/条款编号/引用原文/时效**四要素逐项**核验（纯函数：`normalize_law_name` / `normalize_article_no` / `cn_numeral_to_int` / `text_similarity` / `classify_validity`）。
- API：`backend/app/api/v1/research.py`（`POST/GET /research/sessions`）、`backend/app/api/v1/legal.py`（`POST /legal/citations/verify`、`POST /legal/citations/verify-batch`）。

### 3.2 合同审查（Contract Review）

**目标**：上传合同 → 风险分级 + 对照修改视图 + 依据核验。

- 编排服务：`backend/app/services/contract_review.py`（`ContractReviewService`）
  1. 解析（`backend/app/tools/parsers.py` DOCX/PDF/TXT 保真段落 + 段落锚点；扫描版 PDF 返回 `OCR_REQUIRED` 提示）；
  2. 版本化 Prompt `contract_review@v1.0.0`（`model_tier: strong`）；
  3. 风险固定 **5 档**：`critical`/`high`/`medium`/`low`/`info`（非法值降级为 `info`，`overall_risk` 取 findings 最高等级）；
  4. 审查立场：甲方/乙方/中立（`ReviewStance`）；
  5. 每条 risk 的 `basis` 走 `CitationVerifier` 核验，回填 `basis_status`/`basis_verified`/`basis_source_url`；
  6. 持久化 `contract_reviews`（`findings`/`redline` JSONB）。
- API：`backend/app/api/v1/contract.py`（`POST /contract/reviews` multipart、`POST /contract/reviews/text`、`GET /contract/reviews`、`GET /contract/reviews/{id}`）。
- 输出语义：`redline` = `[{clause_no, before, after, reason, level}]`，**仅为建议视图，不冒充 Word 原生修订**（`backend/app/models/contract.py` 注释）。

### 3.3 规范性文件合法性审核（Government Legal Review）

**目标**：送审文件 → 11 节点 Agent 工作流 → 10 段标准报告 → 交付物导出。

- 工作流：LangGraph 11 节点主图（`backend/app/agent/graph.py|nodes.py|state.py|harness.py`），`EvidenceHarness` 引证双校验 + `SecurityHarness` 路由白名单。**PHASE 1-5 未删除/弱化任何既有节点**。
- 规则包（确定性、不调 LLM）：`backend/app/gov_rules/`（`registry.yaml` + `national.yaml` + `shanghai.yaml` + `xuhui.yaml`），维度 **A~J**（`constants.GovReviewDimension`）。
  - 合规诚实性：`law_basis_article: null`、`effective_date: null`、`legal_review_status: pending_legal_review`、`reviewed_by: null`（未核实前不得当已核实标准）。
- 报告组装（确定性）：`backend/app/services/gov_review_report.py` → 10 段标准（`schemas/gov_review.py` 的 `GOV_REPORT_SECTION_TITLES`：基本信息/审核范围/审核依据/发现问题/具体条款位置/风险等级/修改建议/材料缺失清单/待人工核实事项/合法性审核意见初稿）+ 四类结论（`GovReviewConclusion`）。
- 导出：`backend/app/services/gov_export.py`（意见书 DOCX / 报告 PDF[weasyprint] / 条款问题清单 XLSX[openpyxl]）；通用意见书 DOCX 复用 `backend/app/services/report_export.py`。
- API：`backend/app/api/v1/gov.py`（规则包查询/解析）、`backend/app/api/v1/documents.py`（`POST /documents/upload` 触发工作流）、`backend/app/api/v1/tasks.py`（`GET /tasks/{id}/gov-report`、`GET /tasks/{id}/gov-export`、`GET /tasks/{id}/report/export`）。

---

## 4. 11 个一级模块 · 功能与状态矩阵

一级导航单一事实源：`frontend/src/lib/nav.ts`（`PRIMARY_MODULES`）。状态采用**五态**：
**A 真正可用** ｜ **B 部分完成** ｜ **C 仅有界面** ｜ **D 尚未开发** ｜ **E 受外部依赖阻塞**。

| # | 模块 | 路径 | 角色白名单 | comingSoon | 后端证据 | 前端证据 | 状态 |
|---|---|---|---|---|---|---|---|
| 1 | 工作台 Workspace | `/dashboard` | 全部 | 否 | `api/v1/tasks.py`、`notifications.py`、`search.py` | `(app)/dashboard/page.tsx` | **A 真正可用** |
| 2 | 法律研究 Legal Research | `/research` | 全部 | 是 | `services/legal_research.py`、`services/citation_verifier.py`、`api/v1/research.py` | 无 `/research` 页面 | **B 部分完成**（后端就绪，前端未接线） |
| 3 | AI 助手 Legal Assistant | `/assistant` | 全部 | 否 | 无专属后端 API（无 `assistant` 路由/service） | `(app)/assistant/page.tsx` + `lib/assistant-store.ts`（**localStorage 本地会话**，注释明示"后端 Conversation API 未落地"） | **C 仅有界面** |
| 4 | 合同审查 Contract Review | `/contract` | reviewer/supervisor/admin | 是 | `services/contract_review.py`、`api/v1/contract.py` | 无 `/contract` 页面 | **B 部分完成**（后端就绪，前端未接线） |
| 5 | 文件分析 Document Analysis | `/documents` | 全部 | 否 | `api/v1/documents.py`、`tools/parsers.py`、`tools/ocr.py` | `(app)/documents/page.tsx` | **A 真正可用** |
| 6 | 规范性文件审核 Government Review | `/upload`(+`/review`,`/report`) | 全部 | 否 | `agent/*`、`gov_rules/*`、`services/gov_review_report.py`、`services/gov_export.py`、`api/v1/tasks.py` | `(app)/upload/page.tsx`、`(app)/review/[id]/page.tsx`、`(app)/report/[id]/page.tsx` | **A 真正可用**（`gov-report`/`gov-export` 前端页面**未接线**，见 §6） |
| 7 | 法律文书 Legal Editor | `/editor` | reviewer/supervisor/admin | 是 | 无 service/API | 无 `/editor` 页面 | **D 尚未开发** |
| 8 | AI 工作流 Workflows | `/tasks` | 全部 | 否 | `api/v1/tasks.py`（列表/状态/文档/报告） | `(app)/tasks/page.tsx` | **A 真正可用** |
| 9 | 法律知识库 Knowledge Base | `/knowledge` | 全部 | 是 | 无 `knowledge_bases` 表/API（`legal_documents` 为**共享法规库**，不属知识库模块） | 无 `/knowledge` 页面 | **D 尚未开发** |
| 10 | 项目与团队 Projects | `/projects` | reviewer/supervisor/admin | 是 | 数据层就绪：`models/workspace.py`（`projects`/`document_versions`/`document_chunks`），**无 projects CRUD API** | 无 `/projects` 页面 | **B 部分完成** |
| 11 | 管理与设置 Settings | `/account` | 全部 | 否 | `api/v1/account.py`、`api/v1/billing.py` | `(app)/account/page.tsx`、`pricing/page.tsx` | **A 真正可用** |

**次级与管理员入口**（`nav.ts` 的 `SECONDARY_ITEMS`/`ADMIN_ITEMS`/`BOTTOM_ITEMS`，非 11 模块）：通知（A，`api/v1/notifications.py`）、报告（A，`(app)/reports/page.tsx`）、反馈（A，`api/v1/user_feedback.py`）、历史（**D**，`comingSoon: true`）、管理后台（A，`api/v1/admin_user_feedback.py`）、套餐与计费（A，支付宝真实闭环）。

### 4.1 跨切面能力状态

| 能力 | 证据 | 状态 |
|---|---|---|
| 身份认证 | `services/auth_service.py`、`api/v1/auth.py`（27 端点，JWT access+refresh rotation/revoke） | **A 真正可用** |
| 多租户隔离 | `services/tenant.py`、`models/*` 的 `organization_id`（迁移 `0006`） | **A 真正可用** |
| 支付 | `services/payment/*`、`api/v1/billing.py`（支付宝已上线；微信 `WXPAY_ENABLED=false`） | **A 真正可用**（微信：**E 受外部资质阻塞**） |
| 发票系统 | 代码库无任何发票模型/接口 | **D 尚未开发**（商业化缺口） |
| 数据源适配器 | `models/legal.py` 的 `LegalSource`，`authorization_status` 默认 `unknown` | **E 受外部依赖阻塞**（须逐源核实 robots/条款） |
| 可观测性 | `services/metrics.py`（Prometheus）、Sentry（env-gated） | **A 真正可用** |
| 审计留痕 | `services/audit.py`、`models/platform.py`（`AuditRecord`） | **A 真正可用** |
| CI 前端质量门禁 | `.github/workflows/ci.yml` 仅 ruff+mypy+pytest，无前端 typecheck/lint/E2E | **技术债**（见 §6） |

---

## 5. 最终验收场景（端到端）

### 场景一：规范性文件 草案上传 → 审核 → 报告 → 导出

1. `POST /api/v1/documents/upload`（Bearer JWT；`≤50MB`；白名单 `docx/pdf/png/jpg/jpeg/txt`）→ 返回 `{task_id, trace_id, document_id, parse_status: parsing}`；
2. 后台 `trigger_doc_parse_background` 触发 LangGraph 11 节点工作流，结果写入 `review_results`，通知写入 `notifications`（`kind=node_progress`）；
3. `GET /api/v1/tasks/{id}/status` 轮询进度；`GET /api/v1/tasks/{id}/report` 取结构化报告；
4. `GET /api/v1/tasks/{id}/gov-report` 取 10 段标准报告；
5. 导出：`GET /api/v1/tasks/{id}/gov-export?format=docx|pdf|xlsx`（意见书/报告/条款问题清单），或 `GET /api/v1/tasks/{id}/report/export`（通用意见书 DOCX）。
   **验收判据**：报告含免责声明（`DISCLAIMER`）；未提供材料标为「材料不足」而非认定违法（`MISSING_MATERIAL_NOTE`）。

### 场景二：合同审查

1. `POST /api/v1/contract/reviews`（multipart，含 `stance`/`contract_type`/`project_id`）或 `POST /contract/reviews/text`；
2. 返回 `findings`（5 档风险明细，每条带依据核验状态）+ `redline`（before→after 建议视图）+ `overall_risk`；
3. `GET /api/v1/contract/reviews/{id}` 复核。
   **验收判据**：无风险时 `findings`/`redline` 为空数组，不臆造；扫描版 PDF 明确返回 `OCR_REQUIRED`。

### 场景三：法律研究 · 引证可点击

1. `POST /api/v1/research/sessions`（question/jurisdiction/as_of_date/top_k）；
2. 返回固定 8 段回答（缺失段以 `SECTION_EMPTY_PLACEHOLDER` 占位，禁止省略段落）；
3. `citations[]` 含 `verified`/`needs_human_review`/`source_url`/`validity`/`message`，前端可点击跳转权威来源。
   **验收判据**：法规库无命中时结论提示需人工复核；核验未通过统一提示 `CANNOT_VERIFY_MESSAGE`。

---

## 6. 非目标（明确不做什么）

1. **不出正式法律结论**：所有 AI 输出为辅助结果，正式合法性审核意见须经有权人员审核确认（`schemas/gov_review.py` `DISCLAIMER`）。
2. **不伪装 Word 原生修订**：合同 `redline` 仅为对照建议视图，不生成/不声称 track-changes 原生修订。
3. **不绕访问控制抓取**：数据源未核实 robots/条款前不实现抓取，`authorization_status` 保持 `unknown`。
4. **不把未实现模块伪装成可用**：`comingSoon` 模块不可点击、无假入口。
5. **不擅自变更域名/备案/支付配置**：`legal86.com.cn` 未接入，与 `legalai86.com.cn` 非同一域名。
6. **本阶段不实现**：发票系统、法律知识库、法律文书编辑器、项目 CRUD API、历史模块——均标注为未开发（见 §4）。

---

## 7. 合规与免责声明

- **域名**：合法生产域名仅 `https://legalai86.com.cn`（`/health` 挂根路径 200）；`legal86.com.cn` 无 DNS，二者**不是同一域名**。
- **AI 免责**：规范性审核全部输出附 `DISCLAIMER`（"以上均为 AI 辅助审查结果，不代表法定审核机构作出的正式结论；正式合法性审核意见必须经过有权人员审核确认。"）。
- **规则包合规**：规则包 `legal_review_status = pending_legal_review`，`law_basis_article`/`effective_date` = `null`，**未核实前不得作为已核实标准**。
- **数据源合规**：`legal_sources.authorization_status` 保持 `unknown`（未逐源核实 robots.txt/使用条款前不宣称 READY）。
- **审计留痕**：`audit_records` 强制保留 3 年（`models/platform.py` 注释）；埋点 `ip` 仅存哈希、禁采 PII（`models/analytics.py`）。

---

## 8. 未完成项与下一阶段优先事项

| 优先级 | 事项 | 现状 | 下一步 |
|---|---|---|---|
| P0 | 法律研究 / 合同审查 **前端页面接线** | 后端就绪，`comingSoon` | 补 `/research`、`/contract` 页面并解锁入口（`nav.ts`） |
| P0 | 规范性审核 `gov-report`/`gov-export` **前端接线** | 后端就绪，入口未接 | 在 `/review/[id]`、`/report/[id]` 接入报告与导出按钮 |
| P1 | 数据源适配器 | 阻塞（`unknown`） | 逐源核实 robots/条款后实现适配器 + 离线样例 |
| P1 | 规则包法律审核 | `pending_legal_review` | 逐条补全 `law_basis_article`/`effective_date` 并送法律专业人员审核 |
| P1 | 项目与团队 CRUD API | 数据层就绪 | 实现 `projects` CRUD + 前端 `/projects` |
| P2 | 法律知识库 / 法律文书编辑器 | 尚未开发 | 建表 + service + 页面 |
| P2 | 发票系统 | 未开发 | 商业化关键缺口，需建模 |
| P2 | CI 前端门禁 | 技术债 | CI 增 `tsc --noEmit`/lint/E2E |
| P2 | 历史索引漂移 | 技术债 | 单独迁移清理（见 DATABASE 文档） |

> 每阶段纪律：跑测试 → 更新文档 → 提交 Git → 生成进度报告 → 记录未完成项（`docs/CHANGELOG_LEGALAI86.md`）。

---

*本文所有模块状态判定均基于仓库只读扫描；标注为"部分完成/仅有界面/尚未开发/受外部依赖阻塞"者，须补对应实现并经测试后方可改判为"真正可用"。未验证内容不编造、不夸大。*
