# LEGALAI86 生产级架构升级 · PHASE 0 代码与部署审计

> 本文档为「将 LegalAI 86 升级为 AI-Native Legal Workspace for China」的 **PHASE 0（现有代码与部署审计）** 交付物。
> 审计方式：**只读**扫描本地代码仓库 + 生产只读探测。未修改任何生产配置、DNS、ICP 备案或支付配置。
> 项目主体：上海衍策引擎人工智能科技有限公司 · 品牌「智审 · LegalReview」。

## 0. 审计元信息

| 项 | 值 |
|---|---|
| 审计时间 | 2026-10-19 |
| 代码仓库 | `/Users/shajindi/traework/legal-review`（origin: `git@github.com:shajindi-gif/legal-review.git`） |
| 审计基线提交 | `5886e89`（`test: 稳定 E2E 冒烟，消除生产环境渲染竞态抖动 (#17)`） |
| 安全升级分支 | `upgrade/legalai86-platform`（从 `main` @ 5886e89 切出） |
| 生产服务器 | `124.221.229.12`（ubuntu 用户） |
| 生产域名 | `https://legalai86.com.cn`（`/health` 挂根路径） |
| 后端代码量 | `backend/app` 约 16,218 行 Python |

### 0.1 域名核实结论（重点，未做任何改动）

- `legalai86.com.cn`：DNS 解析到 `124.221.229.12`，`https://legalai86.com.cn/health` 返回 **200** → **这是当前真实生产域名**。
- `legal86.com.cn`：**无 DNS 记录、无法解析**（`curl` 报 `Could not resolve host`）。
- 代码/配置中所有生产绑定（`core/config.py` 的 `public_base_url`、CORS、nginx `server_name`、compose `CORS_ORIGINS`）**全部指向 `legalai86.com.cn`**。
- 结论：`legal86.com.cn` 与 `legalai86.com.cn` **不是同一域名**，前者当前未接入。**按指令要求：未擅自视为同一域名、未修改 DNS / ICP 备案 / 生产域名绑定。** 若需启用 `legal86.com.cn`，须由运营方单独完成备案与解析后再接入（列为待办，非本次自动执行项）。

### 0.2 审计限制

- 生产数据库「实际 schema 与迁移是否一致」、生产 `deploy/.env` 实际取值属敏感信息，本次**未读取**，相关项标记为 `UNKNOWN（需生产验证）`，但均提供了验证命令。
- OCR / weasyprint 等重依赖在生产容器是否真实可加载，标记 `UNKNOWN`。

---

## 1. 二十项审计结果总表

图例：`READY` 真实可用 ｜ `PARTIAL` 部分实现 ｜ `MISSING` 未实现 ｜ `BROKEN` 存在故障 ｜ `UNKNOWN` 缺验证证据

