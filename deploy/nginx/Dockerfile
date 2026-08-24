FROM nginx:1.27-alpine
RUN sed -i 's#dl-cdn.alpinelinux.org#mirrors.tencentyun.com#g' /etc/apk/repositories && \
    apk add --no-cache bash certbot certbot-nginx
COPY conf.d /etc/nginx/conf.d
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
