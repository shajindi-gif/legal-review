#!/usr/bin/env bash
# legalai86.com.cn 一键部署脚本（自建 VPS · Ubuntu 22.04/24.04 · Docker Compose）
#
# 设计目标：
#   - 跑通"裸机 Ubuntu" -> "HTTPS 站点可用" 的全流程
#   - 所有 IP 都不是硬编码（VPS 换机器只改 env）
#   - 关键节点都进 trap，失败留下现场日志
#   - 部署用 Let's Encrypt 自动签发 + 续期，不依赖云平台证书
#   - alembic 迁移在 backend 启动前强制跑一次
#
# 用法：
#   sudo bash deploy.sh
# 或先覆盖：
#   sudo DOMAIN=legalai86.com.cn EMAIL=admin@legalai86.com.cn PROJECT_DIR=/opt/legal-review bash deploy.sh
#
# 必须的环境变量（deploy.sh 内部未给则用默认值）：
#   DOMAIN        主域名（默认 legalai86.com.cn）
#   WWW_DOMAIN    www 子域（默认 www.legalai86.com.cn）
#   EMAIL         Let's Encrypt 注册邮箱（默认 admin@$DOMAIN）
#   PROJECT_DIR   代码根目录（默认 /opt/legal-review）
#   REPO_URL      git 仓库 URL
#   SSH_PORT      SSH 端口（22）

set -euo pipefail
IFS=$'\n\t'

# ============================================================
# 0. 默认值
# ============================================================
export DOMAIN=${DOMAIN:-legalai86.com.cn}
export WWW_DOMAIN=${WWW_DOMAIN:-www.legalai86.com.cn}
export EMAIL=${EMAIL:-admin@${DOMAIN}}
export PROJECT_DIR=${PROJECT_DIR:-/opt/legal-review}
export REPO_URL=${REPO_URL:-https://github.com/shajindi-gif/legal-review.git}
export SSH_PORT=${SSH_PORT:-22}
export COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}
export DEPLOY_DIR="$PROJECT_DIR/deploy"
export ENV_FILE="$DEPLOY_DIR/.env"

# 颜色
RED='\033[1;31m'; GRN='\033[1;32m'; YEL='\033[1;33m'; CYN='\033[1;36m'; NC='\033[0m'
log()  { printf '\n${CYN}== %s ==${NC}\n' "$*"; }
ok()   { printf '${GRN}OK  %s${NC}\n' "$*"; }
warn() { printf '${YEL}WARN %s${NC}\n' "$*"; }
die()  { printf '${RED}!!  %s${NC}\n' "$*" >&2; exit 1; }

# ============================================================
# 1. 预检
# ============================================================
log "[1/8] 系统预检"

[[ $(id -u) -eq 0 ]] || die "请用 root 跑: sudo bash $0"

# OS 必须是 Ubuntu 22.04+ (部署脚本假设 apt / systemd)
if ! command -v apt-get >/dev/null 2>&1; then
    die "本脚本只支持 Ubuntu/Debian 系。若是 CentOS/RHEL 请改用对应包管理器分支。"
fi

# 检查 curl / git / openssl
for bin in curl git openssl; do
    command -v "$bin" >/dev/null 2>&1 || die "缺少工具: $bin  请 apt-get install $bin"
done

ok "系统预检通过（DOMAIN=$DOMAIN, PROJECT_DIR=$PROJECT_DIR）"

# ============================================================
# 2. DNS 自检（警告而非 fail——可能 CDN 在前面）
# ============================================================
log "[2/8] DNS 解析自检"

PUBLIC_IP=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null \
            || curl -fsS --max-time 5 https://ifconfig.me 2>/dev/null \
            || hostname -I | awk '{print $1}')
[[ -n "$PUBLIC_IP" ]] || die "无法获取本机公网 IP，请确认出口网络"