| # | 审计项 | 状态 | 结论摘要 |
|---|---|---|---|
| 1 | 前端技术栈 | **READY** | Next.js **16.3.2** / React 19.2.8 / TS 5 / Tailwind v4 / TanStack Query 5 / Zustand 5 / axios / Radix UI；`next.config.mjs`（Next 16 要求 `.mjs`）。 |
| 2 | 后端技术栈 | **READY** | FastAPI + SQLAlchemy 2(async) + asyncpg + Alembic + pgvector + Redis + LangGraph + structlog + sentry-sdk；解析栈 python-docx / pypdf / paddleocr / weasyprint。 |
| 3 | 数据库结构 | **PARTIAL** | 已有 9 个迁移、约 16 张表（users/organizations/user_plans/orders/payments/review_tasks/documents/legal_documents/legal_clauses/audit_records/notifications/oauth_identities/verification_codes/refresh_tokens/analytics_events/user_feedback）。缺升级所需的 projects、document_versions、document_chunks、knowledge_bases、research_sessions、contract_reviews、playbooks、agent_runs 等。 |
| 4 | 身份认证 | **READY** | 本地密码 + 邮箱验证码登录；JWT access+refresh（rotation + revoke 持久化）；OAuth 渠道（微信/QQ/微博）预留开关默认关。27 个 auth 端点。 |
| 5 | 权限控制 | **PARTIAL** | 有 `require_role` / `get_tenant_context` / super_admin 的角色级 RBAC；**缺** 细粒度 permissions 表与组织成员角色表。 |
| 6 | 用户与组织模型 | **PARTIAL** | `organizations` 表 + `users.organization_id` + `services/tenant.py` 的 `apply_org_filter` 实现多租户隔离；**缺** `organization_members`（成员关系仅靠 users.organization_id）。 |
| 7 | 支付系统 | **READY / PARTIAL** | 支付宝 `page.pay/wap.pay` **真实闭环已上线**（下单+回调验签+幂等结算+退款）；微信 V3（Native/JSAPI/H5）已实现但 `WXPAY_ENABLED=false` 未开（需商户资质）。 |
| 8 | 发票系统 | **MISSING** | 代码库**无任何发票**模型/接口；仅商业化文档提及「对公发票」为规划。属商业化关键缺口。 |
| 9 | API 接口 | **READY** | `api/v1` 共 **88 个** endpoint，15 个路由文件，统一 `/api/v1` 前缀。 |
| 10 | RAG 系统 | **PARTIAL** | `tools/rag.py`：pgvector(HNSW) 向量 + pg_trgm 关键词**混合召回** + 元数据/时效过滤，分数归一化加权。**缺** Reranker、Citation Verification Engine、多版本比对。 |
| 11 | 文件存储 | **PARTIAL** | `services/sandbox.py` 沙箱 + docker volume（`legal_backend_uploads` / `_sandbox`）+ nginx `/uploads/` 直连。**非 S3 兼容对象存储**。 |
| 12 | PDF/DOCX 解析 | **PARTIAL** | `tools/parsers.py` 支持 txt/docx/pdf-text/ocr，输出 `body_paragraphs/title/parser_version`；**未确认**保留表格/页码/条款编号的原位映射（合同 Redline 依赖此能力）。 |
| 13 | OCR 能力 | **PARTIAL** | `tools/ocr.py` 接 PaddleOCR，PDF 无文本层时回退 OCR。依赖极重（paddleocr/paddlepaddle），生产可用性 `UNKNOWN`；OCR 置信信息保留情况待验。 |
| 14 | AI 模型接入 | **READY** | `tools/llm.py` 统一网关：四档 `strong/balanced/flash/reasoner` → DeepSeek V4 Pro/Flash 与 Qwen3.7-Max，重试+指数退避+抖动、限流、超时、JSON Mode；模型名集中配置，未硬编码。 |
| 15 | Agent 工作流 | **READY（仅规范性审核）** | LangGraph 11 节点主图 + 3 条件路由 + `evidence_verify` Retry 边 + iteration 上限；`EvidenceHarness` 引证双校验 + `SecurityHarness` 路由白名单。**合同审查 / 法律研究 / 文书起草 Agent 尚未实现。** |
| 16 | Docker 部署 | **READY** | `deploy/docker-compose.prod.yml`：postgres(pgvector)/redis/backend/frontend/nginx/prometheus(+certbot profile)。 |
| 17 | Nginx 配置 | **READY** | `legalai86.com.cn.conf`：TLS1.2/1.3、HSTS、安全头、SSE 反代（`proxy_buffering off` + 600s）、`/api` `/uploads` `/_next` 分流。 |
| 18 | 环境变量 | **READY（文档化）** | `core/config.py` + compose 对照，支付/邮件/LLM 密钥全部走 env。「生产实际值」`UNKNOWN`。 |
| 19 | 自动化测试 | **PARTIAL** | 后端 pytest **37 个测试文件**；前端 Playwright E2E 冒烟 3 用例。CI（`.github/workflows/ci.yml`）仅跑 ruff+mypy+pytest，**无覆盖率门槛、无前端 typecheck/lint、无 E2E**。 |
| 20 | 安全漏洞与技术债务 | **见 §3** | 见下文明细。 |

---

## 2. 能力矩阵（复用 / 重构 / 新建 / 技术债 / 安全 / 影响面）

### 2.1 可直接复用（低改动）

- **认证体系**：`api/deps.py` 的 `get_current_user` / `require_role` / `get_tenant_context`、`services/auth_service.py`、JWT rotation/revoke。
- **支付闭环**：`services/payment/*`（provider / service / 幂等 / 退款）、`api/v1/billing.py` — 已真实上线，直接承载新套餐。
- **多租户隔离**：`services/tenant.py` + `organizations` + `users.organization_id`。
- **Agent 内核**：`agent/graph.py|nodes.py|state.py|harness.py` + `prompt_manager` + `prompts/registry.yaml`。
- **LLM/Embedding/RAG/解析工具**：`tools/llm.py`、`tools/embedding.py`、`tools/rag.py`、`tools/parsers.py`、`tools/legal_splitter.py`。
- **法规库**：`services/legal_library.py` + `models/legal.py` + `api/v1/legal.py`（法条级 `LegalClause` + embedding）。
- **可观测性**：`services/metrics.py` + `api/v1/metrics.py`（Prometheus）、Sentry（env-gated）。
- **审计留痕**：`services/audit.py` + `models/platform.py`（AuditRecord）。
- **前端基建**：`lib/api.ts`（服务端 rewrite + 静默刷新）、Radix 组件、`AppShell`。

