# 数据库设计 · 行政规范性文件智能合法性审查 Agent 系统

> 文档版本：v1.0.0
> 最后更新：2026-08-22
> 数据库：PostgreSQL 16 + pgvector 扩展
> 设计原则：可追溯 / 可审计 / 任务隔离 / 法规版本化

---

## 1. 概览

### 1.1 扩展与编码

```sql
CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- 数据库编码
ENCODING 'UTF8'
LC_COLLATE 'zh_CN.UTF-8'
LC_CTYPE 'zh_CN.UTF-8'
```

### 1.2 表清单

| 编号 | 表名 | 用途 | Sprint |
|------|------|------|--------|
| T01 | users | 用户 | S1 |
| T02 | organizations | 单位 | S1 |
| T03 | documents | 送审文件元数据 | S1 |
| T04 | legal_documents | 法规库 | S3 |
| T05 | review_tasks | 审查任务 | S1 |
| T06 | review_results | 审查结果缓存 | S4 |
| T07 | agent_logs | Agent 运行日志 | S4 |
| T08 | audit_records | 审计记录 | S1 |
| T09 | feedback_cases | 人工反馈案例 | S5 |
| T10 | prompts | Prompt 版本管理 | S1 |
| T11 | golden_dataset | 评测集 | S5 |
| T12 | eval_runs | 评测运行记录 | S5 |

### 1.3 命名规范

- 表名：snake_case 复数
- 主键：`id` UUID
- 外键：`{table_singular}_id`
- 时间：`created_at` / `updated_at` / `deleted_at`
- 状态：`status` 枚举
- 软删除：`deleted_at IS NOT NULL`

---

## 2. 核心表 Schema

### T01 · users（用户）

```sql
CREATE TABLE users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username        VARCHAR(64) NOT NULL UNIQUE,
    real_name       VARCHAR(64) NOT NULL,
    email           VARCHAR(128) UNIQUE,
    phone           VARCHAR(20),
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(32) NOT NULL CHECK (role IN ('submitter','reviewer','supervisor','admin','librarian')),
    organization_id UUID REFERENCES organizations(id),
    status          VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active','disabled','locked')),
    last_login_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_users_org ON users(organization_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_users_role ON users(role) WHERE deleted_at IS NULL;
```

### T02 · organizations（单位）

```sql
CREATE TABLE organizations (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(128) NOT NULL,
    type        VARCHAR(32) NOT NULL CHECK (type IN ('county_dept','township','street','public_inst','state_owned')),
    parent_id   UUID REFERENCES organizations(id),
    region_code VARCHAR(12),
    status      VARCHAR(16) NOT NULL DEFAULT 'active',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at  TIMESTAMPTZ
);
CREATE INDEX idx_org_parent ON organizations(parent_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_org_type ON organizations(type) WHERE deleted_at IS NULL;
```

### T03 · documents（送审文件）

```sql
CREATE TABLE documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id         UUID NOT NULL REFERENCES review_tasks(id),
    original_name   VARCHAR(255) NOT NULL,
    file_type       VARCHAR(16) NOT NULL CHECK (file_type IN ('docx','pdf','image','txt')),
    file_size       BIGINT NOT NULL,
    file_hash       VARCHAR(64) NOT NULL,  -- sha256
    storage_path    VARCHAR(512) NOT NULL, -- 沙箱内相对路径
    mime_type       VARCHAR(64),
    uploaded_by     UUID NOT NULL REFERENCES users(id),
    parsed_json     JSONB,                  -- 文件解析结构化结果
    parse_status    VARCHAR(16) NOT NULL DEFAULT 'pending' CHECK (parse_status IN ('pending','parsing','done','failed')),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_docs_task ON documents(task_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_docs_hash ON documents(file_hash) WHERE deleted_at IS NULL;
```

### T04 · legal_documents（法规库）

