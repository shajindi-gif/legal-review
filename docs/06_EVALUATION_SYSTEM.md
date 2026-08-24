# 评测系统设计 · 行政规范性文件智能合法性审查 Agent 系统

> 文档版本：v1.0.0
> 最后更新：2026-08-22
> 责任人：FDE 交付负责人
> Sprint：Sprint 5（验证层 - 评测体系 + 证据链 + 人工闭环 + 可观测性）
> 依据：02_SYSTEM_ARCHITECTURE.md 第 4/6/9 节、03_DATABASE_DESIGN.md T08-T12、01_PRD.md FR-029/031/032/035

---

## 1. 设计目标

| 目标 | 指标 | 来源 |
|------|------|------|
| 证据覆盖率 100% | 每条风险判断必附法规条款 + 原文 + 解释 | FR-029 / 硬约束#6 |
| 幻觉率 ≤ 5% | 无依据判断比例 | NFR / Sprint 5 验收 |
| 评测集 ≥ 100 份 | 覆盖 6 大审查维度 | NFR-011 |
| 人工闭环不可省 | 人工修改回流案例库 → 优化 Prompt | FR-031/032 / 硬约束#8 |
| 全链路可追溯 | trace_id 贯穿 + 审计日志保留 3 年 | FR-035 / 硬约束#7 |

---

## 2. 评测分层架构

| 层级 | 评测对象 | 指标 | 触发时机 | 实现模块 |
|------|----------|------|----------|----------|
| L1 节点级 | 单 Agent 输出 | Schema 合规率 / 置信度分布 / EvidenceHarness 缺字段率 | 每次节点执行 | EvidenceHarness.enforce_silent |
| L2 链路级 | 多 Agent 协作 | Retry 次数 / 链路总耗时 / 路由正确率 | 每次审查任务 | graph.py 条件路由日志 |
| L3 任务级 | 端到端审查 | 风险点召回率 / 准确率 / 人工修改率 | 每次任务完成 | FeedbackCase 对比 |
| L4 评测集级 | Golden Dataset | 6 大指标（见 §4） | Prompt 变更 / 定期回归 | EvalRunner |
| L5 线上 | 线上任务 | 通过率 / 人工修改率 / 幻觉率采样 | 实时 + 周期 Batch | MetricsCollector |

---

## 3. Golden Dataset 设计

### 3.1 类别分布（100 份）

| 类别 | GoldenCategory | 数量 | 预期结果 | 说明 |
|------|---------------|------|---------|------|
| 标准规范性文件 | normal | 20 | PASS | 合法文件，应通过全部审查 |
| 主体违法 | authority_violation | 15 | FAIL - 主体 | 制定主体不合法 / 越权 |
| 程序缺失 | procedure_missing | 15 | RISK - 程序 | 五项程序要素缺失 |
| 内容违法 | content_violation | 30 | FAIL/RISK - 内容 | 六类违法情形 |
| 边界灰色 | boundary | 15 | 置信度 < 0.8 | 测试模型边界判断能力 |
| 非规范性文件 | non_normative | 5 | 分类为否 | 不进入审查流程 |
| **合计** | | **100** | | 覆盖 6 大审查维度 |

### 3.2 数据结构

每条 Golden Case（`golden_dataset` 表 T11）：
```json
{
  "case_name": "某县违规设置行政许可",
  "category": "content_violation",
  "input_file_path": "/data/golden/case_042.docx",
  "expected_json": {
    "is_normative": true,
    "authority": { "status": "pass" },
    "procedure": { "status": "pass" },
    "content": {
      "status": "fail",
      "risks": [
        {
          "risk_type": "违法设置行政许可",
          "law_name": "行政许可法",
          "article": "第十五条",
          "severity": "high"
        }
      ]
    },
    "overall_status": "fail"
  },
  "expected_status": "fail",
  "notes": "越权设定行政许可前置条件"
}
```

### 3.3 导入流程

```
法规库管理员上传 Golden Cases（JSON/CSV）
  → GoldenDatasetService.batch_import()
  → 校验 expected_json schema 合规
  → 写入 golden_dataset 表
  → 返回导入统计（成功/失败/去重）
```

---

## 4. 6 大评测指标

