#!/usr/bin/env bash
# legalai86.com.cn 数据库定时备份脚本
#
# 行为：
#   - pg_dump 自定义格式（-F c），压缩 + 可选表恢复
#   - 保留 30 天本地备份 + 上传腾讯云 COS（如果配了）
#   - 写日志到 /var/log/legal-backup.log
#
# 部署：
#   sudo install -m 755 backup_pg.sh /opt/legal-review/deploy/scripts/backup_pg.sh
#   sudo install -m 600 .env /etc/legal-backup.env
#   echo "0 2 * * * root COS_BUCKET=... /opt/legal-review/deploy/scripts/backup_pg.sh" \
#       | sudo tee /etc/cron.d/legal-backup

set -euo pipefail
IFS=$'\n\t'

BACKUP_DIR=${BACKUP_DIR:-/opt/backup/legalai86}
KEEP_DAYS=${KEEP_DAYS:-30}
COMPOSE_DIR=${COMPOSE_DIR:-/opt/legal-review/deploy}
COMPOSE_FILE=${COMPOSE_FILE:-docker-compose.prod.yml}
TS=$(date +%Y%m%d_%H%M%S)
DATE=$(date +%Y%m%d)

LOG_FILE=${LOG_FILE:-/var/log/legal-backup.log}
log() { printf '[%s] %s\n' "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" "$*" | tee -a "$LOG_FILE"; }

mkdir -p "$BACKUP_DIR"

# 1. 拉取生产 .env 取密码（不依赖当前 shell）
if [[ ! -f "$COMPOSE_DIR/.env" ]]; then
    log "FATAL: 找不到 $COMPOSE_DIR/.env"
    exit 1
fi
set -a
# shellcheck disable=SC1090
source "$COMPOSE_DIR/.env"
set +a
: "${POSTGRES_PASSWORD:?需要 POSTGRES_PASSWORD}"

# 2. 全量 dump（自定义格式，压缩）
log "开始备份..."
DUMP_FILE="$BACKUP_DIR/legal_review_${TS}.dump"
docker exec legal-pg pg_dump -U legal -d legal_review -F c -f /tmp/backup.dump
docker cp legal-pg:/tmp/backup.dump "$DUMP_FILE"
docker exec legal-pg rm -f /tmp/backup.dump

# 3. 也导一份纯 SQL 便于 grep
SQL_FILE="$BACKUP_DIR/legal_review_${TS}.sql"
docker exec legal-pg pg_dump -U legal -d legal_review > "$SQL_FILE"

SIZE=$(du -h "$DUMP_FILE" | cut -f1)
log "备份完成: $DUMP_FILE ($SIZE)"

# 4. 清理 N 天前的本地备份
find "$BACKUP_DIR" -name "legal_review_*.dump" -mtime +"$KEEP_DAYS" -delete
find "$BACKUP_DIR" -name "legal_review_*.sql"  -mtime +"$KEEP_DAYS" -delete
log "已清理 $KEEP_DAYS 天前的旧备份"

# 5. 可选：上传到腾讯云 COS
if [[ -n "${COS_BUCKET:-}" ]] && [[ -n "${COS_SECRET_ID:-}" ]] && [[ -n "${COS_SECRET_KEY:-}" ]] && [[ -n "${COS_REGION:-}" ]]; then
    COSCLI=${COSCLI:-/usr/local/bin/coscli}
    if [[ -x "$COSCLI" ]]; then
        $COSCLI cp "$DUMP_FILE" "cos://$COS_BUCKET/db/legal_review_${TS}.dump" 2>>"$LOG_FILE" \
            && log "已上传到 COS: $COS_BUCKET/db/legal_review_${TS}.dump" \
            || log "WARN: COS 上传失败"
    else
        log "WARN: coscli 未安装 ($COSCLI), 跳过 COS 上传"
    fi
fi

# 6. 上传用户文件（uploads volume 单独备份）
UPLOADS_TAR="$BACKUP_DIR/uploads_${DATE}.tar.gz"
docker run --rm \
    -v legal_backend_uploads:/from:ro \
    -v "$BACKUP_DIR":/to \
    alpine tar czf "/to/uploads_${DATE}.tar.gz" -C /from . 2>>"$LOG_FILE" \
    && log "用户文件备份: $UPLOADS_TAR" \
    || log "WARN: 用户文件备份失败"
find "$BACKUP_DIR" -name "uploads_*.tar.gz" -mtime +"$KEEP_DAYS" -delete

log "备份任务完成"