```sql
CREATE TABLE legal_documents (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    law_name        VARCHAR(255) NOT NULL,
    issuing_authority VARCHAR(128) NOT NULL,  -- 发布机关
    publish_date    DATE NOT NULL,
    effective_date  DATE,
    expire_date     DATE,
    law_type        VARCHAR(32) NOT NULL CHECK (law_type IN ('law','admin_reg','local_reg','rule','policy','judicial')),
    law_level       VARCHAR(16) NOT NULL CHECK (law_level IN ('national','province','city','county')),
    version         VARCHAR(32) NOT NULL,    -- 法规版本号
    parent_law_id   UUID REFERENCES legal_documents(id), -- 被修订法规
    status          VARCHAR(16) NOT NULL DEFAULT 'effective' CHECK (status IN ('draft','effective','amended','repealed','expired')),
    raw_text        TEXT NOT NULL,
    parsed_json     JSONB,                    -- 结构化（章节/条款）
    keywords        VARCHAR(255)[] DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_law_name ON legal_documents(law_name) WHERE deleted_at IS NULL;
CREATE INDEX idx_law_type_level ON legal_documents(law_type, law_level) WHERE deleted_at IS NULL;
CREATE INDEX idx_law_status ON legal_documents(status) WHERE deleted_at IS NULL;
```

### T04b · legal_clauses（法规条款 - 切分原子化）

```sql
CREATE TABLE legal_clauses (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    law_id          UUID NOT NULL REFERENCES legal_documents(id),
    chapter         VARCHAR(128),         -- 章
    section         VARCHAR(128),         -- 节
    article_no      VARCHAR(32) NOT NULL, -- 条款号，如"第十五条"
    article_title   VARCHAR(255),
    content         TEXT NOT NULL,        -- 条款原文
    keywords        VARCHAR(255)[] DEFAULT '{}',
    embedding       vector(1024),         -- BGE-M3 1024 维
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 向量索引（HNSW 算法，pgvector 0.5+）
CREATE INDEX idx_clause_embedding ON legal_clauses USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);
CREATE INDEX idx_clause_law ON legal_clauses(law_id);
CREATE INDEX idx_clause_article ON legal_clauses(article_no);
-- 全文检索（中文 trigram）
CREATE INDEX idx_clause_content_trgm ON legal_clauses USING gin (content gin_trgm_ops);
```

### T05 · review_tasks（审查任务）

```sql
CREATE TABLE review_tasks (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id        UUID NOT NULL UNIQUE,  -- 全链路追踪 ID
    title           VARCHAR(255) NOT NULL,
    submitter_id    UUID NOT NULL REFERENCES users(id),
    submitter_org_id UUID NOT NULL REFERENCES organizations(id),
    status          VARCHAR(32) NOT NULL DEFAULT 'created'
                    CHECK (status IN ('created','parsing','classifying','reviewing','verifying','reporting','human_review','done','failed','cancelled')),
    current_node    VARCHAR(64),           -- 当前所在 Agent 节点
    iteration       INT NOT NULL DEFAULT 0,-- Retry 计数
    max_iteration   INT NOT NULL DEFAULT 5, -- 迭代上限（硬约束）
    priority        VARCHAR(8) NOT NULL DEFAULT 'normal' CHECK (priority IN ('low','normal','high','urgent')),
    assigned_reviewer_id UUID REFERENCES users(id),
    submitted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    due_at          TIMESTAMPTZ,
    metadata        JSONB DEFAULT '{}',    -- 扩展字段
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at      TIMESTAMPTZ
);
CREATE INDEX idx_tasks_status ON review_tasks(status) WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_submitter ON review_tasks(submitter_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_reviewer ON review_tasks(assigned_reviewer_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_tasks_trace ON review_tasks(trace_id);
```

### T06 · review_results（审查结果缓存）

```sql
CREATE TABLE review_results (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id         UUID NOT NULL REFERENCES review_tasks(id),
    agent_name      VARCHAR(64) NOT NULL,  -- 产出 Agent
    iteration       INT NOT NULL DEFAULT 0,
    node_status     VARCHAR(16) NOT NULL CHECK (node_status IN ('pass','fail','retry','skipped')),
    output_json     JSONB NOT NULL,        -- Agent 完整输出
    risks           JSONB DEFAULT '[]',    -- 风险点列表
    evidences       JSONB DEFAULT '[]',    -- 证据链
    confidence      NUMERIC(4,3),          -- 0.000-1.000
    duration_ms     INT,                  -- 节点耗时
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_results_task ON review_results(task_id);
CREATE INDEX idx_results_agent ON review_results(agent_name, iteration);
```

