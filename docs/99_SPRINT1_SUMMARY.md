# Sprint 1 交付总结 · 行政规范性文件智能合法性审查 Agent 系统

> 交付日期：2026-08-22
> 阶段：Sprint 1（设计基线）
> 状态：✅ 完成，待技术委员会评审

---

## 1. 交付物清单

| 编号 | 文档 | 路径 | 状态 |
|------|------|------|------|
| 00 | Sprint 规划总览 | [docs/00_SPRINT_PLAN.md](file:///Users/shajindi/traework/legal-review/docs/00_SPRINT_PLAN.md) | ✅ |
| 01 | PRD 产品需求规格 | [docs/01_PRD.md](file:///Users/shajindi/traework/legal-review/docs/01_PRD.md) | ✅ |
| 02 | 系统架构设计 | [docs/02_SYSTEM_ARCHITECTURE.md](file:///Users/shajindi/traework/legal-review/docs/02_SYSTEM_ARCHITECTURE.md) | ✅ |
| 03 | 数据库设计 | [docs/03_DATABASE_DESIGN.md](file:///Users/shajindi/traework/legal-review/docs/03_DATABASE_DESIGN.md) | ✅ |
| 04 | Agent Graph 设计 | [docs/04_AGENT_GRAPH_DESIGN.md](file:///Users/shajindi/traework/legal-review/docs/04_AGENT_GRAPH_DESIGN.md) | ✅ |
| 99 | Sprint 1 总结（本文档） | [docs/99_SPRINT1_SUMMARY.md](file:///Users/shajindi/traework/legal-review/docs/99_SPRINT1_SUMMARY.md) | ✅ |

---

## 2. 设计基线对齐表

| 维度 | 设计基线 |
|------|---------|
| 业务范围 | 县级司法局合法性审查部门 + 5 类送审单位 + 8 项审查项 |
| 功能需求 | 40 条 FR（P0/P1 分级） |
| 非功能需求 | 20 条 NFR（性能/安全/合规/可观测） |
| 架构分层 | 应用层 / Agent 编排层 / 能力服务层 / 数据层 |
| Harness | Context / Evidence / Quality / Security 四类 |
| Loop | 审核质量 / 人工反馈 / 法规更新 三类 |
| Agent 数量 | 9 个审核 Agent + 1 个 Supervisor |
| Graph 框架 | LangGraph 状态图 |
| 数据库 | PostgreSQL 16 + pgvector + 12 张表 |
| 评测体系 | Golden Dataset 100 例 + 6 大指标 |
| 技术栈 | FastAPI / Next.js / pgvector / DeepSeek+Qwen / Docker |
| 迭代上限 | MAX_ITER = 5（硬约束） |

---

## 3. 硬约束落地自查

| # | 硬约束 | 落地位置 | 状态 |
|---|--------|---------|------|
| 1 | Agent 五可（评估/追溯/迭代/扩展/商业化） | 04 文档第 10 章 | ✅ |
| 2 | Prompt 版本化，禁硬编码 | 04 文档第 6 章 + prompts 表 | ✅ |
| 3 | 未注册工具禁调 | 04 文档第 7 章 TOOL_REGISTRY | ✅ |
| 4 | Agent 必须有版本号 | prompts.version 字段 | ✅ |
| 5 | 未经评估 Prompt 禁合并 | 04 文档 6.3 + eval_runs 表 | ✅ |
| 6 | Agent 循环有上限 | ReviewState.max_iteration=5 | ✅ |
| 7 | 安全节点不可绕过 | Supervisor 强制路由 + Security Harness | ✅ |
| 8 | 人工审查闭环不可省 | human_review 必经节点 + 报告章节 | ✅ |
| 9 | AI 不替代最终法律责任 | PRD 1.4 + 报告"审查意见"章节 | ✅ |
| 10 | 所有判断附法规依据 | Evidence Harness + Pydantic 强校验 | ✅ |

---

## 4. Sprint 1 验收 Checklist

- [x] 4 份核心文档（PRD/架构/DB/Agent Graph）全部完成
- [x] Schema 可直接用于 Alembic 迁移（含 pgvector/HNSW 索引）
- [x] Agent Graph 可直接用于 LangGraph 实现（State Schema + 路由表）
- [x] 所有硬约束在文档中明确标注
- [x] 提供 Sprint 2 启动所需的接口契约（5 个 REST 端点）
- [x] Prompt/Tool/Agent 版本管理机制定义
- [x] 评测体系（Golden Dataset + 6 指标）框架定义
- [x] 商业化扩展路径（5 阶段）规划

---

## 5. 风险与未决项

| 项 | 风险/未决 | 处置建议 |
|----|----------|---------|
| 法规库初始数据 | 需司法客户提供县级现行法规清单 | Sprint 3 启动前由法规库管理员提供 |
| OCR 选型 | PaddleOCR vs 商用 API | Sprint 2 评测后决定 |
| Embedding 模型 | BGE-M3 维度 1024 vs bge-large-zh 1024 | Sprint 3 A/B 评测 |
| LLM 供应商 | DeepSeek-V3 / Qwen2.5 | 双模型 Gateway 设计，Sprint 4 切换 |
| 中文 PDF 模板 | WeasyPrint 中文字体 | Sprint 6 验证 |
| Demo 数据脱敏 | 现场演示需匿名化 | Sprint 7 实现 |

---

## 6. Sprint 2 启动条件

### 6.1 已具备

- ✅ 文件存储 Schema（documents 表 + 沙箱路径规则）
- ✅ 文件上传 API 契约（POST /api/v1/documents/upload）
- ✅ 任务查询 API 契约（GET /api/v1/tasks/{task_id}）
- ✅ document_json 结构契约（含锚点 anchor 用于回链）

### 6.2 Sprint 2 待实现

| 任务 | 依赖本文档 |
|------|-----------|
| 文件上传 + 沙箱 | T03 documents 表 + NFR-004 隔离 |
| OCR | T03 parse_status + FR-003 |
| 文本结构化 | T03 parsed_json + FR-004/005 |
| 解析结果预览 UI | FR-008 + document_json Schema |
| 解析失败回退 | FR-009 |
| 上传审计日志 | T08 audit_records + FR-010 |

---

## 7. Sprint 2 起手任务（建议优先级）

1. 后端骨架：FastAPI + SQLAlchemy + Alembic 初始化（基于 03 文档 Schema）
2. 文件沙箱：MinIO 或本地卷 + 任务级目录隔离
3. 上传 API：POST /api/v1/documents/upload + Hash 校验
4. OCR 工具：先集成 PaddleOCR，评测 5 类样本
5. 结构化提取器：实现 [structure_extractor](file:///Users/shajindi/traework/legal-review/docs/04_AGENT_GRAPH_DESIGN.md) 工具
6. doc_parse 节点：[Agent Graph 第 3.1 节](file:///Users/shajindi/traework/legal-review/docs/04_AGENT_GRAPH_DESIGN.md) 实现
7. 上传审计日志：[T08 表](file:///Users/shajindi/traework/legal-review/docs/03_DATABASE_DESIGN.md) 落库
8. 解析预览 UI：Next.js 页面 + Tailwind

---

## 8. 下一步计划

- **立即：** 等待技术委员会评审 4 份文档
- **评审通过后：** 启动 Sprint 2（文件解析能力）
- **并行可启动：** 法规库数据准备（由法规库管理员对接司法客户）

---

**Sprint 1 交付终止。**