### 2.2 需要重构 / 增强

| 对象 | 问题 | 方向 |
|---|---|---|
| `frontend AppShell` | 仅「左导航+顶栏+主区」，右侧 Context Panel 为**空槽位** | 升级为 Legora 式**三栏工作台**（左导航/中内容/右 AI+引证）；新增 Workspace 一级入口 |
| `tools/rag.py` | 无 Reranker、无 Citation Verification、无版本比对 | 增 Reranker 阶段 + 新增 `CitationVerifier` |
| `tools/parsers.py` | 文档结构（表格/页码/条款锚点）保真不足 | 增结构保真（合同审查 Redline / 导出依赖） |
| `api/v1/feedback.py` | 仍以 `X-User-Id` 头作 `reviewer_id` | 统一改用 JWT 主体 |
| 前端导航 | 传统多页仪表盘，无 11 模块导航 | 重构为模块化一级导航 + 按角色显隐 |
| 前端工程化 | package.json **无** `lint`/`typecheck` 脚本；CI 不含前端 | 补脚本并纳入 CI |

### 2.3 需要新建（PHASE 1-3）

- 统一工作台 Workspace（三栏 + 项目/任务列表）
- Legal Research 模块 + Citation Verification Engine（15 类检索能力 + 结构化回答模板）
- Contract Review 模块（15 类合同、立场、风险分级 CRITICAL/HIGH/MEDIUM/LOW/INFO、Redline、报告导出）
- Government Review 增强（规则包：国家通用/上海市/徐汇区；10 段输出标准；意见书 DOCX / 报告 PDF / 问题清单 XLSX）
- 文档编辑器（富文本 + AI 改写 + 版本历史 + 导出）
- 数据模型：projects / document_versions / document_chunks / knowledge_bases / research_sessions / contract_reviews / playbooks / agent_runs / agent_steps / tool_executions
- **发票系统**（商业化关键缺口）

### 2.4 技术债务

- `jwt_secret` 默认值 `change_me_in_production`（须确保生产 env 已覆盖）。
- 大量 FastAPI 处理器返回裸 `dict/list`（mypy 已 `disallow_any_generics` 关闭）。
- 生产镜像**内嵌代码**（无 volume mount），部署须「迁移先行再换容器」，回滚成本高。
- 本地文件存储非对象存储，扩容/多实例受限。
- 仓库中存在**未跟踪文件**（见 §4），须防止误提交或误删。

### 2.5 安全隐患

| 等级 | 项 | 证据 |
|---|---|---|
| 高 | 退款/管理端点鉴权依赖 `require_role`，须确认无越权 | `billing.py` refund 已加鉴权，生产验证 401/404 正确 |
| 中 | `feedback.py` 信任 `X-User-Id` 作 reviewer_id | `backend/app/api/v1/feedback.py:L46-L52`；前端 `lib/api.ts:L53` 注入 |
| 中 | `deps.get_actor` 保留 `X-User-Id` 兼容路径 | `backend/app/api/deps.py:L47-L55` |
| 中 | `_sandbox`/`uploads` 上传安全（病毒/类型检测） | `services/sandbox.py`，需核验 magic 检测完整度 |
| 低 | nginx CSP 让位给前端 nonce（配置正确，但前端需强制动态渲染） | `deploy/nginx/conf.d/legalai86.com.cn.conf:L75` |
| 待评 | 日志是否含敏感（密钥/合同正文） | 需专项审查 |

### 2.6 对「已有用户 / 数据 / 支付链路」的影响面

- **支付**：新增套餐/计量不得改动现有 Alipay 订单/回调/退款路径与既有 `PLAN_PRICING_CENTS` 语义；所有计费新增须幂等。
- **数据**：所有新表以 `organization_id` + UUID 主键增量新增，**不修改/删除** users/payments/orders/legal_* 既有列；迁移须可回滚。
- **既有用户**：不改登录/鉴权入口语义；前端导航重构须保证老路由可达或重定向。

