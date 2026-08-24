# SaaS 目标架构详细设计

> **版本**：v1.0  
> **创建日期**：2026-08-22  
> **关联文档**：[06_SAAS_UPGRADE_PLAN.md](./06_SAAS_UPGRADE_PLAN.md) | [02_SYSTEM_ARCHITECTURE.md](./02_SYSTEM_ARCHITECTURE.md)

---

## 一、分层架构（9 层）

```
┌─────────────────────────────────────────────────────────────────┐
│ ① 边缘层：浏览器 → Cloudflare CDN → Nginx (HTTPS/WAF)           │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ ② 前端层：Next.js 16 + React 19 + Tailwind（7 页面）            │
│   / /login /register /dashboard /upload /review/[id] /report    │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ ③ API 层：FastAPI                                                │
│   - JWT 鉴权中间件（PyJWT）                                       │
│   - 限流中间件（Redis 滑窗）                                      │
│   - 数据隔离中间件（Tenant isolation）                           │
│   - /api/v1/auth/* · /api/v1/review/* · /api/v1/subscription/*   │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ ④ Agent 层：LangGraph 11 节点工作流（已有）                       │
│   doc_parse → doc_classify → legal_retrieve →                   │
│   authority_review → procedure_review → content_review →        │
│   risk_assessment → evidence_verify → report_generation →       │
│   human_review → END                                             │
│   + SecurityHarness + EvidenceHarness + Prompt 版本化            │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ ⑤ 工具栈：LLM Gateway · RAG · BGE-M3 Embedding · OCR · PDF 渲染  │
└───────────────────────────┬─────────────────────────────────────┘
                            ▼
┌──────────────────┬──────────────────┬──────────────────────────┘
│ ⑥ PostgreSQL     │ ⑦ Redis          │ ⑧ 对象存储（COS）         │
│ pgvector + 13 张 │ 缓存 + 限流 +    │ 用户上传文件 + 生成的    │
│ 表 + Alembic     │ JWT 黑名单 +     │ PDF 报告                  │
│ 迁移              │ SSE 消息队列     │                          │
└──────────────────┴──────────────────┴──────────────────────────┘
                            │
                            ▼
                   ┌────────────────┐
                   │ ⑨ DeepSeek API │
                   │ V4 Pro/Flash    │
                   └────────────────┘
```

---

## 二、模块清单与改造点

### 2.1 已有模块（复用）

| 模块 | 文件 | 改造点 |
|---|---|---|
| FastAPI 主应用 | `backend/app/main.py` | 增加鉴权/限流/审计中间件 |
| API 路由 | `backend/app/api/v1/*.py` | 7 个路由全部加 `Depends(get_current_user)` |
| LangGraph | `backend/app/agent/graph.py` | 不变，已产品化 |
| 节点 | `backend/app/agent/nodes.py` | 不变，已有 trace_id + AgentLog 持久化 |
| SecurityHarness | `backend/app/agent/harness.py` | 不变 |
| LLM Gateway | `backend/app/tools/llm.py` | 增加用户级优先队列（Pro 用户优先） |
| RAG 检索 | `backend/app/tools/rag.py` | 不变 |
| BGE-M3 | `backend/app/tools/embedding.py` | 改为独立容器（内存隔离） |
| OCR | `backend/app/tools/ocr.py` | 不变 |
| Prompt 版本化 | `backend/app/agent/prompts/registry.yaml` | 增加灰度发布字段 |
| 评测/反馈 | `backend/app/api/v1/eval.py` `feedback.py` | 不变 |
| 审计 | `backend/app/models/platform.py` | 强化关键操作记录 |

### 2.2 新增模块

| 模块 | 文件 | 职责 |
|---|---|---|
| Auth 服务 | `backend/app/services/auth.py` | bcrypt + JWT + 刷新 token |
| Quota 服务 | `backend/app/services/quota.py` | Redis 配额扣减（Lua 原子） |
| Review 服务 | `backend/app/services/review.py` | 业务编排（创建/查询/报告渲染） |
| Payment 服务 | `backend/app/services/payment.py` | 订单 + 支付回调（预留） |
| SSE Broker | `backend/app/services/sse.py` | 流式推送节点事件 |
| PDF Renderer | `backend/app/services/pdf.py` | Markdown → PDF（weasyprint） |
| Auth 路由 | `backend/app/api/v1/auth.py` | 注册/登录/刷新/me/logout |
| Review 路由 | `backend/app/api/v1/review.py` | create/status/report/history |
| Subscription 路由 | `backend/app/api/v1/subscription.py` | upgrade/current/orders |
| Next.js 前端 | `frontend/` | 7 页面 + 组件 |

