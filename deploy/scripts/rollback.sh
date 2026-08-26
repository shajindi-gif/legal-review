#!/usr/bin/env bash
# legalai86.com.cn 一键回滚脚本
#
# 三种回滚粒度：
#   --migration  回滚最近一次 alembic 迁移（推荐，仅 DB 变更）
#   --image      回滚到上一个 docker image tag（推荐，全栈回滚）
#   --full       全栈回滚：image + migration + 清理非法数据
#
# 用法：
#   sudo bash rollback.sh --migration
#   sudo bash rollback.sh --image
#   sudo bash rollback.sh --full
#
# 适用场景：
#   1. 0006 迁移后生产出现 organization_id NULL / FK 违反
#   2. 部署了 broken image（启动 crash / 5xx 大量）
#   3. M16.1 多租户逻辑导致数据串租（极严重）

set -euo pipefail
IFS=$'\n\t'

COMPOSE_DIR=${COMPOSE_DIR:-/opt/legal-review/deploy}
COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}
BACKUP_DIR=${BACKUP_DIR:-/opt/backup/legalai86}
TS=$(date +%Y%m%d_%H%M%S)

RED='\033[1;31m'; GRN='\033[1;32m'; YEL='\033[1;33m'; CYN='\033[1;36m'; NC='\033[0m'
log() { printf '\n${CYN}== %s ==${NC}\n' "$*"; }
ok()  { printf '${GRN}OK %s${NC}\n' "$*"; }
warn(){ printf '${YEL}WARN %s${NC}\n' "$*"; }
die() { printf '${RED}!! %s${NC}\n' "$*" >&2; exit 1; }

[[ $(id -u) -eq 0 ]] || die "请用 root 跑: sudo bash $0"
[[ -d "$COMPOSE_DIR" ]] || die "找不到 $COMPOSE_DIR"

cd "$COMPOSE_DIR"

# 解析参数
MODE=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --migration) MODE=migration; shift ;;
        --image)     MODE=image; shift ;;
        --full)      MODE=full; shift ;;
        *) die "未知参数: $1" ;;
    esac
done
[[ -n "$MODE" ]] || die "用法: $0 --migration | --image | --full"

# ==========================
# 0. 强制备份（任何回滚前都做）
# ==========================
log "[0/3] 强制备份当前状态"
mkdir -p "$BACKUP_DIR"
docker exec legal-pg pg_dump -U legal -d legal_review -F c -f /tmp/pre_rollback.dump
docker cp legal-pg:/tmp/pre_rollback.dump "$BACKUP_DIR/pre_rollback_${TS}.dump"
docker exec legal-pg rm -f /tmp/pre_rollback.dump
ok "已备份到 $BACKUP_DIR/pre_rollback_${TS}.dump"

# ==========================
# 1. Migration 回滚
# ==========================
if [[ "$MODE" == "migration" ]] || [[ "$MODE" == "full" ]]; then
    log "[1/3] alembic downgrade -1（最近一次迁移）"
    docker exec legal-backend alembic current
    docker exec legal-backend alembic downgrade -1
    ok "已回滚 migration"

    if [[ "$MODE" == "full" ]]; then
        log "    full 模式：清掉 organization_id 残余列（手动 SQL）"
        warn "回滚后如需彻底移除 organization_id 列，请人工连 DB 跑："
        warn "  ALTER TABLE review_tasks DROP COLUMN organization_id;"
        warn "  ALTER TABLE documents DROP COLUMN organization_id;"
        warn "  ALTER TABLE review_results DROP COLUMN organization_id;"
        warn "  ALTER TABLE agent_logs DROP COLUMN organization_id;"
        warn "  ALTER TABLE notifications DROP COLUMN organization_id;"
        warn "  ALTER TABLE user_feedback DROP COLUMN organization_id;"
    fi
fi

# ==========================
# 2. Image 回滚
# ==========================
if [[ "$MODE" == "image" ]] || [[ "$MODE" == "full" ]]; then
    log "[2/3] 回滚 docker image"

    # 列出 backend 历史镜像
    echo "    现有 backend 镜像："
    docker images legal-review/backend --format '  {{.Tag}}  {{.CreatedAt}}'

    # 默认回滚到上一个 tag
    TARGET=${ROLLBACK_TAG:-}
    if [[ -z "$TARGET" ]]; then
        TARGET=$(docker images legal-review/backend --format '{{.Tag}}' | grep -v latest | head -1)
        [[ -n "$TARGET" ]] || die "找不到可回滚的镜像 tag，请用 ROLLBACK_TAG=v1.2.3 显式指定"
        warn "未指定 ROLLBACK_TAG，自动选 $TARGET"
    fi

    log "    回滚到 tag=$TARGET"
    BACKEND_TAG=$TARGET FRONTEND_TAG=$TARGET \
        docker compose -f "$COMPOSE_FILE" up -d --no-deps --force-recreate backend frontend
    ok "backend / frontend 已回滚"

    log "    等待 backend /health ..."
    HEALTHY=0
    for i in $(seq 1 30); do
        if docker exec legal-backend curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
            HEALTHY=1; break
        fi
        sleep 2
    done
    [[ "$HEALTHY" -eq 1 ]] || die "回滚后 backend 60s 内未 healthy"
    ok "backend /health 200"
fi

# ==========================
# 3. 重启 + 验证
# ==========================
log "[3/3] 重启 + 验证"
docker compose -f "$COMPOSE_FILE" restart
sleep 5

if [[ -x ./scripts/verify.sh ]]; then
    log "    跑 verify.sh ..."
    if bash ./scripts/verify.sh; then
        ok "verify.sh 通过"
    else
        warn "verify.sh 仍有 FAIL，请人工排查"
    fi
else
    warn "找不到 scripts/verify.sh，跳过验证"
fi

log "回滚完成"
echo ""
echo "  备份保留: $BACKUP_DIR/pre_rollback_${TS}.dump"
echo "  恢复命令: docker exec -i legal-pg pg_restore -U legal -d legal_review --clean < $BACKUP_DIR/pre_rollback_${TS}.dump"
