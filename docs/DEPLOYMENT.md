# LegalAI 86 /「智审 · LegalReview」部署手册

> 适用产品：LegalAI 86 /「智审 · LegalReview」（行政规范性文件智能合法性审查 Agent 系统）
> 分支：`upgrade/legalai86-platform`
> 形态：自建 VPS · Ubuntu 22.04/24.04 · Docker Compose
> 域名：`legalai86.com.cn`（唯一合法生产域名）
>
> **重要前提**：本手册当前环境**未获得生产部署批准，本次未执行任何生产部署**。以下内容仅为**步骤与检查清单**，供获得批准后按序执行。所有命令均取自仓库真实脚本与配置，未做臆测。

---

## 0. 文档定位与阅读顺序

本手册描述从「本地开发」到「生产上线」的完整路径，覆盖：
环境前置 → 服务器与目录 → 域名现状 → 镜像构建 → 数据库迁移 → 脚本逐一说明 → 三种部署模式 → 验证/冒烟 → 备份恢复 → 上线检查清单 → 安全红线 → 本地开发 → 已知风险。

相关参考文档（仓库内）：
- `DEPLOY.md` — 早期部署手册（首次部署流程）
- `GO_LIVE.md` — 上线手册与 24 项 checklist
- `docs/PAYMENT_SETUP.md` — 支付平台配置与对接约定

---

## 1. 环境与前置条件

### 1.1 生产服务器

| 项 | 要求 |
|---|---|
| OS | Ubuntu 22.04 / 24.04 LTS（`deploy.sh` 依赖 `apt` / `systemd`） |
| 端口 | 22、80、443 需可外网访问（80 用于 certbot webroot 挑战） |
| Docker | Docker Engine + `docker compose` 插件（`deploy.sh` 会自动安装） |
| 资源 | 建议 ≥ 4 vCPU / 8 GB RAM / 80 GB SSD |
| 工具 | `curl`、`git`、`openssl`、`ssh`；`rsync`（可选，缺失时 `sync.sh` 退化） |

### 1.2 本地（运维机）

- `ssh` 客户端、`rsync`（可选）、`curl`、`openssl`
- `jq`（`verify-payment.sh` / `verify-alipay-only.sh` 解析 JSON，缺失时退化为 `grep`）
- `python3`（`install-payment-env.sh` 在**远端**用 `python3` 做 `.env` 精确合并）
- Python 3.11+ 与 Node 22 + pnpm（仅在本地跑测试/构建时需要）

### 1.3 凭据前置

- LLM：至少配置 `DEEPSEEK_API_KEY` 或 `QWEN_API_KEY` 之一；**都不配则 `LLM_PROVIDER=mock` 走本地兜底**（见 `deploy/.env.example`）。
- 支付：按渠道准备微信/支付宝凭证（见 §7.2、§7.3）；仅支付宝场景见 `ALIPAY_ONLY` 模式。
- 邮件：`AUTH_EMAIL_ENABLED=false` 时默认不启用。

---

## 2. 生产服务器与目录结构

### 2.1 服务器信息（项目记忆）

| 项 | 值 |
|---|---|
| 生产服务器 IP | `124.221.229.12` |
| 登录用户 | `ubuntu`（非 root） |
| 私钥 | `/Users/shajindi/Downloads/04-项目与密码/yanceedu.pem` |
| 代码根目录 | `/opt/legal-review` |

> 由于登录用户是 `ubuntu` 而非 `root`，凡**触碰 `/opt`、`/etc`、`/var` 等的脚本**（如备份目录创建、`.env` 写入、`docker`、`git`）在服务器上均需 `sudo`。各脚本提供 `REMOTE_SUDO=sudo` 开关来适配非 root 登录：

```bash
REMOTE_SUDO=sudo SSH_HOST=ubuntu@124.221.229.12 PROJECT_DIR=/opt/legal-review \
  bash deploy/scripts/sync.sh
```

> 注意：`sync.sh` / `install-payment-env.sh` / `verify-payment.sh` / `verify-alipay-only.sh` 的 `SSH_HOST` **默认值为 `root@124.221.229.12`**（脚本头注释），生产实际登录用户是 `ubuntu`，因此务必显式传 `SSH_HOST=ubuntu@124.221.229.12` 并加 `REMOTE_SUDO=sudo`，否则会被拒绝或报权。

### 2.2 关键目录

```
/opt/legal-review/                    # 代码根（git 仓库）
/opt/legal-review/deploy/             # 部署目录（COMPOSE_FILE 相对此目录）
/opt/legal-review/deploy/.env         # 生产环境变量（chmod 600，含密钥，禁入 git）
/opt/legal-review/deploy/.env.bak-*   # install-payment-env.sh 写入前的自动备份
/opt/backup/legalai86/                # backup_pg.sh 备份目录（需 sudo 写）
/var/log/legal-backup.log             # backup_pg.sh 日志
/etc/legal-backup.env                 # 备份脚本可选独立 env
```

### 2.3 生产容器与镜像

容器名（`deploy/docker-compose.prod.yml`）：

