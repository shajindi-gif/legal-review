# LegalAI 86 /「智审 · LegalReview」系统架构

> 本文档描述「LegalAI 86 / 智审 · LegalReview」在 **`upgrade/legalai86-platform`** 分支上的真实系统架构。
> 撰写原则：**只写代码中可核验的事实**，不编造、不夸大；模块状态严格区分五态；法律规范性内容不当作已核实标准。
>
> 项目主体：上海衍策引擎人工智能科技有限公司 · 品牌「智审 · LegalReview」。
> 代码基线：`main@5886e89`；升级分支：`upgrade/legalai86-platform`。

---

## 0. 真实性声明与五态定义

本文所有结论均来自对仓库的**只读**核查（读代码 / 配置 / 部署文件），引用一律使用仓库相对路径。

**模块状态五态**（全文统一）：

| 状态 | 含义 |
|---|---|
| **真正可用** | 代码已实现且有测试或部署证据支撑，可实际运行 |
| **部分完成** | 主链路可用，但存在明确的已知缺口（本文逐条列出） |
| **仅有界面** | 只存在前端页面/入口，后端能力未接通或缺位 |
| **尚未开发** | 无对应实现 |
| **受外部依赖阻塞** | 实现已就绪或可写，但被第三方资质 / 未核实授权 / 未决配置阻塞 |

**本次已核实的工程质量事实**（仅在下列范围内声明通过，不扩展到他项）：

- 后端：`ruff` 全绿；`mypy app`（strict）全绿；`pytest tests/ -q --no-cov` → **543 passed / 27 skipped**。
- 前端：PHASE 1-6 时 `npx tsc --noEmit` 通过、`pnpm build` 通过（21 条路由编译成功）。

**必须坚持的合规边界**：

1. 合法生产域名**仅有** `legalai86.com.cn`（`/health` 挂根路径返回 200）；`legal86.com.cn` **无 DNS 解析、当前未接入**。二者**并非同一域名**，本文档不暗示其为同一域名。
2. 规范性审核规则包（`backend/app/gov_rules/`）的 `legal_review_status` 仍为 **`pending_legal_review`**，且 `law_basis_article` / `effective_date` 为 **`null`** —— 这些是**待核实的候选规则**，**不得当作已核实的法律标准**使用。
3. 数据源适配器在**逐源核实** robots.txt / 使用条款 / 授权前，`authorization_status` 保持 **`unknown`**，不得宣称 READY。

---

## 1. 概览与目标

### 1.1 定位

「LegalAI 86 / 智审 · LegalReview」原为**行政规范性文件智能合法性审查 Agent 系统**（面向司法局等场景），现升级对标 **Legora** 的「**AI-Native Legal Workspace for China**」：从单一审核工具，演进为覆盖**法律研究 / 合同审查 / 规范性文件审核 / 文件分析 / AI 助手**的一体化 AI 原生法律工作台。

### 1.2 本次升级范围（PHASE 1–6，均可核验）

| PHASE | 交付物 | 提交 |
|---|---|---|
| PHASE 0 | 代码与部署审计 `docs/LEGALAI86_AUDIT.md` | `1c4f568` |
| PHASE 1-1 | 法律依据核验引擎 `services/citation_verifier.py` | `e278cb6` |
| PHASE 1-2 | 数据模型扩展迁移 `0009_legalai86_workspace.py` | — |
| PHASE 1-3 | 法律研究模块 `services/legal_research.py` | — |
| PHASE 1-4 | 合同审查模块 `services/contract_review.py` | — |
| PHASE 1-5 | 规范性审核增强（规则包 + 10 段报告 + 导出） | — |
| PHASE 1-6 | 前端统一工作台（三栏 + 11 模块一级导航） | — |

**升级硬约束**：不删除 / 弱化 / 替换既有司法局 LangGraph 11 节点工作流；因「**未经评估的 Prompt 变更禁止合并**」，PHASE 1-5 以**确定性（数据驱动、不调 LLM）** 的规则包 + 报告 + 导出层**叠加**在工作流之上，而非改写既有 Prompt。

---

## 2. 总体架构

```
                    ┌───────────────────────────────────────────┐
  Browser ── HTTPS ─┤ nginx (deploy/nginx/conf.d/…)        :80/443│
                    └───────┬───────────────────────┬───────────┘
                            │ /api/*,/health,/uploads│ / ,/_next/static
                            ▼                       ▼
                 ┌────────────────────┐   ┌──────────────────────────┐
                 │ backend (FastAPI)  │   │ frontend (Next.js)       │
                 │ app.main:app :8000 │   │ standalone :3081         │
                 └─────────┬──────────┘   └──────────────────────────┘
        ┌──────────────────┼─────────────────────────┐
        ▼                  ▼                         ▼
  PostgreSQL(pgvector)   Redis                 LLM Gateway / OCR / Parser
  legal_review DB       缓存·限流·队列          (tools/llm.py, tools/ocr.py, tools/parsers.py)
```

