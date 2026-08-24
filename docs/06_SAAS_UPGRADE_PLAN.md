# SaaS 升级工程规划（Sprint 6 → Sprint 12）

> **版本**：v1.0  
> **创建日期**：2026-08-22  
> **作者**：高级全栈架构师 + DevOps 工程师  
> **状态**：待评审  
> **前置条件**：Sprint 1-5 已交付（FastAPI + LangGraph 11 节点 + RAG + DeepSeek V4 + BGE-M3 本地 + 评测反馈闭环 + 审计可观测）

---

## 一、升级目标

把当前本地 Agent Demo 升级为可对政府部门、企业客户直接交付的商业化 SaaS 产品。

**最终用户体验**：
- 用户访问 `https://你的域名.com`
- 注册账号 → 登录系统 → 上传行政规范性文件 → 点击"开始智能审查"
- 后端调用 Agent Workflow
- 实时展示 Agent 执行状态（11 节点流转可视化）
- 返回风险等级 + 问题清单 + 法规依据引用
- 下载 PDF 审查报告

---

## 二、当前架构 vs 目标架构对照

### 当前架构（Local Demo）

| 层级 | 已有组件 | 状态 |
|---|---|---|
| ① 接入层 | FastAPI `:8010` + Swagger `/docs` | ✅ 可用 |
| ② Agent 层 | LangGraph 11 节点 + SecurityHarness + EvidenceHarness + Prompt 版本化 | ✅ 已完成 |
| ③ 工具栈 | LLM Gateway（DeepSeek V4 Pro/Flash）+ RAG 混合检索 + BGE-M3 本地 Embedding + OCR | ✅ 已完成 |
| ④ 存储层 | PostgreSQL（pgvector + pg_trgm + 9 张表）+ 本地 `_sandbox` | ⚠️ 缺 Redis / 对象存储 |
| ⑤ 前端 | **完全缺失** | ❌ |
| ⑥ 鉴权 | User 模型已建，无注册登录流程 | ❌ |
| ⑦ 商业化 | 无订阅 / 支付 / 订单模型 | ❌ |
| ⑧ 部署 | Docker（仅 postgres），无 Nginx / HTTPS / 域名 | ❌ |
| ⑨ 安全 | 无 API 限流 / 异常监控 / 数据隔离 | ❌ |
| ⑩ 测试 | 仅 Unit Test（321 个），无 E2E | ⚠️ |

### 目标架构（SaaS Production）

详见 [07_SAAS_ARCHITECTURE.md](./07_SAAS_ARCHITECTURE.md)。

---

## 三、Sprint 路线图（9 阶段 → 7 Sprint）

| Sprint | 阶段映射 | 交付目标 | 可演示里程碑 |
|---|---|---|---|
| **Sprint 6** | 阶段 2：用户系统 | 注册 / 登录 / JWT 鉴权 / 权限控制 / 用户等级（Free 3 次/日、Pro 无限、Enterprise 团队）| `curl` 完成注册→登录→获取 JWT→调用受保护接口 |
| **Sprint 7** | 阶段 4：API 产品化 | `POST /api/review/create` + `GET /api/review/{id}/status`（SSE 实时节点流转）+ `GET /api/report/{id}` + 用户配额扣减 + 数据隔离 | `curl` 上传文件 → 实时查看 11 节点流转 → 拿到 JSON 报告 |
| **Sprint 8** | 阶段 3：前端开发 | Next.js 16 + Tailwind，7 页面（/ /login /register /dashboard /upload /review/[id] /report/[id] /admin）| 浏览器完整 SaaS 用户体验 |
| **Sprint 9** | 阶段 5 + 6：文件系统 + 商业化 | 腾讯云 COS 对象存储 + PDF/DOCX 上传链路 + Subscription / Order / Payment 三张表 + 套餐（体验版 / 专业版 ¥299/月 / 企业版 ¥1999/月）| 用户上传 PDF → 审查 → 下载报告 + 模拟支付下单 |
| **Sprint 10** | 阶段 7：部署 | Dockerfile（前后端）+ docker-compose（4 服务）+ 腾讯云 CVM 部署 + Nginx 反代 + Let's Encrypt SSL + Cloudflare DNS | `https://你的域名.com` 公网可访问 |
| **Sprint 11** | 阶段 8：安全加固 | API 限流（Redis 滑窗）+ 日志聚合（Loki）+ Sentry 异常监控 + 用户数据隔离 + 操作审计强化 + Prompt 版本管理增强 + Agent 运行轨迹前端可视化 | 安全扫描 0 高危 + 异常监控接入 + 限流生效 |
| **Sprint 12** | 阶段 9：测试 + 最终交付 | Unit Test ≥85% + API Test（pytest-vcr）+ E2E Test（Playwright 覆盖 5 主流程）+ 性能压测（locust）+ 安全扫描（bandit）+ 完整交付包 | Demo 可演示 + 交付包齐全 |