---

## 3. 安全检查点与备份 / 回滚方案（已建立/待执行）

| 检查点 | 状态 | 说明 |
|---|---|---|
| Git 独立升级分支 | **已建立** | `upgrade/legalai86-platform`（自 5886e89） |
| 代码基线提交 | **已记录** | `5886e89` |
| 数据库备份方案 | 已有脚本 | `deploy/scripts/backup_pg.sh`（生产 `pg_dump`） |
| 配置备份方案 | 已有实践 | 部署时 `/opt/legal-review-backups` + `deploy/.env` 600 权限自动备份（`install-payment-env.sh`） |
| 迁移回滚方案 | **需补** | 每个新迁移必须实现 `downgrade()`；部署前 `alembic downgrade -1` 演练；先 `upgrade head` 再换容器 |
| 禁止项 | 已遵守 | 未删用户 / 未清库 / 未覆盖用户文件 / 未泄露密钥 / 未改生产支付配置 / 未破坏性迁移 |

**生产只读验证命令（需授权后执行）**：

```bash
ssh -i /Users/shajindi/Downloads/04-项目与密码/yanceedu.pem ubuntu@124.221.229.12 \
  'cd /opt/legal-review && sudo docker compose -f deploy/docker-compose.prod.yml ps && \
   sudo docker exec legal-pg psql -U legal -d legal_review -c "\dt" && \
   sudo docker exec legal-backend alembic current'
```

---

## 4. 未跟踪文件清单（防误提交 / 防误删）

以下文件在仓库磁盘存在但**未被 git 跟踪**，不得在无关提交中误带，也不得误删：

- `backend/app/services/analytics_sink.py`（35 行，当前无引用）
- `backend/app/services/report_export.py`（174 行，`markdown_to_docx`，仅被其测试引用）
- `backend/tests/test_report_export.py`（221 行）
- `docs/rectification/`
- `frontend/src/components/analytics/PageViewTracker.tsx`
- `frontend/src/components/billing/UpgradeDialog.tsx`

> 处置建议：`report_export` + 其测试是 PHASE 1「Word/PDF 导出」的**现成资产**，后续在专门提交中一并纳入并接入业务；`analytics_sink` / 前端两个组件同理待接线。当前阶段保持原状。

---

## 5. 结论与 PHASE 1 入口

**总体判断**：现有系统是一个**架构扎实、支付闭环真实、Agent 内核成熟**的「行政规范性文件合法性审核」单体产品。升级不是推倒重写，而是**增量加装**：以现有 Agent / RAG / 支付 / 多租户为地基，新增「统一工作台 + 法律研究（含引用核验）+ 合同审查 + 规范性审核增强 + Word/PDF 导出」四大 MVP 能力。

**PHASE 1 首期改造清单（按优先级）**：

1. **数据模型扩展**（可回滚迁移）：`projects` / `document_versions` / `document_chunks` / `contract_reviews` / `legal_sources` 补充字段（`source_url`/`content_hash`/`last_verified_at` 等）。
2. **Citation Verification Engine**：`services/citation_verifier.py` + `tools/` 接入 Agent，输出「已核实/未找到可核验依据」状态。
3. **三栏工作台 Workspace**：改造 `AppShell` + 新增 Workspace 路由 + 项目/任务列表。
4. **Legal Research 模块**：结构化回答模板（【问题】【适用法域及时间】【结论】【法律依据】…）+ 可点击引证。
5. **Contract Review 模块**：DOCX/PDF 结构保真解析 + 风险分级 + 对照修改视图（Redline 先做对照视图，不伪装原生修订）。
6. **规范性审核增强**：规则包机制（国家通用/地方）+ 10 段输出标准 + 意见书 DOCX / 报告 PDF / 清单 XLSX 导出（复用 `report_export`）。
7. **真实数据来源适配器**：按 `robots.txt` / 服务条款逐源核实，实现适配器接口 + 离线样例，不绕访问控制。

**每阶段纪律**：跑测试 → 更新文档 → 提交 Git → 生成进度报告 → 记录未完成项。

---

*本审计所有状态判定均基于本地代码只读扫描 + 生产只读探测；标注 `UNKNOWN` 项须在生产环境补充验证后方可宣称 READY。未验证内容不编造、不夸大。*
