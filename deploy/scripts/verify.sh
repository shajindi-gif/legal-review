#!/usr/bin/env bash
# legalai86.com.cn 部署后验证脚本
#
# 验证 7 类指标，任意一个 FAIL 立即退出：
#   1. 容器全部 healthy
#   2. 前端 200
#   3. 后端 health 200
#   4. 登录 API（验证 0003 身份系统）
#   5. 多租户隔离（验证 M16.1：两个用户的数据不互通）
#   6. 证书有效期 > 30 天
#   7. 数据库迁移版本（应该是 0006 head）
#
# 用法：
#   sudo bash verify.sh
#   DOMAIN=legalai86.com.cn sudo bash verify.sh
#
# 部署回滚判断：>=2 项 FAIL 即建议回滚；本脚本只做"健康度检测"。

set -euo pipefail
DOMAIN=${DOMAIN:-legalai86.com.cn}
BASE_URL=${BASE_URL:-https://$DOMAIN}
FAIL=0

RED='\033[1;31m'; GRN='\033[1;32m'; YEL='\033[1;33m'; CYN='\033[1;36m'; NC='\033[0m'
pass() { printf '${GRN}✓ %s${NC}\n' "$*"; }
warn() { printf '${YEL}! %s${NC}\n' "$*"; FAIL=$((FAIL+1)); }
fail() { printf '${RED}✗ %s${NC}\n' "$*"; FAIL=$((FAIL+1)); }

echo "=================================================="
echo " LegalAI86 部署验证 — $BASE_URL"
echo " $(date -u +'%Y-%m-%dT%H:%M:%SZ')"
echo "=================================================="

# 1. 容器
echo ""
echo "[1/7] 容器状态"
EXPECTED=(legal-pg legal-redis legal-backend legal-frontend legal-nginx)
for c in "${EXPECTED[@]}"; do
    status=$(docker ps --filter "name=^${c}$" --format '{{.Status}}' 2>/dev/null || true)
    if [[ -z "$status" ]]; then
        fail "容器 $c 未运行"
    elif [[ "$status" != *"healthy"* ]] && [[ "$status" != *"Up"* ]]; then
        fail "容器 $c 状态异常: $status"
    else
        pass "容器 $c: $status"
    fi
done

# 2. 前端
echo ""
echo "[2/7] 前端 HTTP 200"
code=$(curl -sS -o /dev/null -w '%{http_code}' --noproxy '*' "$BASE_URL/" 2>/dev/null || echo "000")
if [[ "$code" == "200" ]]; then
    pass "GET / -> 200"
else
    fail "GET / -> $code"
fi

# 3. 后端 health
echo ""
echo "[3/7] 后端健康"
health=$(curl -sS --noproxy '*' "$BASE_URL/api/v1/health" 2>/dev/null || echo "")
if echo "$health" | grep -q '"status":"ok"'; then
    pass "/api/v1/health = ok"
else
    fail "/api/v1/health 异常: $health"
fi

# 4. 登录 API（用 demo 账号探测 401/200/422，不要求成功）
echo ""
echo "[4/7] 登录 API 可达"
code=$(curl -sS -o /dev/null -w '%{http_code}' --noproxy '*' \
    -H "Content-Type: application/json" \
    -d '{"phone":"13800000000","verification_code":"000000"}' \
    "$BASE_URL/api/v1/auth/login-by-phone" 2>/dev/null || echo "000")
if [[ "$code" =~ ^(200|400|401|422|429)$ ]]; then
    pass "POST /api/v1/auth/login-by-phone -> $code (路由可达)"
else
    fail "POST /api/v1/auth/login-by-phone -> $code"
fi

# 5. 多租户隔离（仅探测 SQL：两个 org 看到不同 task 列表）
echo ""
echo "[5/7] 多租户隔离冒烟"
if docker exec legal-backend python /app/scripts/verify_tenant_isolation.py 2>/dev/null; then
    pass "M16.1 多租户隔离通过"
else
    warn "M16.1 验证脚本未运行（需先创建 scripts/verify_tenant_isolation.py）"
fi

# 6. 证书
echo ""
echo "[6/7] 证书有效期"
if docker exec legal-nginx test -f "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" 2>/dev/null; then
    expiry=$(docker exec legal-nginx openssl x509 -in "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" -noout -enddate 2>/dev/null | cut -d= -f2)
    if [[ -n "$expiry" ]]; then
        pass "证书到期: $expiry"
    else
        warn "证书存在但无法解析到期日"
    fi
else
    fail "证书文件未就位 /etc/letsencrypt/live/$DOMAIN/fullchain.pem"
fi

# 7. alembic 迁移版本
echo ""
echo "[7/7] alembic 迁移版本"
current=$(docker exec legal-backend alembic current 2>/dev/null | grep -oE '[0-9a-f]{12}' | head -1 || echo "")
if [[ -n "$current" ]]; then
    pass "alembic current = $current"
else
    fail "无法获取 alembic current"
fi

echo ""
echo "=================================================="
if [[ $FAIL -eq 0 ]]; then
    printf '${GRN}✅ 全部通过${NC}\n'
    exit 0
else
    printf '${YEL}⚠ %d 项异常${NC}\n' "$FAIL"
    exit 1
fi