| 服务 | 容器名 | 镜像 | 端口 |
|---|---|---|---|
| postgres | `legal-pg` | `pgvector/pgvector:pg16` | 容器内 `5432`，**不映射主机** |
| redis | `legal-redis` | `redis:7-alpine` | 容器内 `6379`，**不映射主机** |
| backend | `legal-backend` | `legal-review/backend:latest` | 容器内 `8000`，**不映射主机** |
| frontend | `legal-frontend` | `legal-review/frontend:latest` | 容器内 `3081`，**不映射主机** |
| nginx | `legal-nginx` | `legal-review/nginx:latest` | `80:80` / `443:443`（唯一对外端口） |
| prometheus | `legal-prometheus` | `prom/prometheus:latest` | **不映射任何端口**（仅内网 `appnet`） |
| certbot | `legal-certbot` | `certbot/certbot:latest` | `profile=certbot`，无端口 |

- 网络：`legal_appnet`（bridge）。
- 命名卷：`legal_pg_data`、`legal_redis_data`、`legal_backend_sandbox`、`legal_backend_uploads`、`legal_certbot_conf`、`legal_certbot_www`、`legal_prometheus_data`。

---

## 3. 域名与备案现状

### 3.1 唯一合法域名

- **生产合法域名只有 `legalai86.com.cn`**（含 `www.legalai86.com.cn`，见 `deploy/nginx/conf.d/legalai86.com.cn.conf` 的 `server_name`）。
- ICP 备案（见 `docs/PAYMENT_SETUP.md`）：`legalai86.com.cn` 已完成 ICP 备案（沪ICP备 2026045851 号-4）。
- **`legal86.com.cn` 无 DNS 解析**，**绝不可**将其与 `legalai86.com.cn` 视为同一域名，也不可将它写入任何配置、回调地址、白名单。

### 3.2 健康检查路径（易错点）

- 生产健康检查为 **`https://legalai86.com.cn/health`**（挂根路径，返回 200）。该路径在 `deploy/nginx/conf.d/legalai86.com.cn.conf` 中由 `location = /health` 直接反代到 `backend:8000/health`。
- 后端健康路由挂根路径、**不进 `/api/v1` 前缀**（`backend/app/api/v1/health.py` 注释 + `backend/app/main.py` 的 `app.include_router(health_router.router)`）。
- 因此 **`https://legalai86.com.cn/api/v1/health` 会返回 404，这是正常现象**（`docs/PAYMENT_SETUP.md` §四 Q3 亦如此说明）。排查时请打 `/health`，不要打 `/api/v1/health`。
- 另有就绪探针 `GET /ready`（含 `SELECT 1` 的 DB 探活，见 `backend/app/api/v1/health.py`），通过 `location /api/` 前的根路径 —— 注意 `/ready` 不在 nginx 显式 `location =` 中，实际经 `location /` 落到前端，**生产排障以 `/health` 为准**。

> 提示：`deploy/scripts/sync.sh` 与 `deploy/deploy.sh` 结尾的自动冒烟里打印的是 `https://127.0.0.1/api/v1/health`，该路径会 404 —— 这是脚本内遗留的探测路径，**不代表真实健康检查失败**；以 `/health` 为权威判据。`verify.sh`、`verify-alipay-only.sh` 用的是正确的 `/health`。

### 3.3 DNS / 证书

- TLS 由 Let's Encrypt（certbot webroot 模式）签发，证书存于命名卷 `legal_certbot_conf`（nginx 只读挂载 `/etc/letsencrypt`）。
- 证书自动续期由独立 `certbot` 容器（`profile=certbot`）每 12h `certbot renew`；容器内 `/docker-entrypoint.d/reload-on-cert-change.sh` 监听 `/etc/letsencrypt/live/legalai86.com.cn/fullchain.pem` 变化触发 `nginx -s reload`（见 §6.9）。
- **不得擅自改 DNS 解析、备案状态或域名绑定**（见 §11）。

---

## 4. 镜像与构建

### 4.1 构建上下文与镜像

| 服务 | 构建上下文（相对 `deploy/`） | Dockerfile |
|---|---|---|
| backend | `../backend` | `backend/Dockerfile` |
| frontend | `../frontend` | `frontend/Dockerfile` |
| nginx | `./nginx` | `deploy/nginx/Dockerfile` |

- backend 镜像：`python:3.11-slim`，**`COPY . .` 把代码打进镜像**，`CMD uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2`。
  - **后端镜像内置代码、无 volume 挂载**（`docker-compose.prod.yml` 中 backend 只挂了 `_sandbox` 与 `uploads` 两个卷）。**因此改了后端代码必须重新 `build backend` 并重建容器，热改无效。**
- frontend 镜像：多阶段构建（`node:22-bookworm-slim`），standalone 运行在 `3081`，含独立 `HEALTHCHECK`。
- nginx 镜像：`nginx:1.27-alpine`，内置 `reload-on-cert-change.sh`，暴露 80/443。

### 4.2 构建命令

