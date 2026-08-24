# Agent Graph 设计 · 行政规范性文件智能合法性审查 Agent 系统

> 文档版本：v1.0.0
> 最后更新：2026-08-22
> 框架：LangGraph（两层 Graph = 主控 Supervisor + 子图审核）
> 硬约束：trace_id/iteration/version 必填 / MAX_ITER=5 / Evidence Harness 强制

---

## 1. State Schema

### 1.1 全局 State 定义

```python
from typing import TypedDict, Literal, Optional, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime

class Evidence(BaseModel):
    law_name: str
    article: str               # 条款号，如 "第十五条"
    original_text: str         # 条款原文
    explanation: str           # 与文件冲突的解释

class RiskItem(BaseModel):
    dimension: Literal["authority","procedure","content","prohibition","interest"]
    risk_type: str             # 如 "违法设置行政许可"
    severity: Literal["low","medium","high","critical"]
    evidence: Evidence          # 证据链（强制）
    confidence: float = Field(ge=0.0, le=1.0)
    suggestion: str            # 修改建议

class AgentOutput(BaseModel):
    agent_name: str
    node_status: Literal["pass","fail","retry","skipped"]
    risks: List[RiskItem] = []
    evidences: List[Evidence] = []
    confidence: float = Field(ge=0.0, le=1.0)
    raw_json: Dict[str, Any]
    duration_ms: int
    iteration: int

class ReviewState(TypedDict):
    # === 追踪元数据（硬约束必填）===
    trace_id: str
    task_id: str
    iteration: int              # 当前迭代
    max_iteration: int          # = 5
    prompt_versions: Dict[str, str]  # {agent_name: version}
    # === Context Harness ===
    document_json: Dict[str, Any]   # 文件解析结构化结果
    legal_context: List[Dict]        # 检索召回的条款
    user_context: Dict[str, Any]     # 用户/单位/权限
    # === 各节点输出 ===
    parse_result: Optional[AgentOutput]
    classify_result: Optional[AgentOutput]
    retrieval_result: Optional[AgentOutput]
    authority_result: Optional[AgentOutput]
    procedure_result: Optional[AgentOutput]
    content_result: Optional[AgentOutput]
    risk_result: Optional[AgentOutput]      # 综合评级
    verify_result: Optional[AgentOutput]    # Evidence Verifier
    report_result: Optional[AgentOutput]
    # === 路由控制 ===
    is_normative: Optional[bool]            # 是否规范性文件
    overall_status: Literal["pass","risk","fail"]
    needs_human_review: bool
    feedback: Optional[Dict]                # 人工反馈
    # === 终态 ===
    finished: bool
    error: Optional[str]
```

### 1.2 State 流转不变量

| 不变量 | 校验点 |
|--------|--------|
| `trace_id` 全程不变 | 每节点入口校验 |
| `iteration` 每次 Retry 自增 | Retry 节点 |
| `iteration > max_iteration` 必须人工兜底 | Supervisor 路由 |
| 所有 RiskItem 必含 `evidence` | Evidence Verifier |
| `prompt_versions` 必填 | 全节点 |

---

## 2. Graph 拓扑

### 2.1 主图（Supervisor 控制图）

```
START
  │
  ▼
[doc_parse] ─────► [doc_classify]
                       │
            ┌──────────┴──────────┐
            ▼ is_normative=False   ▼ is_normative=True
    [report: 非规范性文件]      [legal_retrieve]
                                   │
                                   ▼
                          [authority_review]
                                   │
                       ┌───────────┴───────────┐
                       ▼ authority=PASS         ▼ authority=FAIL
                [procedure_review]         [report: 主体不合法]
                       │
                       ▼
                [content_review]
                       │
                       ▼
                [risk_assessment]
                       │
                       ▼
                [evidence_verify] ◄─── Retry Edge (iteration < MAX)
                       │
              ┌────────┴────────┐
              ▼ verify=PASS       ▼ verify=FAIL & 超限
        [report_generation]   [human_fallback]
              │                       │
              ▼                       ▼
        [human_review] ◄───────────────┘
              │
              ▼
            END
```

### 2.2 路由决策表

