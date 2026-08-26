#!/bin/sh
# /docker-entrypoint.d/reload-on-cert-change.sh
#
# 监听 Let's Encrypt 证书变更，触发 nginx -s reload
# 由独立 certbot 容器（profile=certbot）续期
# 这里只做"看见证书换了就 reload nginx"的副作用
#
# 设计：
#   - 启动后等 nginx 主进程就绪
#   - inotifywait 监控 /etc/letsencrypt/live/legalai86.com.cn/fullchain.pem
#   - 任何 modify / create / move 事件触发 nginx -s reload
#   - 每 6h 兜底 reload 一次（防御 inotify 漏事件）

set -e

CERT_DIR="/etc/letsencrypt/live/legalai86.com.cn"
CERT_FILE="${CERT_DIR}/fullchain.pem"
RELOAD_EVERY="21600"  # 6h

log() { printf '[reload-watch] %s\n' "$*"; }

# 等待证书首次就位（最长 5 分钟）
log "等待证书就位 $CERT_FILE ..."
i=0
while [ ! -f "$CERT_FILE" ] && [ $i -lt 60 ]; do
    sleep 5
    i=$((i + 1))
done
if [ ! -f "$CERT_FILE" ]; then
    log "WARN: 证书 5 分钟内未就位，watch 启动但不触发 reload（首次 deploy 后请手动 certbot 申请）"
else
    log "证书就位: $CERT_FILE"
fi

# 兜底定时 reload
(
    while :; do
        sleep "$RELOAD_EVERY"
        log "兜底 reload (每 ${RELOAD_EVERY}s)"
        nginx -s reload 2>/dev/null || log "reload 失败（nginx 未就绪？）"
    done
) &

# inotify 触发 reload
if command -v inotifywait >/dev/null 2>&1; then
    log "启动 inotifywait 监控 $CERT_DIR"
    inotifywait -m -e modify -e create -e moved_to \
        --format '%f %e' "$CERT_DIR" 2>/dev/null \
    | while read -r FILE EVENT; do
        log "检测到证书变更: $FILE $EVENT"
        sleep 2  # 等 certbot 写完
        nginx -s reload 2>/dev/null || log "reload 失败"
    done
else
    log "WARN: inotifywait 不可用，仅靠兜底定时 reload"
    while :; do sleep 3600; done
fi
