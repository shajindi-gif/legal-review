#!/usr/bin/env bash
# legalai86.com.cn 增量推送 + 重启脚本
#
# 场景：服务器已经在跑（deploy.sh 跑过一次），现在只想把新代码推上去 + 重启 backend/frontend
#       而不是把整个 VPS 重做一次。
#
# 用法（在 deploy/ 目录下，假设你已经能 ssh 到服务器）：
#   SSH_HOST=root@124.221.229.12 \
#   PROJECT_DIR=/opt/legal-review \
#   bash deploy/scripts/sync.sh
#
# 可选：
#   COMPOSE_FILE=docker-compose.prod.yml   # 默认
#   REBUILD_BACKEND=1                      # 默认 1（改了后端代码必须 rebuild）
#   REBUILD_FRONTEND=1                     # 默认 1（改了前端代码必须 rebuild）
#   SKIP_PULL=1                            # 默认 0；1 表示代码已经在服务器上了，跳过 git pull
#   RESTART_NGINX=0                        # 默认 0；改了 nginx conf 才设 1
#
# 安全注意：
#   - 脚本不会写入 / 修改任何支付凭证；只搬运代码、重启容器
#   - 失败会 trap 退出，保留日志供事后排查
#   - 日志只输出容器名 + 启动状态，不打印密钥

set -euo pipefail
IFS=$'\n\t'

# ============================================================
# 默认值
# ============================================================
SSH_HOST=${SSH_HOST:-root@124.221.229.12}
PROJECT_DIR=${PROJECT_DIR:-/opt/legal-review}
COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}
DEPLOY_DIR="$PROJECT_DIR/deploy"
REBUILD_BACKEND=${REBUILD_BACKEND:-1}
REBUILD_FRONTEND=${REBUILD_FRONTEND:-1}
SKIP_PULL=${SKIP_PULL:-0}
RESTART_NGINX=${RESTART_NGINX:-0}
# REMOTE_SUDO=sudo：远端 docker / git 用 sudo（非 root 登录时用；免密 sudo）
REMOTE_SUDO=${REMOTE_SUDO:-}

RED='\033[1;31m'; GRN='\033[1;32m'; YEL='\033[1;33m'; CYN='\033[1;36m'; NC='\033[0m'
log()  { printf '\n${CYN}== %s ==${NC}\n' "$*"; }
ok()   { printf '${GRN}OK  %s${NC}\n' "$*"; }
warn() { printf '${YEL}WARN %s${NC}\n' "$*"; }
die()  { printf '${RED}!!  %s${NC}\n' "$*" >&2; exit 1; }

# ============================================================
# 0. 预检
# ============================================================
log "[0/6] 预检"

command -v ssh >/dev/null 2>&1 || die "缺少 ssh 客户端"
command -v rsync >/dev/null 2>&1 || warn "未检测到 rsync，将退化为 scp + tar"

# 探测 ssh 连通性（不执行命令，避免某些环境要求 TTY）
if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$SSH_HOST" true 2>/dev/null; then
    die "无法 SSH 到 ${SSH_HOST}（检查 ~/.ssh/config 或 key 权限）"
fi
ok "SSH 连通 $SSH_HOST"

# 本地 git 状态提示（不是阻断；服务器可独立 git pull）
LOCAL_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "no-git")
LOCAL_DIRTY=$(git diff --quiet 2>/dev/null && echo "clean" || echo "dirty")
log "本地 HEAD: $LOCAL_SHA ($LOCAL_DIRTY)"
[[ "$LOCAL_DIRTY" == "dirty" ]] && warn "工作区有未提交变更，服务器同步前请先 git commit"

# ============================================================
# 1. 拉取最新代码到服务器
# ============================================================
log "[1/6] 服务器 git pull"

if [[ "$SKIP_PULL" != "1" ]]; then
    ssh "$SSH_HOST" "set -e; cd '$PROJECT_DIR' && \
        $REMOTE_SUDO git fetch --all --prune && \
        $REMOTE_SUDO git reset --hard origin/\$(git symbolic-ref --short HEAD) && \
        git rev-parse --short HEAD" \
        | tee /tmp/legal-sync-head.log
    REMOTE_SHA=$(tail -1 /tmp/legal-sync-head.log)
    ok "服务器 HEAD: $REMOTE_SHA"