| 当前节点 | 条件 | 下一节点 |
|----------|------|----------|
| doc_classify | is_normative=False | report_generation（非规范性） |
| doc_classify | is_normative=True | legal_retrieve |
| authority_review | status=FAIL | report_generation（主体不合法） |
| authority_review | status=PASS | procedure_review |
| evidence_verify | status=PASS | report_generation |
| evidence_verify | status=FAIL & iteration < MAX | legal_retrieve（Retry） |
| evidence_verify | status=FAIL & iteration ≥ MAX | human_fallback |
| report_generation | always | human_review |
| human_review | feedback.give_up | END |
| human_review | feedback.confirm | END |

---

## 3. 9 个 Agent 节点定义

### 3.1 Node: doc_parse（Document Understanding Agent）

| 项 | 内容 |
|----|------|
| **Input** | document_json（待解析）、task_id、file_path |
| **Output Schema** | `ReviewState.parse_result: AgentOutput`，含 `document_json` 字段（标题/发布机关/日期/正文/附件/关键词/政策领域） |
| **Prompt** | 无需 LLM（纯工具调用） |
| **Tool** | `ocr_tool`、`docx_parser`、`pdf_parser`、`structure_extractor` |
| **Eval** | 字段 F1 ≥ 95%，OCR 字符准确率 ≥ 95% |
| **Harness** | Context（注入 trace_id）；Security（文件沙箱读取） |

**document_json Schema：**

```json
{
  "title": "XX县关于...的若干意见",
  "issuing_authority": "XX县人民政府",
  "publish_date": "2026-08-01",
  "effective_date": "2026-09-01",
  "doc_number": "X政发〔2026〕X号",
  "body_paragraphs": [{"id":"p1","text":"...","anchor":"#p1"}],
  "attachments": [{"name":"附件1","path":"..."}],
  "keywords": ["中小企业","财政补贴"],
  "policy_domain": "经济发展"
}
```

### 3.2 Node: doc_classify（Document Classification Agent）

| 项 | 内容 |
|----|------|
| **Input** | document_json |
| **Output Schema** | `classify_result: AgentOutput`，含 `is_normative: bool`、`confidence`、`reasoning` |
| **Prompt** | `prompts.doc_classify.v1.0.0`，判定 4 要素：公民权利义务 / 企业经营 / 普遍约束力 / 重复适用 |
| **Tool** | `llm_complete`（结构化输出 Pydantic） |
| **Eval** | 分类准确率 ≥ 90%，置信度阈值 0.7 |
| **Harness** | Evidence（必须引用 4 要素判断依据） |

### 3.3 Node: legal_retrieve（Legal Retrieval Agent）

| 项 | 内容 |
|----|------|
| **Input** | document_json、审核问题清单（动态生成） |
| **Output Schema** | `retrieval_result: AgentOutput`，含 `legal_context: List[Evidence]` |
| **Prompt** | `prompts.legal_query.v1.0.0`，将审核问题转为检索 query |
| **Tool** | `rag_search`（pgvector HNSW + trigram 混合）、`case_search` |
| **Eval** | Top-10 召回 ≥ 90%，引用准确率 ≥ 85% |
| **Harness** | Context（结果入 state）；Security（法规库只读） |

### 3.4 Node: authority_review（Authority Review Agent）

| 项 | 内容 |
|----|------|
| **Input** | document_json.issuing_authority、legal_context |
| **Output Schema** | `authority_result: AgentOutput`，含 `risks: List[RiskItem]`、`status: PASS/RISK/FAIL` |
| **Prompt** | `prompts.authority_review.v1.0.0`，检查主体是否在法定制定主体清单 |
| **Tool** | `llm_complete`、`authority_registry`（主体清单查询） |
| **Eval** | 主体判断准确率 ≥ 95% |
| **Harness** | Evidence（必须引用《地方组织法》/省级规范性文件管理办法） |

### 3.5 Node: procedure_review（Procedure Review Agent）

| 项 | 内容 |
|----|------|
| **Input** | document_json（程序要素：评估论证/征求意见/合法性审查/集体讨论/公开发布） |
| **Output Schema** | `procedure_result: AgentOutput`，含 5 项程序检查结果 |
| **Prompt** | `prompts.procedure_review.v1.0.0` |
| **Tool** | `llm_complete`、`procedure_checklist` |
| **Eval** | 程序缺失检出率 ≥ 85% |
| **Harness** | Evidence（每项缺失必须引用程序法规依据） |

**5 项程序：**

