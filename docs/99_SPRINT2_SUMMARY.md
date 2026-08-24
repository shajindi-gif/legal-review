# Sprint 2 阶段性总结 · 后端骨架交付

> 交付日期：2026-08-22
> 阶段：Sprint 2（文件解析能力）后端骨架
> 状态：✅ 后端骨架完成，待集成测试 + 5 类样本 OCR 评测

---

## 1. 交付物清单

| 类别 | 文件 | 说明 |
|------|------|------|
| 项目骨架 | `pyproject.toml` / `.env` / `.gitignore` / `Dockerfile` / `docker-compose.yml` / `README.md` | 全部就绪 |
| 核心配置 | `app/core/config.py` / `constants.py` / `errors.py` / `logging.py` | Settings + StrEnum + AppError 体系 + structlog |
| DB 基础 | `app/db/base.py` / `session.py` | DeclarativeBase + 异步 engine/session/dispose |
| ORM 模型 | `app/models/{user,document,legal,task,platform}.py` | 12 张表，含 pgvector Vector(1024) |
| Alembic | `alembic.ini` / `env.py` / `script.py.mako` / `versions/0001_initial_schema.py` | 含 pgvector/HNSW/pg_trgm 扩展与 12 张表迁移 |
| Schemas | `app/schemas/{common,document,task}.py` | Pydantic v2 + DocumentJson 结构化输出 |
| 服务层 | `app/services/sandbox.py` / `audit.py` | 沙箱（路径防逃逸 + 任务隔离 + Hash）+ 审计 |
| 工具层 | `app/tools/{parsers,ocr,registry}.py` | txt/docx/pdf/ocr 解析 + Tool Registry 强校验 |
| Agent 层 | `app/agent/{state,harness,nodes,graph}.py` | ReviewState + 四类 Harness + doc_parse + LangGraph stub |
| API 层 | `app/api/deps.py` + `app/api/v1/{health,documents,tasks}.py` | 健康检查 + 上传 + 任务查询 |
| 测试 | `tests/{conftest,test_sandbox,test_parsers,test_harness}.py` | 20 个用例全部通过 |
| 应用入口 | `app/main.py` | FastAPI 工厂 + trace_id 中间件 + 全局异常处理 |

---

## 2. 质量门控结果

| 门控 | 命令 | 结果 |
|------|------|------|
| Python 语法 | `python3 -m compileall app tests` | ✅ 0 错误 |
| Ruff Lint | `ruff check app/ tests/` | ✅ All checks passed |
| 单元测试 | `pytest tests/` | ✅ 20 passed in 0.21s |

测试覆盖：
- `test_sandbox.py` 8 个用例：扩展名/大小/路径逃逸/任务隔离/Hash/sanitize
- `test_parsers.py` 4 个用例：TXT 基础解析/空文件/dispatch/不支持类型
- `test_harness.py` 8 个用例：Context/Evidence 完整性/Evidence 拒绝/Quality 迭代上限/Security 节点

---

## 3. 硬约束落地

| 硬约束 | 落地位置 |
|--------|---------|
| Agent 五可 | `app/agent/state.py` 含 trace_id/iteration/version；`tools/registry.py` 工具版本化 |
| Prompt 版本化 | `app/models/platform.py` Prompt 表含 version 字段（Sprint 4 落地 YAML） |
| 未注册工具禁调 | `app/tools/registry.py` `get_tool()` 强校验 |
| Agent 版本号 | ToolSpec.version + Prompt.version |
| 未经评估 Prompt 禁合并 | `app/models/platform.py` Prompt.status 含 evaluating（Sprint 5 完整） |
| Agent 循环上限 | `ReviewState.max_iteration=5` + `QualityHarness.check_iteration` |
| 安全节点不可绕过 | `SecurityHarness.assert_node_allowed` |
| 人工审查闭环 | `nodes.py` 含 `human_review_node` stub（Sprint 6 完整） |
| AI 不替代法律责任 | PRD §1.4 + 报告章节"审查意见"含人工签发栏 |
| 所有判断附法规依据 | `EvidenceHarness.enforce` + Pydantic 强校验 |

---

## 4. 接口已就绪（Sprint 3 启动依赖）

| 接口 | 路径 | 状态 |
|------|------|------|
| 文件上传 | `POST /api/v1/documents/upload` | ✅ |
| 任务查询 | `GET /api/v1/tasks/{task_id}` | ✅ |
| 任务状态 | `GET /api/v1/tasks/{task_id}/status` | ✅ |
| 任务文件列表 | `GET /api/v1/tasks/{task_id}/documents` | ✅ |
| 单文件详情（含 parsed_json） | `GET /api/v1/tasks/{task_id}/documents/{doc_id}` | ✅ |
| 健康检查 | `GET /health` `/ready` | ✅ |
| OpenAPI | `GET /api/v1/openapi.json` | ✅ |
| 文档 | `GET /docs` `/redoc` | ✅ |

---

## 5. Sprint 2 剩余工作

| 任务 | 状态 | 说明 |
|------|------|------|
| 后端骨架 | ✅ | 本文档 |
| 端到端集成测试 | ⏳ | 需启动 PostgreSQL+pgvector，跑 alembic upgrade + 上传→解析全流程 |
| 5 类样本解析准确率评测 | ⏳ | 需准备 5 类样本（Word/PDF/扫描件）+ PaddleOCR 模型下载 |
| 解析结果预览 UI | ⏳ | Next.js frontend，Sprint 7 与 Dashboard 一并交付 |
| Demo 模式 | ⏳ | Sprint 7 |

---

## 6. 启动方式

```bash
# 1. 启动依赖
cd /Users/shajindi/traework/legal-review
docker compose up -d postgres redis

# 2. 后端
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
alembic upgrade head

# 3. 跑测试
PYTHONPATH=. pytest

# 4. 启动 API
uvicorn app.main:app --reload --port 8000
# 文档：http://localhost:8000/docs
```

---

## 7. Sprint 3 启动条件

### 已具备
- ✅ 法规库 ORM（`LegalDocument` + `LegalClause`）
- ✅ `legal_clauses.embedding` 列（pgvector Vector(1024)）
- ✅ HNSW 向量索引（迁移脚本中）
- ✅ 中文 trigram 全文检索索引
- ✅ Tool Registry 注册机制（`rag_search` 待 Sprint 3 注册）

### Sprint 3 待实现
1. `app/tools/embedding.py` - BGE-M3 封装
2. `app/tools/rag.py` - RAG 混合检索（关键词+向量+元数据过滤）
3. `app/services/legal_library.py` - 法规库导入/切分/索引服务
4. `app/api/v1/legal.py` - 法规库管理 API（导入/查询/状态）
5. `legal_retrieve_node` - Agent 节点实现
6. 法规库初始数据（需法规库管理员对接司法客户提供县级现行法规清单）
7. Embedding 模型 A/B 评测（BGE-M3 vs bge-large-zh）

---

**Sprint 2 后端骨架交付终止。下一步：启动 PostgreSQL 跑端到端集成测试，或直接进入 Sprint 3 法规库与 RAG。**