### 2.1 前端（`frontend/`）

- 框架：**Next.js 16.3.2 / React 19.2.8 / TypeScript 5 / Tailwind v4**（`frontend/package.json`）。使用 App Router，路由分组为 `(app)` / `(auth)` / `(admin)`（`frontend/src/app/**/page.tsx`）。
- 数据与状态：TanStack Query 5 + Zustand 5 + axios；UI 基座 Radix UI。
- 统一工作台外壳：`frontend/src/components/dashboard/AppShell.tsx` —— **三栏布局**：
  - 左：`SideNav.tsx`（一级导航，由 `lib/nav.ts` 单一事实源驱动，按角色显隐）；
  - 中：主内容区（`main#main-content`）；
  - 右：`ContextPanel.tsx`（上下文面板，宽 320px，桌面可开合、移动端隐藏；无内容时展示**明确空状态，不伪造内容**），由页面通过 `lib/workspace-context.tsx` 的 `useRegisterContextPanel` 注入。
- 生产构建：`frontend/Dockerfile` 采用 Node 22 + `pnpm@11.6.0` 多阶段构建（builder `pnpm build` → runner `npx next start -H 0.0.0.0 -p 3081`）。

### 2.2 后端（`backend/`）

- 框架：**FastAPI + Uvicorn**（`app/main.py:create_app`），应用描述“行政规范性文件智能合法性审查 Agent 系统 API”。
- 关键中间件：CORS、`X-Trace-Id` 注入（`trace_id_middleware`）、**API 边缘 per-IP 限流**（`rate_limit_middleware`，Redis 固定窗口，超限 429）。
- 依赖栈（`backend/pyproject.toml`）：SQLAlchemy 2 (async) + asyncpg + Alembic + **pgvector** + Redis + **LangGraph** + Jinja2 + PyYAML + structlog + sentry-sdk；解析栈 python-docx / pypdf / **paddleocr** / weasyprint / openpyxl。
- 探针：`app/api/v1/health.py` 定义 `GET /health`（存活，不查 DB）与 `GET /ready`（含 DB `SELECT 1` 就绪）。**注意：`health` router 以根路径挂载**（`app/main.py` 中 `app.include_router(health_router.router)`，**不进 `/api/v1` 前缀**）。
- API 根前缀：`app/api/v1/__init__.py` → `APIRouter(prefix="/api/v1")`，聚合 18 个子 router：
  `auth / account / documents / legal / research / contract / gov / tasks / eval / feedback / audit / metrics / notifications / search / user-feedback / admin/user-feedback / billing / analytics`。

### 2.3 数据层

- **PostgreSQL（pgvector 镜像 `pgvector/pgvector:pg16`）**：主库 `legal_review`。向量检索依赖 pgvector（`clause.embedding`）——见 `backend/app/tools/rag.py`。
- **Redis 7**：缓存 / 限流 / 队列（`--maxmemory 256mb --maxmemory-policy allkeys-lru`）。
- 说明：代码与部署文件中**未发现 Qdrant**（全仓检索 `qdrant` 无匹配）。向量能力由 **pgvector** 承担，本文不宣称存在 Qdrant 组件。
- ORM 迁移：Alembic；`0009_legalai86_workspace.py` 新增 `projects / document_versions / document_chunks / research_sessions / contract_reviews / legal_sources`，并为 `legal_documents` 补溯源字段（`source_url / source_type / content_hash / last_verified_at / document_number`）。

### 2.4 文件与 OCR

- 沙箱：`services/sandbox.py` 将上传文件限制在 `SANDBOX_ROOT`（容器 `/app/_sandbox`），`docker volume legal_backend_sandbox / legal_backend_uploads` 持久化；nginx `location /uploads/` 直连后端。
- 解析：`tools/parsers.py`（DOCX/PDF/TXT → `body_paragraphs` 带段落锚点 `id` / `anchor`、`title`、`parser_version`）。
- OCR：`tools/ocr.py` 接 PaddleOCR，**数字 PDF 无文本层时回退 OCR**（`nodes.doc_parse_node` 依据 `parsed._needs_ocr` 触发）。依赖较重（paddleocr/paddlepaddle），**生产容器内的实际可加载性未核实**（`UNKNOWN`）。

### 2.5 LLM Gateway（`backend/app/tools/llm.py`）

- 统一网关，按**档位（tier）**路由，**不硬编码模型名**：`strong | balanced | flash | reasoner`。
- Provider：`DeepSeekProvider`（`deepseek-v4-pro` / `deepseek-v4-flash`）、`QwenProvider`（DashScope OpenAI 兼容：`qwen3.7-max` / `qwen-plus` / `qwen-turbo`）、`MockProvider`（测试/CI）。
- 硬约束：**未配置 API key 时禁用真实 provider，强制回退 mock**。
- 具备重试 + 指数退避 + 抖动、超时、限流、JSON Mode；生产默认 `LLM_PROVIDER=mock`（`deploy/docker-compose.prod.yml`），需显式配置密钥与 provider 才走真实模型。

