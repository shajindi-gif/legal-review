# GO_LIVE — legalai86.com.cn 上线手册

> **当前状态**：M0 ~ M16.1 全部代码已就位；M16.2（支付）/ M16.3（隐私政策四件套）尚未实现。  
> **目标**：本手册给出从「现在」到「全栈 + HTTPS 上线」的最短路径，含**上线前 24 项 checklist**、**回滚预案**、**已知未完工项**。

---

## 0. 三句话总览

1. **代码**已经全部准备好（`M0~M16.1` + M15 部署包）。
2. **法律 / 商业前置**差几样（ICP / 微信支付商户 / 隐私政策文本），我列在第 3 节。
3. **执行部署**只需要 1 步：`sudo bash deploy.sh`。剩下的事是配置 DNS + 拿到凭证。

---

## 1. 上线前 24 项 Checklist

### 1.1 法律 / 商业前置（**没有这些不要上线**）

- [ ] **域名 ICP 备案**已通过（`legalai86.com.cn` 在工信部有备案号）
- [ ] **公安备案**已通过（备案号格式：`京公网安备 1101010xxxxxx 号`）
- [ ] **营业执照**已办（M16.2 微信支付商户申请要求主体一致）
- [ ] **用户协议 / 隐私政策 / Cookie 政策**文本由律师 review 通过（M16.3 落地后会自动套用，但**上线前必须有人工 review 过的版本**）
- [ ] **微信支付商户号**已申请（M16.2 上线条件）
- [ ] **服务合同 / SLA**（B 端用，律所客户必备）

### 1.2 服务器 / 域名

- [ ] **VPS** 已购买：4 vCPU / 8 GB RAM / 80 GB SSD / Ubuntu 22.04+（**不是 docker-machine 之类的托管 K8s**）
- [ ] **公网 IP** 已拿到，记为 `<VPS_IP>`
- [ ] **DNS 解析**生效（DNSPod / 阿里云 / Cloudflare）：
  - `legalai86.com.cn` A `<VPS_IP>`
  - `www.legalai86.com.cn` A `<VPS_IP>`
- [ ] **SSH 密钥**已配置（推荐禁用密码登录）
- [ ] **云厂商安全组**只放 22/80/443 三端口

### 1.3 凭据 / 密钥

- [ ] **DEEPSEEK_API_KEY** 或 **QWEN_API_KEY**（至少一个，不填则 LLM 走 mock）
- [ ] **LLM_PROVIDER** 已选择（`mock` / `deepseek` / `qwen` / `dashscope`）
- [ ] **管理员手机号**（用 `_register_by_phone_internal` 跑第一个账号）
- [ ] **演示数据 seed**（可选，跑 `seed_users_orgs.py` + `seed_henan_laws.py`）

### 1.4 代码 / 部署

- [ ] **git 推送权限**：`https://github.com/shajindi-gif/legal-review.git` 可拉（`deploy.sh` 第 4 步）
- [ ] **DNS 已解析**（`dig +short legalai86.com.cn A` 返回 `<VPS_IP>`）
- [ ] **80 端口可外网**（certbot webroot 验证需要）
- [ ] **20 分钟连续时间**（首次部署 8-15 分钟，验证 5 分钟）

---

## 2. 一键上线（5 步）

```bash
# === Step 1: 上传代码到服务器 ===
ssh root@<VPS_IP>
mkdir -p /opt && cd /opt
git clone https://github.com/shajindi-gif/legal-review.git
cd /opt/legal-review/deploy

# === Step 2: 自定义 .env（首次 deploy.sh 会自动生成，跳过这步也行）===
# 仅在需要预设 LLM key / ICP 备案号 / 微信支付时执行
cp .env.example .env
nano .env   # 填好 DEEPSEEK_API_KEY / ICP_RECORD / LEGAL_ENTITY_NAME 等

# === Step 3: 一键部署 ===
sudo bash deploy.sh
# 预计 8-15 分钟。脚本会按 8 个阶段跑：
#   [1/8] 系统预检
#   [2/8] DNS 自检
#   [3/8] 安装 Docker
#   [4/8] 拉代码
#   [5/8] 生成 .env（强随机密码）
#   [6/8] 构建镜像 + 启动 postgres/redis/backend/frontend
#   [7/8] alembic upgrade head  ← 关键：会跑 0006 多租户迁移
#   [8/8] Let's Encrypt 证书 + 启动 nginx

# === Step 4: 启动 certbot 自动续期（独立 profile）===
cd /opt/legal-review/deploy
docker compose -f docker-compose.prod.yml --profile certbot up -d

# === Step 5: 验证 ===
cd /opt/legal-review/deploy
sudo bash scripts/verify.sh
# 期望: 7/7 PASS, 包含 M16.1 多租户隔离冒烟
```

---

## 3. 已交付代码清单（M0 ~ M16.1）

### 3.1 部署包（M15，6 文件 / 1117 行）

