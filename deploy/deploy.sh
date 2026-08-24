#!/usr/bin/env bash
# 一键部署 legalai86.com.cn (腾讯云 + Docker Compose)
# 在 124.221.229.12 上以 root 身份执行
set -euo pipefail

export DOMAIN=${DOMAIN:-legalai86.com.cn}
export WWW_DOMAIN=${WWW_DOMAIN:-www.legalai86.com.cn}
export EMAIL=${EMAIL:-admin@legalai86.com.cn}
export PROJECT_DIR=${PROJECT_DIR:-/opt/legal-review}
export COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}

log() { printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }
die() { printf '\n\033[1;31m!! %s\033[0m\n' "$*"; exit 1; }

[[ $(id -u) -eq 0 ]] || die "请用 root 跑: sudo bash deploy.sh"

# 1. DNS 自检 -------------------------------------------------------
log "[1/7] 检查 DNS 解析"
RESOLVED=$(getent hosts "$DOMAIN" 2>/dev/null | awk '{print $1}' | head -1 || true)
EXPECTED_IP="124.221.229.12"
if [[ -z "$RESOLVED" ]]; then
    die "DNS 未解析 $DOMAIN,先到腾讯云 DNSPod 加 A 记录 @ -> $EXPECTED_IP (含 www)"
fi
if [[ "$RESOLVED" != "$EXPECTED_IP" ]]; then
    die "DNS 解析 $DOMAIN -> $RESOLVED,与本机 IP $EXPECTED_IP 不一致"
fi
echo "  $DOMAIN -> $RESOLVED  OK"

# 2. Docker 安装 -----------------------------------------------------
log "[2/7] 安装/检查 Docker"
if ! command -v docker >/dev/null 2>&1; then
    apt-get update
    apt-get install -y ca-certificates curl gnupg
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
docker compose version >/dev/null 2>&1 || die "docker compose 不可用"
systemctl enable --now docker

# 3. 项目代码 -------------------------------------------------------
log "[3/7] 拉取项目代码"
if [[ ! -d "$PROJECT_DIR" ]]; then
    echo "  请先把代码 push 到 git,然后改下面这一行:"
    echo "    git clone <你的 repo url> $PROJECT_DIR"
    die "未自动 git clone,等用户填 repo"
fi
cd "$PROJECT_DIR/deploy"
git pull --ff-only || true

# 4. 环境变量 -------------------------------------------------------
log "[4/7] 写 .env"
ENV_FILE="$PROJECT_DIR/deploy/.env"
if [[ ! -f "$ENV_FILE" ]]; then
    SECRET=$(openssl rand -hex 32)
    PG_PASS=$(openssl rand -hex 16)
    cat > "$ENV_FILE" <<EOF
POSTGRES_PASSWORD=$PG_PASS
JWT_SECRET=$SECRET
LLM_PROVIDER=${LLM_PROVIDER:-mock}
DEEPSEEK_API_KEY=${DEEPSEEK_API_KEY:-}
QWEN_API_KEY=${QWEN_API_KEY:-}
CORS_ORIGINS=https://$DOMAIN,https://$WWW_DOMAIN
EOF
    chmod 600 "$ENV_FILE"
    echo "  已生成 $ENV_FILE (含随机密码/secret),需要时再编辑"
fi
set -a; source "$ENV_FILE"; set +a

# 5. 拉镜像 + 启动 ---------------------------------------------------
log "[5/7] docker compose build + up -d"
docker compose -f "$COMPOSE_FILE" pull --ignore-pull-failures || true
docker compose -f "$COMPOSE_FILE" build
docker compose -f "$COMPOSE_FILE" up -d postgres redis backend frontend nginx
echo "  等待 backend 健康 (最多 60s) ..."
for i in $(seq 1 30); do
    if docker exec legal-backend curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "  backend healthy"; break
    fi
    sleep 2
done

# 6. 申请证书 -------------------------------------------------------
log "[6/7] 申请 Let's Encrypt 证书"
docker compose -f "$COMPOSE_FILE" run --rm --entrypoint "\
    certbot certonly --webroot --webroot-path=/var/www/certbot \
        --email $EMAIL --agree-tos --no-eff-email \
        -d $DOMAIN -d $WWW_DOMAIN" nginx || die "证书申请失败,确认 80 端口可外网访问 + DNS 已生效"
docker compose -f "$COMPOSE_FILE" restart nginx

# 7. 验证 --------------------------------------------------------
log "[7/7] 验证 4 个端点"
sleep 5
curl -sS -o /dev/null -w "  GET  /                           %{http_code}\n" --noproxy '*' "http://127.0.0.1/"
curl -sS -o /dev/null -w "  GET  /login                      %{http_code}\n" --noproxy '*' "http://127.0.0.1/login"
curl -sS -o /dev/null -w "  POST /api/v1/auth/login          %{http_code}\n" --noproxy '*' -H "Content-Type: application/json" \
    -d '{"email":"demo@shajindi.com","password":"Demo@2024"}' "http://127.0.0.1/api/v1/auth/login"
curl -sS -o /dev/null -w "  GET  /api/v1/audit/count         %{http_code}\n" --noproxy '*' "http://127.0.0.1/api/v1/audit/count"

cat <<'TXT'

✅ 部署完成。下一步:
   1. 从本机 Mac 验证:  curl -I --noproxy '*' https://legalai86.com.cn/
   2. 浏览器打开:       https://legalai86.com.cn/login
   3. 登录账号:         demo@shajindi.com / Demo@2024
   4. 改 .env 后重启:    cd /opt/legal-review/deploy && docker compose -f docker-compose.prod.yml up -d

TXT