### T07 · agent_logs（Agent 运行日志）

```sql
CREATE TABLE agent_logs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id        UUID NOT NULL,
    task_id         UUID REFERENCES review_tasks(id),
    agent_name      VARCHAR(64) NOT NULL,
    iteration       INT NOT NULL DEFAULT 0,
    prompt_version  VARCHAR(32) NOT NULL,   -- Prompt 版本
    tool_name       VARCHAR(64),
    input_summary   TEXT,                   -- 输入摘要（避免全量存）
    output_summary  TEXT,
    tokens_in       INT,
    tokens_out      INT,
    latency_ms      INT,
    cost_cny        NUMERIC(10,4),
    status          VARCHAR(16) NOT NULL CHECK (status IN ('success','failed','timeout','retry')),
    error_msg       TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_logs_trace ON agent_logs(trace_id);
CREATE INDEX idx_logs_task ON agent_logs(task_id);
CREATE INDEX idx_logs_agent ON agent_logs(agent_name, created_at DESC);
```

### T08 · audit_records（审计记录）

```sql
CREATE TABLE audit_records (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    trace_id        UUID,
    actor_id        UUID REFERENCES users(id),
    actor_role      VARCHAR(32),
    action          VARCHAR(64) NOT NULL,  -- create/upload/review/modify/sign/delete
    target_type     VARCHAR(32),           -- task/document/law/report
    target_id       UUID,
    before_value    JSONB,
    after_value     JSONB,
    ip_address      INET,
    user_agent      VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_actor ON audit_records(actor_id, created_at DESC);
CREATE INDEX idx_audit_target ON audit_records(target_type, target_id);
CREATE INDEX idx_audit_trace ON audit_records(trace_id);
```

### T09 · feedback_cases（人工反馈案例）

```sql
CREATE TABLE feedback_cases (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    task_id         UUID NOT NULL REFERENCES review_tasks(id),
    reviewer_id     UUID NOT NULL REFERENCES users(id),
    agent_name      VARCHAR(64) NOT NULL,
    section         VARCHAR(64),            -- 报告章节
    ai_output       JSONB NOT NULL,         -- AI 原始输出
    human_modified  JSONB NOT NULL,         -- 人工修改后内容
    modify_reason   TEXT NOT NULL,
    reason_category VARCHAR(32) CHECK (reason_category IN ('wrong_law','wrong_clause','wrong_judgment','missing_risk','extra_risk','format','other')),
    incorporated    BOOLEAN NOT NULL DEFAULT FALSE,  -- 是否已回流到 Prompt/规则
    prompt_version_after VARCHAR(32),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_feedback_task ON feedback_cases(task_id);
CREATE INDEX idx_feedback_agent ON feedback_cases(agent_name, incorporated);
```

### T10 · prompts（Prompt 版本管理）

```sql
CREATE TABLE prompts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_key      VARCHAR(64) NOT NULL,  -- 如 'authority_review'
    version         VARCHAR(32) NOT NULL,  -- 语义化版本 v1.0.0
    template        TEXT NOT NULL,        -- 含 {{变量}} 占位符
    variables       JSONB DEFAULT '{}',   -- 变量定义
    model_name      VARCHAR(64),          -- 推荐 LLM
    temperature     NUMERIC(3,2) DEFAULT 0.2,
    status          VARCHAR(16) NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','evaluating','active','deprecated')),
    eval_pass_rate  NUMERIC(5,2),         -- 评测通过率
    created_by      UUID REFERENCES users(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    activated_at    TIMESTAMPTZ,
    UNIQUE (prompt_key, version)
);
CREATE INDEX idx_prompts_key_active ON prompts(prompt_key, status) WHERE status = 'active';
```

### T11 · golden_dataset（评测集）