```bash
# 生产：在服务器 /opt/legal-review/deploy 下
sudo docker compose -f docker-compose.prod.yml build backend            # 仅后端
sudo docker compose -f docker-compose.prod.yml build backend frontend   # 前后端
sudo docker compose -f docker-compose.prod.yml build                    # 全量（首次）

# 首次全栈启动
sudo docker compose -f docker-compose.prod.yml up -d
# 证书续期容器（独立 profile）
sudo docker compose -f docker-compose.prod.yml --profile certbot up -d
```

- **依赖变更**（`pyproject.toml` / `pnpm-lock.yaml`）会改变镜像层缓存，必须重新 `build`。
- backend / frontend 镜像 tag 固定为 `legal-review/backend:latest` / `legal-review/frontend:latest`（`docker-compose.prod.yml` 硬编码）。

---

## 5. 数据库迁移（alembic）

### 5.1 配置

- `backend/alembic.ini`：`script_location = alembic`，`sqlalchemy.url` 为占位值 —— **真实 URL 由 `backend/alembic/env.py` 从 `settings`（即容器注入的 `DATABASE_URL`）动态注入**。
- 迁移脚本目录：`backend/alembic/versions/`（当前含 `0001_initial_schema` … `0009_legalai86_workspace`、`c369d702b000_expand_documents_mime_type_to_128` 等）。

### 5.2 执行方式与顺序（关键）

- **生产部署序列（先迁移后换容器）**：
  1. tar 增量推送新代码到服务器；
  2. 备份（见 §9）；
  3. `docker compose build backend`；
  4. **`docker compose run --rm --no-deps backend alembic upgrade head`**（在**新旧容器切换前**先跑迁移）；
  5. `docker compose up -d backend`（换新容器）。
- 运行中容器的等价写法：`docker exec legal-backend alembic upgrade head`。
- 校验当前版本：`docker exec legal-backend alembic current`。

> 顺序差异提示：`deploy/scripts/sync.sh` 的内置顺序是 `build → up -d backend/frontend → 等 healthy → alembic upgrade head`，即**先换容器再迁移**，与上述「先迁移后换容器」的受控序列**不同**。生产建议采用受控序列（先 `compose run --rm --no-deps backend alembic upgrade head`，再 `up -d backend`），以避免新代码先于 schema 生效导致报错。若使用 `sync.sh`，请知悉此差异并在迁移失败时立即 `rollback.sh --migration`。

### 5.3 初始数据 seed（默认不自动跑）

- `deploy/deploy.sh` 检测到 `backend/scripts/seed_users_orgs.py` 时**默认不自动执行**，仅提示，避免覆盖生产账号。
- 需要时手动：`docker exec legal-backend python /app/scripts/seed_users_orgs.py`。
- 其他 seed 脚本（均位于 `backend/scripts/`）：`seed_poc.py`、`seed_laws.py`、`seed_henan_laws.py`、`m0_smoke.py`、`verify_tenant_isolation.py`。

---

## 6. 部署脚本说明（逐个）

> 下列脚本均在仓库 `deploy/` 下，用法取自脚本头注释与真实参数默认值。

### 6.1 `deploy/deploy.sh` — 首次全栈部署（裸机 → HTTPS 站点）

- 用途：在**全新 Ubuntu 机器**上从零跑通 `docker` → 拉代码 → 生成 `.env` → 构建启动 → certbot 签证书 → 起 nginx。8 步：系统预检 / DNS 自检 / 装 Docker / 拉代码 / 生成 `.env` / build+up（不含 nginx）/ alembic 迁移 / 证书+nginx。
- 关键变量（有默认值）：`DOMAIN`、`WWW_DOMAIN`、`EMAIL`、`PROJECT_DIR=/opt/legal-review`、`REPO_URL`、`SSH_PORT=22`、`COMPOSE_FILE=docker-compose.prod.yml`。
- 用法：`sudo bash deploy.sh` 或 `sudo DOMAIN=legalai86.com.cn EMAIL=admin@legalai86.com.cn PROJECT_DIR=/opt/legal-review bash deploy.sh`。
- 行为要点：**必须 root 执行**；首次自动生成 `deploy/.env`（`openssl rand` 生成 `POSTGRES_PASSWORD` / `JWT_SECRET`）并 `chmod 600`；DNS 未解析时仅 WARN 并置 `SKIP_CERTBOT=1`，证书步骤需 DNS 生效后手动重跑；首次启动顺序是 `up -d postgres redis backend frontend` → 等 `/health`（最多 90s）→ `alembic upgrade head` → certbot → `up -d nginx`。
- 注意：脚本收尾打印的自动冒烟打的是 `https://127.0.0.1/api/v1/health`（会 404），以 `/health` 为准。

### 6.2 `deploy/scripts/sync.sh` — 增量推送 + 重启

