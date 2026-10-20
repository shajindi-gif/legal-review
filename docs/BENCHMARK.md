# LegalAI 86 /「智审 · LegalReview」评测基准（BENCHMARK）

> 仓库：`legal-review` ｜ 分支：`upgrade/legalai86-platform` ｜ 编制日期：2026-10-20
> **阅读前必读（诚实性声明）**：
> 1. 本文件 §2 列出的首期验收目标（可核验引用准确率 ≥98%、重大问题召回率 ≥90%、文档解析成功率 ≥95%、跨组织数据泄露测试 = 0、关键业务链路测试通过率 = 100%）**均为研发验收目标（目标值）**，**尚未**在由专业人员标注标准答案的评测集上运行评测。**在任何实际评测完成前，不得宣称已达成上述目标。**
> 2. 模型自评不能作为唯一评测依据；法律评测需要由专业人员标注标准答案。
> 3. §3 仅记录**当前可核验的真实工程门禁结果与测试文件清单**，**不含任何准确率/召回率数字**。

---

## 1. 指标定义

以下为 5 个验收指标的**口径定义**（用于后续评测立项；定义本身可核验，但**均未评测**）。

### 1.1 可核验引用准确率

- **口径**：在评测集全部产出引用中，经 `backend/app/services/citation_verifier.py` 四要素核验（法规名称 / 条款编号 / 引用原文 / 时效）通过并标记 `verified=True` 的比例。
- **核验通过判定**（代码事实）：法规名称匹配（归一化等值 / 名称包含 / 相似度 ≥ 0.85）、时效为现行有效、条款定位成功、引用原文吻合（相似度 ≥ 0.999 记 `exact`，≥ 0.90 记 `near`）方为通过；原文缺失但条款层可核验亦记通过（`citation_verifier.py:37-40,340-378`）。
- **不予采信项**：相似度不得等同于法律效力（`citation_verifier.py:5-8` 设计原则）。
- **来源**：`docs/06_EVALUATION_SYSTEM.md` §4「条款引用准确率」（该文定义目标 ≥ 85%，与本文件 ≥ 98% 的目标口径不同，见 §2 说明）。

### 1.2 重大问题召回率

- **口径**：在评测集中被专业人员标注为「重大问题」（如主体越权、违法设定行政许可/处罚/强制、违反上位法等）的风险点，被系统实际识别出的比例 = 命中重大问题数 / 标注重大问题总数。
- **相关实现**：规则包按维度 A~J 与 severity 5 档输出风险（`backend/app/schemas/gov_review.py`、`backend/app/services/gov_rules.py`）；风险分级见 `backend/app/core/constants.py`。
- **说明**：现有 `EvalRunner` 已实现「法规检索准确率（Top-10 召回）」与「风险判断一致性（Cohen's Kappa）」（`backend/app/services/eval_runner.py:108-165`），但其口径与「重大问题召回率」**不完全等同**，本指标需按上表重新定义并配专业标注。

### 1.3 文档解析成功率

- **口径**：上传文档中，解析器成功产出可用结构化结果（`document_json`：`body_paragraphs` / `title` 等）的比例 = 成功解析数 / 上传总数。
- **相关实现**：`backend/app/tools/parsers.py`（txt / docx / pdf-text / OCR 回退）；现有 `EvalRunner` 的字段 F1（`parse_acc`，`eval_runner.py:89-105`）可作字段级参考，但「成功率」为端到端可用/不可用二分口径。
- **已知限制**：OCR 依赖 `paddleocr`/`paddlepaddle`，生产容器可用性 **UNKNOWN**（`docs/LEGALAI86_AUDIT.md` 审计项 #13）。

### 1.4 跨组织数据泄露测试

- **口径**：创建两个不同 `organization_id` 的账号，分别访问同一批资源，断言**任何一方均不可见对方资源**；通过判据 = 泄露条数 **0**。
- **相关实现**：`backend/app/services/tenant.py` 的 `apply_org_filter_with_column()`（应用层强制 `organization_id` 过滤）；冒烟脚本 `backend/scripts/verify_tenant_isolation.py`（另一账号不可见 → 「隔离生效」）。
- **现有覆盖缺口**：隔离仅覆盖 tasks + documents，`notifications` / `feedback` **未接入**（`docs/rectification/00_ISSUE_REGISTER.md` R2-2），故「= 0」在补齐前**不成立**。

