# 系统架构设计 · 行政规范性文件智能合法性审查 Agent 系统

> 文档版本：v1.0.0
> 最后更新：2026-08-22
> 架构原则：Graph-based Agent + Harness Engineering + Loop Optimization + Evaluation Driven
> 技术栈：FastAPI + LangGraph + PostgreSQL/pgvector + DeepSeek/Qwen + Next.js

---

## 1. 架构总览

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| Graph-based | 所有审核流程以 LangGraph 状态图编排，节点可追溯、可热插拔 |
| Harness Engineering | 四类 Harness（Context/Evidence/Quality/Security）约束 Agent 行为 |
| Loop-driven | 三类 Loop（审核质量/人工反馈/法规更新）持续优化 |
| Evaluation-first | 任何 Agent/Prompt 变更必须先过 Golden Dataset 评测 |
| Trace-by-default | trace_id 贯穿全链路，可追溯每次决策 |
| Human-in-the-loop | 人工复核不可省略，AI 不替代法律责任 |

### 1.2 四层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     应用层 (Application Layer)                  │
│  Next.js Web │ 上传/审查/看板/反馈 │ Demo 模式 │ PDF 导出       │
└──────────────────────────┬──────────────────────────────────────┘
                           │ REST + WebSocket
┌──────────────────────────▼──────────────────────────────────────┐
│                 Agent 编排层 (Agent Orchestration Layer)         │
│  Supervisor Agent │ LangGraph State Machine │ 9 个审核 Agent    │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Harness Control Layer                                   │   │
│  │  Context │ Evidence │ Quality │ Security Harness         │   │
│  └──────────────────────────────────────────────────────────┘   │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Loop Self-Optimization                                  │   │
│  │  审核质量 Loop │ 人工反馈 Loop │ 法规更新 Loop            │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────┬──────────────────────────────────────┘
                           │ Tool calls
┌──────────────────────────▼──────────────────────────────────────┐
│              能力服务层 (Capability Service Layer)              │
│  文件解析 │ OCR │ 法规检索 │ Embedding │ 报告生成 │ 评测引擎    │
└──────────────────────────┬──────────────────────────────────────┘
                           │ SQL + Vector + Object
┌──────────────────────────▼──────────────────────────────────────┐
│                数据层 (Data Layer)                               │
│  PostgreSQL │ pgvector │ 文件沙箱 │ 审计日志 │ Golden Dataset │
└─────────────────────────────────────────────────────────────────┘
```

### 1.3 物理部署拓扑

```
                  ┌──────────────────┐
                  │   用户浏览器      │
                  └────────┬─────────┘
                           │ HTTPS
                  ┌────────▼─────────┐
                  │  Nginx (反向代理) │
                  └────────┬─────────┘
            ┌──────────────┴──────────────┐
            │                              │
   ┌────────▼────────┐           ┌─────────▼────────┐
   │ Next.js Frontend│           │  FastAPI Backend  │
   │   (Node 容器)   │           │  (Python 容器)    │
   └─────────────────┘           └────────┬──────────┘
                                          │
                       ┌──────────────────┼──────────────────┐
                       │                  │                  │
              ┌────────▼────────┐ ┌───────▼───────┐ ┌────────▼────────┐
              │   PostgreSQL    │ │  Redis Cache │ │  LLM API Gateway │
              │  + pgvector     │ │  + 任务队列    │ │ DeepSeek/Qwen   │
              └─────────────────┘ └───────────────┘ └─────────────────┘
                       │
              ┌────────▼────────┐
              │   文件沙箱存储   │
              │  (MinIO/本地卷) │
              └─────────────────┘
```

---

## 2. Agent 编排层（核心）

### 2.1 Supervisor Agent

| 项 | 设计 |
|----|------|
| 职责 | 总流程控制、任务拆解、Agent 调度、状态管理 |
| 输入 | 任务元数据 + 文件解析结果 + 历史决策 |
| 输出 | 下一节点路由决策 + 全局 State 更新 |
| 实现 | LangGraph 主控图 + 路由表 |
| 迭代上限 | MAX_ITER = 5（强制终态） |

### 2.2 LangGraph 状态机

```
START
  │
  ▼