- 用途：服务器已在跑，只把新代码推上去并重启 backend/frontend，不做整机重跑。
- 步骤（6 步）：预检（ssh 连通）/ 服务器 `git pull`（`fetch`+`reset --hard origin/<branch>`）/ 选择性 `build` / 滚动 `up -d --no-deps` / 等 `/health`（最多 90s）/ `alembic upgrade head` / 端到端冒烟。
- 变量：`SSH_HOST`（默认 `root@124.221.229.12`）、`PROJECT_DIR`、`COMPOSE_FILE`、`REBUILD_BACKEND=1`、`REBUILD_FRONTEND=1`、`SKIP_PULL=0`、`RESTART_NGINX=0`（改 nginx conf 才设 1）、`REMOTE_SUDO`。
- 用法示例：
  ```bash
  REMOTE_SUDO=sudo SSH_HOST=ubuntu@124.221.229.12 PROJECT_DIR=/opt/legal-review \
    bash deploy/scripts/sync.sh
  ```
- 安全说明（脚本头）：不改动任何支付凭证；失败 `trap` 退出并留日志；只打印容器名与启动状态，不打印密钥。
- 注意：**`git reset --hard`** 会丢弃服务器端本地改动；且其重启/migrate 顺序与 §5.2 受控序列相反（见提示）。

### 6.3 `deploy/scripts/install-payment-env.sh` — 支付凭证安装

- 用途：把真实支付凭证写入 `deploy/.env`，**仅重启 backend** 生效。
- 必填环境变量（非 ALIPAY_ONLY 时）：`WXPAY_ENABLED`、`ALIPAY_ENABLED`、`WXPAY_MCHID`、`WXPAY_APPID`、`WXPAY_APPSECRET`、`WXPAY_API_V3_KEY`、`WXPAY_MCH_SERIAL_NO`、`WXPAY_MCH_PRIVATE_KEY`、`WXPAY_PUBLIC_KEY`、`WXPAY_PUBLIC_KEY_ID`、`ALIPAY_APP_ID`、`ALIPAY_PRIVATE_KEY`、`ALIPAY_PUBLIC_KEY`。
- 设计原则（脚本头 + `docs/PAYMENT_SETUP.md` §三）：
  - 私钥**绝不进代码/日志/仓库**；脚本只写入 `deploy/.env`，密钥值不上日志（仅本地做长度/前缀校验）。
  - **仅替换 `WXPAY_*` / `ALIPAY_*` 字段，绝不覆盖 `JWT_SECRET` / `POSTGRES_PASSWORD`**（远端用 `python3` 按 key 名精确合并）。
  - 写入前**自动备份**旧 `.env` 为 `deploy/.env.bak-YYYYMMDD-HHMMSS`。
  - 写入后 `.env` 强制 **`chmod 600`**（root/所属用户独占）。
  - **只重启 backend**，不动 nginx / 前端 / PostgreSQL / Redis。
- PEM 约定：多行私钥必须**单行**存储（真实换行 → 字面 `\n`）；脚本校验含真实换行即报错，长度 < 100 也报错。
- 用法：
  ```bash
  REMOTE_SUDO=sudo SSH_HOST=ubuntu@124.221.229.12 PROJECT_DIR=/opt/legal-review \
    ALIPAY_ONLY=1 ALIPAY_ENABLED=true ALIPAY_APP_ID=... \
    ALIPAY_PRIVATE_KEY=... ALIPAY_PUBLIC_KEY=... \
    bash deploy/scripts/install-payment-env.sh
  ```
- 完成后等待 backend `/health` 200（最多 60s），再跑支付验收。

### 6.4 `deploy/scripts/verify.sh` — 部署后健康度验证（7 项）

- 用途：容器状态 / 前端 200 / 后端 `/health` / 登录路由可达 / 多租户隔离 / 证书有效期 / alembic 版本。
- 用法：`sudo DOMAIN=legalai86.com.cn bash verify.sh`。
- 判定：任一项 FAIL 计入 `FAIL` 计数；**≥ 2 项 FAIL 即建议回滚**（脚本头说明）。检查点为：
  - 容器 `legal-pg / legal-redis / legal-backend / legal-frontend / legal-nginx` 是否 healthy/Up；
  - `GET /` 是否 200；`GET /health` 是否含 `"status":"ok"`；
  - `POST /api/v1/auth/login/phone` 是否可达（接受 200/400/401/422/429）；
  - `docker exec legal-backend python /app/scripts/verify_tenant_isolation.py`（rc=2 表示无演示账号，跳过，非异常）；
  - 证书文件 `/var/lib/docker/volumes/legal_certbot_conf/_data/live/$DOMAIN/fullchain.pem` 到期日；
  - `alembic current`。

### 6.5 `deploy/scripts/verify-payment.sh` — 支付验收（微信/支付宝通用）

- 用途：凭证写入后跑「下单 → 轮询 → 主动查单补偿」服务层证据；**不发起真实扣款**（真付需人工扫码）。
- 变量：`SSH_HOST`、`DOMAIN`、`TOKEN`（浏览器 localStorage 拷 JWT）或 `USER_EMAIL`/`USER_PASS`、`PLAN`（默认 `pro`）、`PERIOD`（默认 30）、`CHANNEL`（默认 `wechat`）、`PAY_TYPE`（默认按渠道：微信 `h5`、支付宝 `page`）。
- 检查：`/health`、`/billing/pricing`、`POST /api/v1/billing/orders`、`GET /api/v1/billing/orders/{id}` 轮询与主动查单。
- **注意**：其健康检查打的是 `$API/health` = `https://<domain>/api/v1/health`，该路径 404（见 §3.2）；实际以 `/health` 为准。真付后查日志：`docker logs --tail=200 legal-backend 2>&1 | grep -E "payment_(success|fail|verify)"`。