| 指标 | 目标 | 计算方法 | 数据来源 |
|------|------|---------|---------|
| 文件解析准确率 | ≥ 95% | 字段 F1 = 2×(precision×recall)/(precision+recall) | document_json vs expected_json 字段对比 |
| 法规检索准确率 | ≥ 90% | Top-10 召回率 = |命中条款 ∩ 标注条款| / |标注条款| | legal_context vs expected_risks |
| 条款引用准确率 | ≥ 85% | 条款精确匹配率 = 正确引用数 / 总引用数 | AgentOutput.evidences vs expected |
| 风险判断一致性 | ≥ 90% | Cohen's Kappa = (p_o - p_e) / (1 - p_e) | overall_status + risk_types vs expected |
| 报告完整性 | 100% | 必填字段完整率 = 完整字段数 / 应填字段数 | report_markdown 7 章节检查 |
| 幻觉率 | ≤ 5% | 无依据判断比例 = 无证据风险数 / 总风险数 | risks 无 evidence 或 law_name 为空 |

### 4.1 指标计算实现

```python
@dataclass
class EvalMetrics:
    parse_acc: float          # L1
    retrieval_acc: float      # L2
    citation_acc: float       # L3
    risk_kappa: float         # L4 (Cohen's Kappa)
    report_complete: float    # L5
    hallucination_rate: float # L6
    overall_pass: bool        # 全部达标 → True
```

### 4.2 评测门控规则

```
overall_pass = (
    parse_acc >= 0.95
    AND retrieval_acc >= 0.90
    AND citation_acc >= 0.85
    AND risk_kappa >= 0.90
    AND report_complete >= 1.0
    AND hallucination_rate <= 0.05
)
```

Prompt 变更激活（`PromptManager.activate()`）：
- `overall_pass == True` 且 `overall_pass_rate >= min_eval_pass_rate`（默认 90%）
- 否则拒绝激活，旧版本保持 active

---

## 5. EvalRunner 评测管线

### 5.1 流程

```
1. 加载 Golden Dataset（按 category 过滤可选）
2. 对每条 Case：
   a. 解析输入文件 → document_json
   b. 运行 LangGraph 审查流程 → AgentOutput 全链
   c. 对比 expected_json → 计算 6 大指标
   d. 记录单条结果（pass/fail + diff）
3. 汇总指标 → 写入 eval_runs 表
4. 输出评测报告（JSON + Markdown）
5. 触发 Prompt 门控判断
```

### 5.2 服务接口

```python
class EvalRunner:
    """评测运行器 - 跑 Golden Dataset 评测。"""

    async def run(
        self,
        *,
        prompt_version: str,
        categories: list[GoldenCategory] | None = None,
        max_cases: int | None = None,
    ) -> EvalRun:
        """运行评测，返回 EvalRun 记录（含 6 大指标）。"""

    async def compute_metrics(
        self, actual: dict, expected: dict,
    ) -> EvalMetrics:
        """计算单条 Case 的 6 大指标。"""
```

### 5.3 评测记录（eval_runs 表 T12）

| 字段 | 类型 | 说明 |
|------|------|------|
| run_id | UUID | 评测批次 ID |
| prompt_version | str | 被评测的 Prompt 版本 |
| total_cases | int | 评测总数 |
| parse_acc | float | 解析准确率 |
| retrieval_acc | float | 检索准确率 |
| citation_acc | float | 引用准确率 |
| risk_kappa | float | 风险一致性 Kappa |
| report_complete | float | 报告完整性 |
| hallucination_rate | float | 幻觉率 |
| overall_pass | bool | 全部达标 |
| raw_result_path | str | 原始结果 JSON 路径 |

---

## 6. 三类 Loop 自优化机制

### 6.1 Loop 1：审核质量 Loop（Sprint 4 已实现）

```
AI 审核 → EvidenceHarness 发现缺证据 → Retry → legal_retrieve 重新检索 → 重新判断
迭代上限：MAX_ITER = 5
超限 → human_fallback 兜底
```

**触发条件**：
- Evidence 缺 law_name / article / original_text
- 置信度 < 0.7
- evidence_verify_router 判断 FAIL

**Sprint 4 落地**：`evidence_verify_router` + `EvidenceHarness.enforce_silent()` + Retry Edge

### 6.2 Loop 2：人工反馈 Loop（Sprint 5 实现）