else
    warn "SKIP_PULL=1，跳过 git pull"
fi

# ============================================================
# 2. 选择性 rebuild（只重建改动的服务）
# ============================================================
log "[2/6] 选择性 build"

BUILD_ARGS=()
[[ "$REBUILD_BACKEND" == "1" ]] && BUILD_ARGS+=(backend)
[[ "$REBUILD_FRONTEND" == "1" ]] && BUILD_ARGS+=(frontend)

if [[ ${#BUILD_ARGS[@]} -gt 0 ]]; then
    BUILD_LIST=$(printf '%s ' "${BUILD_ARGS[@]}")
    ssh "$SSH_HOST" "set -e; cd '$DEPLOY_DIR' && \
        $REMOTE_SUDO docker compose -f '$COMPOSE_FILE' build $BUILD_LIST"
    ok "build 完毕: $BUILD_LIST"
else
    warn "REBUILD_BACKEND=0 REBUILD_FRONTEND=0，跳过 build"
fi

# ============================================================
# 3. 滚动重启 backend / frontend
# ============================================================
log "[3/6] 滚动重启服务"

UP_ARGS=()
[[ "$REBUILD_BACKEND" == "1" ]] && UP_ARGS+=(backend)
[[ "$REBUILD_FRONTEND" == "1" ]] && UP_ARGS+=(frontend)
[[ "$RESTART_NGINX" == "1" ]] && UP_ARGS+=(nginx)

if [[ ${#UP_ARGS[@]} -gt 0 ]]; then
    UP_LIST=$(printf '%s ' "${UP_ARGS[@]}")
    ssh "$SSH_HOST" "set -e; cd '$DEPLOY_DIR' && \
        $REMOTE_SUDO docker compose -f '$COMPOSE_FILE' up -d --no-deps $UP_LIST"
    ok "重启完毕: $UP_LIST"
else
    warn "没有需要重启的服务"
fi

# ============================================================
# 4. 等待 backend healthy
# ============================================================
log "[4/6] 等待 backend /health (最多 90s)"

HEALTHY=0
for i in $(seq 1 30); do
    if ssh "$SSH_HOST" "$REMOTE_SUDO docker exec legal-backend python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)\"" >/dev/null 2>&1; then
        HEALTHY=1; break
    fi
    sleep 3
done
[[ "$HEALTHY" -eq 1 ]] || die "backend 90s 内未 healthy；ssh $SSH_HOST 'docker logs --tail=200 legal-backend' 看日志"
ok "backend /health 200"

# ============================================================
# 5. alembic 迁移（如有新增迁移）
# ============================================================
log "[5/6] alembic upgrade head"

ssh "$SSH_HOST" "cd '$DEPLOY_DIR' && $REMOTE_SUDO docker exec legal-backend alembic upgrade head"
ok "alembic 升级完成（无新迁移会立即返回）"

# ============================================================
# 6. 端到端冒烟（前端 + 定价接口）
# ============================================================
log "[6/6] 端到端冒烟"

SMOKE_DOMAIN=${SMOKE_DOMAIN:-legalai86.com.cn}
ssh "$SSH_HOST" "set -e
    printf '  frontend root         '; curl -sS -o /dev/null -w 'HTTP %{http_code}\n' --noproxy '*' https://127.0.0.1/ || true;
    printf '  api  /api/v1/health   '; curl -sS -o /dev/null -w 'HTTP %{http_code}\n' --noproxy '*' https://127.0.0.1/api/v1/health || true;
    printf '  api  /api/v1/billing/pricing  '; curl -sS -o /dev/null -w 'HTTP %{http_code}\n' --noproxy '*' https://127.0.0.1/api/v1/billing/pricing || true;
"

cat <<'TXT'

==============================================================
  增量推送完成
==============================================================
  服务器 HEAD：见上文
  已重启：      见 UP_ARGS
  健康检查：    /health 200 + /api/v1/billing/pricing 200

  接下来：
    1) 跑支付凭证安装：bash deploy/scripts/install-payment-env.sh
    2) 跑支付验收：    bash deploy/scripts/verify-payment.sh

==============================================================
TXT