### 6.6 `deploy/scripts/verify-alipay-only.sh` — 仅支付宝验收

- 用途：只接通支付宝商业闭环（微信未配置时用）；流程同 `verify-payment.sh` 但跳过全部 `WXPAY_*` 校验。
- 变量：`SSH_HOST`、`DOMAIN`、`TOKEN` 或 `USER_EMAIL`/`USER_PASS`、`PLAN`、`PERIOD`、`PAY_TYPE=page|wap`（默认 `page`）、`ALIPAY_RETURN_URL`。
- 检查点：**`GET https://<domain>/health`（正确的根路径）**、`/billing/pricing`、登录拿 JWT、`POST /api/v1/billing/orders`（`channel=alipay`）、校验 `pay_url` 指向 `openapi.alipay.com` / `mclient.alipay.com` 且含 `sign=`、轮询 `GET /billing/orders/{id}`、主动查单回写。
- 结尾给出扫码付款步骤与真付后查日志命令。

### 6.7 `deploy/scripts/backup_pg.sh` — 数据库 + 上传文件定时备份

- 用途：`pg_dump -F c` 自定义压缩格式 + 一份纯 SQL；保留 30 天；可选上传腾讯云 COS；另备份 `legal_backend_uploads` 卷。
- 变量：`BACKUP_DIR=/opt/backup/legalai86`、`KEEP_DAYS=30`、`COMPOSE_DIR=/opt/legal-review/deploy`、`COMPOSE_FILE=docker-compose.prod.yml`、`LOG_FILE=/var/log/legal-backup.log`；COS 可选（`COS_BUCKET` / `COS_SECRET_ID` / `COS_SECRET_KEY` / `COS_REGION`，`coscli` 存在才传）。
- 依赖：从 `deploy/.env` 读取 `POSTGRES_PASSWORD`；对 `legal-pg` 执行 `pg_dump -U legal -d legal_review`。
- 部署建议（脚本头）：`sudo install -m 755 ...`、`sudo install -m 600 .env /etc/legal-backup.env`，并配 `/etc/cron.d/legal-backup`（如 `0 2 * * * root ...`）。
- **写 `/opt/backup` 与 `/var/log` 需 sudo**（生产以 `ubuntu` 用户时务必 `sudo`）。

### 6.8 `deploy/scripts/rollback.sh` — 一键回滚（三种粒度）

- 用途：`--migration`（回滚最近一次 alembic 迁移）/ `--image`（回滚到上一个镜像 tag）/ `--full`（image + migration + 清理非法数据）。
- **任何回滚前强制备份**：`pg_dump ... pre_rollback_<TS>.dump` 落到 `BACKUP_DIR`。
- 变量：`COMPOSE_DIR=/opt/legal-review/deploy`、`COMPOSE_FILE`、`BACKUP_DIR=/opt/backup/legalai86`、`ROLLBACK_TAG`（显式指定镜像 tag）。
- 用法：`sudo bash rollback.sh --migration | --image | --full`。**必须 root**（脚本开头 `id -u` 校验）。
- `--full` 会提示人工清 `organization_id` 残余列（给出 `ALTER TABLE ... DROP COLUMN` 命令，**需人工连 DB 执行**）。
- 回滚后恢复命令：`docker exec -i legal-pg pg_restore -U legal -d legal_review --clean < .../pre_rollback_<TS>.dump`。
- 注意：`--image` 依据 `docker images legal-review/backend` 的 tag 选取；而 `docker-compose.prod.yml` 将 backend/frontend 镜像 tag **硬编码为 `:latest`**，实际回滚是否生效取决于服务器上是否存在可回滚的历史 tag，须人工核对（见 §13）。

### 6.9 `deploy/nginx/reload-on-cert-change.sh` — 证书变更自动 reload

- 位置：被 `deploy/nginx/Dockerfile` 复制为 `/docker-entrypoint.d/reload-on-cert-change.sh`，随 nginx 容器启动。
- 行为：等待 `/etc/letsencrypt/live/legalai86.com.cn/fullchain.pem` 就位（最长 5 分钟）；`inotifywait` 监听该目录 `modify/create/moved_to` 触发 `nginx -s reload`；另有每 6h（`RELOAD_EVERY=21600`）兜底 reload；`inotifywait` 不可用时仅靠兜底定时。
- 注意：证书目录**硬编码为 `legalai86.com.cn`**；换域名需同步改此脚本。

---

## 7. 三种部署模式

### 7.1 常规部署（生产受控序列，推荐）