---

## 三、数据库结构（13 张表）

### 3.1 已有 9 张表

| 表 | 模型 | 状态 |
|---|---|---|
| organizations | Organization | ✅ |
| users | User | ✅（需扩展 password_hash 已有） |
| review_tasks | ReviewTask | ✅ |
| review_results | ReviewResult | ✅ |
| agent_logs | AgentLog | ✅ |
| documents | Document | ✅（storage_path 改 COS URL） |
| legal_documents | LegalDocument | ✅ |
| legal_clauses | LegalClause | ✅（含 embedding） |
| audit_records | AuditRecord | ✅ |

### 3.2 新增 4 张表

#### user_plans（用户订阅等级）
```sql
CREATE TABLE user_plans (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_type VARCHAR(16) NOT NULL DEFAULT 'free',  -- free | pro | enterprise
    daily_quota INT NOT NULL DEFAULT 3,             -- Free 3, Pro -1(无限), Enterprise -1
    used_today INT NOT NULL DEFAULT 0,
    reset_at TIMESTAMPTZ,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expired_at TIMESTAMPTZ,                          -- NULL = 永久
    auto_renew BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(16) NOT NULL DEFAULT 'active',    -- active | expired | suspended
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id)
);
CREATE INDEX idx_user_plans_status ON user_plans(status) WHERE status = 'active';
```

#### subscriptions（订阅记录）
```sql
CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    plan_type VARCHAR(16) NOT NULL,                  -- pro | enterprise
    billing_cycle VARCHAR(16) NOT NULL,              -- monthly | yearly
    amount_cny NUMERIC(10, 2) NOT NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expired_at TIMESTAMPTZ NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',   -- pending | active | canceled | expired
    auto_renew BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_subscriptions_user ON subscriptions(user_id, status);
```

#### orders（订单）
```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    subscription_id UUID REFERENCES subscriptions(id),
    plan_type VARCHAR(16) NOT NULL,
    billing_cycle VARCHAR(16) NOT NULL,
    amount_cny NUMERIC(10, 2) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',    -- pending | paid | canceled | refunded
    provider VARCHAR(16),                             -- wechat | alipay | stripe
    provider_order_id VARCHAR(128),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    paid_at TIMESTAMPTZ,
    UNIQUE(provider, provider_order_id)
);
CREATE INDEX idx_orders_user ON orders(user_id, status);
```

#### payments（支付记录）
```sql
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    provider VARCHAR(16) NOT NULL,                   -- wechat | alipay | stripe
    provider_payment_id VARCHAR(128) UNIQUE,
    amount_cny NUMERIC(10, 2) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'pending',  -- pending | success | failed | refunded
    raw_response JSONB,
    paid_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_payments_order ON payments(order_id);
```

### 3.3 Migration 计划

| Migration | 内容 | Sprint |
|---|---|---|
| `0002_user_plan_quota.py` | user_plans 表 + 现有 users 加 company 字段 | 6 |
| `0003_subscription_order_payment.py` | subscriptions + orders + payments 三表 | 9 |
| `0004_audit_enhance.py` | audit_records 增加 ip_geolocation + risk_score 字段 | 11 |

---

## 四、API 路由总表

### 4.1 已有 API（加鉴权改造）

| Method | Path | 鉴权 | 改造 |
|---|---|---|---|
| POST | `/api/v1/documents/upload` | 必须 | 加 `Depends(get_current_user)` + 配额扣减 |
| GET | `/api/v1/tasks/{id}` | 必须 | 加用户隔离（仅能查自己的） |
| GET | `/api/v1/legal/laws` | 可选 | 公开查询，仅管理员可改 |
| POST | `/api/v1/legal/import` | 管理员 | 仅 admin role |
| GET | `/api/v1/audit/*` | 管理员 | 仅 admin role |
| GET | `/api/v1/metrics/*` | 管理员 | 仅 admin role |

### 4.2 新增 API

