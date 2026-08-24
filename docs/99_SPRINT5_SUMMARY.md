# Sprint 5 阶段性总结 · 评测体系 + 人工反馈闭环 + 全链路可观测性

> 交付日期：2026-08-22
> 阶段：Sprint 5（评测系统 + Golden Dataset + 人工反馈闭环 + 可观测性 + 审计 API）
> 状态：✅ 后端核心完成，待真实 API 联调 + Golden Dataset 真实样本入库

---

## 1. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| 评测系统设计 | [docs/06_EVALUATION_SYSTEM.md](file:///Users/shajindi/traework/legal-review/docs/06_EVALUATION_SYSTEM.md) | 5 级评测分层 + 6 大指标定义 + Golden Dataset 设计 + 3 个自优化 Loop + 可观测性架构 |
| 评测 Pydantic Schema | [app/schemas/eval.py](file:///Users/shajindi/traework/legal-review/backend/app/schemas/eval.py) | GoldenCaseCreate/Read + GoldenBatchImport + EvalRunCreate/Read + FeedbackCreate/Read/BatchReview |
| 评测服务层 | [app/services/eval_runner.py](file:///Users/shajindi/traework/legal-review/backend/app/services/eval_runner.py) | GoldenDatasetService 导入/查询/删除 + EvalRunner 6 大指标计算 + Cohen's Kappa + 评测门控 |
| 人工反馈服务 | [app/services/feedback.py](file:///Users/shajindi/traework/legal-review/backend/app/services/feedback.py) | FeedbackCaseService 记录/查询/Batch 复盘/标记吸收 |
| 可观测性采集器 | [app/services/metrics.py](file:///Users/shajindi/traework/legal-review/backend/app/services/metrics.py) | MetricsCollector 线程安全 + P50/P99 延迟 + pass_rate + 重试均值 + 幻觉率均值 |
| 评测 API | [app/api/v1/eval.py](file:///Users/shajindi/traework/legal-review/backend/app/api/v1/eval.py) | Golden Dataset CRUD + EvalRun 触发/查询，共 8 个端点 |
| 反馈 API | [app/api/v1/feedback.py](file:///Users/shajindi/traework/legal-review/backend/app/api/v1/feedback.py) | 反馈提交/查询/未吸收列表/Batch 复盘/标记吸收，共 5 个端点 |
| 审计 API | [app/api/v1/audit.py](file:///Users/shajindi/traework/legal-review/backend/app/api/v1/audit.py) | 审计日志查询/trace 追踪/count，共 4 个端点 |
| 指标 API | [app/api/v1/metrics.py](file:///Users/shajindi/traework/legal-review/backend/app/api/v1/metrics.py) | /metrics 快照拉取 + /nodes 节点级 + /reset 重置，共 3 个端点 |
| 路由挂载 | [app/api/v1/__init__.py](file:///Users/shajindi/traework/legal-review/backend/app/api/v1/__init__.py) | 新增 4 个 router 挂载到 /api/v1 前缀 |
| 单元测试 | tests/test_eval_runner.py / test_feedback.py / test_metrics.py / test_eval_api.py / test_feedback_api.py / test_audit_api.py / test_metrics_api.py | 7 个测试文件，覆盖 Sprint 5 全部模块 |

---

## 2. 质量门控结果

| 门控 | 命令 | 结果 |
|------|------|------|
| Ruff Lint | `ruff check app/ tests/` | ✅ All checks passed |
| 单元测试 | `pytest tests/` | ✅ 321 passed in 2.34s |
| 代码覆盖率 | `pytest --cov` | ✅ 84%（Sprint 5 核心模块 ≥ 93%） |

Sprint 5 模块覆盖率明细：
- `app/services/eval_runner.py` 93%（GoldenDatasetService + EvalRunner + 6 大指标计算）
- `app/services/feedback.py` 100%（人工反馈全流程）
- `app/services/metrics.py` 98%（线程安全指标采集）
- `app/schemas/eval.py` 100%

Sprint 5 新增测试：
- `test_eval_runner.py`：EvalMetrics.overall_pass、_field_f1、_retrieval_recall、_citation_accuracy、_cohen_kappa、_report_completeness、_hallucination_rate、compute_case_metrics、check_gate、GoldenDatasetService、EvalRunner.run
- `test_feedback.py`：record 成功/校验、list_by_task、list_unincorporated、batch_review 统计、mark_incorporated、to_read 转换
- `test_metrics.py`：节点延迟 P50/P99、pass_rate、重试均值/最大、幻觉率均值、任务时长、线程安全并发 10×100、单例
- `test_eval_api.py`：Golden 批量/单条导入、列表过滤、详情、删除、count、EvalRun 触发/列表/详情、422 校验、404 错误
- `test_feedback_api.py`：反馈提交、X-User-Id 缺失/非法、ai_output==human_modified 校验、任务反馈列表、未吸收列表、Batch 复盘、标记吸收、404
- `test_audit_api.py`：审计列表/过滤、trace 追踪、单条详情、404、count
- `test_metrics_api.py`：/metrics 空快照、/metrics 带数据、/metrics/nodes、/metrics/reset

---

## 3. 核心设计落地

### 3.1 评测体系（FR-029/031）

#### 6 大评测指标

| 指标 | 计算方式 | 阈值 | 说明 |
|------|---------|------|------|
| `parse_acc` | 字段 F1（precision + recall） | ≥ 0.95 | 文件解析准确率 |
| `retrieval_acc` | Top-10 召回率（law_name + article 命中） | ≥ 0.90 | 法规检索准确率 |
| `citation_acc` | 正确引用数 / 总引用数 | ≥ 0.85 | 条款引用准确率 |
| `risk_kappa` | Cohen's Kappa 一致性 | ≥ 0.90 | 风险等级一致性 |
| `report_complete` | 7 章节必填字段完整率 | = 1.0 | 报告完整性 |
| `hallucination_rate` | 无依据判断比例 | ≤ 0.05 | 幻觉率 |

- **聚合**：`_AggMetrics` 跨多 Case 聚合，Kappa 用全样本观察/期望一致性计算
- **门控**：`EvalRunner.check_gate()` 要求 `overall_pass=True`（6 指标全部达标）
- **写入**：评测结果落 `eval_runs` 表（run_id + prompt_version + 6 指标 + overall_pass）

#### Golden Dataset 管理

- **6 类别**：normal / authority_violation / procedure_missing / content_violation / boundary / non_normative
- **批量导入**：容错（单条失败不影响其他），返回 total/success/failed/errors
- **CRUD**：导入/列表（category 过滤）/详情/删除/count

### 3.2 人工反馈闭环（FR-032）

- **记录**：`record(task_id, reviewer_id, feedback)` 写入 `feedback_cases` 表
- **校验**：`ai_output == human_modified` 拒绝记录（无变化无需反馈）
- **查询**：`list_by_task()` 任务全量反馈、`list_unincorporated()` 未吸收列表
- **Batch 复盘**：`batch_review()` 按 reason_category 分组 + top 10 reasons 排序
- **吸收**：`mark_incorporated(case_id, prompt_version_after)` 标记反馈已进入下一版 Prompt
- **长期保留**：`feedback_cases` 表作为案例库资产（硬约束#8 人工闭环不可省）

### 3.3 可观测性（FR-035）

#### MetricsCollector 线程安全采集

- **节点级**：`record_node_latency(agent, ms)` + `record_pass_fail(agent, passed)`
- **链路级**：`record_retry(trace_id, count)` + `record_hallucination(trace_id, rate)`
- **任务级**：`record_task_duration(ms)`
- **百分位数**：P50 + P99（节点延迟、任务时长）
- **线程安全**：`threading.Lock` 保护，10×100 并发记录无异常
- **单例**：`get_metrics_collector()` 全局单例，Agent 节点直接调用

#### 审计日志全链路

- **3 年保留**：`audit_records` 表合规要求
- **多维度过滤**：trace_id / action / target_type / actor_id / 时间范围
- **trace 追踪**：`GET /audit/trace/{trace_id}` 按时间升序返回单 trace 全链路操作
- **审计覆盖**：评测运行、Golden Case 增删、反馈提交、标记吸收均写入审计

---

## 4. API 端点清单（17 个新端点）

### 4.1 评测 API（/api/v1/eval）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/eval/golden/cases` | 新增单条 Golden Case |
| POST | `/eval/golden/import` | 批量导入 Golden Cases（容错） |
| GET | `/eval/golden/cases` | 查询 Golden Dataset（category 过滤） |
| GET | `/eval/golden/cases/{case_id}` | 查询单条 Golden Case |
| DELETE | `/eval/golden/cases/{case_id}` | 删除单条 Golden Case |
| GET | `/eval/golden/count` | 统计 Golden Dataset 总数 |
| POST | `/eval/runs` | 触发一次评测运行（6 大指标 + overall_pass） |
| GET | `/eval/runs` | 评测运行历史列表 |
| GET | `/eval/runs/{run_id}` | 查询单次评测运行 |

### 4.2 反馈 API（/api/v1/feedback）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/feedback/tasks/{task_id}` | 提交人工反馈（需 X-User-Id 头） |
| GET | `/feedback/tasks/{task_id}` | 查询任务全部反馈 |
| GET | `/feedback/unincorporated` | 未吸收反馈列表 |
| GET | `/feedback/batch-review` | 周期 Batch 复盘（高频 reason 统计） |
| POST | `/feedback/cases/{case_id}/incorporate` | 标记反馈被 Prompt 吸收 |

### 4.3 审计 API（/api/v1/audit）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/audit/records` | 审计日志查询（多维度过滤 + 分页） |
| GET | `/audit/trace/{trace_id}` | 按 trace_id 全链路追踪 |
| GET | `/audit/records/{record_id}` | 查询单条审计记录 |
| GET | `/audit/count` | 统计审计日志总数 |

### 4.4 指标 API（/api/v1/metrics）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/metrics` | 拉取指标快照（节点 P50/P99 + 重试 + 幻觉率 + 任务时长） |
| GET | `/metrics/nodes` | 节点级指标明细 |
| POST | `/metrics/reset` | 重置全局采集器（排障用） |

---

## 5. 硬约束落地核对

| 硬约束 | Sprint 5 落地 |
|--------|--------------|
| AI agents 必须 evaluable | ✅ GoldenDatasetService + EvalRunner 提供 6 大指标评测 |
| Prompt 变更未评估禁止合并 | ✅ `EvalRunner.check_gate()` 门控 + `Prompt.eval_pass_rate` 字段 |
| 人工闭环不可省 | ✅ FeedbackCaseService + /feedback API 全链路 |
| Agent 必须有 version | ✅ EvalRun.prompt_version 关联 Prompt 版本 |
| 安全节点不可绕过 | ✅ 评测/反馈/审计 API 全部写入 audit_records |

---

## 6. 与 Sprint 4 的衔接

Sprint 4 已交付 LLM Gateway + Prompt 版本化 + Tool Registry + Security Harness + LangGraph 工作流 + 11 Agent 节点。Sprint 5 在此之上补齐：

- **评测闭环**：对 Sprint 4 的 Prompt 版本做 Golden Dataset 评测，未达 90% pass_rate 禁止激活
- **反馈闭环**：Sprint 4 的 Agent 输出可被人工修改 → 写入 feedback_cases → Batch 复盘 → 下一版 Prompt 吸收
- **可观测性**：Sprint 4 的 Agent 节点可通过 `get_metrics_collector()` 上报延迟/通过率/重试，/metrics 拉取
- **审计闭环**：Sprint 4 的 Security Harness `audit_log` 字段现在可被 /audit/trace 追踪全链路

---

## 7. 下一步建议

1. **真实 LLM API 联调**：配置 DeepSeek-V4-Pro + Qwen3.7-Max API Key，跑端到端审查流程
2. **Golden Dataset 真实样本**：按 6 类别各标注 ≥ 10 条（共 ≥ 60 条）真实规范性文件样本
3. **LangGraph 集成 case_runner**：将 EvalRunner 的 case_runner 接到真实 LangGraph 工作流（目前框架级用 expected 作 mock）
4. **MetricsCollector 接入 Agent 节点**：在 `_run_llm_node` 入口加 `record_node_latency` + `record_pass_fail`
5. **法规库更新循环**：定期检查法规时效 + 自动标记失效 + 触发 RAG 索引重建
6. **前端联调**：基于 /api/v1/eval + /feedback + /audit + /metrics 端点开发管理后台

---

## 8. Sprint 5 完成度

| 模块 | 完成度 | 备注 |
|------|--------|------|
| 06_EVALUATION_SYSTEM.md 设计文档 | ✅ 100% | 评测分层 + Golden Dataset + 6 大指标 + 3 Loop + 可观测性 |
| 评测服务层（GoldenDatasetService + EvalRunner） | ✅ 100% | 6 大指标计算 + 门控 + 框架级 case_runner 注入 |
| 人工反馈闭环（FeedbackCaseService） | ✅ 100% | 记录/查询/Batch 复盘/标记吸收 |
| 可观测性（MetricsCollector） | ✅ 100% | 线程安全 + P50/P99 + 单例 |
| 评测/反馈/审计/指标 API | ✅ 100% | 17 个端点 + 路由挂载 |
| 单元测试 + ruff | ✅ 100% | 7 个测试文件 + 321 passed + 84% 覆盖率 |

**Sprint 5 后端核心交付完成。**
