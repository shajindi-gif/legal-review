# 部署手册 — legalai86.com.cn

> 适用版本：M15 之后（2026-08-25 起）。  
> 部署模式：自建 VPS · Ubuntu 22.04/24.04 · Docker Compose  
> 证书：Let's Encrypt 自动（webroot 模式）  
> 反代：Nginx 1.27 alpine（80/443 同域反代）  
> 后端：FastAPI + Uvicorn (容器内 8000)  
> 前端：Next.js standalone (容器内 3081)

---

## 0. 部署前清单

### 0.1 服务器最低要求

| 项 | 最低 | 推荐 |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU（11 节点 Agent 流水线并发） |
| RAM | 4 GB | 8 GB（LLM 流量高峰期稳定） |
| 磁盘 | 40 GB SSD | 80 GB SSD（用户上传 + DB 增长） |
| OS | Ubuntu 22.04 LTS | Ubuntu 24.04 LTS |
| 端口 | 22, 80, 443 可外网 | 同上 + 6000-6100（调试 SSH） |

### 0.2 域名 DNS

在 DNS 服务商（腾讯云 DNSPod / 阿里云 / Cloudflare）添加：

| 主机记录 | 记录类型 | 记录值 | TTL |
|---|---|---|---|
| `@` | A | `你的_VPS_IP` | 600 |
| `www` | A | `你的_VPS_IP` | 600 |

> 部署脚本会做 DNS 自检。如果 CDN 在前面（例如 Cloudflare 代理），需要让 certbot 走 `dns-cloudflare` 插件模式（**本手册不覆盖**，需要改 deploy.sh 步骤 8）。

### 0.3 必备工具

- SSH 客户端（macOS Terminal / Windows PowerShell / MobaXterm）
- 当前仓库的 git 写入权限或管理员可手动 rsync 代码

---

## 1. 首次部署

### 1.1 准备环境

```bash
# 用 SSH 登录服务器
ssh root@<your_vps_ip>

# 创建工作目录
mkdir -p /opt && cd /opt

# （可选）确认 DNS 已生效
dig +short legalai86.com.cn A
dig +short www.legalai86.com.cn A
# 两个都应返回 <your_vps_ip>
```

### 1.2 上传代码

两种方式任选：

**A. Git 克隆（推荐）**
```bash
cd /opt
git clone https://github.com/shajindi-gif/legal-review.git
```

**B. rsync 推送（无外网 Git 时）**
```bash
# 本机
rsync -avz --exclude='.venv' --exclude='node_modules' --exclude='.next' \
    --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
    /Users/shajindi/traework/legal-review/ root@<your_vps_ip>:/opt/legal-review/
```

### 1.3 运行 deploy.sh

```bash
cd /opt/legal-review/deploy
chmod +x deploy.sh
sudo bash deploy.sh
```

**脚本会自动完成 8 个阶段**：
1. 系统预检（root / Ubuntu / 必备工具）
2. DNS 解析自检（警告而非 fail，可继续）
3. 安装 Docker + Compose plugin
4. 拉取最新代码
5. 生成 `.env`（含随机 PG 密码 + JWT secret）
6. 构建镜像 + 启动 postgres / redis / backend / frontend
7. **alembic 迁移**（`alembic upgrade head`）
8. Let's Encrypt 证书签发 + 启动 nginx

**预计耗时**：首次 8-15 分钟（取决于网络拉镜像速度）。

### 1.4 启动 certbot 自动续期

```bash
cd /opt/legal-review/deploy
docker compose -f docker-compose.prod.yml --profile certbot up -d
```

容器每 12h 检查一次证书，< 30 天时自动续签并 reload nginx。

### 1.5 验证清单

部署完成后**依次**执行：

```bash
# 1. 容器全部 healthy
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep legal-

# 2. 前端 HTTP 200
curl -sI --noproxy '*' https://legalai86.com.cn/ | head -1
# 期望: HTTP/2 200

# 3. 后端健康
curl -sS --noproxy '*' https://legalai86.com.cn/api/v1/health
# 期望: {"status":"ok",...}

# 4. 证书生效
docker exec legal-nginx ls -la /etc/letsencrypt/live/legalai86.com.cn/

# 5. 登录页能渲染
curl -sS --noproxy '*' https://legalai86.com.cn/login | grep -o '<title>[^<]*</title>'
# 期望: <title>...</title> 含 LegalAI 字样
```