1. 评估论证（是否做了必要性/可行性/合法性论证）
2. 征求意见（是否公开征求社会意见 + 是否征求相关部门意见）
3. 合法性审查（是否经过司法局合法性审查前置）
4. 集体讨论（是否经政府常务会议/部门办公会议审议）
5. 公开发布（是否通过政府公报/网站公开发布）

### 3.6 Node: content_review（Content Compliance Agent）

| 项 | 内容 |
|----|------|
| **Input** | document_json.body_paragraphs、legal_context |
| **Output Schema** | `content_result: AgentOutput`，含 `risks: List[RiskItem]`（按六类违法情形） |
| **Prompt** | `prompts.content_review.v1.0.0` |
| **Tool** | `llm_complete`、`rag_search`（按段落检索） |
| **Eval** | 风险点召回 ≥ 85%，幻觉率 ≤ 5% |
| **Harness** | Evidence（每风险点必含条款原文）；Quality（Verifier 校验） |

**六类违法情形：**

1. 违法增加行政权力（增设职权、扩张权限）
2. 违法设置行政许可（违反《行政许可法》）
3. 违法设置行政处罚（违反《行政处罚法》）
4. 违法设置行政强制（违反《行政强制法》）
5. 违法设置收费/证明事项（无依据收费/循环证明）
6. 违法增加企业义务/限制公平竞争（违反《优化营商环境条例》）

### 3.7 Node: risk_assessment（Risk Assessment Agent）

| 项 | 内容 |
|----|------|
| **Input** | authority_result、procedure_result、content_result |
| **Output Schema** | `risk_result: AgentOutput`，含 `overall_status: PASS/RISK/FAIL`、`risk_summary` |
| **Prompt** | `prompts.risk_assessment.v1.0.0`，按风险等级权重综合评级 |
| **Tool** | `llm_complete`（Aggregator 模式） |
| **Eval** | 与人工标注 kappa ≥ 0.85 |
| **Harness** | Quality（必须有 4 维度评分理由） |

**评级规则：**

| 条件 | 总体评级 |
|------|----------|
| 任一 critical 风险 | FAIL |
| 任一 high 风险且 ≥ 2 处 | FAIL |
| 任一 high 风险 | RISK |
| 多处 medium 风险 | RISK |
| 仅 low 风险或无风险 | PASS |

### 3.8 Node: evidence_verify（Evidence Verification Agent）

| 项 | 内容 |
|----|------|
| **Input** | 全部 AgentOutput（authority/procedure/content/risk） |
| **Output Schema** | `verify_result: AgentOutput`，含 `pass: bool`、`missing_evidences: List` |
| **Prompt** | `prompts.evidence_verify.v1.0.0` |
| **Tool** | `evidence_checker`、`rag_search`（补检） |
| **Eval** | 证据覆盖率 100% |
| **Harness** | Quality（核心节点）；触发 Retry Loop |

**校验项（按顺序）：**

1. 每个 RiskItem 必含 `evidence.law_name`
2. 每个 RiskItem 必含 `evidence.article`
3. 每个 RiskItem 必含 `evidence.original_text`
4. 引用原文与法规库原文编辑距离 ≤ 阈值（如 0.15）
5. confidence ≥ 0.7
6. 重复风险点合并

**失败处理：**
- 触发 `Retry Edge` → 回到 legal_retrieve 重新检索
- `iteration` 自增
- `iteration >= max_iteration` → 转 human_fallback

### 3.9 Node: report_generation（Report Generation Agent）

| 项 | 内容 |
|----|------|
| **Input** | 全部 AgentOutput、overall_status、user_context |
| **Output Schema** | `report_result: AgentOutput`，含 `report_markdown`、`report_pdf_path` |
| **Prompt** | `prompts.report_generation.v1.0.0`（章节模板） |
| **Tool** | `llm_complete`、`pdf_renderer`（WeasyPrint） |
| **Eval** | 报告完整性 100%（必填章节）；引用回链率 100% |
| **Harness** | Evidence（章节"审查依据"必须列出全部引用法规） |

**报告章节模板：**