---

## 四、各 Sprint 详细范围

### Sprint 6：SaaS 用户系统（阶段 2）

**新增模型**：
- `UserPlan`（用户等级表）：user_id, plan_type（free/pro/enterprise）, daily_quota, used_today, reset_at
- `QuotaLog`（配额日志）：user_id, action, cost, created_at

**新增 API**：
- `POST /api/v1/auth/register`：注册（email + password + company）
- `POST /api/v1/auth/login`：登录，返回 JWT（access_token + refresh_token）
- `POST /api/v1/auth/refresh`：刷新 token
- `GET /api/v1/auth/me`：当前用户信息
- `POST /api/v1/auth/logout`：登出（Redis 黑名单）

**新增服务**：
- `AuthService`：密码哈希（bcrypt）+ JWT 签发/校验（pyjwt）+ 刷新 token
- `QuotaService`：基于 Redis 的日配额扣减（滑窗 + Lua 原子操作）
- `RoleGuard` 依赖：FastAPI Depends 注入当前用户 + 权限校验

**改造点**：
- 现有 `documents/upload` API 加 `Depends(get_current_user)` 强制鉴权
- 现有 `tasks` / `legal` / `audit` API 加用户隔离（WHERE user_id = current_user.id）

**用户等级**：
| 等级 | 价格 | 配额 | 团队 | 功能 |
|---|---|---|---|---|
| Free | 免费 | 3 次/日 | 1 人 | 基础审查 + JSON 报告 |
| Pro | ¥299/月 | 无限 | 1 人 | + PDF 报告 + 历史记录 + 风险趋势 |
| Enterprise | ¥1999/月 | 无限 | 10 人 | + 团队协作 + API 调用 + 优先支持 |

**Migration 文件**：`alembic/versions/0002_user_plan_quota.py`

**测试要求**：
- `tests/test_auth_register.py`：注册成功、邮箱重复、密码强度
- `tests/test_auth_login.py`：登录成功、密码错误、token 过期
- `tests/test_quota.py`：Free 用户第 4 次拒绝、Pro 用户无限通过

---

### Sprint 7：Agent API 产品化（阶段 4）

**新增 API（用户友好命名）**：
- `POST /api/v1/review/create`  
  输入：file（multipart）+ title  
  输出：`{ review_id, trace_id, status: "queued" }`  
  后台：异步启动 LangGraph Workflow
- `GET /api/v1/review/{id}/status`  
  返回：`{ status, current_node, node_history[], progress_pct, eta_seconds }`  
  实现：Server-Sent Events（SSE）流式推送节点流转
- `GET /api/v1/review/{id}/report`  
  返回：完整审查报告 JSON（summary + risks + evidences + suggestions + report_markdown）
- `GET /api/v1/review/{id}/report.pdf`  
  返回：PDF 二进制（weasyprint 渲染 report_markdown）
- `GET /api/v1/review/history`  
  返回：当前用户历史审查列表（分页）

**新增模型**：
- `ReviewView`（视图模型）：聚合 ReviewTask + ReviewResult + Document + 用户的可读视图
- 无新表，复用现有 `review_tasks` + `review_results`

**新增服务**：
- `ReviewService`：业务编排（创建任务 → 触发 Workflow → 查询状态 → 渲染报告）
- `SSEBroker`：SSE 流式推送器（基于 asyncio.Queue）
- `PDFRenderer`：Markdown → PDF（weasyprint / reportlab）