**浏览器验证**：打开 `https://legalai86.com.cn/login` 确认：
- ✅ 地址栏锁图标 + 证书签发方是 Let's Encrypt
- ✅ 页面能正常渲染
- ✅ F12 控制台无 CORS / Mixed Content 报错

---

## 2. 日常运维

### 2.1 查看日志

```bash
# 实时
docker logs -f legal-backend
docker logs -f legal-frontend
docker logs -f legal-nginx

# 最近 200 行
docker logs --tail=200 legal-backend
```

### 2.2 重启服务

```bash
cd /opt/legal-review/deploy

# 重启单个
docker compose -f docker-compose.prod.yml restart backend

# 重启全部（保留数据卷）
docker compose -f docker-compose.prod.yml restart

# 改 .env 后（生效要 recreate）
docker compose -f docker-compose.prod.yml up -d
```

### 2.3 升级代码

```bash
cd /opt/legal-review
git pull --ff-only

cd deploy
docker compose -f docker-compose.prod.yml build
docker compose -f docker-compose.prod.yml up -d

# 若有 alembic 新迁移
docker exec legal-backend alembic upgrade head

# 强制让 nginx 重载（如果只改了 nginx 配置）
docker exec legal-nginx nginx -s reload
```

### 2.4 备份数据库

```bash
# 全量 dump
docker exec legal-pg pg_dump -U legal -d legal_review -F c -f /tmp/backup.dump
docker cp legal-pg:/tmp/backup.dump /opt/backup/legal_review_$(date +%Y%m%d).dump

# 只导出 SQL
docker exec legal-pg pg_dump -U legal -d legal_review > /opt/backup/legal_review_$(date +%Y%m%d).sql

# 恢复
cat /opt/backup/legal_review_20260825.sql | docker exec -i legal-pg psql -U legal -d legal_review
```

建议加 cron：
```cron
0 2 * * * /opt/legal-review/deploy/scripts/backup_pg.sh >> /var/log/legal-backup.log 2>&1
```

### 2.5 备份用户上传

```bash
# 上传文件存在 named volume legal_backend_uploads
docker run --rm \
    -v legal_backend_uploads:/from \
    -v /opt/backup/uploads:/to \
    alpine tar czf /to/uploads_$(date +%Y%m%d).tar.gz -C /from .
```

### 2.6 查看资源占用

```bash
docker stats --no-stream
# NAME            CPU %   MEM USAGE / LIMIT
# legal-backend   5.3%    380MiB / 8GiB
# legal-frontend  0.5%    120MiB / 8GiB
# legal-nginx     0.1%    12MiB / 8GiB
# legal-pg        2.1%    650MiB / 8GiB
# legal-redis     0.3%    35MiB / 8GiB
```

---

## 3. 常见事故与响应

### 3.1 证书过期 / 续签失败

```bash
# 手动续期
docker compose -f docker-compose.prod.yml run --rm certbot renew \
    --webroot -w /var/www/certbot \
    --post-hook "docker exec legal-nginx nginx -s reload"

# 查看详细错误
docker logs --tail=100 legal-certbot 2>/dev/null || \
    docker compose -f docker-compose.prod.yml run --rm certbot renew --webroot -w /var/www/certbot --dry-run
```

### 3.2 后端 500 / 启动失败

```bash
# 1. 看日志
docker logs --tail=300 legal-backend | grep -E 'Error|Traceback|alembic'

# 2. 数据库连接失败？先确认 postgres 健康
docker ps --filter name=legal-pg --format '{{.Status}}'
docker exec legal-pg pg_isready -U legal -d legal_review

# 3. alembic 失败？手动跑迁移
docker exec legal-backend alembic upgrade head
docker exec legal-backend alembic current

# 4. 端口被占？检查 8000
docker exec legal-backend ss -tlnp | grep 8000
```

### 3.3 前端 502 Bad Gateway

```bash
# 1. frontend 容器没起
docker ps --filter name=legal-frontend

# 2. nginx 配置错误
docker exec legal-nginx nginx -t
docker logs --tail=50 legal-nginx

# 3. 反向 backend 的 /api/ 连不上
docker exec legal-frontend wget -qO- http://backend:8000/health
# 期望: {"status":"ok",...}
# 失败说明 backend 没在容器网络里，或 /health 路径不对
```

### 3.4 磁盘满

```bash
# 看磁盘
df -h

# 看 docker 占多少
docker system df

# 清理无用镜像 / 停止的容器 / 缓存
docker system prune -a --volumes    # 慎用，会清数据卷
# 推荐只清不用镜像：
docker image prune -a

# 日志占满：限单个容器日志大小（重启时生效）
# 写入 /etc/docker/daemon.json
# {
#   "log-driver": "json-file",
#   "log-opts": { "max-size": "50m", "max-file": "3" }
# }
# 然后 systemctl restart docker
```

