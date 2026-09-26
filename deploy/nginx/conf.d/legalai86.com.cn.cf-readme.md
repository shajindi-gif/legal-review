# Cloudflare 接入完成后的 nginx 改动 — legalai86.com.cn
# 作用：让 Cloudflare 边缘节点的反代请求带着真实客户端 IP
#
# 使用方式：
#   1. 用户完成 CF 后台添加 zone、修改 NS、A 记录开启代理（橙色云朵）
#   2. 确认 https://legalai86.com.cn/ 已经返回 server: cloudflare 响应头
#   3. 然后再执行此文件中的变更

# === 需要修改的文件 ===
# /opt/legal-review/deploy/nginx/conf.d/legalai86.com.cn.conf (生产)
# /Users/shajindi/traework/legal-review/deploy/nginx/conf.d/legalai86.com.cn.conf (本地同步)

# === 变更位置 ===
# 在 server { listen 443 ssl; } 块的 server_name 行（line 42）之后，
# 在 ssl_certificate 行之前，插入以下 set_real_ip_from 块：

# ---- begin Cloudflare real IP ----
# Cloudflare 官方 IP 段（参考 https://www.cloudflare.com/ips/）
# v4
set_real_ip_from 173.245.48.0/20;
set_real_ip_from 103.21.244.0/22;
set_real_ip_from 103.22.200.0/22;
set_real_ip_from 103.31.4.0/22;
set_real_ip_from 141.101.64.0/18;
set_real_ip_from 108.162.192.0/18;
set_real_ip_from 190.93.240.0/20;
set_real_ip_from 188.114.96.0/20;
set_real_ip_from 197.234.240.0/22;
set_real_ip_from 198.41.128.0/17;
# Cloudflare 共用 IP 段
set_real_ip_from 162.158.0.0/15;
set_real_ip_from 104.16.0.0/13;
set_real_ip_from 104.24.0.0/14;
set_real_ip_from 172.64.0.0/13;
set_real_ip_from 131.0.72.0/22;
# v6
set_real_ip_from 2400:cb00::/32;
set_real_ip_from 2606:4700::/32;
set_real_ip_from 2803:f800::/32;
set_real_ip_from 2405:b500::/32;
set_real_ip_from 2405:8100::/32;
set_real_ip_from 2a06:98c0::/29;
set_real_ip_from 2c0f:f248::/32;
# CF 会在请求头里带客户端 IP
real_ip_header CF-Connecting-IP;
# ---- end Cloudflare real IP ----

# === 验证方法 ===
# 1. 上传后，docker exec legal-nginx nginx -t
# 2. docker exec legal-nginx nginx -s reload
# 3. 浏览器访问 https://legalai86.com.cn/login（如果后端有日志记录 X-Real-IP）
#    应看到真实客户端 IP（用户的家庭 IP / 手机 IP），不是 CF 节点 IP
# 4. 或者：curl -H "CF-Connecting-IP: 1.2.3.4" https://legalai86.com.cn/health
#    然后看后端日志记录的 IP

# === 风险 ===
# - 在 CF 还没切 NS 时改这个不影响直连（因为客户端不通过 CF，没有 CF-Connecting-IP 头）
#   nginx 会按默认行为取 $remote_addr（直连 IP）
# - CF 切完后，所有外部请求都会带 CF-Connecting-IP 头，nginx 会用该头覆盖 $remote_addr
# - 如果你不希望 CF 代理所有流量，CF 后台可以单独控制子域名