```bash
# 1) 本机：增量推送（tar / rsync）或服务器 git 拉取
# 2) 服务器：先备份
sudo bash /opt/legal-review/deploy/scripts/backup_pg.sh
# 3) 服务器：构建后端镜像
cd /opt/legal-review/deploy && sudo docker compose -f docker-compose.prod.yml build backend
# 4) 服务器：先迁移（旧容器仍在，schema 先行）
sudo docker compose -f docker-compose.prod.yml run --rm --no-deps backend alembic upgrade head
# 5) 服务器：换后端容器
sudo docker compose -f docker-compose.prod.yml up -d --no-deps backend
# 6) 验证
sudo DOMAIN=legalai86.com.cn bash /opt/legal-review/deploy/scripts/verify.sh
```

> 也可用 `sync.sh` 一键完成（注意其顺序与 §5.2 提示的差异）。前端有改动时同法 `build frontend` + `up -d --no-deps frontend`；nginx conf 有改动才 `RESTART_NGINX=1`。

### 7.2 仅支付宝模式（`ALIPAY_ONLY`，不需微信配置）

```bash
# 1) 只装支付宝凭证（跳过 WXPAY_* 必填校验）
REMOTE_SUDO=sudo SSH_HOST=ubuntu@124.221.229.12 PROJECT_DIR=/opt/legal-review \
  ALIPAY_ONLY=1 ALIPAY_ENABLED=true \
  ALIPAY_APP_ID=... ALIPAY_PRIVATE_KEY=... ALIPAY_PUBLIC_KEY=... \
  bash deploy/scripts/install-payment-env.sh
# 2) 仅支付宝验收
REMOTE_SUDO=sudo SSH_HOST=ubuntu@124.221.229.12 DOMAIN=legalai86.com.cn \
  USER_EMAIL=... USER_PASS=... PAY_TYPE=page \
  bash deploy/scripts/verify-alipay-only.sh
```

- 该模式下 `install-payment-env.sh` 只校验 `ALIPAY_ENABLED/ALIPAY_APP_ID/ALIPAY_PRIVATE_KEY/ALIPAY_PUBLIC_KEY`；其余 `WXPAY_*` 以 `WXPAY_ENABLED=false` 与空值写入（后续补微信时再改）。
- **不改 `JWT_SECRET` / `POSTGRES_PASSWORD`**；写入前自动备份 `.env`；写入后 `chmod 600`；**只重启 backend**（不影响 nginx / 前端 / PostgreSQL / Redis）。

### 7.3 回滚模式

```bash
sudo bash /opt/legal-review/deploy/scripts/rollback.sh --migration   # 仅 DB 变更回退（推荐）
sudo bash /opt/legal-review/deploy/scripts/rollback.sh --image       # 全栈镜像回退（推荐）
sudo bash /opt/legal-review/deploy/scripts/rollback.sh --full        # image + migration + 人工清列
```

- 触发场景（脚本头）：迁移后组织字段 NULL / FK 违反；部署了 broken image（启动 crash / 大量 5xx）；多租户串租（严重）。
- 回滚前会自动 `pg_dump pre_rollback`；回滚后自动跑 `verify.sh`。

---

## 8. 健康检查与冒烟测试

### 8.1 权威健康检查

```bash
# 根路径 /health（200；挂根路径，不进 /api/v1）
curl -sS -o /dev/null -w '%{http_code}\n' https://legalai86.com.cn/health
# 期望：200

# 容器内直连（nginx 之外）
docker exec legal-backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"
```

> 再次强调：`https://legalai86.com.cn/api/v1/health` **会 404，属正常**。

### 8.2 计价/路由冒烟

```bash
curl -sS https://legalai86.com.cn/api/v1/billing/pricing        # 期望定价 JSON
```

### 8.3 指标服务（Prometheus）

- 指标端点：`GET /api/v1/metrics/prometheus`（Prometheus 文本格式，见 `backend/app/api/v1/metrics.py`）。
- **豁免限流**：`/api/v1/metrics/prometheus` 在 `rate_limit_exempt_paths` 白名单内（默认值见 `backend/app/core/config.py`，中间件按精确路径判断，见 `backend/app/main.py`）——**必须保持该豁免**，否则 Prometheus 抓取会被 per-IP 限流 429。
- 抓取配置：`deploy/prometheus/prometheus.yml` 目标 `backend:8000`，`metrics_path: /api/v1/metrics/prometheus`；告警规则 `deploy/prometheus/alerts.yml`。
- **指标服务不对外暴露端口**：`legal-prometheus` 无 `ports` 映射，仅在内网 `appnet`；`/api/v1/metrics/prometheus` 虽经 `location /api/` 可达，但不要新增对外端口或将其暴露到公网。

### 8.4 铸 token 冒烟（需带 `role` 参数）

生产做 token 冒烟/调试时，签发 access token 的函数签名要求 `role`：

```bash
docker exec legal-backend python -c "from uuid import UUID; from app.services.auth_service import create_access_token; print(create_access_token(UUID('<user_id>'), '<role>'))"
```