[doc_parse] ─────────────► [doc_classify]
                              │
                  ┌───────────┴────────────┐
                  ▼                         ▼
        [legal_retrieve]            [non_normative_exit]
                  │
                  ▼
        [authority_review]
                  │
                  ▼
        [procedure_review]
                  │
                  ▼
        [content_review]
                  │
                  ▼
        [risk_assessment]
                  │
                  ▼
        [evidence_verify] ◄──── Retry Loop (≤ 5)
                  │ PASS
                  ▼
        [report_generation]
                  │
                  ▼
        [human_review]
                  │
                  ▼
                 END
```

### 2.3 9 个审核 Agent 一览

| Agent | 职责 | 输入 | 输出 | 工具 |
|-------|------|------|------|------|
| Document Understanding Agent | OCR + 结构化 | 原始文件 | 结构化 JSON | OCR/Parser |
| Document Classification Agent | 判定规范性 | 结构化 JSON | 分类+置信度 | LLM |
| Legal Retrieval Agent | 法规 RAG | 审核问题 | 条款清单 | RAG/Vector |
| Authority Review Agent | 主体合法性 | 文件主体信息 | PASS/RISK/FAIL | RAG |
| Procedure Review Agent | 五项程序检查 | 程序要素 | 程序风险清单 | RAG |
| Content Compliance Agent | 六类违法情形 | 文本条款 | 风险点列表 | RAG |
| Evidence Verification Agent | 证据链检查 | 全部风险点 | PASS/RETRY | Verifier |
| Report Generation Agent | 报告生成 | 全部审查结果 | 审查意见书 | Template |
| Risk Assessment Agent | 综合风险评级 | 各 Agent 结果 | 风险等级 | Aggregator |

> 详细 Input/Output Schema/Prompt/Tool/Eval 见 [04_AGENT_GRAPH_DESIGN.md](04_AGENT_GRAPH_DESIGN.md)

---

## 3. Harness Control Layer

### 3.1 Context Harness（上下文管理）

| 子项 | 说明 |
|------|------|
| 文件上下文 | 结构化文件 + 原文段落锚点 |
| 法规上下文 | 检索召回的条款 + 历史案例 |
| 用户上下文 | 角色/单位/权限/历史偏好 |
| 状态上下文 | trace_id/iteration/version 贯穿 |
| 防遗忘 | 每 Node 输入前注入 Context Window |

**实现要点：**
- Context Window 通过 State Schema 注入，每个 Node 必读
- 超长上下文采用"分段摘要 + 原文锚点"策略
- 节点间共享上下文通过 LangGraph `state` 字段

### 3.2 Evidence Harness（证据约束）

**强制输出格式：**

```json
{
  "risk": "违法设置行政许可",
  "evidence": {
    "law_name": "行政许可法",
    "article": "第十五条",
    "original_text": "符合法定条件、标准的，行政机关应当依法...作出准予行政许可的书面决定。",
    "explanation": "文件第 X 条规定增设行政许可，与上位法冲突。"
  },
  "confidence": 0.92
}
```

**校验规则：**
- 缺法规名 → Verifier 拦截，Retry
- 缺条款号 → Verifier 拦截，Retry
- 缺原文 → Verifier 拦截，Retry
- 引用与原文不一致（编辑距离 > 阈值）→ Retry
- 禁止无依据判断

### 3.3 Quality Harness（质量门控）

```
Agent 输出 → Verifier 检查 → PASS → 下一步
                          → FAIL → Retry（≤ MAX_ITER）
                                  → 超限 → 人工兜底