---

## 3. Agent 架构（LangGraph）

> 代码：`backend/app/agent/{graph.py, nodes.py, state.py, harness.py}`

### 3.1 两层 Graph 与 11 节点流水线

主控图为 `StateGraph(ReviewState)`，**11 个节点**，入口 `doc_parse`，终态 `human_review → END`（`graph.build_review_graph`）：

```
START
  ▼
doc_parse ──► doc_classify
                  │
        ┌── is_normative=False ──► report_generation（非规范性文件，直接出报告）
        └── is_normative=True  ──► legal_retrieve ──► authority_review
                                                        │
                              ┌── authority=FAIL ──► report_generation（主体不合法）
                              └── authority=PASS ──► procedure_review ──► content_review
                                                                              ▼
                                                                    risk_assessment
                                                                          ▼
                                                                   evidence_verify ◄─┐
                                                          ┌── PASS ──► report_generation│
                                                          │                            │
                                                          ├── FAIL & iteration<max ────┘ (Retry Edge)
                                                          └── FAIL & 超限 ──► human_fallback
                                                                              │
                                                          report_generation ──┤
                                                                              ▼
                                                                        human_review ──► END
```

节点职责（`nodes.py`）：

| 节点 | 职责 | Prompt key |
|---|---|---|
| `doc_parse` | OCR + 结构化解析，产出 `document_json`、`body_paragraphs[].id/anchor` | —（沙箱解析） |
| `doc_classify` | 判定是否为行政规范性文件（4 要素），产出 `is_normative` | `doc_classify` |
| `legal_retrieve` | RAG 混合召回（生成 query 后检索），产出 `legal_context` | `legal_query` |
| `authority_review` | 制定主体合法性审查 | `authority_review` |
| `procedure_review` | 程序审查（5 项） | `procedure_review` |
| `content_review` | 内容违法情形审查 | `content_review` |
| `risk_assessment` | 4 维度综合评级，产出 `overall_status`（pass/risk/fail） | `risk_assessment` |
| `evidence_verify` | 证据校验（触发 Retry Loop） | `evidence_verify` |
| `report_generation` | 结构化审查报告（长文，`max_tokens=8192`） | `report_generation` |
| `human_review` | 人工复核终态 | — |
| `human_fallback` | 迭代超限兜底（转人工） | — |

### 3.2 State Schema（`agent/state.py`）

`ReviewState` 为 `TypedDict(total=False)`。**硬约束必填字段**：

- `trace_id`、`task_id`、`iteration`、`max_iteration`（默认 5）、`prompt_versions`。

其余字段：`document_json` / `legal_context` / `user_context`（Context Harness）；各节点输出 `parse_result`…`report_result`（统一 `AgentOutput`）；路由控制 `is_normative` / `overall_status` / `needs_human_review` / `feedback`；终态 `finished` / `error`。

核心 Pydantic 模型：

- `Evidence`：`law_name / article / original_text / explanation` —— **每个风险点必须附证据**。
- `RiskItem`：`dimension(authority|procedure|content|prohibition|interest)`、`risk_type`、`severity(low|medium|high|critical)`、**`paragraph_id` / `paragraph_anchor`（正文锚点，供前端风险—段落精准联动）**、`evidence`、`confidence∈[0,1]`、`suggestion`。
- `AgentOutput`：`agent_name / node_status(pass|fail|retry|skipped) / risks / evidences / confidence / raw_json / duration_ms / iteration`。

### 3.3 四类 Harness（`agent/harness.py`）

| Harness | 关键约束 |
|---|---|
| **Context Harness** | 每节点入口注入 `trace_id / document_json / legal_context / user_context` |
| **Evidence Harness** | 逐项校验：`evidence.law_name`、`article`、`original_text` 非空且 `confidence ≥ min_confidence`；`enforce` 缺失即抛 `ValidationError`（**不绕过**）；`enforce_silent` 返回缺失列表供节点内部决策 |
| **Quality Harness** | 迭代门控：`iteration ≥ MAX_ITER(=settings.max_iteration, 默认 5)` 抛 `IterationLimitExceededError`；`should_retry` 判是否可重试 |
| **Security Harness** | 节点白名单 + 强制路由表 + State 不变量校验 + 审计日志 |

### 3.4 EvidenceHarness 双校验（`evidence_verify_node`）

`evidence_verify` 是**核心质量门**，执行**双重校验**：

