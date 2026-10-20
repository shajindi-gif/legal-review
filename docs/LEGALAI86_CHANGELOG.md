# LegalAI 86 升级变更日志（PHASE 1 起）

> 记录「AI-Native Legal Workspace for China」升级各阶段的可核验产出。
> 基线：`main@5886e89`；升级分支：`upgrade/legalai86-platform`。
> 原则：只有真实通过测试并提交的改动才计入；未验证项一律标注状态，不宣称完成。

---

## PHASE 0 — 代码与部署审计

- 产物：`docs/LEGALAI86_AUDIT.md`（20 项能力 READY/PARTIAL/MISSING/BROKEN/UNKNOWN + 能力矩阵 + 安全检查点 + 未跟踪文件清单 + PHASE 1 清单）。
- 核实结论：合法生产域名仅 `legalai86.com.cn`（`/health` 挂根路径 200）；`legal86.com.cn` 无 DNS 解析，**未做任何 DNS/备案/域名绑定变更**。
- 提交：`1c4f568`

## PHASE 1-1 — Citation Verification Engine（法律依据核验）

- 新增 `app/services/citation_verifier.py`：
  - 四要素逐项核验：法规名称 / 条款编号 / 引用原文 / 时效。
  - 纯函数（`cn_numeral_to_int` / `normalize_article_no` / `text_similarity` /
    `classify_text_match` / `classify_validity`）+ `LawLookup` 抽象（DB/假实现可注入）。
  - 无法核验时返回明确状态与统一提示「暂未找到可核验的权威依据，需要人工复核。」
- 新增 `app/schemas/citation.py`：`CitationClaim` / `CitationVerificationResult` /
  `CitationBatch*` / `CANNOT_VERIFY_MESSAGE`。
- API：`POST /legal/citations/verify`、`POST /legal/citations/verify-batch`。
- 测试：`tests/test_citation_verifier.py` 30 例全绿。
- 提交：`e278cb6`

## PHASE 1-2 — 数据模型扩展迁移

- 迁移 `alembic/versions/0009_legalai86_workspace.py`（`down_revision=0008`，**含完整 downgrade**，
  已实测 upgrade → downgrade → upgrade 往返成功）：
  - 新表 `projects` / `document_versions` / `document_chunks` / `research_sessions` /
    `contract_reviews` / `legal_sources`。
  - 新表统一：UUID 主键 + `organization_id` 多租户隔离 + `created_at/updated_at` +
    `created_by` + `status`；含必要唯一约束与索引。
  - `legal_documents` 补溯源字段：`source_url` / `source_type` / `content_hash` /
    `last_verified_at` / `document_number`（供 CitationVerifier 读取，引证可点击跳转）。
- 新增 ORM：`app/models/workspace.py`（Project/DocumentVersion/DocumentChunk）、
  `app/models/research.py`（ResearchSession）、`app/models/contract.py`（ContractReview）、
  `LegalSource`（`app/models/legal.py`）。
- 新增枚举：`ProjectType/ProjectStatus/DocumentVersionStatus/ResearchStatus/ReviewStance/
  ContractRiskLevel/ContractReviewStatus/LegalSourceType/SourceAuthorizationStatus`。
- 校验：`ruff` 全绿、`mypy`（strict，100 文件）全绿、`pytest` 496 passed（3 个 FAIL 属未跟踪
  `test_report_export.py` 基线问题，非回归）。

## PHASE 1-3 — Legal Research 模块（结构化回答 + 引证可核验）

- 版本化 Prompt：`app/agent/prompts/legal_research/v1.0.0.yaml` + `registry.yaml` 注册
  （`model_tier: strong`，禁止在 YAML 硬编码模型名）。
- 新增 `app/services/legal_research.py`（`LegalResearchService`）：
  - RAG 召回相关条款（唯一可引用依据）→ 版本化 Prompt → LLM 结构化输出。
  - 固定 8 段回答模板并按序组装：【问题】【适用法域及时间】【结论】【法律依据】
    【分析】【适用条件与例外】【风险及待核实事项】【官方来源】，缺失段以占位文本呈现，
    禁止省略段落。
  - 逐条引证走 `CitationVerifier` 核验；核验结果含 `source_url`，前端可点击跳转权威来源。
  - 持久化 `research_sessions`（含 prompt 版本、LLM 用量元数据，可追溯）。
  - 降级策略：RAG 失败不阻塞（提示需人工复核）；LLM 失败落库 `failed` 会话（可追溯）。
- 新增 `app/schemas/research.py`（`ResearchRequest`/`ResearchSection`/`ResearchCitation`/
  `ResearchSessionRead`/列表等）。
