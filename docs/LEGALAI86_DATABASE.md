# LegalAI 86 /「智审 · LegalReview」数据库设计文档

> 本文基于仓库真实 ORM 模型（`backend/app/models/*.py`）与 Alembic 迁移
> （`backend/alembic/versions/*.py`）撰写，字段/约束/索引均可回溯到代码。
> 未在本仓库实际存在的组件（如 Qdrant）一律标注**未接入**，不编造。
> 升级分支：`upgrade/legalai86-platform`；相关：`docs/LEGALAI86_PRD.md`、`docs/LEGALAI86_AUDIT.md`。

---

## 1. 数据层概览

| 组件 | 用途 | 证据 |
|---|---|---|
| **PostgreSQL**（asyncpg / SQLAlchemy 2 async） | 主数据库；扩展 `vector`（pgvector）、`uuid-ossp`、`pg_trgm` | `backend/alembic/versions/0001_initial_schema.py`；`backend/app/db/base.py`；`core/config.py` `database_url` |
| **pgvector** | 向量存储与检索（`legal_clauses.embedding` HNSW；`document_chunks.embedding`），维度 1024（BGE-M3） | `0001` 建 `idx_clause_embedding`（HNSW，`vector_cosine_ops`，m=16/ef_construction=64）；`models/legal.py`、`models/workspace.py`（`Vector(get_settings().embedding_dim)`）；`core/config.py` `embedding_dim=1024` |
| **Redis** | 限流（LLM RPM）/ SSE / 缓存，DB 兜底 | `core/redis.py`、`services/rate_limit.py`、`tools/llm.py`、`models/identity.py`（`RateLimitBucket` 注释"优先 Redis，挂了降级到 DB"）；`core/config.py` `redis_url` |
| **Qdrant** | —— | **未接入**：`backend/app` 全仓库无任何 Qdrant 引用；向量统一由 pgvector 承载 |
| 文件存储 | 本地沙箱 + Docker volume（`legal_backend_uploads`/`_sandbox`）+ nginx `/uploads/` | `services/sandbox.py`；`docs/LEGALAI86_AUDIT.md` §1 第 11 项（**非 S3 兼容对象存储**，技术债） |

> 结论：**"PostgreSQL + pgvector + Redis" 是真实数据层；Qdrant 不存在于本代码库**。

---

## 2. 表清单（按域分组）

所有表定义分散于 `backend/app/models/`，集中导入见 `backend/app/models/__init__.py`。共 **33 张表**。

### 2.1 身份 / 租户（`models/user.py` + `models/identity.py`）

| 表 | 说明 | 关键点 |
|---|---|---|
| `organizations` | 单位/组织（T02） | `type`、`parent_id` 自引用、`region_code`；索引 `idx_org_parent`/`idx_org_type`（部分索引 `deleted_at IS NULL`） |
| `users` | 用户（T01） | `username`/`email` 唯一；`role`、`organization_id`、`status`；含身份 M0 增量列（`is_super_admin`、onboarding、锁定/验证时间戳） |
| `user_plans` | 订阅与配额（T13） | `user_id` 唯一；`tier`、`quota_daily`（-1 不限）、`free_trial_used`/`free_trial_limit`（`0007`） |
| `orders` | 套餐订单（T14） | `amount_cny` Numeric(10,2)；`status` |
| `payments` | 支付流水（T15） | `order_id`+`user_id`；`raw_callback` JSONB 存回调 |
| `oauth_identities` | OAuth 绑定（T16） | `uq(provider, provider_user_id)`；`access_token_enc`/`refresh_token_enc` **Fernet 加密后存 LargeBinary** |
| `verification_codes` | 验证码（T17） | `code_hash`（bcrypt）；`ix_vc_target_purpose`、`ix_vc_expires` |
| `refresh_tokens` | 刷新令牌（T18） | `token_hash` 唯一；`replaced_by_id` 自引用支持 rotation |
| `user_login_events` | 登录审计（T19） | 成功/失败均落库；`ip_address` INET（原始） |
| `user_acquisition_sources` | UTM 归因（T20） | **PK = user_id**（一用户一行） |
| `user_events` | 通用事件（T21） | `event_name`、`properties` JSONB、`ip_address` INET |
| `account_link_pending` | 待合并账号（T22） | `confirm_token` 唯一 |
| `rate_limit_buckets` | DB 兜底限流（T23） | **PK = BigInteger 自增**（非 UUID）；`ix_rlb_key_window` |