**改造点**：
- 现有 `trigger_doc_parse_background` 改名为 `ReviewService.start_workflow`，统一入口
- 现有 LangGraph 节点流转日志（agent_logs）作为 SSE 推送数据源
- `report_generation` 节点输出持久化到 `review_results.output_json`，供 PDF 渲染

**测试要求**：
- `tests/test_review_create.py`：上传 → 返回 review_id
- `tests/test_review_status_sse.py`：SSE 流式接收节点事件
- `tests/test_review_report.py`：JSON 报告完整、PDF 可下载
- `tests/test_review_isolation.py`：用户 A 看不到用户 B 的 review

---

### Sprint 8：前端开发（阶段 3）

**技术栈**：Next.js 16 + React 19 + Tailwind CSS + shadcn/ui + TanStack Query + Zustand

**项目结构**：
```
frontend/
├── app/
│   ├── (public)/           # 公开路由
│   │   ├── page.tsx        # 首页（产品介绍）
│   │   ├── login/page.tsx
│   │   └── register/page.tsx
│   ├── (app)/              # 受保护路由
│   │   ├── dashboard/page.tsx
│   │   ├── upload/page.tsx
│   │   ├── review/[id]/page.tsx
│   │   └── report/[id]/page.tsx
│   ├── (admin)/            # 管理员路由
│   │   └── admin/page.tsx
│   ├── layout.tsx
│   └── api/                # Next.js API Routes（代理后端）
├── components/
│   ├── ui/                 # shadcn 组件
│   ├── review/
│   │   ├── NodeFlowChart.tsx   # 11 节点流转可视化
│   │   ├── RiskList.tsx        # 风险清单
│   │   ├── EvidenceCard.tsx    # 法规依据卡片
│   │   └── ReportViewer.tsx    # 报告预览 + PDF 下载
│   └── dashboard/
│       ├── UsageCard.tsx       # 配额使用
│       └── HistoryTable.tsx    # 历史审查
├── lib/
│   ├── api.ts              # FastAPI 调用封装
│   ├── auth.ts             # JWT 管理
│   └── sse.ts              # SSE 客户端
└── package.json
```

**页面详细规格**：

| 路由 | 组件 | 功能 |
|---|---|---|
| `/` | HomePage | 产品介绍 + 3 套餐对比 + CTA 注册 |
| `/login` | LoginForm | email + password → JWT 存 localStorage |
| `/register` | RegisterForm | email + password + company → 自动登录 |
| `/dashboard` | Dashboard | 配额卡片 + 最近审查 + 上传入口 |
| `/upload` | UploadPage | 拖拽上传 + 标题输入 → 创建 review → 跳转 /review/[id] |
| `/review/[id]` | ReviewLive | SSE 实时节点流转 + 当前进度 + 风险/证据/建议 |
| `/report/[id]` | ReportView | 完整报告 markdown 渲染 + PDF 下载按钮 |
| `/admin` | AdminPanel | 用户管理 + 审查统计 + 法规库管理 |

**关键交互**：
1. 上传后跳转 `/review/[id]`，SSE 推送节点事件实时更新流程图
2. 节点流转可视化：用 react-flow 渲染 11 节点 + 当前节点高亮 + 已完成节点绿勾
3. 风险清单：按严重度（critical > high > medium > low）排序，可展开查看法规原文
4. 报告下载：调用 `/api/v1/review/{id}/report.pdf` 直接下载

**测试要求**：
- `e2e/register.spec.ts`：注册流程
- `e2e/login.spec.ts`：登录流程
- `e2e/upload_review.spec.ts`：上传到审查完成
- `e2e/report_download.spec.ts`：报告下载

---

### Sprint 9：文件系统 + 商业化（阶段 5 + 6）

**对象存储接入**：
- 接入腾讯云 COS（或阿里云 OSS）
- 上传链路：用户上传 → 后端临时接收 → 同步到 COS → 返回 COS URL
- 下载链路：生成预签名 URL（有效期 1 小时）
- 现有 `storage_path` 字段改造：从本地 `_sandbox/xxx` 改为 `cos://bucket/xxx`

**新增模型**：
- `Subscription`（订阅表）：user_id, plan_type, started_at, expired_at, status, auto_renew
- `Order`（订单表）：id, user_id, plan_type, amount_cny, status（pending/paid/canceled/refunded）, created_at, paid_at
- `Payment`（支付表）：order_id, provider（wechat/alipay/stripe）, provider_order_id, amount_cny, status, raw_response, paid_at