- API：`POST /research/sessions`、`GET /research/sessions`、`GET /research/sessions/{id}`
  （JWT 鉴权 + 多租户隔离）。
- 测试：`tests/test_legal_research.py` 10 例全绿（含 API 层）。
- 校验：`ruff`/`mypy` 全绿、`pytest` 506 passed（仅基线 3 个 `test_report_export` FAIL）。
- 连带更新：`tests/test_prompt_manager.py` 中 registry 计数 8→9（新增 legal_research）。

## PHASE 1-4 — Contract Review 模块（风险分级 + 对照修改视图）

- 版本化 Prompt：`app/agent/prompts/contract_review/v1.0.0.yaml` + `registry.yaml` 注册
  （`model_tier: strong`，禁止在 YAML 硬编码模型名）。
- 新增 `app/services/contract_review.py`（`ContractReviewService`）：
  - 解析文本（复用 `app/tools/parsers.py` DOCX/PDF/TXT 保真段落，带段落锚点）→
    版本化 Prompt → LLM 结构化输出。
  - 风险分级固定 5 档（CRITICAL/HIGH/MEDIUM/LOW/INFO），非法值降级为 INFO；
    审查立场甲/乙/中立（`ReviewStance`）；`overall_risk` 取 findings 最高等级。
  - 输出「对照修改视图」= findings（问题清单）+ redline（before→after）；
    **仅建议视图，不伪装 Word 原生修订**；无风险时数组为空，不臆造。
  - 每条 risk 的法律依据（basis）走 `CitationVerifier` 核验，回填
    `basis_status`/`basis_verified`/`basis_source_url`，未核实项显式标注。
  - 持久化 `contract_reviews`（findings/redline JSONB，含 prompt 版本与 LLM 用量元数据）。
  - 降级策略：LLM 失败落库 `failed` 记录（可追溯），摘要置占位文本。
- 新增 `app/schemas/contract.py`（`ContractFinding`/`ContractRedlineItem`/
  `ContractReviewRequest`/`ContractReviewRead`/列表/`highest_risk`/立场与等级中文标签）。
- API：`POST /contract/reviews`（multipart 上传 docx/pdf/txt）、
  `POST /contract/reviews/text`（纯文本）、`GET /contract/reviews`、
  `GET /contract/reviews/{id}`（JWT 鉴权 + 多租户隔离 + 文件类型/大小校验 + OCR 提示）。
- 测试：`tests/test_contract_review.py` 11 例全绿（纯函数 / 编排层 / API 层）。
- 校验：`ruff`/`mypy`（strict，106 文件）全绿、`pytest` 517 passed（仅基线 3 个
  `test_report_export` FAIL）。
- 连带更新：`tests/test_prompt_manager.py` 中 registry 计数 9→10（新增 contract_review）。

## PHASE 1-5 — 规范性文件合法性审核增强（规则包 + 10 段输出 + 导出）

> 硬约束遵守：**不删除/弱化/替换**既有司法局 LangGraph 11 节点工作流；因「未经评估的
> Prompt 变更禁止合并」，本阶段**不修改任何既有 Prompt**，以**确定性（数据驱动、不调
> LLM）**规则包 + 报告 + 导出层叠加在工作流之上。不编造条号/日期，未核实字段留空。

- 新增规则包注册表 `app/gov_rules/registry.yaml` + 规则包
  `national.yaml` / `shanghai.yaml` / `xuhui.yaml`（按地域分层：全国 / 上海市 / 徐汇区）。
  - 字段清单：`rule_id / dimension(A~J) / title / risk_type / severity(critical|high|
    medium|low|info) / law_basis(仅法规名) / law_basis_article / region / effective_date /
    condition / evidence_required(送审材料) / exception / source_url / pending_fields`。
  - 合规诚实性：`law_basis_article: null`、`effective_date: null`（不编造条号/日期），
    登记 `pending_fields`；`legal_review_status: pending_legal_review`、`reviewed_by: null`
    （**未核实前不得把地方规范当全国标准**）。
  - 覆盖维度：national 12 条（A~I）、shanghai 4 条（E/F/G/J）、xuhui 2 条（E/J）。
- 新增 `app/schemas/gov_review.py`：审核维度 A~J、风险 5 档、结论 4 类
  （`no_obvious_violation / needs_revision / major_risk / insufficient_basis`）、
  10 段输出模型（`GOV_REPORT_SECTION_TITLES`）+ `DISCLAIMER` + `MISSING_MATERIAL_NOTE`。
