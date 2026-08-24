FROM nginx:1.27-alpine
RUN apk add --no-cache bash certbot certbot-nginx
COPY conf.d /etc/nginx/conf.d
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