### 1.5 关键业务链路测试通过率

- **口径**：对预定义的关键业务链路（上传 → 解析 → 合法性审查 → 报告生成 → 导出）逐条执行，通过判据 = 全部通过（**100%**）。
- **相关实现**：LangGraph 11 节点主图 + 条件路由（`docs/06_EVALUATION_SYSTEM.md` §6.1）；报告导出 `backend/app/services/gov_export.py`、`backend/app/services/report_export.py`。
- **说明**：此为端到端链路口径，**非**单元测试通过率；当前后端 pytest 全绿**不等于**满足该目标（见 §3）。

---

## 2. 首期验收目标（**目标值 · 未评测**）

| 指标 | 首期验收目标 | 状态 |
|------|--------------|------|
| 可核验引用准确率 | **≥ 98%** | **未评测 / 目标值** |
| 重大问题召回率 | **≥ 90%** | **未评测 / 目标值** |
| 文档解析成功率 | **≥ 95%** | **未评测 / 目标值** |
| 跨组织数据泄露测试 | **= 0** | **未评测 / 目标值** |
| 关键业务链路测试通过率 | **= 100%** | **未评测 / 目标值** |

> ⚠️ **上述只是研发验收目标，不得在实际评测前宣称已经达到。**
> 评测必须由**专业人员标注标准答案**，且**模型自评不能作为唯一评测依据**（需人工抽样复核）。

**与既有评测体系的关系说明**：`docs/06_EVALUATION_SYSTEM.md` §4 已给出另一组目标（解析 ≥95% / 检索 ≥90% / 引用 ≥85% / Kappa ≥90% / 报告完整 100% / 幻觉率 ≤5%），并由 `EvalRunner.overall_pass` 门控（`eval_runner.py:48-58`）。二者为**不同来源的目标口径**，本文件 §2 的 5 项为首期验收目标；无论采用哪组，**均未在专业标注集上评测**。

---

## 3. 当前可核验的真实工程统计

以下为研发门禁实测记录（**命令如下，本文件编制时未重跑测试**；数字以仓库门禁记录为准）：

| 门禁 | 实测结果 | 复现命令 |
|------|----------|----------|
| 后端 Lint | `ruff` **全绿** | `cd backend && ruff check .` |
| 后端类型检查 | `mypy app`（**strict**）**全绿** | `cd backend && mypy app` |
| 后端单元测试 | **543 passed / 27 skipped** | `cd backend && pytest tests/ -q --no-cov` |
| 前端类型检查 | `npx tsc --noEmit` **通过** | `cd frontend && npx tsc --noEmit` |
| 前端构建 | `pnpm build` **通过** | `cd frontend && pnpm build` |

> 佐证：`docs/CHANGELOG_LEGALAI86.md` PHASE 1-5 记录「`pytest` **543 passed**」；PHASE 1-6 记录「`npx tsc --noEmit` 通过；`pnpm build` 通过（21 条路由全部编译成功）」。以上为**工程门禁**结果，**不代表** §2 任何业务指标达标。

### 3.1 后端测试文件清单与其静态规模

下表的「用例函数」列为对各文件内 `def test_`（含 `async def test_`）的**静态计数**，用于说明测试规模与覆盖模块；**该计数不是 pytest 用例数**（参数化会放大用例数）。**精确用例数只能引用 §3 表内的总数 543 passed / 27 skipped。**