```sql
CREATE TABLE golden_dataset (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    case_name        VARCHAR(255) NOT NULL,
    category         VARCHAR(32) NOT NULL CHECK (category IN ('normal','authority_violation','procedure_missing','content_violation','boundary','non_normative')),
    input_file_path  VARCHAR(512) NOT NULL,
    expected_json    JSONB NOT NULL,        -- 期望输出（含风险点、依据、置信度）
    expected_status  VARCHAR(16) NOT NULL,  -- 期望总体 PASS/RISK/FAIL
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_golden_category ON golden_dataset(category);
```

### T12 · eval_runs（评测运行）

```sql
CREATE TABLE eval_runs (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    run_id          UUID NOT NULL UNIQUE,
    prompt_version  VARCHAR(32) NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL,
    finished_at     TIMESTAMPTZ,
    total_cases     INT NOT NULL,
    parse_acc       NUMERIC(5,2),         -- 文件解析准确率
    retrieval_acc   NUMERIC(5,2),         -- 检索准确率
    citation_acc    NUMERIC(5,2),         -- 引用准确率
    risk_kappa      NUMERIC(4,3),         -- 风险一致性
    report_complete  NUMERIC(5,2),        -- 报告完整性
    hallucination_rate NUMERIC(5,2),      -- 幻觉率
    overall_pass     BOOLEAN,
    raw_result_path  VARCHAR(512)         -- 原始结果文件
);
CREATE INDEX idx_evalruns_prompt ON eval_runs(prompt_version, started_at DESC);
```

---

## 3. 视图与物化视图

### 3.1 任务统计视图

```sql
CREATE VIEW v_task_stats AS
SELECT
    DATE_TRUNC('day', submitted_at) AS day,
    submitter_org_id,
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE status = 'done') AS done,
    COUNT(*) FILTER (WHERE status = 'failed') AS failed,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) AS avg_duration_s
FROM review_tasks
WHERE deleted_at IS NULL
GROUP BY 1, 2;
```

### 3.2 Agent 性能视图

```sql
CREATE VIEW v_agent_perf AS
SELECT
    agent_name,
    prompt_version,
    AVG(latency_ms) AS avg_latency_ms,
    PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY latency_ms) AS p99_latency,
    COUNT(*) FILTER (WHERE status = 'success')::FLOAT / COUNT(*) AS success_rate,
    AVG(tokens_in + tokens_out) AS avg_tokens
FROM agent_logs
WHERE created_at > now() - INTERVAL '7 days'
GROUP BY 1, 2;
```

---

## 4. 数据生命周期

| 表 | 保留期 | 归档策略 |
|----|--------|---------|
| documents | 3 年 | 归档至冷存储后删除 |
| review_tasks | 3 年 | 同上 |
| review_results | 1 年 | 转冷 |
| agent_logs | 6 个月 | 转 ELK 后删 |
| audit_records | 3 年（合规要求） | 强制保留 |
| feedback_cases | 长期 | 不删除（案例库资产） |
| legal_documents | 长期 | 不删除（历史版本） |
| golden_dataset | 长期 | 不删除 |

---

## 5. 备份与恢复

| 类型 | 频率 | 保留 |
|------|------|------|
| 法规库增量 | 每日 02:00 | 7 天 |
| 全量 | 每周日 03:00 | 4 周 |
| 文件沙箱 | 每周日 04:00 | 4 周 |
| 审计日志 | 每日 02:30 | 90 天 |

**恢复目标：** RPO ≤ 24h，RTO ≤ 4h。

---

## 6. Alembic 迁移注意事项

1. pgvector 扩展必须在第一个迁移中创建
2. HNSW 索引在大数据量时构建较慢，应在法规库填充前或离线构建
3. UUID 主键默认值依赖 `uuid-ossp` 扩展
4. 中文 trigram 索引需 `pg_trgm` 扩展
5. `vector(1024)` 维度需与 Embedding 模型对齐（BGE-M3 = 1024）

---

## 7. 数据访问层约定

| 层 | 责任 |
|----|------|
| SQLAlchemy ORM | 实体映射 |
| Pydantic Schema | API 输入输出校验 |
| Repository Pattern | 业务查询封装 |
| Service Layer | 事务边界 |

> 代码骨架将在 Sprint 2 实现阶段落库，本文档只定义 Schema 契约。

---

**数据库设计文档终止**