```
一、文件基本情况
   （一）文件名称
   （二）制定机关
   （三）发布日期
   （四）文号

二、审查依据
   （一）法律法规依据（列出全部引用法规）
   （二）审查规范依据

三、审核过程
   （一）审核程序
   （二）Agent 节点流转

四、发现问题
   （一）主体合法性
   （二）程序完整性
   （三）内容合法性
   每个问题包含：风险 / 依据 / 原文 / 解释 / 建议

五、风险等级
   PASS / RISK / FAIL

六、修改建议

七、审查意见
   AI 初审意见 + 人工复核栏
```

---

## 4. Harness 接入点矩阵

| Harness | 接入节点 | 接入方式 |
|---------|---------|---------|
| Context | 所有节点 | State 字段注入 |
| Evidence | doc_classify / authority / procedure / content / report | Pydantic 校验 + Verifier |
| Quality | risk / evidence_verify / report | Verifier 节点 |
| Security | doc_parse / 全节点 | 文件沙箱 + 审计日志 |

---

## 5. Loop 实现细节

### 5.1 审核质量 Loop（Graph 内）

```python
# 伪代码：LangGraph 条件边
def evidence_verify_router(state: ReviewState) -> str:
    if state["verify_result"].node_status == "pass":
        return "report_generation"
    if state["iteration"] < state["max_iteration"]:
        state["iteration"] += 1
        return "legal_retrieve"  # Retry
    return "human_fallback"

graph.add_conditional_edges(
    "evidence_verify",
    evidence_verify_router,
    {
        "report_generation": "report_generation",
        "legal_retrieve": "legal_retrieve",
        "human_fallback": "human_fallback",
    },
)
```

### 5.2 人工反馈 Loop（Graph 外）

- 触发点：human_review 节点
- 流程：人工修改 → 写入 feedback_cases → 周期 Batch 复盘 → 更新 prompts 表版本 → CI 评测门控

### 5.3 法规更新 Loop（离线）

- 触发：每日定时任务 / 法规库管理员手动
- 流程：导入新法规 → 切分条款 + Embedding → 重跑历史 golden_dataset → 标记需复查项 → 通知审查主管

---

## 6. Prompt 版本管理

### 6.1 Prompt 文件结构

```
backend/app/agents/prompts/
├── doc_classify/
│   ├── v1.0.0.yaml
│   └── v1.1.0.yaml
├── authority_review/
│   └── v1.0.0.yaml
├── procedure_review/
│   └── v1.0.0.yaml
├── content_review/
│   └── v1.0.0.yaml
├── risk_assessment/
│   └── v1.0.0.yaml
├── evidence_verify/
│   └── v1.0.0.yaml
├── report_generation/
│   └── v1.0.0.yaml
└── registry.yaml          # Prompt 版本注册表
```

### 6.2 Prompt YAML 模板

```yaml
# backend/app/agents/prompts/authority_review/v1.0.0.yaml
prompt_key: authority_review
version: v1.0.0
model_name: deepseek-v3
temperature: 0.2
variables:
  - name: issuing_authority
    type: string
    required: true
  - name: legal_context
    type: list
    required: true
template: |
  你是县级司法局行政合法性审查专家。请审查以下文件的制定主体是否合法。

  ## 文件制定主体
  {{issuing_authority}}

  ## 法规依据
  {{legal_context}}

  ## 审查要点
  1. 制定主体是否在法定制定主体清单内
  2. 是否具有制定权限
  3. 是否超越职权

  ## 输出格式（严格 JSON）
  {
    "status": "PASS|RISK|FAIL",
    "risks": [...],
    "evidences": [
      {"law_name":"...","article":"...","original_text":"...","explanation":"..."}
    ],
    "confidence": 0.0-1.0,
    "reasoning": "..."
  }
```

### 6.3 版本切换约束

- 生产环境只允许 `status='active'` 的 Prompt
- 任何 Prompt 变更必须先过 golden_dataset 评测
- 评测通过率 ≥ 90% 才能激活
- 旧版本状态置为 `deprecated`，可回滚

---

## 7. 工具注册表