**新增 API**：
- `POST /api/v1/subscription/upgrade`：升级套餐（生成订单）
- `GET /api/v1/subscription/current`：当前订阅
- `POST /api/v1/payment/wechat/notify`：微信支付回调
- `POST /api/v1/payment/alipay/notify`：支付宝回调
- `GET /api/v1/orders`：订单列表

**套餐价格**：
| 套餐 | 月费 | 年费 | 主要权益 |
|---|---|---|---|
| 体验版 | 免费 | - | 3 次/日，JSON 报告 |
| 专业版 | ¥299/月 | ¥2999/年 | 无限审查，PDF 报告，历史记录 |
| 企业版 | ¥1999/月 | ¥19999/年 | 团队 10 人，API 调用，优先支持 |

**支付集成**：
- 第一阶段：预留接口，仅生成订单（不真实扣款）
- 第二阶段：接入微信扫码支付 + 支付宝当面付
- 第三阶段：接入 Stripe（海外客户）

**Migration 文件**：`alembic/versions/0003_subscription_order_payment.py`

---

### Sprint 10：部署 + 域名上线（阶段 7）

**部署目标**：腾讯云 CVM（4 核 8G ¥168/月）+ Cloudflare DNS + Let's Encrypt SSL

**Docker Compose 服务**：
```yaml
services:
  postgres:    # pgvector + pg_trgm
  redis:       # 缓存 + 限流
  backend:     # FastAPI + Agent
  frontend:    # Next.js（standalone build）
  nginx:       # 反代 + SSL
  celery:      # 异步任务（Sprint 11 可选）
```

**Dockerfile 清单**：
- `backend/Dockerfile`（已有，需优化：多阶段构建 + 非 root 用户）
- `frontend/Dockerfile`（新建：Next.js standalone）
- `nginx/Dockerfile`（新建：基于 nginx:alpine）
- `nginx/nginx.conf`（反代 + SSL + gzip）

**部署步骤**：
1. 购买腾讯云 CVM（4C8G，Ubuntu 22.04）
2. 域名解析到 CVM IP（Cloudflare DNS）
3. 安装 Docker + docker-compose
4. clone 仓库，配置 `.env.production`
5. `docker-compose up -d`
6. 申请 Let's Encrypt SSL（certbot）
7. 配置 Nginx 反代（前端 80→3000，后端 /api→8000）
8. 启动后跑种子脚本（法规库 + 管理员账号）
9. 浏览器访问 `https://你的域名.com`

**.env.example**：补全所有生产变量（DATABASE_URL / REDIS_URL / DEEPSEEK_API_KEY / JWT_SECRET / COS_SECRET_ID / COS_BUCKET / WECHAT_APP_ID 等）

---

### Sprint 11：安全加固 + 可观测性（阶段 8）

**安全**：
- API 限流：Redis 滑动窗口（Free 60/小时，Pro 600/小时，Enterprise 6000/小时）
- 用户数据隔离：所有查询 WHERE user_id = current_user.id
- 操作审计：现有 `audit_records` 表强化，关键操作（注册/登录/上传/支付）必记
- Prompt 版本管理：现有 registry.yaml 已版本化，增加灰度发布（10%/50%/100%）
- 安全扫描：bandit + safety + pip-audit 加入 CI

**可观测性**：
- 日志聚合：Loki + Promtail（收集 backend/agent 日志）
- 异常监控：Sentry SDK 接入（自动捕获未处理异常）
- 性能监控：Prometheus + Grafana（API P50/P99 + Agent 节点耗时）
- Agent 运行轨迹：前端 `/review/[id]` 可视化 11 节点流转 + 每节点 token / latency / cost

**新增中间件**：
- `RateLimitMiddleware`：Redis 滑窗限流
- `TenantIsolationMiddleware`：自动注入 user_id 到所有查询
- `AuditMiddleware`：关键操作自动审计

---

### Sprint 12：测试 + 最终交付（阶段 9）

**测试矩阵**：