- 新增 `app/services/gov_rules.py`（`GovRulePackManager`）：加载/校验（维度∈A~J、
  severity∈5 档）、`resolve_for_region`（国家通用恒选 + 地域子串匹配）、按维度排序。
- 新增 `app/services/gov_review_report.py`（**确定性、不调 LLM**）：由既有节点结果 + 规则包
  组装 10 段标准报告（关键词映射维度、条款位置、风险统计、材料缺失、待人工核实、
  合法性审核意见初稿）；四类结论判定 + 报告统一附免责声明。
- 新增 `app/services/gov_export.py`：`report_to_markdown`（10 段）；DOCX 复用
  `report_export.markdown_to_docx`；PDF 走 weasyprint（CJK 字体回退）；XLSX 走 openpyxl
  （「条款问题清单」+「材料缺失清单」两表）。
- API（JWT 鉴权 + 多租户 `_load_task`）：
  - `GET /gov/rule-packs` / `GET /gov/rule-packs/resolve?region=` / `GET /gov/rule-packs/{id}`
  - `GET /tasks/{task_id}/gov-report`（10 段标准报告）
  - `GET /tasks/{task_id}/gov-export?format=docx|pdf|xlsx`（意见书 / 报告 / 清单）
  - `GET /tasks/{task_id}/report/export`（通用审查意见书 DOCX）
- 测试：`tests/test_gov_review.py` 22 例全绿（规则包 / 报告 / 导出 / HTTP 四层）。
- 校验：`ruff` 全绿、`mypy`（strict，111 文件）全绿、`pytest` **543 passed**（含此前
  基线 3 个 `test_report_export` 用例，因 `/tasks/{id}/report/export` 已接线而通过）。
- 依赖：`pyproject.toml` 新增 `openpyxl>=3.1.0`（weasyprint 已在），mypy overrides 补
  `openpyxl*` / `weasyprint*`（无 `py.typed`，`ignore_missing_imports`）。

## PHASE 1-6 — 前端统一工作台（三栏 + 11 模块一级导航）

- 新增 `frontend/src/lib/nav.ts`：11 个一级模块的**单一事实源**（工作台 / 法律研究 /
  AI 助手 / 合同审查 / 文件分析 / 规范性文件审核 / 法律文书 / AI 工作流 / 法律知识库 /
  项目与团队 / 管理与设置），每项含 `roles` 角色白名单与 `comingSoon` 标记；
  遵循既有硬约束「未真正实现的模块不展示假入口」——未实现模块置 `comingSoon: true`，
  不可点击并显示「即将」角标。
- 重写 `SideNav.tsx`：由 `nav.ts` 驱动渲染并**按登录角色过滤显隐**
  （合同审查/法律文书/项目与团队仅对 reviewer/supervisor/admin 可见）；
  「更多」分组保留通知 / 报告 / 反馈 / 历史；管理员分组保留管理后台 / 用户反馈；
  底部为套餐计费 / 账户设置（账户设置指向真实 `/account`）。
- 新增 `frontend/src/lib/workspace-context.tsx`：`WorkspaceProvider` / `useWorkspace` /
  `useRegisterContextPanel`（页面挂载时注入第三栏内容、卸载清除）。
- 新增 `frontend/src/components/dashboard/ContextPanel.tsx`：三栏布局第三栏
  （右侧上下文面板，宽 320px；桌面端可开合、移动端隐藏；无页面内容时展示明确空状态，
  不伪造内容）。
- 改造 `AppShell.tsx`：`SideNav + 主区 + ContextPanel` 三栏布局；
  `TopBar.tsx` 新增上下文面板开关（`PanelRight`，`data-testid="context-panel-toggle"`）。
- 校验：`npx tsc --noEmit` 通过；`pnpm build` 通过（21 条路由全部编译成功）。

---

## 未完成项（滚动记录）

- 数据源适配器：需逐源核实 robots.txt / 使用条款 / 授权后再实现抓取，未核实前
  `legal_sources.authorization_status` 保持 `unknown`，不得宣称 READY。
- 规范性审核增强：**PHASE 1-5 已完成**（规则包 + 10 段输出 + 导出）。规则包
  `legal_review_status` 仍为 `pending_legal_review`，`law_basis_article`/`effective_date`
  待逐条核实补全并送法律专业人员审核；`gov-report`/`gov-export` 前端页面未接线。
- 前端：法律研究 / 合同审查 / 法律文书 / 法律知识库 / 项目与团队 仍为 `comingSoon`
  （后端已就绪的模块待补前端页面后解锁入口）；Context Panel 需各页面按需注册内容。
- 技术债：CI 缺前端 typecheck/lint 与 E2E；`analytics_events` 等历史索引漂移需单独迁移清理。