```
人工修改 AI 意见 → 记录到 feedback_cases → 周期 Batch 复盘 → 优化 Prompt → 重新评测
```

**流程**：
1. 审查员在 `human_review` 节点对 AI 意见批注、修改、签发
2. `FeedbackCaseService.record()` 写入 feedback_cases（ai_output vs human_modified + modify_reason）
3. 周期性 Batch：统计 modify_reason 高频原因 → 生成 Prompt 优化建议
4. Prompt 变更必须过 Golden Dataset 评测（门控）
5. 评测通过 → 激活新版本 → 旧版本 deprecated

**FeedbackCase 数据结构**（feedback_cases 表 T09）：
```json
{
  "task_id": "uuid",
  "reviewer_id": "uuid",
  "agent_name": "content_review",
  "section": "content",
  "ai_output": { "status": "pass", "risks": [] },
  "human_modified": { "status": "fail", "risks": [...] },
  "modify_reason": "AI 遗漏违法设置行政许可",
  "reason_category": "missed_risk",
  "incorporated": false,
  "prompt_version_after": null
}
```

### 6.3 Loop 3：法规更新 Loop（Sprint 5 实现触发机制）

```
新增法规文件 → 自动解析 → 更新知识库 → 重新测试历史案例 → 标记需复查项
```

**触发**：
- 法规库管理员手动触发（`POST /api/v1/legal/documents` 导入新法规）
- 每日定时检查法规库版本（`check_time_validity` + 自动状态变更）

**Sprint 5 实现**：
- 法规导入后触发 `EvalRunner.run()` 回归测试
- 对历史 feedback_cases 中 `incorporated=false` 的案例重测
- 标记需复查任务（`review_tasks.need_recheck = true`）

---

## 7. 可观测性设计

### 7.1 指标采集

| 指标 | 采集点 | 存储 | 用途 |
|------|--------|------|------|
| node_latency_p50/p99 | _run_llm_node start/end | MetricsCollector 内存 + 周期 flush | 节点性能监控 |
| retry_count | evidence_verify_router 迭代计数 | ReviewState.iteration | 重试质量 |
| pass_rate | 各节点 node_status 统计 | EvalRun + MetricsCollector | 节点质量 |
| hallucination_rate | risks 无 evidence 比例 | EvalRun.hallucination_rate | 幻觉监控 |
| task_duration | 任务 start → END | ReviewTask + MetricsCollector | 端到端性能 |

### 7.2 MetricsCollector 实现

```python
class MetricsCollector:
    """内存指标采集器 - 线程安全 + 周期 flush。"""

    def record_node_latency(self, agent: str, duration_ms: int) -> None: ...
    def record_retry(self, trace_id: str, count: int) -> None: ...
    def record_pass_fail(self, agent: str, passed: bool) -> None: ...
    def record_hallucination(self, trace_id: str, rate: float) -> None: ...
    def snapshot(self) -> dict: ...  # 供 /metrics API 拉取
```

### 7.3 日志规范

- 结构化 JSON 日志（`structlog`）
- trace_id 贯穿全链路（`bind_trace_id()`）
- Agent 节点入口/出口审计（SecurityHarness.audit_log）
- 审计记录入 `audit_records` 表（保留 3 年，合规要求）

### 7.4 告警阈值

| 告警 | 阈值 | 动作 |
|------|------|------|
| 任务超时 | > 5 分钟 | 标记 need_human_review |
| Retry 超限 | iteration > 5 | 进入 human_fallback |
| 幻觉率突增 | 线上采样 > 10% | 触发 Prompt 回滚 |
| 法规库版本异常 | check_time_validity 失败 | 标记法规失效 |

---

## 8. 数据模型（T08-T12，已建表）

| 表 | 模型 | Sprint 5 用途 |
|----|------|---------------|
| T08 audit_records | AuditRecord | AuditService.log() 全链路审计 |
| T09 feedback_cases | FeedbackCase | FeedbackCaseService 人工反馈闭环 |
| T10 prompts | Prompt | PromptManager.sync_to_db() 版本管理 |
| T11 golden_dataset | GoldenDataset | GoldenDatasetService 评测集管理 |
| T12 eval_runs | EvalRun | EvalRunner 评测记录 |