1. **LLM 判断**：LLM 返回 `status`（PASS / RETRY / FAIL）；
2. **EvidenceHarness 强校验**：对 `authority / procedure / content / risk` 四个上游结果分别跑 `EvidenceHarness.enforce_silent`，**任一处缺失证据字段即强制 `node_status="retry"`**（覆盖 LLM 的 PASS 判断，`raw_json.harness_missing` 记录缺失明细）。

路由（`evidence_verify_router`）：

- `PASS` → `report_generation`
- `FAIL/RETRY` 且 `iteration < max_iteration` → `legal_retrieve`（**Retry Edge**，`iteration` 自增）
- `FAIL/RETRY` 且 `iteration ≥ max_iteration` → `human_fallback`

### 3.5 安全节点不可绕过

- 每个节点被 `security_checked(node_name)` 装饰（`graph._wrap_nodes`），入口依次执行：**State 不变量校验 → 节点白名单校验 → 入口审计 → 节点本体 → 出口审计**；节点抛错记录 error 审计后**原样上抛（不吞错）**。
- 每次路由决策走 `SecurityHarness.assert_route_allowed(current, nxt)`，`current → nxt` 必须命中 `SUPERVISOR_ROUTE_TABLE`；**未注册节点 / 未注册路由立即抛 `ValidationError`**。
- 启动期自检 `graph.validate_route_table()` 校验路由表内节点均在白名单。

### 3.6 端到端触发与流式通知

`nodes.trigger_doc_parse_background` 通过 `graph.astream(state, stream_mode="updates")` 驱动工作流，逐 chunk 触发 `notifier.emit_node_running` / `emit_node_done`（前端可感知节点进度）。**异常隔离**：工作流失败不影响上传 API 已返回的 201，失败时更新 `task.status=FAILED`。

---

## 4. Prompt 与版本治理

> 代码：`backend/app/services/prompt_manager.py`、`backend/app/agent/prompts/registry.yaml`、`.../<key>/vX.yaml`

### 4.1 单一事实源

- **`registry.yaml`** 是 Prompt 版本的注册表；`PromptManager` 启动时加载到内存 `_registry`。
- 每个 prompt 的模板文件位于 `prompts/<prompt_key>/<version>.yaml`（如 `prompts/legal_research/v1.0.0.yaml`）。
- 加载优先级：**DB active > YAML `active_version` > YAML 文件**。
- 渲染：**Jinja2 `StrictUndefined`**，缺失变量直接报错；必填变量为空串 / 纯空白也视为缺失（避免生成“制定机关：”这类空内容）。

### 4.2 model_tier：只写档位，禁止硬编码模型名

`registry.yaml` 每条仅声明 `prompt_key / active_version / model_tier / temperature / min_eval_pass_rate`，**明确禁止硬编码模型名**；运行时由 `tools/llm.py` 按 provider 的 `tier_models` 将 tier 映射到具体模型（`nodes._run_llm_node` 传 `tier=spec.model_tier`，**不传 `spec.model_name`**）。

当前注册 10 个 prompt 及档位：

| prompt_key | active_version | model_tier | min_eval_pass_rate |
|---|---|---|---|
| doc_classify | v1.0.0 | flash | 0.90 |
| legal_query | v1.0.0 | flash | 0.85 |
| authority_review | v1.0.0 | strong | 0.95 |
| procedure_review | v1.0.0 | balanced | 0.85 |
| content_review | v1.0.0 | strong | 0.85 |
| risk_assessment | v1.0.0 | reasoner | 0.85 |
| evidence_verify | v1.0.0 | strong | 1.00 |
| report_generation | v1.0.0 | balanced | 1.00 |
| legal_research | v1.0.0 | strong | 0.90 |
| contract_review | v1.0.0 | strong | 0.90 |

### 4.3 评估门控（未经评估不得合并）

`PromptManager.activate(session, key, version, eval_pass_rate)` 硬约束：

- `eval_pass_rate < min_eval_pass_rate` → **拒绝激活**（抛错，文案即“硬约束：未经评估 Prompt 禁合并”）；
- 激活前将旧 active 版本置 `deprecated`（**可回滚**，`deactivate` 提供回滚）；
- 未在 registry 注册的 `prompt_key` **禁止调用**（`NotFoundError`）。

### 4.4 版本可追溯

每次节点调用都把 `prompt_version` 写入 `state.prompt_versions[agent_name]`，并落库到 `AgentLog.prompt_version` 与 `ReviewResult`；研究/合同服务在 `metadata_` 中记录 `prompt_key` / `prompt_version` / LLM 用量元数据。

---

## 5. 鉴权与多租户

> 代码：`backend/app/api/deps.py`、`services/auth_service.py`、`services/core_auth_client.py`、`services/tenant.py`

### 5.1 JWT → CorePrincipal

`get_current_user`（`api/deps.py`）：