| 类型 | 工具 | 覆盖 | 目标 |
|---|---|---|---|
| Unit Test | pytest + pytest-asyncio | service / tool / agent | ≥85% |
| API Test | httpx + pytest-vcr | all `/api/v1/*` | 100% 路由 |
| E2E Test | Playwright | 5 主流程 | 全通过 |
| 性能压测 | locust | 上传 + 审查 | P99 < 30s |
| 安全扫描 | bandit + safety | backend | 0 高危 |

**E2E 5 主流程**：
1. 注册 → 登录 → 上传 → 审查完成 → 下载报告
2. Free 用户第 4 次审查被拒
3. 升级套餐（模拟支付）→ 配额解锁
4. 管理员登录 → 查看用户列表 → 禁用用户
5. 历史审查列表 → 详情 → 重新下载报告

**最终交付清单**：
1. ✅ 产品架构图（已交付，本文档 + 07_SAAS_ARCHITECTURE.md）
2. ✅ 完整代码（前端 + 后端 + Migration + Docker）
3. ✅ 数据库 Migration（alembic/versions/0002 ~ 0004）
4. ✅ Docker 部署文件（docker-compose.yml + 4 Dockerfile）
5. ✅ 云服务器部署步骤（DEPLOYMENT.md）
6. ✅ 域名上线步骤（DEPLOYMENT.md 第 6 节）
7. ✅ 用户使用流程（USER_GUIDE.md）
8. ✅ Demo 演示流程（DEMO_SCRIPT.md）

---

## 五、技术选型

| 层 | 选型 | 理由 |
|---|---|---|
| 前端框架 | Next.js 16 + React 19 | SSR + App Router + RSC，SEO 友好 |
| 前端 UI | Tailwind CSS + shadcn/ui | 快速搭建 + 设计系统统一 |
| 状态管理 | Zustand + TanStack Query | 轻量 + 服务端状态专业 |
| 后端框架 | FastAPI（已有） | 异步 + OpenAPI + 类型安全 |
| Agent | LangGraph（已有） | 节点编排 + 状态机 + 可追溯 |
| 数据库 | PostgreSQL + pgvector（已有） | 关系 + 向量一体 |
| 缓存 | Redis 7 | 限流 + JWT 黑名单 + SSE 消息队列 |
| 对象存储 | 腾讯云 COS | 国内访问快 + 预签名 URL |
| LLM | DeepSeek V4 Pro/Flash（已有） | 中文合规审查效果好 + 成本低 |
| Embedding | BGE-M3 本地（已有） | 无网络依赖 + 私有部署 |
| PDF 渲染 | weasyprint | 纯 Python + 中文字体支持 |
| 容器 | Docker + docker-compose | 简单可复制 |
| 反代 | Nginx | SSL 终止 + 静态资源 + gzip |
| SSL | Let's Encrypt + certbot | 免费 + 自动续期 |
| CDN/DNS | Cloudflare | 免费 CDN + DDoS 防护 |
| 监控 | Sentry + Loki + Prometheus | 异常 + 日志 + 指标三件套 |
| E2E 测试 | Playwright | 跨浏览器 + 真实用户行为 |

---

## 六、风险与应对

| 风险 | 影响 | 应对 |
|---|---|---|
| DeepSeek API 限流 | 用户审查卡顿 | LLM Gateway 已有重试 + 限流；Pro 用户优先队列 |
| BGE-M3 内存占用高（2GB+） | 服务器 OOM | 独立容器 + 内存限制 + 冷启动优化 |
| 用户上传恶意文件 | 解析器崩溃 | 沙箱解析 + 文件类型白名单 + 大小限制 50MB |
| 法规库过时 | 审查结果不准 | Sprint 12 后启动法规库月度更新循环（已有 feedback loop） |
| 支付回调失败 | 订单状态不一致 | 幂等回调 + 对账任务（每日凌晨） |
| 单点故障 | 服务不可用 | 第一阶段单机部署；第二阶段引入负载均衡 + 数据库主从 |

---

## 七、下一步

1. **评审本文档** → 确认 Sprint 范围 + 技术选型 + 套餐定价
2. **执行 Sprint 6**：用户系统（注册/登录/JWT/配额）
3. 按 Sprint 顺序推进，每个 Sprint 完成后回归测试 + 演示

---

**附**：详细目标架构见 [07_SAAS_ARCHITECTURE.md](./07_SAAS_ARCHITECTURE.md)。