- 函数签名（`backend/app/services/auth_service.py`）：`create_access_token(user_id: UUID, role: str, tier: str = PlanTier.FREE)` —— **`role` 是必填位置参数，不带会报错**。
- `role` 取值须为系统角色：`submitter` / `reviewer` / `supervisor` / `admin` / `librarian`（见 `docs/03_DATABASE_DESIGN.md` 的 `users.role` 约束）。
- 冒烟仅用于本地/受控验证，token 与用户 ID 不得写入日志或提交仓库。

---

## 9. 备份与恢复

### 9.1 备份（`deploy/scripts/backup_pg.sh`）

- 产出：
  - `legal_review_<TS>.dump`（`pg_dump -F c` 压缩，可 `pg_restore` 精确恢复）
  - `legal_review_<TS>.sql`（纯 SQL，便于 grep）
  - `uploads_<DATE>.tar.gz`（`legal_backend_uploads` 卷）
- 位置：`/opt/backup/legalai86/`；保留 `KEEP_DAYS=30` 天；日志 `/var/log/legal-backup.log`。
- 可选上传腾讯云 COS（需 `coscli` + `COS_*` 变量）。
- 定时：建议写入 `/etc/cron.d/legal-backup`（脚本头给示例 `0 2 * * *`）。
- **注意**：写 `/opt/backup`、`/var/log` 需 sudo；生产以 `ubuntu` 运行时务必 `sudo`。

### 9.2 恢复

```bash
# 用自定义格式 dump 恢复（会 --clean 覆盖现有对象，谨慎）
docker exec -i legal-pg pg_restore -U legal -d legal_review --clean < /opt/backup/legalai86/legal_review_<TS>.dump
```

- `rollback.sh` 亦会在回滚前自动生成 `pre_rollback_<TS>.dump` 并给出恢复命令。
- 恢复为**高风险操作**：请先 `pg_dump` 当前状态二次备份，并在获得批准后执行。

---

## 10. 上线检查清单（可勾选）

### 10.1 前置与合规

- [ ] 域名 `legalai86.com.cn` ICP 备案有效；**不涉及/不使用 `legal86.com.cn`**
- [ ] 用户协议 / 隐私政策 / Cookie 政策文本经人工 review
- [ ] LLM 至少一个 Key（`DEEPSEEK_API_KEY` 或 `QWEN_API_KEY`）已备；否则确认接受 `LLM_PROVIDER=mock`
- [ ] 支付渠道凭证已备（支付宝 / 微信，按渠道）
- [ ] 安全组仅放行 22 / 80 / 443

### 10.2 部署执行

- [ ] `deploy/.env` 存在且 `chmod 600`，`JWT_SECRET` / `POSTGRES_PASSWORD` 已设置
- [ ] `docker compose -f docker-compose.prod.yml build backend` 成功
- [ ] **先迁移**：`docker compose run --rm --no-deps backend alembic upgrade head` 成功
- [ ] **后换容器**：`docker compose up -d --no-deps backend` 成功
- [ ] `docker exec legal-backend alembic current` 显示预期版本
- [ ] `legal-nginx` 已运行（80/443）；证书已就位

### 10.3 验证

- [ ] `https://legalai86.com.cn/health` 返回 200（**非 `/api/v1/health`**）
- [ ] `GET https://legalai86.com.cn/` 返回 200
- [ ] `https://legalai86.com.cn/api/v1/billing/pricing` 返回定价 JSON
- [ ] `sudo DOMAIN=legalai86.com.cn bash deploy/scripts/verify.sh` 全绿（FAIL < 2）
- [ ] 若涉及支付：`verify-alipay-only.sh` 或 `verify-payment.sh` 服务层全 PASS
- [ ] `legal-prometheus` 内网抓取 `/api/v1/metrics/prometheus` 正常，且**未新增对外端口**
- [ ] 备份：`backup_pg.sh` 能产出完整 dump，cron 已挂

### 10.4 回滚预案

- [ ] 已确认 `rollback.sh` 可用；已知悉 `--image` 依赖历史镜像 tag（见 §13）
- [ ] 已确认可用备份 dump 的恢复命令与演练结论

---

## 11. 安全与禁止事项

**禁止（红线）：**

1. **不擅自变更 DNS 解析 / ICP 备案 / 域名绑定**；不引入 `legal86.com.cn` 等非备案域名，不将其与 `legalai86.com.cn` 混用。
2. **不新增对外暴露端口**：postgres / redis / backend / frontend / prometheus 均只在 `legal_appnet` 内网；对外仅 nginx 的 80/443。**指标服务（prometheus、`/api/v1/metrics/prometheus`）不对外暴露端口。**
3. **密钥不入日志/仓库/镜像**：私钥、`JWT_SECRET`、`POSTGRES_PASSWORD`、支付密钥只存 `deploy/.env`（`600`），`.env` 与 `*.pem`/`*.key` 已在 `.gitignore`。任何脚本/日志不得打印密钥值。
4. **不得改动支付安装脚本对 `JWT_SECRET` / `POSTGRES_PASSWORD` 的保留逻辑**（这两项永不被支付凭证安装覆盖）。
5. **必须保持 `/api/v1/metrics/prometheus` 在限流豁免名单内**。
6. **未经明确批准，不得执行任何生产部署/迁移/回滚命令**。本手册撰写环境**未获得生产部署批准，本次未部署生产**。
7. **无 volume 挂载的后端镜像**：不得假设改代码会热生效；任何后端代码变更都必须 `build backend` 并重建容器。
8. 触碰 `/opt`、`/etc`、`/var` 的操作在服务器上（`ubuntu` 用户）必须 `sudo`。