1. 提取 `Authorization: Bearer <token>`（缺失 / 非 Bearer 直接 `AuthError`）；
2. **本地 JWT 优先**：`auth_service.decode_token` → 校验 `type=="access"` → 按 `sub` 加载本地 `User` → 组装 `CorePrincipal`（`_principal_from_local_user`）；账号非 active 抛 `AuthError`；
3. 本地失败则**回退 Core Auth**：`core_auth_client.me(token)`（Strangler 双跑旧流量）；Core 不可达映射为 503，401/403 映射为 `AuthError`。

`CorePrincipal`（`services/core_auth_client.py`，frozen dataclass）承载 `id / tenant_id / role / organization_id / is_super_admin` 等业务层所需字段；可选鉴权 `get_current_user_optional` 供免登录端点使用。

### 5.2 角色守卫

- `require_role(*allowed)` 返回依赖守卫，`str(current_user.role)` 不在白名单则 `AuthError`；角色字面量：`submitter | reviewer | supervisor | admin | librarian`。

### 5.3 多租户隔离（应用层，非 RLS）

设计选择（`services/tenant.py`）：**不引入 PostgreSQL RLS**，而在应用层强制 `WHERE organization_id = current_user.organization_id`，避免 superuser 绕过与迁移复杂度。

- `get_tenant_context`（`api/deps.py`）组合 `user + org + is_team + is_super_admin`；
- `apply_org_filter_with_column(stmt, user, org, *, org_column, user_id_column)`：
  - **super_admin → 不过滤**（跨租户，审计/客服场景）；
  - **团队组织（state_owned/public_inst/county_dept/township/street，即非 personal）→ `WHERE organization_id = user.organization_id`**（同组织成员可见彼此数据）；
  - **personal 组织 → 退回 `user_id_column == user.id`**（个人虚拟组织，单租户隔离）。
- `load_user_org` 预加载组织避免 N+1；`can_view_org` 提供单点判定。

契约：所有新表以 `organization_id` + UUID 主键增量新增，**不修改/删除**既有 users/payments/orders/legal_* 列。

### 5.4 已知缺口

- **无**细粒度 `permissions` 表与 `organization_members` 成员关系表（成员关系仅靠 `users.organization_id`）→ 权限控制为 **PARTIAL**。
- `deps.get_actor` 与 `api/v1/feedback.py` 仍保留 `X-User-Id` 兼容路径（技术债，见 §9）。

---

## 6. 模块清单与实现状态矩阵

图例同 §0。表中「后端」与「前端」分列，避免把后端已就绪误读为前端可用。

### 6.1 后端 API / 服务

| 模块（相对路径） | 状态 | 说明 / 证据 |
|---|---|---|
| Agent 工作流 `agent/graph.py`+`nodes.py` | **真正可用** | 11 节点 + 3 条件路由 + Retry 边 + 双 Harness；仅规范性审核场景（生产 LLM 需配置密钥，默认 `mock`） |
| 法律依据核验 `services/citation_verifier.py` | **真正可用** | 四要素逐项核验（名称/条号/原文/时效）；纯函数 + `LawLookup` 抽象；测试 `tests/test_citation_verifier.py` 30 例全绿 |
| 法律研究 `services/legal_research.py`（API `/research/sessions`） | **真正可用** | RAG→版本化 Prompt→固定 8 段→逐条核验→落库 `research_sessions`；10 例全绿 |
| 合同审查 `services/contract_review.py`（API `/contract/reviews`） | **真正可用** | 5 档风险 + 立场 + findings/redline（**仅建议视图，不伪装 Word 原生修订**）+ 依据核验；11 例全绿 |
| 规范性审核规则包 `services/gov_rules.py`（API `/gov/rule-packs`） | **部分完成** | 加载/校验/按地域解析可用；**规则内容 `legal_review_status=pending_legal_review`、`law_basis_article`/`effective_date=null`，未经法律审核** |
| 规范性审核 10 段报告 `services/gov_review_report.py` | **真正可用** | **确定性、不调 LLM**；四类结论 + 免责声明；由既有节点结果 + 规则包组装 |
| 规范性导出 `services/gov_export.py` | **真正可用** | DOCX（复用 `report_export.markdown_to_docx`）/ PDF（weasyprint CJK）/ XLSX（openpyxl，两表） |
| 通用报告导出 `services/report_export.py` | **真正可用** | Markdown→DOCX 纯本地转换；随 `/tasks/{id}/report/export` 接线后原基线用例转为通过 |
| Prompt 版本管理 `services/prompt_manager.py` | **真正可用** | 单一事实源 + 评估门控 + 回滚 |
| 鉴权 `services/auth_service.py` + `api/deps.py` | **真正可用** | 本地 JWT（access+refresh rotation/revoke）+ Core 回退 |
| 多租户 `services/tenant.py` | **部分完成** | 应用层隔离可用；**缺** `organization_members` / 细粒度 permissions |
| RAG `tools/rag.py` | **部分完成** | pgvector(HNSW) 向量 + pg_trgm 关键词混合召回 + 元数据/时效过滤；**缺 Reranker** |
| OCR `tools/ocr.py` | **部分完成** | PaddleOCR + 无文本层回退；**生产容器可加载性 UNKNOWN**，OCR 置信信息保留待验 |
| 解析 `tools/parsers.py` | **部分完成** | 输出 `body_paragraphs`/`title`/`parser_version`；表格/页码原位映射未确认 |
| LLM Gateway `tools/llm.py` | **真正可用** | 四档 tier 路由 + 重试/限流/JSON Mode；模型名集中配置 |
| 支付 `api/v1/billing.py` + `services/payment/*` | **部分完成** | 支付宝 `page/wap.pay` 真实闭环；微信 V3 已实现但 `WXPAY_ENABLED=false`（**受商户资质阻塞**） |
| 发票系统 | **尚未开发** | 无任何发票模型/接口 |
| 数据源适配器（`legal_sources`） | **受外部依赖阻塞** | 未逐源核实 robots/条款/授权前 `authorization_status=unknown` |
| 可观测性 `services/metrics.py` + Prometheus | **真正可用** | `/metrics` + compose `prometheus`（内网，不对外） |
| 审计留痕 `services/audit.py` | **真正可用** | `AuditRecord` + Security Harness 审计日志 |

