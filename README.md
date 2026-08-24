# 行政规范性文件智能合法性审查 Agent 系统

> FDE 项目 · 县级司法局合法性审查部门
> Sprint 1 设计基线 ✅ ｜ Sprint 2 文件解析能力（进行中）

## 项目结构

```
legal-review/
├── docs/                          # 工程文档（Sprint 1 完成）
│   ├── 00_SPRINT_PLAN.md
│   ├── 01_PRD.md
│   ├── 02_SYSTEM_ARCHITECTURE.md
│   ├── 03_DATABASE_DESIGN.md
│   ├── 04_AGENT_GRAPH_DESIGN.md
│   └── 99_SPRINT1_SUMMARY.md
├── backend/                       # FastAPI 后端
│   ├── app/
│   │   ├── core/                  # config/constants/errors/logging
│   │   ├── db/                    # base/session
│   │   ├── models/                # ORM（12 张表）
│   │   ├── schemas/               # Pydantic Schemas
│   │   ├── services/              # sandbox/audit 业务服务
│   │   ├── tools/                 # parsers/ocr/registry 工具
│   │   ├── agent/                 # LangGraph state/harness/nodes/graph
│   │   ├── api/v1/                # REST 路由
│   │   └── main.py                # FastAPI 入口
│   ├── alembic/                   # 迁移
│   ├── tests/                     # pytest
│   ├── pyproject.toml
│   ├── Dockerfile
│   └── .env
├── docker-compose.yml             # Postgres+pgvector / Redis / Backend
└── README.md
```

## 快速启动

```bash
# 1. 启动依赖（PostgreSQL+pgvector / Redis）
docker compose up -d postgres redis

# 2. 后端安装
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# 3. 数据库迁移（含 pgvector/HNSW/pg_trgm 扩展）
alembic upgrade head

# 4. 启动 API
uvicorn app.main:app --reload --port 8000

# 5. 跑测试
pytest

# 6. 文档：访问 http://localhost:8000/docs
```

## 工程铁律

详见 [docs/00_SPRINT_PLAN.md §4](docs/00_SPRINT_PLAN.md)

1. Agent 五可：评估/追溯/迭代/扩展/商业化
2. Prompt 版本化，禁硬编码
3. 未注册工具禁调
4. Agent 必须有版本号
5. 未经评估 Prompt 禁合并
6. Agent 循环有上限（MAX_ITER=5）
7. 安全节点不可绕过
8. 人工审查闭环不可省
9. AI 不替代最终法律责任
10. 所有判断附法规依据（Evidence Harness）

## Sprint 进度

| Sprint | 状态 | 关键交付 |
|--------|------|---------|
| 1 设计 | ✅ | PRD + 架构 + DB + Agent Graph |
| 2 解析 | 🚧 | 文件上传 + OCR + 结构化（本 Sprint） |
| 3 检索 | ⏳ | 法规库 + Embedding + RAG |
| 4 审核 | ⏳ | 9 个审核 Agent + LangGraph |
| 5 验证 | ⏳ | Verifier + Evidence + Retry Loop |
| 6 报告 | ⏳ | 审查意见书 + PDF |
| 7 部署 | ⏳ | Dashboard + Demo |