### 3.5 整站恢复（最坏情况）

```bash
# 1. 备份当前数据卷快照（防止误操作）
docker run --rm -v legal_pg_data:/from -v /opt/backup:/to \
    alpine tar czf /to/pgdata_$(date +%Y%m%d).tar.gz -C /from .

# 2. 拉最新代码 + 重建
cd /opt/legal-review && git pull
cd deploy
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml build --no-cache
docker compose -f docker-compose.prod.yml up -d postgres redis backend frontend
docker exec legal-backend alembic upgrade head
docker compose -f docker-compose.prod.yml up -d nginx

# 3. 验证
bash ./scripts/verify.sh    # 见 §4
```

---

## 4. 验证脚本（建议落地）

把以下内容保存为 `deploy/scripts/verify.sh`：

```bash
#!/usr/bin/env bash
# 用法： bash verify.sh
set -e
DOMAIN=${DOMAIN:-legalai86.com.cn}

echo "== 1. 容器状态 =="
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep legal- || { echo "FAIL: 容器未起"; exit 1; }

echo "== 2. 前端 HTTP 200 =="
curl -sI --noproxy '*' "https://127.0.0.1/" | head -1
curl -sI --noproxy '*' "https://127.0.0.1/" | head -1 | grep -q "200" || { echo "FAIL: 前端非 200"; exit 1; }

echo "== 3. 后端 /api/v1/health =="
curl -fsS --noproxy '*' "https://127.0.0.1/api/v1/health" || { echo "FAIL: 后端不健康"; exit 1; }

echo "== 4. 登录 API =="
curl -fsS -o /dev/null -w "  POST /api/v1/auth/login  %{http_code}\n" --noproxy '*' \
    -H "Content-Type: application/json" \
    -d '{"email":"demo@shajindi.com","password":"Demo@2024"}' \
    "https://127.0.0.1/api/v1/auth/login"

echo "== 5. 证书 =="
docker exec legal-nginx ls /etc/letsencrypt/live/$DOMAIN/fullchain.pem || { echo "FAIL: 证书未就位"; exit 1; }

echo ""
echo "✅ 验证通过"
```

`chmod +x verify.sh` 后每次升级代码前跑一次。

---

## 5. 安全清单

部署后**必须**做的事：

- [ ] **改 SSH 端口 + 禁密码登录**（用 SSH key）
- [ ] 启用腾讯云 / 阿里云 **安全组**：只放 22 / 80 / 443
- [ ] 启用 **fail2ban**
- [ ] 设置 **自动安全更新**：`unattended-upgrades`
- [ ] **DB / Redis 不暴露公网**（compose 里已不加 ports，公网进不来）
- [ ] `.env` 权限 600（deploy.sh 已设）
- [ ] 启用 **腾讯云 / 阿里云 免费 DDoS 基础防护**
- [ ] 监控：用腾讯云可观测 / 阿里云 ARMS / 自建 Uptime Kuma（HTTP 探针）

---

## 6. 未来扩展点（不是 M15 必做）

- [ ] **CDN**：把 `legalai86.com.cn` 套到腾讯云 CDN / Cloudflare（注意要改 certbot 为 DNS 模式）
- [ ] **WAF**：腾讯云 Web 应用防火墙
- [ ] **日志收集**：腾讯云 CLS / Loki + Grafana
- [ ] **CI/CD**：GitHub Actions 跑 `pnpm build` + `docker build` + `docker push`，服务器 webhook pull
- [ ] **蓝绿部署**：用 nginx upstream 切流量
- [ ] **K8s 迁移**：当单实例撑不住时（DAU > 5k 考虑）

---

## 7. 联系 / 排错

- 部署脚本源码：`/opt/legal-review/deploy/deploy.sh`
- Docker Compose：`/opt/legal-review/deploy/docker-compose.prod.yml`
- Nginx 配置：`/opt/legal-review/deploy/nginx/conf.d/legalai86.com.cn.conf`
- 日志查询：`docker logs <container>`
- 数据库直连：`docker exec -it legal-pg psql -U legal -d legal_review`
- 进入 backend 容器：`docker exec -it legal-backend bash`

如遇本手册未覆盖的问题，**先看 docker logs**，再回看 deploy.sh 输出。