### 6.2 前端页面与 11 模块导航

`frontend/src/lib/nav.ts` 是 **11 个一级模块的单一事实源**：模块未真正实现则 `comingSoon: true`，**禁止点击、显示「即将」角标、不得展示假入口**。

| 一级模块 | 前端页面 | 状态 | 说明 |
|---|---|---|---|
| 工作台 Workspace (`/dashboard`) | `(app)/dashboard/page.tsx` | **真正可用** | 三栏外壳承载 |
| 法律研究 (`/research`) | — | **尚未开发**（前端） | 后端已就绪；导航 `comingSoon: true` |
| AI 助手 (`/assistant`) | `(app)/assistant/page.tsx` | **真正可用** | — |
| 合同审查 (`/contract`) | — | **尚未开发**（前端） | 后端已就绪；`comingSoon: true`，角色限 reviewer/supervisor/admin |
| 文件分析 (`/documents`) | `(app)/documents/page.tsx` | **真正可用** | — |
| 规范性文件审核 (`/upload`,`/review/[id]`,`/report/[id]`) | `(app)/upload`、`(app)/review/[id]`、`(app)/report/[id]` | **部分完成** | 上传→审查→报告可达；**`gov-report` / `gov-export` 前端未接线** |
| 法律文书 (`/editor`) | — | **尚未开发** | `comingSoon: true`，角色限 reviewer/supervisor/admin |
| AI 工作流 (`/tasks`) | `(app)/tasks/page.tsx` | **真正可用** | — |
| 法律知识库 (`/knowledge`) | — | **尚未开发** | `comingSoon: true` |
| 项目与团队 (`/projects`) | — | **尚未开发** | `comingSoon: true`，角色限 reviewer/supervisor/admin |
| 管理与设置 (`/account`) | `(app)/account/page.tsx` | **真正可用** | — |

次级（`SECONDARY_ITEMS`）：通知 `/notifications`、报告 `/reports`、反馈 `/dashboard/feedback`（可用）；历史 `/history`（`comingSoon`）。
管理员：`/admin`、`/admin/feedback`。底部：套餐计费 `/pricing`、账户设置 `/account`。
公共页：`/`、`/terms`、`/privacy`、`/cookies`；`(auth)`：`/login`、`/register`、`/forgot-password`。

---

## 7. 关键数据流

### 7.1 规范性文件审核主链路（上传 → 报告 → 导出）

```
POST /api/v1/documents（上传，沙箱落盘，201 返回）
   └─(异步)─► trigger_doc_parse_background
        └─► LangGraph astream：
            doc_parse → doc_classify → [legal_retrieve → authority_review → procedure_review
            → content_review → risk_assessment → evidence_verify(↺Retry)] → report_generation
            → human_review → END
   每节点：PromptManager.render(key) → LLM(tier) → Pydantic 解析 → 落库 ReviewResult / AgentLog
   进度：notifier emit_node_running / emit_node_done（配合 nginx SSE 600s 长连）
取得产物：
   GET /api/v1/tasks/{task_id}/report            → 结构化审查报告
   GET /api/v1/tasks/{task_id}/report/export     → 通用审查意见书 DOCX
   GET /api/v1/tasks/{task_id}/gov-report        → 10 段标准审核报告（确定性组装）
   GET /api/v1/tasks/{task_id}/gov-export?format=docx|pdf|xlsx → 意见书 / 报告 / 问题清单
```

### 7.2 规范性审核 10 段报告（`gov_review_report.build_gov_report`）

