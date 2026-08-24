# Sprint 规划总览 · 行政规范性文件智能合法性审查 Agent 系统

> 文档版本：v1.0.0
> 最后更新：2026-08-22
> 责任人：FDE 交付负责人
> 适用范围：县级司法局合法性审查部门 MVP/商用版本

---

## 1. 项目交付总览

| 阶段 | 周期 | 关键交付物 | 验收准则 |
|------|------|-----------|---------|
| Sprint 1 | 设计 | PRD + 架构 + DB + Agent Graph | 文档评审通过，技术委员会签字 |
| Sprint 2 | 解析 | 文件上传 + OCR + 文本结构化 | 5 类样本（Word/PDF/扫描件）解析准确率 ≥ 95% |
| Sprint 3 | 检索 | 法规库 + Embedding + RAG | Top-10 检索召回率 ≥ 90%，引用准确率 ≥ 85% |
| Sprint 4 | 审核 | 9 个审核 Agent + Graph | 关键节点单测覆盖 ≥ 80%，端到端可跑通 |
| Sprint 5 | 验证 | Verifier + Evidence Chain + Retry Loop | 证据覆盖率 100%，幻觉率 ≤ 5% |
| Sprint 6 | 报告 | 审查意见书 + PDF 导出 | 输出符合司法局规范模板 |
| Sprint 7 | 部署 | Dashboard + Docker + Demo | 现场 3 分钟完成单文件审查 Demo |

---

## 2. Sprint 1 详细任务拆解

### 2.1 PRD（产品需求规格）
- [x] 业务背景与范围
- [x] 用户角色与场景
- [x] 功能需求（FR-001 ~ FR-040）
- [x] 非功能需求（NFR-001 ~ NFR-020）
- [x] 验收标准
- [x] 风险与合规边界

### 2.2 系统架构
- [x] 四层架构：Graph + Harness + Loop + Evaluation
- [x] 组件拓扑图
- [x] 数据流与控制流
- [x] 安全与审计
- [x] 部署拓扑

### 2.3 数据库设计
- [x] PostgreSQL + pgvector Schema
- [x] 9 张核心表 + 索引策略
- [x] 数据生命周期
- [x] 备份与归档

### 2.4 Agent Graph 设计
- [x] State Schema（trace_id/iteration/version）
- [x] 9 个 Agent 节点定义（Input/Output/Prompt/Tool/Eval）
- [x] 边与条件路由
- [x] Harness 接入点
- [x] Loop 边界与迭代上限

---

## 3. 文档索引

| 编号 | 文档 | 路径 |
|------|------|------|
| 00 | Sprint 规划总览 | `docs/00_SPRINT_PLAN.md` |
| 01 | PRD 产品需求规格 | `docs/01_PRD.md` |
| 02 | 系统架构设计 | `docs/02_SYSTEM_ARCHITECTURE.md` |
| 03 | 数据库设计 | `docs/03_DATABASE_DESIGN.md` |
| 04 | Agent Graph 设计 | `docs/04_AGENT_GRAPH_DESIGN.md` |
| 05 | RAG 知识库设计 | `docs/05_RAG_KNOWLEDGE_BASE.md`（Sprint 3） |
| 06 | Evaluation 系统设计 | `docs/06_EVALUATION_SYSTEM.md`（Sprint 5） |
| 07 | 部署与运维 | `docs/07_DEPLOYMENT.md`（Sprint 7） |

---

## 4. 工程铁律（来自项目硬约束）

1. 所有 Agent 必须可评估、可追溯、可迭代、可扩展、可商业化（"五可"原则）
2. Prompt 模板必须版本化，禁止硬编码
3. 未注册工具禁止调用
4. 无版本号的 Agent 禁止生产部署
5. 未经评估的 Prompt 变更禁止合并
6. Agent 循环必须有迭代上限
7. 安全节点不可被绕过
8. AI 不可替代最终法律责任（人工审查闭环不可省略）

---

## 5. Sprint 1 验收 Checklist

- [ ] 4 份文档全部完成并通过技术评审
- [ ] Schema 可直接用于 Alembic 迁移脚本
- [ ] Agent Graph 可直接用于 LangGraph 实现
- [ ] 所有硬约束在文档中明确标注
- [ ] 提供 Sprint 2 启动所需的接口契约