```python
# backend/app/agents/tool_registry.py（伪代码）

TOOL_REGISTRY = {
    "ocr_tool":          {"module":"app.tools.ocr","class":"OCRTool","version":"v1.0.0"},
    "docx_parser":       {"module":"app.tools.parsers","class":"DocxParser","version":"v1.0.0"},
    "pdf_parser":        {"module":"app.tools.parsers","class":"PDFParser","version":"v1.0.0"},
    "structure_extractor":{"module":"app.tools.structure","class":"StructureExtractor","version":"v1.0.0"},
    "rag_search":        {"module":"app.tools.rag","class":"RAGSearch","version":"v1.0.0"},
    "case_search":       {"module":"app.tools.rag","class":"CaseSearch","version":"v1.0.0"},
    "llm_complete":      {"module":"app.tools.llm","class":"LLMComplete","version":"v1.0.0"},
    "authority_registry":{"module":"app.tools.registries","class":"AuthorityRegistry","version":"v1.0.0"},
    "procedure_checklist":{"module":"app.tools.checklists","class":"ProcedureChecklist","version":"v1.0.0"},
    "evidence_checker": {"module":"app.tools.verifiers","class":"EvidenceChecker","version":"v1.0.0"},
    "pdf_renderer":      {"module":"app.tools.report","class":"PDFRenderer","version":"v1.0.0"},
}

def get_tool(name: str, version: str):
    # 强校验：未注册工具禁止调用
    ...
```

---

## 8. LangGraph 主图骨架（伪代码）

```python
# backend/app/agent/graph.py（伪代码）

from langgraph.graph import StateGraph, END

def build_review_graph():
    g = StateGraph(ReviewState)

    g.add_node("doc_parse",          doc_parse_node)
    g.add_node("doc_classify",       doc_classify_node)
    g.add_node("legal_retrieve",     legal_retrieve_node)
    g.add_node("authority_review",   authority_review_node)
    g.add_node("procedure_review",   procedure_review_node)
    g.add_node("content_review",     content_review_node)
    g.add_node("risk_assessment",    risk_assessment_node)
    g.add_node("evidence_verify",    evidence_verify_node)
    g.add_node("report_generation",  report_generation_node)
    g.add_node("human_review",       human_review_node)
    g.add_node("human_fallback",     human_fallback_node)

    g.set_entry_point("doc_parse")
    g.add_edge("doc_parse", "doc_classify")
    g.add_conditional_edges("doc_classify", classify_router,
        {"non_normative":"report_generation","normative":"legal_retrieve"})
    g.add_edge("legal_retrieve", "authority_review")
    g.add_conditional_edges("authority_review", authority_router,
        {"pass":"procedure_review","fail":"report_generation"})
    g.add_edge("procedure_review", "content_review")
    g.add_edge("content_review", "risk_assessment")
    g.add_edge("risk_assessment", "evidence_verify")
    g.add_conditional_edges("evidence_verify", evidence_verify_router,
        {"pass":"report_generation","retry":"legal_retrieve","fallback":"human_fallback"})
    g.add_edge("report_generation", "human_review")
    g.add_edge("human_review", END)
    g.add_edge("human_fallback", "human_review")

    return g.compile()
```

---

## 9. 评测接入点

| 节点 | 评测方式 | 指标 |
|------|---------|------|
| doc_parse | 与人工标注对比 | 字段 F1 |
| doc_classify | 二分类准确率 | F1 |
| legal_retrieve | Top-K 召回 | Recall@10 |
| authority/procedure/content | 与标注对比 | 风险点 F1 / kappa |
| evidence_verify | 证据覆盖率 | 100% |
| report_generation | 章节完整性 + 引用回链 | 完整率 |
| 端到端 | Golden Dataset 100 例 | 6 大指标 |

---

## 10. 硬约束自查表

| 约束 | 实现位置 | 自查 |
|------|---------|------|
| Agent 可评估 | 评测接入点 + golden_dataset | ✓ |
| 可追溯 | trace_id + agent_logs | ✓ |
| 可迭代 | Prompt 版本化 + max_iteration | ✓ |
| 可扩展 | Tool Registry + Prompt Registry | ✓ |
| 可商业化 | 多场景复用 + 多模型可切 | ✓ |
| Prompt 版本化 | prompts 表 + YAML 文件 | ✓ |
| 未注册工具禁调 | TOOL_REGISTRY 强校验 | ✓ |
| Agent 必须有版本号 | prompts.version + prompts 表 | ✓ |
| 未经评估 Prompt 禁合并 | CI 门控 + eval_runs | ✓ |
| Agent 循环有上限 | max_iteration=5 + 超限兜底 | ✓ |
| 安全节点不可绕过 | Supervisor 强制路由 | ✓ |
| 人工审查闭环 | human_review 必经节点 | ✓ |

---

**Agent Graph 设计文档终止**
