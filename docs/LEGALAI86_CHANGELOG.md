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

---

## 未完成项（滚动记录）

- 数据源适配器：需逐源核实 robots.txt / 使用条款 / 授权后再实现抓取，未核实前
  `legal_sources.authorization_status` 保持 `unknown`，不得宣称 READY。
- Contract Review / 规范性审核增强 / 前端三栏工作台：PHASE 1 后续条目。
- 技术债：CI 缺前端 typecheck/lint 与 E2E；`analytics_events` 等历史索引漂移需单独迁移清理。
