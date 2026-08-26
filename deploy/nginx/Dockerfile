# Nginx + certbot 镜像（基于 alpine）
#
# 容器内包含：
#   - nginx 1.27（主服务，反代 + HTTPS）
#   - certbot（webroot 模式签发 Let's Encrypt）
#   - bash（部署 / 续期脚本用）
#
# 注意：certbot 自动续期由 deploy.sh 启动时的 docker compose --profile certbot 容器
# 完成（独立于本镜像）。本镜像不内置续期进程，避免重复。

FROM nginx:1.27-alpine

# 换源到腾讯云 alpine 镜像
RUN sed -i 's#dl-cdn.alpinelinux.org#mirrors.tencentyun.com#g' \
        /etc/apk/repositories

# 装 bash + inotify-tools + wget（监控证书变更触发 nginx reload；wget 供健康检查）
# 续期由独立 certbot 容器完成；本容器只负责反代 + 证书变更自动 reload
RUN apk add --no-cache bash inotify-tools wget

# 站点配置（conf.d 由 docker-compose 挂载进来，本文件不留默认站点）
RUN rm -f /etc/nginx/conf.d/default.conf

# 证书变更自动 reload（轻量级 watch）
# 监听 /etc/letsencrypt/live/<domain>/fullchain.pem 变更触发 nginx -s reload
RUN mkdir -p /docker-entrypoint.d
COPY reload-on-cert-change.sh /docker-entrypoint.d/reload-on-cert-change.sh
RUN chmod +x /docker-entrypoint.d/reload-on-cert-change.sh

# 健康检查：HTTPS 自检（HTTP 80 会 301 跳转 HTTPS，跟随时证书 host 校验失败，故直接打 443）
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget -q --no-check-certificate --spider https://127.0.0.1/ || exit 1

EXPOSE 80 443

# 启动 nginx + 证书 watch 后台进程
CMD ["sh", "-c", "nginx -g 'daemon off;' & /docker-entrypoint.d/reload-on-cert-change.sh & wait"]