| 文件 | 用途 |
|---|---|
| [deploy/deploy.sh](file:///Users/shajindi/traework/legal-review/deploy/deploy.sh) | 一键部署（266 行，8 阶段） |
| [deploy/docker-compose.prod.yml](file:///Users/shajindi/traework/legal-review/deploy/docker-compose.prod.yml) | 5 服务编排（pg/redis/backend/frontend/nginx + certbot profile） |
| [deploy/nginx/conf.d/legalai86.com.cn.conf](file:///Users/shajindi/traework/legal-review/deploy/nginx/conf.d/legalai86.com.cn.conf) | 反代 + HTTPS（170 行） |
| [deploy/nginx/Dockerfile](file:///Users/shajindi/traework/legal-review/deploy/nginx/Dockerfile) | nginx + certbot 镜像 |
| [deploy/nginx/reload-on-cert-change.sh](file:///Users/shajindi/traework/legal-review/deploy/nginx/reload-on-cert-change.sh) | 证书自动 reload |
| [DEPLOY.md](file:///Users/shajindi/traework/legal-review/DEPLOY.md) | 部署手册（392 行） |

### 3.2 上线新工件（本批次，4 文件 / 600 行）

| 文件 | 用途 |
|---|---|
| [deploy/.env.example](file:///Users/shajindi/traework/legal-review/deploy/.env.example) | 87 行：含 M16 必填变量 |
| [deploy/scripts/verify.sh](file:///Users/shajindi/traework/legal-review/deploy/scripts/verify.sh) | 7 项部署后健康度自检（容器/HTTP/DB/迁移版本） |
| [deploy/scripts/backup_pg.sh](file:///Users/shajindi/traework/legal-review/deploy/scripts/backup_pg.sh) | cron 跑：pg_dump + uploads 备份 + 30 天保留 + 可选 COS |
| [deploy/scripts/rollback.sh](file:///Users/shajindi/traework/legal-review/deploy/scripts/rollback.sh) | 三种粒度回滚：`--migration` / `--image` / `--full` |
| [backend/scripts/verify_tenant_isolation.py](file:///Users/shajindi/traework/legal-review/backend/scripts/verify_tenant_isolation.py) | M16.1 多租户冒烟（防数据串租） |

### 3.3 M16.1 多租户隔离（8 文件 / 1135 行）

| 文件 | 用途 |
|---|---|
| [alembic/versions/0006_tenant_organization_id.py](file:///Users/shajindi/traework/legal-review/backend/alembic/versions/0006_tenant_organization_id.py) | 6 张业务表加 organization_id 列 + backfill + 索引 |
| [app/services/tenant.py](file:///Users/shajindi/traework/legal-review/backend/app/services/tenant.py) | 3 模式隔离 helper（super_admin / team_org / personal） |
| [app/models/document.py](file:///Users/shajindi/traework/legal-review/backend/app/models/document.py) | documents 加列 |
| [app/models/task.py](file:///Users/shajindi/traework/legal-review/backend/app/models/task.py) | tasks / review_results / agent_logs 加列 |
| [app/models/notification.py](file:///Users/shajindi/traework/legal-review/backend/app/models/notification.py) | notifications 加列 |
| [app/models/user_feedback.py](file:///Users/shajindi/traework/legal-review/backend/app/models/user_feedback.py) | user_feedback 加列 |
| [app/api/deps.py](file:///Users/shajindi/traework/legal-review/backend/app/api/deps.py) | TenantContext + get_tenant_context |
| [app/api/v1/tasks.py](file:///Users/shajindi/traework/legal-review/backend/app/api/v1/tasks.py) | 7 endpoint 切换到 ctx |

### 3.4 之前 14 个里程碑的成果

- **M0**：项目骨架（FastAPI + Next.js 16 + pgvector + Redis）
- **M1**：审查 Agent 8 节点 + harness + 图编排
- **M2**：工具集（LLM / Embedding / RAG / 解析 / OCR / 沙箱 / 法规切分）
- **M3**：用户 + 订阅（Organization / UserPlan / Order / Payment / QuotaService）
- **M4**：手机号注册 + 验证码 + JWT refresh（OAuth/RefreshToken/VerificationCode）
- **M5**：通知中心（站内信 + 邮件占位）
- **M6**：用户反馈 + 评分
- **M7**：评估系统（golden_dataset + eval_runs + feedback_cases）
- **M8**：审计 + metrics 指标
- **M9**：UI 主题 + 组件库
- **M10**：核心 UI 流程（登录 / 注册 / 仪表盘 / 审查 / 报告 / 文档）
- **M11**：Assistant 对话
- **M12**：管理员后台（feedback 管理）
- **M13**：评估 / 监控 UI
- **M14**：可观测性（结构化日志 / Prometheus 指标）
- **M15**：部署包
- **M16.1**：多租户隔离（PASS）
- **M16.2**：支付闭环（**待开工**）
- **M16.3**：隐私政策（**待开工**）
- **M16.4**：UI 5 页（**待开工**）

---

## 4. 上线后第一周运维表

| Day | 任务 | 命令 / 工具 |
|---|---|---|
| D+1 | 跑 verify.sh | `bash /opt/legal-review/deploy/scripts/verify.sh` |
| D+1 | 装 cron 自动备份 | `echo "0 2 * * * root bash /opt/legal-review/deploy/scripts/backup_pg.sh" > /etc/cron.d/legal-backup` |
| D+1 | 装 fail2ban | `apt install fail2ban` |
| D+2 | 监控上线 | 部署 Uptime Kuma / 腾讯云可观测，添加探针 `https://legalai86.com.cn/api/v1/health` |
| D+3 | 配置对象存储 | 创建腾讯云 COS / 阿里云 OSS bucket，给 backup_pg.sh 配密钥 |
| D+7 | 第一次回滚演练 | 在 staging 跑 `rollback.sh --image`，确认 5 分钟内恢复 |

---

## 5. 回滚预案（**必读**）

### 5.1 三种回滚粒度

```bash
# 1. 仅回滚最近一次 alembic（DB 改动，保留容器）
sudo bash /opt/legal-review/deploy/scripts/rollback.sh --migration

# 2. 回滚 docker image 到上一个 tag
sudo ROLLBACK_TAG=v1.0.0 bash /opt/legal-review/deploy/scripts/rollback.sh --image

# 3. 全栈回滚（image + migration + 数据清理）
sudo ROLLBACK_TAG=v1.0.0 bash /opt/legal-review/deploy/scripts/rollback.sh --full
```

**任意回滚前脚本会自动备份当前 DB 到** `/opt/backup/legalai86/pre_rollback_*.dump`。

### 5.2 已知风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| **0006 迁移 backfill 失败** | 🔴 高 | 迁移脚本带 try/except；失败不会破坏 schema；可手动 `alembic downgrade -1` |
| **organization_id 写入失败导致查询不出数据** | 🟡 中 | `_filter_by_tenant` 严格 mode；写入路径要确保 organization_id 非空 |
| **数据库密码泄露** | 🔴 严重 | `.env` chmod 600；首次部署时随机生成 |
| **证书过期** | 🟢 低 | certbot profile 自动续期 |
| **CDN 在前导致 certbot 失败** | 🟡 中 | 脚本检测到非本机 IP 会**警告而非失败**；可后续切到 dns-cloudflare 插件 |
| **首次部署 DNS 未生效** | 🟡 中 | 脚本会 SKIP certbot，给出手动重跑命令 |

### 5.3 数据串租（最严重）

如果 verify_tenant_isolation.py **FAIL**：
1. **立刻把 legalai86 设为维护页**（nginx 切 503）
2. 跑 `bash rollback.sh --full`
3. 联系技术负责人 / 律师，评估**是否已经发生数据泄露**（按《个保法》第 57 条应在 72h 内通知监管 + 用户）

---

## 6. 未完工项（**不是 blocker，但上线后 1 个月内必须补齐**）

### 6.1 M16.2 支付闭环

- 升级 / 续费 API（基于已有 Order/Payment 表）
- 微信支付 JSAPI 沙箱接入
- 回调 + 订单状态机
- 套餐配额联动

**前置**：需要 `WECHAT_PAY_MCH_ID` / `WECHAT_PAY_API_V3_KEY` / `WECHAT_PAY_CERT_SERIAL`（在微信支付商户平台 → API 安全 → APIv3 密钥）

### 6.2 M16.3 隐私政策

- 用户协议 / 隐私政策 / Cookie 政策 4 件套（AI 初稿 + 律师 review）
- 路由 `/privacy` / `/terms` / `/cookies` / `/legal/agreement`
- Cookie 横幅 + 同意入库
- ICP 备案号 + 公安备案号落款

**前置**：需要**律师 review 过的正文**（AI 初稿不能直接用）

### 6.3 M16.4 UI 5 页

- 登录页改造
- 注册页（手机号 + 验证码 + 协议勾选）
- 升级页（套餐对比 + 微信支付）
- 账单页（Order/Payment 历史）
- 隐私中心（同意管理 + 政策版本）

### 6.4 多租户隔离端点覆盖

当前只在 `tasks.py` 7 个 endpoint 上接入了 `TenantContext`。M16.5 验证阶段需要把同样模式推广到：

- `documents.py`
- `notifications.py`
- `user_feedback.py`
- `assistant` / `search`（如果存在）

---

## 7. 联系方式

- **代码仓库**：`https://github.com/shajindi-gif/legal-review`
- **部署文档**：`/opt/legal-review/DEPLOY.md`
- **本上线手册**：`/opt/legal-review/GO_LIVE.md`
- **后端日志**：`docker logs -f --tail=200 legal-backend`
- **DB 直连**：`docker exec -it legal-pg psql -U legal -d legal_review`

如遇本手册未覆盖的问题，**先看 `docker logs`**，再回看 `deploy.sh` 输出。