#### Auth（Sprint 6）
| Method | Path | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/auth/register` | 无 | 注册（email + password + company） |
| POST | `/api/v1/auth/login` | 无 | 登录，返回 access + refresh token |
| POST | `/api/v1/auth/refresh` | refresh | 刷新 access token |
| GET | `/api/v1/auth/me` | access | 当前用户信息 + 配额 |
| POST | `/api/v1/auth/logout` | access | 登出（Redis 黑名单） |

#### Review（Sprint 7）
| Method | Path | 鉴权 | 说明 |
|---|---|---|---|
| POST | `/api/v1/review/create` | access | 上传文件 → 返回 review_id |
| GET | `/api/v1/review/{id}/status` | access | SSE 实时节点流转 |
| GET | `/api/v1/review/{id}/report` | access | JSON 完整报告 |
| GET | `/api/v1/review/{id}/report.pdf` | access | PDF 下载（Pro+） |
| GET | `/api/v1/review/history` | access | 历史审查列表（分页） |

#### Subscription（Sprint 9）
| Method | Path | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/subscription/current` | access | 当前订阅 |
| POST | `/api/v1/subscription/upgrade` | access | 升级套餐（生成订单） |
| GET | `/api/v1/orders` | access | 订单列表 |
| POST | `/api/v1/payment/wechat/notify` | 无签名 | 微信支付回调 |
| POST | `/api/v1/payment/alipay/notify` | 无签名 | 支付宝回调 |

#### Admin（Sprint 11）
| Method | Path | 鉴权 | 说明 |
|---|---|---|---|
| GET | `/api/v1/admin/users` | admin | 用户列表 |
| PATCH | `/api/v1/admin/users/{id}` | admin | 禁用/启用用户 |
| GET | `/api/v1/admin/stats` | admin | 平台统计 |

---

## 五、部署拓扑

```
                  公网用户
                     │
                     ▼
            ┌─────────────────┐
            │ Cloudflare DNS  │  ← 域名解析 + DDoS 防护
            └────────┬────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ 腾讯云 CVM      │  4C8G Ubuntu 22.04
            │ ┌─────────────┐ │
            │ │   Nginx     │ │  HTTPS 443 → 80 重定向
            │ │   (SSL)     │ │
            │ └──────┬──────┘ │
            │        │        │
            │   ┌────┴────┐   │
            │   ▼         ▼   │
            │ Frontend  API  │
            │ :3000     :8000 │
            │   │         │   │
            │   └────┬────┘   │
            │        ▼        │
            │ ┌───────────┐  │
            │ │ PostgreSQL │  │  pgvector + pg_trgm
            │ │ + Redis    │  │
            │ └───────────┘  │
            └─────────────────┘
                     │
                     ▼
            ┌─────────────────┐
            │ DeepSeek API    │  远端 LLM
            └─────────────────┘
            ┌─────────────────┐
            │ 腾讯云 COS      │  对象存储
            └─────────────────┘
```

---

## 六、关键决策

1. **前端用 Next.js 而非纯 React**：SSR 利于 SEO（首页产品介绍）+ App Router 简化路由
2. **Redis 单实例**：第一阶段单机 Redis（不要主从），简化运维
3. **对象存储选 COS 不自建 MinIO**：减少运维成本 + 国内访问快
4. **PDF 用 weasyprint 不用 reportlab**：Markdown 渲染保真 + 中文字体好处理
5. **第一阶段不引入 Celery**：用 FastAPI BackgroundTasks + asyncio 足够；第二阶段再上 Celery
6. **支付先预留接口**：Sprint 9 仅生成订单不真实扣款；Sprint 12 后再接微信扫码
7. **限流用 Redis 滑窗不用 Nginx**：业务级限流（按用户等级）Nginx 难以表达

---

## 七、性能与容量预估

| 指标 | 预估值 | 依据 |
|---|---|---|
| 单次审查耗时 | 60-120s | 7 次 LLM 调用 × 5-15s/次 |
| 单机并发审查 | 5-10 | 受 LLM API 限流（DeepSeek 默认 60 QPM） |
| BGE-M3 内存 | 2.5GB | 模型 4.3GB 加载后驻留 |
| PostgreSQL 存储 | 10MB / 审查 | 含 parsed_text + agent_logs + review_results |
| 月度审查量（单机） | 5000-10000 | 日均 200-300 次 |
| 月度 LLM 成本 | ¥500-1500 | 按 DeepSeek V4 Pro 定价 |

---

**附**：详细 Sprint 实施见 [06_SAAS_UPGRADE_PLAN.md](./06_SAAS_UPGRADE_PLAN.md)。