---

## 12. 本地开发与测试运行

### 12.1 本地基础设施（`docker-compose.yml`）

- 该文件**只启动 PostgreSQL（含 pgvector）**：容器名 `legal-review-pg`，主机端口 **`5434:5432`**，库 `legal_review`，用户 `legal`，密码 `legal_dev_pass`；初始化脚本挂载 `docker/init.sql`（创建 `vector` / `pg_trgm` / `uuid-ossp` 扩展）。
- **Redis 不走本 compose**：本地使用 homebrew `redis-server`（`6379`，与 compose 不冲突）。

```bash
docker compose up -d postgres
```

### 12.2 后端本地运行（`.venv` + pytest / ruff / mypy）

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"          # dev 依赖含 pytest / ruff / mypy（见 pyproject.toml）
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload --port 8000

# 质量门禁
pytest                            # asyncio_mode=auto，testpaths=tests，带 --cov
ruff check .                      # line-length=100，规则 E/F/I/N/UP/B/C4/SIM
mypy .                            # 严格可空/返回/不可达；部分重金属库 ignore_missing_imports
```

- `backend/pyproject.toml` 已配置 `[tool.pytest.ini_options]`、`[tool.ruff]`、`[tool.mypy]`。
- 测试默认设 `RATE_LIMIT_ENABLED=false`（`backend/tests/conftest.py`）。

### 12.3 前端本地运行

```bash
cd frontend
pnpm install
pnpm dev        # next dev
pnpm build && pnpm start
```

- 前端本地端口默认 `3000`/`3080`（`backend/app/core/config.py` 默认 CORS 含 `localhost:3000/3080`）；生产容器内为 `3081`。

---

## 13. 已知部署风险与注意事项

1. **脚本探测路径不一致**：`deploy.sh` 与 `sync.sh` 收尾冒烟打 `/api/v1/health`（会 404）；权威判据是 `/health`。`verify-payment.sh` 的健康项同为 `/api/v1/health`（会 FAIL）。以 `/health` 为准，勿据此误判回滚。
2. **迁移与换容器顺序**：生产受控序列是「先 `alembic upgrade head`，再 `up -d backend`」；`sync.sh` 内置顺序为先换容器后迁移（见 §5.2），迁移失败时新代码可能已对旧 schema 运行，需 `rollback.sh --migration`。
3. **镜像回滚的 tag 依赖**：`docker-compose.prod.yml` 中 backend/frontend 镜像 **硬编码为 `:latest`**，而 `rollback.sh --image` 依据 `docker images` 中的历史 tag 回退。若服务器未保留历史 tag（持续 build 覆盖 `:latest`），`--image` 可能无法真正回退当前运行的镜像，需 `ROLLBACK_TAG=<tag>` 显式指定并人工核对。
4. **后端镜像内置代码**：无源码 volume 挂载，任何后端改动必须重建镜像，不能靠挂载/热重载。
5. **`git reset --hard`**：`sync.sh` 的服务器拉取会 `git fetch --all --prune` + `git reset --hard origin/<branch>`，**丢弃服务器端未提交改动**，执行前确认服务器工作区无本地改动。
6. **非 root 登录需 `REMOTE_SUDO`**：脚本默认 `SSH_HOST=root@...`，生产实为 `ubuntu`，务必显式 `SSH_HOST=ubuntu@124.221.229.12` + `REMOTE_SUDO=sudo`，否则 `/opt` 写入/`docker` 会因权限失败。
7. **证书目录/续期域名硬编码**：`reload-on-cert-change.sh` 与 nginx conf 的证书路径、`ALIPAY_RETURN_URL`、`WXPAY_OAUTH_REDIRECT_URL` 均硬编码 `legalai86.com.cn`；换域名须同步多处修改。
8. **`deploy.sh` 首次顺序**：首次部署是「先起 backend → 再 `docker exec` 迁移」，与 §5.2 的「先迁移后换容器」不同；首次部署若迁移报错，backend 仍在旧/初版 schema 上运行，需人工处理。
9. **支付安装仅重启 backend**：这是刻意设计（避免打翻 nginx/前端/DB/Redis）。若误用其它方式全量 `up -d`，可能引入不必要的服务重启与短暂中断。
10. **健康检查依赖**：backend `HEALTHCHECK` 与各脚本都依赖容器内 `python urllib` 打 `http://127.0.0.1:8000/health`；改动该探针行为会影响容器 healthy 判定。
11. **限流豁免必须保持**：`/api/v1/metrics/prometheus` 若被移出 `rate_limit_exempt_paths`，Prometheus 抓取将 429。
12. **无生产批准不得部署**：上述所有命令仅为文档记录，本环境未获批准、未执行生产部署。