### 2.2 任务与文档（`models/task.py` + `models/document.py` + `models/workspace.py`）

| 表 | 说明 | 关键点 |
|---|---|---|
| `review_tasks` | 审查任务（T05） | `trace_id` 唯一；`submitter_id`/`submitter_org_id`/`organization_id`；`status`、`current_node`、`iteration`/`max_iteration` |
| `documents` | 送审文件（T03） | `task_id` FK；`file_hash` sha256；`parsed_json` JSONB；`organization_id`（`0006` 冗余回填） |
| `review_results` | 节点结果缓存（T06） | `agent_name`+`iteration`；`output_json`/`risks`/`evidences` JSONB；`confidence` Numeric(4,3) |
| `agent_logs` | Agent 日志（T07） | `prompt_version`、`tokens_in/out`、`cost_cny` Numeric(10,4)；`organization_id` nullable |
| `projects` | 统一工作台容器（`0009`） | `project_type`（`legal_research`/`contract_review`/`gov_review`/`document_draft`）、`status`、`metadata` JSONB |
| `document_versions` | 版本化文档（`0009`） | **`uq(document_id, version_no)`**；`content_hash` sha256；`project_id`/`document_id` FK |
| `document_chunks` | 文档分块 + 向量（`0009`） | **`uq(document_version_id, chunk_index)`**；`embedding` Vector(1024) |

### 2.3 法律库（`models/legal.py`）——**全局共享，无 `organization_id`**