> DB 模型已在 `app/models/platform.py` 定义，migration 0001 已建表。

---

## 9. API 契约

### 9.1 评测集管理

```
POST   /api/v1/eval/datasets          批量导入 Golden Cases
GET    /api/v1/eval/datasets          列表（category 过滤）
DELETE /api/v1/eval/datasets/{id}     删除单条
```

### 9.2 评测运行

```
POST   /api/v1/eval/runs              触发评测（prompt_version + categories 过滤）
GET    /api/v1/eval/runs              评测记录列表
GET    /api/v1/eval/runs/{run_id}     评测详情（含 6 大指标）
GET    /api/v1/eval/runs/{run_id}/report  评测报告（Markdown）
```

### 9.3 人工反馈

```
POST   /api/v1/tasks/{task_id}/feedback   提交人工反馈（FR-032）
GET    /api/v1/tasks/{task_id}/feedback   查看反馈历史
POST   /api/v1/feedback/batch-review      周期 Batch 复盘（admin）
```

### 9.4 审计与指标

```
GET    /api/v1/audit/records            审计记录查询（trace_id / actor 过滤）
GET    /api/v1/metrics                  实时指标快照（MetricsCollector.snapshot）
```

---

## 10. 服务层接口设计

### 10.1 GoldenDatasetService

```python
class GoldenDatasetService:
    async def batch_import(self, cases: list[dict]) -> dict: ...
    async def list_cases(self, category: str | None = None) -> list[GoldenDataset]: ...
    async def get_case(self, case_id: UUID) -> GoldenDataset: ...
    async def delete_case(self, case_id: UUID) -> None: ...
```

### 10.2 EvalRunner

```python
class EvalRunner:
    async def run(self, *, prompt_version: str,
                 categories: list[GoldenCategory] | None = None) -> EvalRun: ...
    def compute_metrics(self, actual: dict, expected: dict) -> EvalMetrics: ...
    async def get_run(self, run_id: UUID) -> EvalRun: ...
    async def list_runs(self, limit: int = 20) -> list[EvalRun]: ...
```

### 10.3 FeedbackCaseService

```python
class FeedbackCaseService:
    async def record(self, *, task_id: UUID, reviewer_id: UUID,
                     agent_name: str, ai_output: dict, human_modified: dict,
                     modify_reason: str, reason_category: str | None = None) -> FeedbackCase: ...
    async def list_by_task(self, task_id: UUID) -> list[FeedbackCase]: ...
    async def batch_review(self) -> dict: ...  # 统计高频 modify_reason
```

### 10.4 MetricsCollector

```python
class MetricsCollector:
    def record_node_latency(self, agent: str, duration_ms: int) -> None: ...
    def record_retry(self, trace_id: str, count: int) -> None: ...
    def record_pass_fail(self, agent: str, passed: bool) -> None: ...
    def snapshot(self) -> dict: ...
```

---

## 11. 验收准则

| 准则 | 目标 | 验证方式 |
|------|------|---------|
| Golden Dataset 导入 | ≥ 100 份 | API 导入 + 计数验证 |
| 6 大指标计算 | 全部实现 | EvalRunner 单测覆盖 |
| 评测门控 | Prompt 变更不过门控则拒绝 | PromptManager.activate() 测试 |
| 人工反馈写入 | feedback_cases 正确记录 | FeedbackCaseService 单测 |
| 审计追踪 | trace_id 全链路可查 | AuditService 单测 |
| 指标采集 | 5 大指标可拉取 | /metrics API 测试 |
| 单测覆盖 | ≥ 80% | pytest --cov |
| Ruff Lint | 0 错误 | ruff check |

---

## 12. Sprint 5 任务拆解

| 任务 | 优先级 | 依赖 |
|------|--------|------|
| 06_EVALUATION_SYSTEM.md 设计文档 | P0 | - |
| GoldenDatasetService + EvalRunner + 6 大指标 | P0 | 设计文档 |
| FeedbackCaseService + human_review 增强 | P0 | - |
| MetricsCollector 指标采集 | P1 | - |
| 评测/反馈/审计 API 端点 | P0 | 服务层 |
| 单元测试 + ruff | P0 | 全部模块 |
| 99_SPRINT5_SUMMARY.md | P1 | 全部完成 |

---

**评测系统设计文档终止。**