确定性（**不调 LLM**）由既有 `ReviewResult`（`risks`/`evidences`）+ 规则包组装，段落顺序固定（`GOV_REPORT_SECTION_TITLES`）：①基本信息 ②审核范围 ③审核依据 ④发现问题 ⑤条款位置 ⑥风险等级 ⑦修改建议 ⑧材料缺失 ⑨待人工核实 ⑩意见初稿。结论四类：`no_obvious_violation / needs_revision / major_risk / insufficient_basis`；报告统一附 `DISCLAIMER`，材料缺失标注 `MISSING_MATERIAL_NOTE`（**不据材料缺失直接认定程序违法**）。

### 7.3 合同审查（`ContractReviewService`）

```
POST /api/v1/contract/reviews（multipart: docx/pdf/txt）/ …/text（纯文本）
 → tools/parsers.parse（保真段落 + 锚点）→ contract_review Prompt → LLM 结构化输出
 → 抽取 findings（5 档风险）+ redline（before→after，仅建议视图）
 → 每条 basis 走 CitationVerifier 核验，回填 basis_status / basis_verified / basis_source_url
 → 落库 contract_reviews（findings/redline JSONB + prompt 版本 + 用量）
```

### 7.4 法律研究（`LegalResearchService`）

```
POST /api/v1/research/sessions → RAG 召回（唯一可引用依据）→ legal_research Prompt → LLM
 → 固定 8 段模板组装（缺失段以占位文本呈现，禁止省略段落）
 → citations 逐条走 CitationVerifier（含可点击 source_url）
 → 落库 research_sessions（question/jurisdiction/as_of_date/answer_json/citations/prompt 版本）
```

### 7.5 引证核验细节（`CitationVerifier`）

对每条 `CitationClaim`：①法规名称归一化 + 匹配（精确 > 包含 > 相似度 ≥ 0.85）→ ②时效判定（`repealed/expired/draft/not_yet_effective/effective/amended/unknown`）→ ③条号归一化 + 定位 → ④引用原文归一化相似度分档（`exact/near/weak/mismatch/no_text`）。无法核验时返回统一提示 `CANNOT_VERIFY_MESSAGE`（“暂未找到可核验的权威依据，需要人工复核。”）并置 `needs_human_review=true`。**核验为确定性算法，与 LLM 解耦。**

---

## 8. 部署拓扑与环境

### 8.1 生产域名与环境（已核实）

| 项 | 值 |
|---|---|
| 生产服务器 | `124.221.229.12`（ubuntu） |
| 代码目录 | `/opt/legal-review`（`deploy/deploy.sh` `PROJECT_DIR` 默认值） |
| **合法生产域名** | **`https://legalai86.com.cn`**（`/health` 挂根路径返回 200） |
| `legal86.com.cn` | **无 DNS 记录、无法解析，当前未接入；与 legalai86.com.cn 并非同一域名** |

所有生产绑定（CORS、nginx `server_name`、compose `CORS_ORIGINS`、`public_base_url`）**全部指向 `legalai86.com.cn`**。

### 8.2 部署拓扑（`deploy/docker-compose.prod.yml`）

服务（同一 `legal_appnet` 网络）：

| 服务 | 镜像 / 端口 | 说明 |
|---|---|---|
| `postgres` | `pgvector/pgvector:pg16`（内网 5432） | 主库 `legal_review`；不暴露主机端口 |
| `redis` | `redis:7-alpine`（内网 6379） | AOF + LRU 256mb |
| `backend` | `legal-review/backend:latest`，:8000 | Dockerfile 多阶段（python 3.11-slim）；healthcheck `GET /health` |
| `frontend` | `legal-review/frontend:latest`，:3081 | Node 22 + pnpm；`npx next start -p 3081` |
| `nginx` | `legal-review/nginx:latest`，:80/:443 | TLS 终结 + 反代；certbot 证书共享 |
| `prometheus` | `prom/prometheus`（内网） | 指标抓取 + 基础告警，**不对外暴露端口** |
| `certbot` | `certbot/certbot:latest`（`profile=certbot`） | 每 12h `certbot renew` |

nginx 分流（`deploy/nginx/conf.d/legalai86.com.cn.conf`）：`/api/` → backend（`proxy_buffering off`，`proxy_read_timeout=600s` 支持 SSE）；`/health` → backend 根路径探针；`/uploads/` → backend；`/_next/static/` → frontend（1 年强缓存）；`/` → frontend。80 端口仅 ACME + 全 301 跳 HTTPS；HSTS + 安全头；`server_tokens off`。

### 8.3 一键部署（`deploy/deploy.sh`）