| 测试文件 | 用例函数（静态计数） | 覆盖模块 |
|----------|:---:|----------|
| `backend/tests/test_auth_service.py` | 27（整模块 skip，见 §5） | AuthService（本地已冻结） |
| `backend/tests/test_eval_runner.py` | 36 | 评测运行器 / 6 大指标 / Golden Dataset |
| `backend/tests/test_prompt_manager.py` | 27 | Prompt 版本管理 / 门控 |
| `backend/tests/test_auth_upgrade.py` | 25 | 鉴权升级 |
| `backend/tests/test_llm.py` | 25 | LLM 网关 |
| `backend/tests/test_harness.py` | 24 | EvidenceHarness / SecurityHarness |
| `backend/tests/test_gov_review.py` | 23 | 规则包 / 10 段报告 / 导出 / HTTP |
| `backend/tests/test_legal_library.py` | 23 | 法规库 |
| `backend/tests/test_embedding.py` | 23 | 向量化 |
| `backend/tests/test_payment_service.py` | 19 | 支付业务（下单/幂等/退款） |
| `backend/tests/test_nodes_legal_retrieve.py` | 19 | legal_retrieve 节点 |
| `backend/tests/test_graph.py` | 18 | LangGraph 编排 |
| `backend/tests/test_rag.py` | 18 | RAG 混合召回 |
| `backend/tests/test_citation_verifier.py` | 17 | 法律依据核验引擎 |
| `backend/tests/test_legal_splitter.py` | 17 | 法规切分 |
| `backend/tests/test_auth_api.py` | 14 | 鉴权 API |
| `backend/tests/test_verification.py` | 15 | 验证码 |
| `backend/tests/test_eval_api.py` | 13 | 评测 API |
| `backend/tests/test_legal_api.py` | 13 | 法规 API |
| `backend/tests/test_quota_service.py` | 13 | 额度 |
| `backend/tests/test_contract_review.py` | 11 | 合同审查 |
| `backend/tests/test_registry.py` | 11 | Prompt registry |
| `backend/tests/test_alipay_provider.py` | 10 | 支付宝 Provider |
| `backend/tests/test_legal_research.py` | 10 | 法律研究 |
| `backend/tests/test_metrics.py` | 10 | 指标采集 |
| `backend/tests/test_password_hasher.py` | 10 | 密码散列 |
| `backend/tests/test_phone_normalize.py` | 10 | 手机号归一化 |
| `backend/tests/test_feedback.py` | 9 | 反馈闭环 |
| `backend/tests/test_feedback_api.py` | 9 | 反馈 API |
| `backend/tests/test_report_export.py` | 8 | 报告 docx 导出 |
| `backend/tests/test_sandbox.py` | 8 | 文件沙箱 |
| `backend/tests/test_unified_auth.py` | 8 | 统一鉴权 |
| `backend/tests/test_audit_api.py` | 6 | 审计 API |
| `backend/tests/test_rate_limit.py` | 5 | 限流 |
| `backend/tests/test_analytics_api.py` | 4 | 埋点 API |
| `backend/tests/test_metrics_api.py` | 4 | 指标 API |
| `backend/tests/test_nodes_report_generation.py` | 4 | 报告生成节点 |
| `backend/tests/test_parsers.py` | 4 | 文档解析 |

> 注：静态计数合计为 550，**少于** pytest 收集到的 570（543 passed + 27 skipped），差异主要来自**参数化用例**（一个测试函数展开为多条用例），故**不得以本表反推用例数**；精确用例数一律以 §3 表内总数（543 passed / 27 skipped）为准。

---

## 4. 评测方法论

- **标准答案来源**：评测集（Golden Dataset）的 `expected_json` / `expected_status` 必须由**法律专业人员标注**，不得由模型生成或自评填答。数据结构见 `docs/06_EVALUATION_SYSTEM.md` §3.2；导入走 `GoldenDatasetService.batch_import()`（`backend/app/services/eval_runner.py:232-259`），API 为 `POST /api/v1/eval/golden/import`（`backend/app/api/v1/eval.py:118-143`）。
- **模型自评不可作唯一依据**：任何自动指标（含 `EvalRunner` 的 6 大指标）仅作为初筛；须叠加**人工抽样复核**。
- **抽样与人工复核**：对自动判为通过/失败的关键条目按比例抽样，由专业人员复核并记录分歧；分歧条目回填评测集（`docs/06_EVALUATION_SYSTEM.md` §6.2 人工反馈 Loop）。
- **指标计算实现（可核验）**：`backend/app/services/eval_runner.py` 实现了字段 F1、Top-10 召回、引用准确率、Cohen's Kappa、报告完整性、幻觉率；`overall_pass` 门控见 `eval_runner.py:48-58`。评测结果写入 `eval_runs` 表。
- **门控与 Prompt 变更**：Prompt 变更须过评测门控（`EvalRunner.check_gate`，`eval_runner.py:402-410`）。
- **链路与隔离验证**：跨组织隔离用 `backend/scripts/verify_tenant_isolation.py`；端到端链路需另行设计脚本（现无统一链路评测脚本）。
- **诚实性纪律**：不得伪造测试通过、不得伪造引用、未评测即标注「未评测」。

---

## 5. 已知失败 / 跳过用例与原因