```

**Verifier 检查项：**
1. Schema 合法性（Pydantic 校验）
2. 证据完整性（Evidence Harness）
3. 置信度阈值（≥ 0.7）
4. 重复风险合并
5. 引用原文一致性

### 3.4 Security Harness（安全审计）

| 子项 | 说明 |
|------|------|
| 权限控制 | RBAC + 任务级 ACL |
| 文件隔离 | 每任务独立沙箱目录，跨任务不可访问 |
| 审计追踪 | 全操作入 audit_records 表 |
| Prompt 沙箱 | 防注入（敏感词过滤 + 输入长度限制） |
| 数据脱敏 | Demo 模式自动匿名化 |
| 模型调用 | 走内部 Gateway，禁止直连第三方 |

---

## 4. Loop Self-Optimization

### 4.1 Loop 1：审核质量 Loop

```
AI 审核 → Verifier 发现问题 → 重新检索法规 → 重新判断 → 优化报告
   ▲                                                              │
   └──────────────────────────────────────────────────────────────┘
   迭代上限：MAX_ITER = 5
```

**触发条件：**
- 证据缺失
- 置信度 < 0.7
- Verifier 校验失败
- 引用原文不一致

### 4.2 Loop 2：人工反馈 Loop

```
人工修改 AI 意见 → 记录原因 → 入案例库 → 优化 Prompt/规则 → 重新评测
```

**实现：**
- feedback_cases 表记录每次人工修改的原文/AI 意见/最终意见/原因
- 周期性 Batch 复盘，更新 Prompt 版本
- Prompt 变更必须过 Golden Dataset 评测

### 4.3 Loop 3：法规更新 Loop

```
新增法规文件 → 自动解析 → 更新知识库 → 重新测试历史案例 → 标记需复查项
```

**触发：**
- 法规库管理员手动触发
- 每日定时检查法规库版本

---

## 5. 数据流与控制流

### 5.1 主流程数据流

```
1. 文件上传 → 文件沙箱 + Hash 校验
2. 任务创建 → review_tasks 表 + trace_id 生成
3. 文件解析 → 结构化 JSON 入 review_results.cache
4. 文件分类 → 决定是否进入审核流程
5. 法规检索 → 召回条款入 Context
6. 审核 Agent → 输出风险点入 review_results.risks
7. 证据验证 → 通过则进入报告，否则 Retry
8. 报告生成 → 审查意见书 PDF + JSON
9. 人工复核 → 修改回流 → feedback_cases
10. 归档 → audit_records + 报告归档
```

### 5.2 控制流（Supervisor 调度）

| 决策点 | 路由条件 |
|--------|---------|
| 分类后 | 非规范性文件 → 直接出报告退出 |
| 主体不合法 | 跳过程序/内容审核，直接 FAIL 报告 |
| 程序严重缺失 | 标记后继续内容审核（不阻塞） |
| 证据不足 | Retry Loop，≤ 5 次 |
| 置信度过低 | 触发人工兜底 |
| 迭代超限 | 进入人工复核队列 |

---

## 6. 评测系统架构

### 6.1 评测分层

| 层级 | 评测对象 | 指标 |
|------|----------|------|
| L1 节点级 | 单 Agent 输出 | Schema 合规率 / 置信度 |
| L2 链路级 | 多 Agent 协作 | Retry 次数 / 总耗时 |
| L3 任务级 | 端到端审查 | 风险点召回率 / 准确率 |
| L4 评测集级 | Golden Dataset | 6 大指标 |
| L5 线上 | 线上任务 | 人工修改率 / 通过率 |

### 6.2 Golden Dataset

| 类别 | 数量 | 说明 |
|------|------|------|
| 标准规范性文件 | 20 | 应 PASS 案例 |
| 含主体违法 | 15 | 应 FAIL - 主体 |
| 含程序缺失 | 15 | 应 RISK - 程序 |
| 含内容违法 | 30 | 应 FAIL/RISK - 内容 |
| 边界灰色案例 | 15 | 测试置信度 |
| 非规范性文件 | 5 | 应分类为否 |
| **合计** | **100** | 覆盖 6 大审查维度 |

### 6.3 6 大评测指标

| 指标 | 目标 | 计算 |
|------|------|------|
| 文件解析准确率 | ≥ 95% | 字段 F1 |
| 法规检索准确率 | ≥ 90% | Top-10 召回 |
| 条款引用准确率 | ≥ 85% | 条款精确匹配 |
| 风险判断一致性 | ≥ 90% | 与标注 kappa |
| 报告完整性 | 100% | 必填字段 |
| 幻觉率 | ≤ 5% | 无依据判断比例 |

---

## 7. 技术选型说明

| 类别 | 选型 | 理由 |
|------|------|------|
| 后端框架 | FastAPI | 异步性能 + Pydantic 校验 |
| Agent 编排 | LangGraph | 状态图 + 多 Agent + 人机交互 |
| 数据库 | PostgreSQL 16 | 关系型 + 事务 |
| 向量库 | pgvector | 与 PG 一体化，避免双存储 |
| 缓存/队列 | Redis | 热数据 + 任务队列 |
| 文件沙箱 | MinIO / 本地卷 | 对象存储 + 任务隔离 |
| OCR | PaddleOCR / 商用 API | 中文场景识别准 |
| Embedding | BGE-M3 / bge-large-zh | 中文法律语义强 |
| LLM | DeepSeek-V3 / Qwen2.5 | 中文合规 + 成本可控 |
| 前端 | Next.js 14 + TS + Tailwind | SSR + 类型安全 |
| PDF 生成 | WeasyPrint / ReportLab | 中文 PDF 模板 |
| 部署 | Docker Compose | 单机交付简单 |
| 监控 | OpenTelemetry + Prometheus | 链路追踪 + 指标 |

---

## 8. 安全与合规

### 8.1 数据安全

| 项 | 措施 |
|----|------|
| 传输 | HTTPS/TLS 1.3 |
| 存储 | 文件加密（AES-256） |
| 备份 | 法规库每日增量 + 文件每周全量 |
| 销毁 | 任务删除时物理清除沙箱 |
| 脱敏 | Demo 模式自动去除送审单位/人名 |

### 8.2 审计

| 字段 | 说明 |
|------|------|
| trace_id | 全链路追踪 ID |
| actor | 操作人 |
| action | 动作 |
| target | 对象 |
| before | 变更前 |
| after | 变更后 |
| timestamp | 时间 |
| ip | IP 地址 |

### 8.3 合规红线

- AI 不可替代最终法律责任（必须人工签发）
- 所有 AI 判断附法规依据（Evidence Harness）
- 未经评估的 Prompt 变更禁止合并（CI 门控）
- Agent 循环必须有迭代上限（MAX_ITER = 5）
- 安全节点不可被绕过（Supervisor 强制路由）

---

## 9. 可观测性

### 9.1 指标

| 指标 | 说明 |
|------|------|
| node_latency_p50/p99 | 每节点延迟 |
| retry_count | 每任务 Retry 次数 |
| pass_rate | 各节点通过率 |
| hallucination_rate | 幻觉率（线上采样） |
| task_duration | 端到端任务时长 |

### 9.2 日志

- 结构化 JSON 日志
- trace_id 贯穿
- 入 agent_logs 表 + ELK

### 9.3 告警

- 任务超时（> 5 分钟）
- Retry 超限
- 幻觉率突增
- 法规库版本异常

---

## 10. 接口契约（Sprint 2 启动依赖）

### 10.1 文件上传

```
POST /api/v1/documents/upload
Content-Type: multipart/form-data
Response: { "task_id": "uuid", "trace_id": "uuid", "status": "parsing" }
```

### 10.2 任务查询

```
GET /api/v1/tasks/{task_id}
Response: { "trace_id", "status", "current_node", "progress", "result" }
```

### 10.3 审查触发

```
POST /api/v1/tasks/{task_id}/review
Body: { "force_recheck": false }
Response: { "accepted": true, "trace_id": "..." }
```

### 10.4 报告获取

```
GET /api/v1/tasks/{task_id}/report?format=pdf
Response: application/pdf
```

### 10.5 反馈回流

```
POST /api/v1/tasks/{task_id}/feedback
Body: { "section", "original", "modified", "reason" }
```

---

**架构文档终止**