8 步：系统预检 → DNS 自检（不一致仅 WARN，可 CDN 前置）→ 安装 Docker/Compose → 拉代码（`git clone/pull`）→ 生成 `deploy/.env`（`chmod 600`，`POSTGRES_PASSWORD` / `JWT_SECRET` 随机生成）→ `compose build && up -d postgres redis backend frontend` → **等 backend `/health` 200（最多 90s）** → `docker exec legal-backend alembic upgrade head` → certbot 签证书 → 起 nginx。证书未就绪时置 `SKIP_CERTBOT=1`，DNS 生效后手动补签。

**环境变量要点**（均走 env，不进仓库）：`DATABASE_URL` / `REDIS_URL` / `JWT_SECRET` / `CORS_ORIGINS` / `LLM_PROVIDER`（默认 `mock`）/ `EMBEDDING_PROVIDER`（默认 `mock`）/ `MAX_ITERATION`(默认 5) / `MIN_CONFIDENCE`(默认 0.7) / 支付与邮件密钥（默认关闭）。**生产实际取值属敏感信息，未读取**（`UNKNOWN`）。

---

## 9. 未完成项与技术债

### 9.1 未完成（滚动）

1. **规范性审核规则包待法律审核**：`legal_review_status` 仍为 `pending_legal_review`，`law_basis_article` / `effective_date` 为 `null`，待逐条核实后送法律专业人员审核；报告已内置“依据需人工复核”提示。
2. **`gov-report` / `gov-export` 前端未接线**：后端与 API 已就绪，前端页面缺失。
3. **数据源适配器**：未逐源核实 robots / 使用条款 / 授权前 `authorization_status` 保持 `unknown`。
4. **前端 `comingSoon` 模块**：法律研究 / 合同审查 / 法律文书 / 法律知识库 / 项目与团队（后端法律研究、合同审查已就绪，待补前端页面解锁）。
5. **正向清单**：发票系统、数据源适配器、Reranker、文档编辑器、多版本比对均**尚未开发**。

### 9.2 技术债

- **CI 偏弱**（`.github/workflows/ci.yml`）：仅跑后端 `ruff + mypy + pytest`，**无覆盖率门槛、无前端 typecheck/lint、无 E2E**（前端已有 `test:e2e` 但未入 CI）。
- **权限/成员模型**：缺 `organization_members` 与细粒度 `permissions`，当前仅角色级 RBAC。
- **兼容路径**：`api/v1/feedback.py` 以 `X-User-Id` 作 `reviewer_id`；`deps.get_actor` 保留 `X-User-Id` 兼容（未统一到 JWT 主体）。
- **生产镜像内嵌代码**（无 volume mount），部署须“迁移先行再换容器”，回滚成本高。
- **本地文件存储非对象存储**，扩容 / 多实例受限；生产容器内 OCR/weasyprint 可加载性 `UNKNOWN`。
- **`jwt_secret` 默认值**（须确保生产 env 覆盖）；`app/core/config.py` 的 `public_base_url` 等安全默认需生产核对。
- **部署脚本提示文案不一致**：`deploy/deploy.sh` 的完成提示与自检把探针写作 `/api/v1/health`，而实际存活探针 `GET /health` 挂在**根路径**（见 `api/v1/health.py` + `main.py` + nginx `location = /health`），文案待订正。
- **历史索引漂移**：`analytics_events` 等历史索引漂移需单独迁移清理。
- **测试基线**：`pytest tests/ -q --no-cov` → 543 passed / 27 skipped（skipped 为待评估项，非失败）。

---

## 附：主要代码索引

| 关注点 | 相对路径 |
|---|---|
| Agent 图 / 节点 / 状态 / Harness | `backend/app/agent/{graph,nodes,state,harness}.py` |
| Prompt 注册表 / 版本管理 | `backend/app/agent/prompts/registry.yaml`、`backend/app/services/prompt_manager.py` |
| 引证核验 | `backend/app/services/citation_verifier.py` |
| 法律研究 / 合同审查 | `backend/app/services/{legal_research,contract_review}.py` |
| 规范性审核 | `backend/app/services/{gov_rules,gov_review_report,gov_export,report_export}.py`、`backend/app/gov_rules/` |
| 鉴权 / 多租户 | `backend/app/api/deps.py`、`backend/app/services/{auth_service,core_auth_client,tenant}.py` |
| LLM / RAG / 解析 / OCR | `backend/app/tools/{llm,rag,parsers,ocr}.py` |
| API 聚合 / 探针 | `backend/app/api/v1/__init__.py`、`backend/app/api/v1/health.py`、`backend/app/main.py` |
| 前端导航 / 三栏工作台 | `frontend/src/lib/nav.ts`、`frontend/src/components/dashboard/{AppShell,SideNav,ContextPanel}.tsx` |
| 部署 | `deploy/docker-compose.prod.yml`、`deploy/deploy.sh`、`deploy/nginx/conf.d/legalai86.com.cn.conf`、`backend/Dockerfile`、`frontend/Dockerfile` |