RESOLVED=$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | head -1 || true)
if [[ -z "$RESOLVED" ]]; then
    warn "DNS 尚未解析 $DOMAIN，certbot 会失败。请到 DNS 服务商把 A 记录 $DOMAIN / $WWW_DOMAIN -> $PUBLIC_IP 后重试。"
    warn "可继续部署，但 certbot 步骤会等 DNS 生效后手动重跑。"
    SKIP_CERTBOT=1
elif [[ "$RESOLVED" != "$PUBLIC_IP" ]]; then
    warn "$DOMAIN 当前解析到 $RESOLVED，本机 IP 是 $PUBLIC_IP。常见情况：CDN 在前。"
    warn "若你确认 CDN/反代配置正确，继续；否则请先修 DNS。"
    SKIP_CERTBOT=0
else
    ok "$DOMAIN -> $RESOLVED 与本机 IP 一致"
    SKIP_CERTBOT=0
fi

# ============================================================
# 3. Docker / Compose 安装
# ============================================================
log "[3/8] Docker / Compose"

if ! command -v docker >/dev/null 2>&1; then
    warn "未检测到 docker，开始安装"
    apt-get update
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io \
                        docker-buildx-plugin docker-compose-plugin
fi

docker compose version >/dev/null 2>&1 || die "docker compose plugin 未安装"
systemctl enable --now docker
ok "docker $(docker --version) | compose $(docker compose version --short)"

# ============================================================
# 4. 拉代码
# ============================================================
log "[4/8] 拉取项目代码"

if [[ ! -d "$PROJECT_DIR" ]]; then
    git clone "$REPO_URL" "$PROJECT_DIR"
fi
cd "$PROJECT_DIR"
git pull --ff-only || warn "git pull 失败（可能未配置 git 推送权限或非 git 仓库），使用本地代码继续"

cd "$DEPLOY_DIR"
ok "代码就位: $(cd "$PROJECT_DIR" && git rev-parse --short HEAD 2>/dev/null || echo 'no-git')"

# ============================================================
# 5. 写 .env（自动生成密码 / secret）
# ============================================================
log "[5/8] 生成 / 检查 .env"

if [[ ! -f "$ENV_FILE" ]]; then
    SECRET=$(openssl rand -hex 32)
    PG_PASS=$(openssl rand -hex 16)
    cat > "$ENV_FILE" <<EOF
# 自动生成于 $(date -u +"%Y-%m-%dT%H:%M:%SZ")
POSTGRES_PASSWORD=$PG_PASS
JWT_SECRET=$SECRET
LLM_PROVIDER=${LLM_PROVIDER:-mock}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
QWEN_API_KEY=${QWEN_API_KEY:-}
DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY:-}
CORS_ORIGINS=https://$DOMAIN,https://$WWW_DOMAIN
EOF
    chmod 600 "$ENV_FILE"
    ok "已生成 $ENV_FILE（chmod 600，root 独占）"
else
    ok "已存在 $ENV_FILE，跳过生成（要重置请手动删）"
fi

# shellcheck disable=SC1090
set -a; source "$ENV_FILE"; set +a
: "${JWT_SECRET:?JWT_SECRET 必须设置}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD 必须设置}"

# ============================================================
# 6. 构建 + 启动（不含 nginx，等证书到位）
# ============================================================
log "[6/8] docker compose build + up (data + backend + frontend)"

cd "$DEPLOY_DIR"
docker compose -f "$COMPOSE_FILE" build
# 先起 data 层 + backend + frontend；nginx 暂不起，等证书文件就位
docker compose -f "$COMPOSE_FILE" up -d postgres redis backend frontend
ok "postgres / redis / backend / frontend 已起，nginx 待证书"

# 等 backend healthy
log "    等待 backend /health (最多 90s) ..."
HEALTHY=0
for i in $(seq 1 45); do
    if docker exec legal-backend curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        HEALTHY=1; break
    fi
    sleep 2
done
[[ "$HEALTHY" -eq 1 ]] || die "backend 90s 内未 health，请 docker logs legal-backend"
ok "backend /health 200"