### 5.1 27 skipped 的核实结论（**已核实**）

- pytest 报告 `27 skipped`。仓库中对 `skip` / `skipif` / `xfail` 做全仓检索，**唯一**的模块级跳过标记为：
  `backend/tests/test_auth_service.py` 顶部
  ```python
  pytestmark = pytest.mark.skip(
      reason="Strangler 双跑：本地 AuthService 已冻结，由 yance-core packages/auth 承担",
  )
  ```
  （`backend/tests/test_auth_service.py:35-37`）
- 该文件含 **27** 个 `def test_` 函数（静态计数），与「27 skipped」数量一致；其余测试文件**无** `skipif` / `xfail` 标记（`backend/tests/test_legal_research.py` / `test_contract_review.py` / `test_nodes_legal_retrieve.py` / `test_prompt_manager.py` 中的 “skip” 仅为**用例命名**，非跳过标记）。
- **结论**：27 skipped 与 `test_auth_service.py` 的模块级跳过高度吻合，**原因明确为鉴权逻辑已迁移至 `yance-core packages/auth`，本地模块冻结保留供回滚**。
- **保留意见**：若存在 pytest 参数化或收集器层面的其它跳过来源，本文件**未逐一定位**；如需 100% 确认，需在可运行环境中执行 `pytest tests/ -q --no-cov -rs` 查看逐条 skip 原因。

### 5.2 历史上的失败用例

- `docs/CHANGELOG_LEGALAI86.md` 记载 PHASE 1-2 至 1-4 期间存在基线 3 个 `test_report_export.py` 用例 FAIL（属未跟踪文件的基线问题，非回归）；PHASE 1-5 因 `/tasks/{id}/report/export` 端点接线完成，**该 3 例随之通过**，后端全量达 543 passed。

> 状态：跳过原因**已核实**；「是否存在其它跳过来源」为**未逐一定位**。

---

## 6. 待解决问题

| # | 问题 | 证据 | 影响 |
|---|------|------|------|
| B1 | 无经专业人员标注的评测集与评测记录（`eval_runs` 无真实评测数据可查） | `docs/06_EVALUATION_SYSTEM.md` §3；`eval_runner.py`（无执行器时用 expected 作 mock） | 5 项验收指标**无法评测** |
| B2 | 跨租户隔离未覆盖 `notifications` / `feedback` | 整改台账 R2-2 | 「泄露 = 0」在补齐前不成立 |
| B3 | 无统一端到端链路评测脚本 | 仓库 `scripts/` 仅有租户隔离冒烟 | 「链路通过率 100%」缺执行载体 |
| B4 | OCR 生产可用性 UNKNOWN | `docs/LEGALAI86_AUDIT.md` #13 | 影响解析成功率指标可测性 |
| B5 | `EvalRunner` 与首期 5 指标口径未对齐 | `eval_runner.py` vs 本文 §1 | 需先在评测集上统一口径 |
| B6 | 规则包条号/生效日待专业核实 | `CHANGELOG_LEGALAI86.md` PHASE 1-5 | 影响引用准确率的「正确答案」权威性 |

---

## 7. 下一阶段评测计划

1. **建标准答案集**：由法律专业人员标注 Golden Dataset（覆盖主体/程序/内容/边界等类别），落库 `golden_dataset`；标注过程与分歧留存可追溯（对应 §4）。
2. **对齐指标口径**：将 §1 的 5 项指标映射到 `EvalRunner` 计算函数或补充计算实现，明确每一项的分子/分母与通过判据。
3. **补隔离覆盖**：完成 `notifications` / `feedback` 的多租户隔离（R2-2），再执行 `verify_tenant_isolation.py` 全量断言泄露 = 0。
4. **建链路评测脚本**：定义关键业务链路清单（上传→解析→审查→报告→导出）并逐条执行，记录通过/失败。
5. **正式评测与复核**：在专业标注集上运行评测，导出自动指标 → 人工抽样复核 → 记录分歧与修正；**在此之前，§2 全部指标保持「未评测 / 目标值」状态**。
6. **门控接入**：评测通过后方可将其作为 Prompt 变更门控依据（`EvalRunner.check_gate`）。

---

**本基准文档终止。** 除 §3 的工程门禁与 §5 的跳过原因外，本文件**不含**任何已评测的业务准确率/召回率数字；一切验收指标均为**待评测目标**。