| 表 | 说明 | 关键点 |
|---|---|---|
| `legal_documents` | 法规（T04） | `law_name`/`issuing_authority`/`publish_date`；`status`（`effective`/`repealed`/…）；`keywords` ARRAY；**`0009` 补溯源字段** `source_url`/`source_type`/`content_hash`/`last_verified_at`/`document_number` |
| `legal_clauses` | 法规条款（T04b，向量检索） | `article_no`、`content`、`embedding` Vector(1024)；HNSW `idx_clause_embedding` + trigram GIN `idx_clause_content_trgm` |
| `legal_sources` | 权威数据源登记（`0009`） | `authorization_status`（`verified`/`restricted`/`prohibited`/**`unknown` 默认**）；`enabled` 默认 `false`；`ix_legal_sources_domain` |

### 2.4 调研 / 合同（`models/research.py` + `models/contract.py`）

| 表 | 说明 | 关键点 |
|---|---|---|
| `research_sessions` | 法律研究会话（`0009`） | `answer_json` JSONB（固定 8 段）；`citations` JSONB（逐条核验结果）；`as_of_date` |
| `contract_reviews` | 合同审查（`0009`） | `findings` JSONB（`[{level, clause_no, clause_text, issue, suggestion, basis}]`）；`redline` JSONB（`[{clause_no, before, after, reason, level}]`）；`overall_risk`、`stance` |

### 2.5 平台（`models/platform.py`）

| 表 | 说明 | 关键点 |
|---|---|---|
| `audit_records` | 审计记录（T08） | **强制保留 3 年**；`before_value`/`after_value` JSONB；`ip_address` INET |
| `feedback_cases` | 人工反馈案例（T09） | 面向 prompt 优化（`ai_output`/`human_modified`/`modify_reason`）；**长期保留作案例库** |
| `prompts` | Prompt 版本（T10） | **`uq(prompt_key, version)`**；`status`；部分索引 `idx_prompts_key_active`（`status='active'`） |
| `golden_dataset` | 评测集（T11） | 长期保留；`expected_json` JSONB |
| `eval_runs` | 评测运行（T12） | `run_id` 唯一；`parse_acc`/`citation_acc`/`risk_kappa`/`hallucination_rate` |

### 2.6 分析 / 通知 / 反馈（`models/analytics.py` + `models/notification.py` + `models/user_feedback.py`）

| 表 | 说明 | 关键点 |
|---|---|---|
| `analytics_events` | 商业化埋点（`0008`） | **PK = Integer 自增**；`ip_hash`（**哈希，不存原文**）；`properties` JSONB 禁止 PII |
| `notifications` | 通知中心（T24，`0004`） | `read_at NULL = 未读`；复合索引 `ix_notif_recipient_unread`/`ix_notif_recipient_created`；`payload` JSONB |
| `user_feedback` | 用户反馈（T25，`0005`） | 与 `feedback_cases` 分工不同（投票+评论+状态流转）；`organization_id`（`0006` 回填） |

---

## 3. 关键表字段说明（JSONB 用途）

| 表.字段 | 类型 | 用途 |
|---|---|---|
| `contract_reviews.findings` | JSONB | 风险明细数组，5 档（`critical`/`high`/`medium`/`low`/`info`），每条含条款、问题、建议、依据核验状态 |
| `contract_reviews.redline` | JSONB | 对照修改视图（before→after），**建议视图，非 Word 原生修订** |
| `research_sessions.answer_json` | JSONB | 结构化回答（`sections` 8 段 + `retrieved` RAG 命中 + `prompt_version` + `usage`） |
| `research_sessions.citations` | JSONB | 逐条引证核验结果（含 `verified`/`source_url`/`validity`/`message`） |
| `review_results.output_json` | JSONB | 各 Agent 节点原始输出；`report_generation` 内含 `report_markdown` |
| `documents.parsed_json` | JSONB | 解析产物（`body_paragraphs`/`title`/`parser_version`） |
| `prompts.variables` | JSONB | Prompt 模板变量定义 |
| `payments.raw_callback` | JSONB | 支付渠道原始回调 |
| `models/*.metadata_` | JSONB | 各新表统一 `metadata`（列名 `metadata`，属性名 `metadata_`），如规则包 region、prompt 版本 |

---

## 4. 多租户隔离约定

- **列名约定**：业务表统一 `organization_id`（UUID FK → `organizations.id`，`ondelete=CASCADE`，`index=True`）。
- **迁移 `0006_tenant_organization_id.py`**：为 6 张业务表加 `organization_id` + backfill + 索引：
  - `review_tasks`（已有 `submitter_org_id`，冗余保留，不破坏 FK）
  - `documents` ⇐ `task_id → review_tasks.organization_id`
  - `review_results` ⇐ `task_id`
  - `agent_logs` ⇐ `task_id`（**可空**，关联断时也允许）
  - `notifications` ⇐ `recipient_id → users.organization_id`
  - `user_feedback` ⇐ `user_id → users.organization_id`
  - 采用 **nullable → backfill → NOT NULL** 三步走；加复合索引支撑 `WHERE organization_id = ?`。
- **不加租户列（有意为之）**：`legal_documents`/`legal_clauses`（**全局共享法规库**）；`audit_records`/`prompts`/`golden_dataset`/`eval_runs`/`feedback_cases`（**平台数据**）。
- **隔离实现**：`backend/app/services/tenant.py`（`apply_org_filter` / `apply_org_filter_with_column` / `load_user_org`）+ `backend/app/api/deps.py`（`get_tenant_context`）。**未引入 PostgreSQL RLS policy**（`0006` 注释明示：避免 superuser 绕过 + 迁移复杂度）。
- **PHASE 1-2 新表**（`projects`/`document_versions`/`document_chunks`/`research_sessions`/`contract_reviews`）统一遵循"UUID 主键 + `organization_id` + `created_at`/`updated_at` + `created_by` + `status`"约定（`models/workspace.py` 注释）。

---

## 5. JSONB 与索引

### 5.1 主键与公共混入（`backend/app/db/base.py`）

- `UUIDPkMixin`：UUID 主键，`default=uuid4`（PG 侧旧表用 `uuid_generate_v4()`）。
- `TimestampMixin`：`created_at`/`updated_at`（`server_default=now()`，`onupdate=now()`）。
- `SoftDeleteMixin`：`deleted_at`（NULL 即未删除）——大量查询以 `deleted_at IS NULL` 过滤，**大量索引为部分索引**。

### 5.2 唯一约束汇总

| 约束 | 表 |
|---|---|
| `users.username` / `users.email` | users |
| `review_tasks.trace_id` | review_tasks |
| `uq_document_versions_document_version`(document_id, version_no) | document_versions |
| `uq_document_chunks_version_index`(document_version_id, chunk_index) | document_chunks |
| `uq_prompts_key_version`(prompt_key, version) | prompts |
| `eval_runs.run_id` | eval_runs |
| `uq_oauth_provider_user`(provider, provider_user_id) | oauth_identities |
| `refresh_tokens.token_hash` | refresh_tokens |
| `user_plans.user_id` | user_plans |
| `account_link_pending.confirm_token` | account_link_pending |

### 5.3 关键索引

- **向量**：`idx_clause_embedding` = `legal_clauses.embedding` **HNSW**（`vector_cosine_ops`, m=16, ef_construction=64）。
- **全文**：`idx_clause_content_trgm` = `legal_clauses.content` **GIN + gin_trgm_ops**（中文 trigram）。
- **审计/日志**：`idx_audit_actor`(actor_id, created_at)、`idx_audit_target`(target_type, target_id)、`idx_logs_trace`/`idx_logs_task`/`idx_logs_agent`。
- **通知**：`ix_notif_recipient_unread`(recipient_id, read_at, created_at)、`ix_notif_recipient_created`。
- **身份**：`ix_oauth_user`、`ix_rt_user`/`ix_rt_expires`、`ix_vc_target_purpose`（`created_at DESC`）、`ix_login_user_time`/`ix_login_ip_time`/`ix_login_method_time`、`ix_event_name_time`/`ix_event_user_time`/`ix_event_anon_time`。
- **PHASE 1-2 新表**：`ix_*_organization_id`、`ix_document_versions_project_id`/`_document_id`、`ix_contract_reviews_project_id`/`_document_version_id`、`ix_document_chunks_document_version_id`、`ix_legal_sources_domain`、`ix_research_sessions_project_id`。
- **埋点**（`0008`）：`(event, created_at)` 漏斗趋势、`(user_id, created_at)` 用户回溯。

---

## 6. 迁移历史与回滚策略

**迁移链（线性）**：`0001 → 0002 → c369d702b000 → 0003 → 0004 → 0005 → 0006 → 0007 → 0008 → 0009`

| 版本号 | 文件 | 用途 | downgrade |
|---|---|---|---|
| `0001` | `0001_initial_schema.py` | 初始 schema：扩展 `vector`/`uuid-ossp`/`pg_trgm`；T01~T12 共 12 表；HNSW 向量索引；trigram 全文索引 | 完整逆操作（drop 表/索引） |
| `0002` | `0002_saas_user_subscription.py` | SaaS 用户系统：`users.company` + T13 `user_plans` / T14 `orders` / T15 `payments` | 有 |
| `c369d702b000` | `c369d702b000_expand_documents_mime_type_to_128.py` | 仅扩展 `documents.mime_type` VARCHAR(64)→128（备注：其它 autogenerate 差异为历史状态不一致，不修） | 有（回退为 64） |
| `0003` | `0003_production_identity_system.py` | `users` 扩 13 列 + 6 张身份表（T16~T23） | 有 |
| `0004` | `0004_notifications.py` | T24 `notifications` 通知中心 | 有 |
| `0005` | `0005_user_feedback.py` | T25 `user_feedback` 用户反馈中心 | 有 |
| `0006` | `0006_tenant_organization_id.py` | 6 张业务表加 `organization_id` + backfill + 索引（见 §4） | 有 |
| `0007` | `0007_free_trial_quota.py` | `user_plans` 加 `free_trial_used`/`free_trial_limit` | 有 |
| `0008` | `0008_analytics_events.py` | 新建 `analytics_events` + 两查询索引 | 有 |
| `0009` | `0009_legalai86_workspace.py` | PHASE 1-2：新建 `projects`/`document_versions`/`document_chunks`/`research_sessions`/`contract_reviews`/`legal_sources`；`legal_documents` 补溯源字段 | **完整 downgrade，已实测 upgrade→downgrade→upgrade 往返成功** |

**回滚策略**（`docs/LEGALAI86_AUDIT.md` §3）：
1. 每个新迁移**必须实现 `downgrade()`**（`0009` 已满足，含列删除逆序 + 表/索引删除）；
2. 部署前执行 `alembic downgrade -1` 演练；
3. 部署顺序：**先 `alembic upgrade head` 再换容器**；
4. 生产镜像**内嵌代码**（无 volume mount），部署前须先备份（`deploy/scripts/backup_pg.sh`）与 `deploy/.env`。

---

## 7. 数据保留与脱敏

| 表/字段 | 保留与脱敏策略 | 证据 |
|---|---|---|
| `audit_records` | **强制保留 3 年**（合规要求） | `models/platform.py` 注释 |
| `feedback_cases` | **长期保留**，作案例库资产 | `models/platform.py` 注释 |
| `golden_dataset` | **长期保留** | `models/platform.py` 注释 |
| `analytics_events.ip_hash` | **仅存哈希，不存 IP 原文**；`properties` 禁 PII | `models/analytics.py` 表注释 |
| `oauth_identities.access_token_enc`/`refresh_token_enc` | **Fernet 对称加密**后存 LargeBinary | `models/identity.py` 注释 |
| `verification_codes.code_hash` | bcrypt 哈希（非明文） | `models/identity.py` |
| `refresh_tokens.token_hash` | 哈希存储（非明文） | `models/identity.py` |
| `user_login_events.ip_address` / `user_events.ip_address` | INET 原始 IP（**未哈希**，属待评估项） | `models/identity.py` |
| 软删除 | 业务表 `deleted_at` 标记，非物理删除 | `db/base.py` `SoftDeleteMixin` |

---

## 8. 未决与技术债

1. **历史索引漂移**：`c369d702b000` 迁移备注与 `docs/LEGALAI86_AUDIT.md`/`CHANGELOG` 均指出 —— `analytics_events` 等表存在 autogenerate 检测到的 index/timestamp 差异，"历史状态不一致，不在本次修复范围内"，**需单独迁移清理**。
2. **`document_chunks.embedding` 无向量索引**：`0009` 仅建普通索引（`ix_document_chunks_organization_id`、`ix_document_chunks_document_version_id`），**未建 HNSW/GIN**；文档分块向量检索性能待补（对比 `legal_clauses` 已有 HNSW）。
3. **无 `organization_members` 成员关系表**：成员关系仅靠 `users.organization_id`（`docs/LEGALAI86_AUDIT.md` §1 第 6 项判 PARTIAL）。
4. **无细粒度 `permissions` 表**：仅角色级 RBAC（`docs/LEGALAI86_AUDIT.md` §1 第 5 项判 PARTIAL）。
5. **文件存储非对象存储**：本地沙箱 + Docker volume，**非 S3 兼容**，扩容/多实例受限（`docs/LEGALAI86_AUDIT.md` §2.4）。
6. **`knowledge_bases` 等表未建**：PHASE 0 审计 §1 第 3 项列出的 `knowledge_bases`/`playbooks`/`agent_runs`/`agent_steps`/`tool_executions` 等**仍未落地**（对应模块为"尚未开发"，见 `docs/LEGALAI86_PRD.md` §4）。
7. **`legal_sources.authorization_status` 默认 `unknown`**：数据源合规状态未逐源核实，禁止宣称 READY（§2.3 表）。
8. **规则包不落库**：规范性审核规则包以 **YAML 文件**（`backend/app/gov_rules/*.yaml`）加载，**非数据库表**，`legal_review_status=pending_legal_review`、`law_basis_article`/`effective_date` 待补。

---

*本文所有表/字段/约束/索引均取自仓库只读扫描的 ORM 与迁移代码；标注为"未接入/未落地/待补"者须补实现并经迁移验证后方可改判。未验证内容不编造、不夸大。*