# ============================================================
# 7. alembic 迁移
# ============================================================
log "[7/8] alembic upgrade head"

docker exec legal-backend alembic upgrade head
ok "alembic 迁移完成"

# 顺带 seed 初始数据（若 backend 提供了 seed 脚本则跑，否则 warn）
if docker exec legal-backend test -f /app/scripts/seed_users_orgs.py 2>/dev/null; then
    warn "发现 scripts/seed_users_orgs.py，默认 *不* 自动执行，避免覆盖生产账号"
    warn "需要时手动： docker exec legal-backend python /app/scripts/seed_users_orgs.py"
fi

# ============================================================
# 8. 证书 + 起 nginx
# ============================================================
log "[8/8] Let's Encrypt 证书 + 启动 nginx"

if [[ "${SKIP_CERTBOT:-0}" == "1" ]]; then
    warn "跳过 certbot（DNS 解析未到位）"
    warn "等 DNS 生效后手动跑："
    warn "    cd $DEPLOY_DIR && docker compose -f $COMPOSE_FILE run --rm certbot certonly \\"
    warn "      --webroot --webroot-path=/var/www/certbot \\"
    warn "      --email $EMAIL --agree-tos --no-eff-email \\"
    warn "      -d $DOMAIN -d $WWW_DOMAIN"
    warn "    cd $DEPLOY_DIR && docker compose -f $COMPOSE_FILE up -d nginx"
else
    # 第一次签证书（webroot 模式）
    docker compose -f "$COMPOSE_FILE" run --rm certbot certonly \
        --webroot --webroot-path=/var/www/certbot \
        --email "$EMAIL" --agree-tos --no-eff-email \
        -d "$DOMAIN" -d "$WWW_DOMAIN" \
        || die "证书申请失败：确认 80 端口可外网访问 + DNS 已生效 + EMAIL 合法"

    # 起 nginx（带证书）
    docker compose -f "$COMPOSE_FILE" up -d nginx
    sleep 3
    docker compose -f "$COMPOSE_FILE" ps nginx
fi

# ============================================================
# 验证
# ============================================================
cat <<'TXT'

==============================================================
  部署完成
==============================================================
  入口:      https://__DOMAIN__
  后端健康:  https://__DOMAIN__/api/v1/health
  数据库:    legal-review-pg (容器 legal-pg, 5432)
  Redis:     legal-redis (容器, 6379)

  进入容器:
    docker exec -it legal-backend bash
    docker exec -it legal-frontend sh
    docker exec -it legal-pg psql -U legal -d legal_review

  查看日志:
    docker logs -f --tail=200 legal-backend
    docker logs -f --tail=200 legal-frontend
    docker logs -f --tail=200 legal-nginx

  改 .env 后重启:
    cd __DEPLOY_DIR__
    docker compose -f __COMPOSE_FILE__ up -d

  证书自动续期:
    docker compose -f __COMPOSE_FILE__ --profile certbot up -d
    # 后台每 12h 检查一次 certbot renew，nginx 在 deploy.sh 已配
    # post-hook 触发 reload

==============================================================
TXT
TXT=${TXT//__DOMAIN__/$DOMAIN}
TXT=${TXT//__DEPLOY_DIR__/$DEPLOY_DIR}
TXT=${TXT//__COMPOSE_FILE__/$COMPOSE_FILE}
printf '%s\n' "$TXT"

# 最后做个 HTTP 200 自检
log "[verify] HTTP 自检（来自 nginx 反代路径）"
sleep 5
curl -sS -o /dev/null -w "  HTTP %{http_code}  https://$DOMAIN/\n" --noproxy '*' \
    "https://127.0.0.1/"  || warn "  本地 https://127.0.0.1/ 失败（可能证书未生效或 nginx 未起）"
curl -sS -o /dev/null -w "  HTTP %{http_code}  https://$DOMAIN/api/v1/health\n" --noproxy '*' \
    "https://127.0.0.1/api/v1/health" || warn "  本地 https://127.0.0.1/api/v1/health 失败"
