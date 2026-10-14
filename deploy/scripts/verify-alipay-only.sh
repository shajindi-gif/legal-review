#!/usr/bin/env bash
# legalai86.com.cn 支付宝专用验收脚本（不依赖微信配置）
#
# 场景：只想先接通支付宝商业闭环，微信支付未配置 / WXPAY_* 缺失。
#       流程与 verify-payment.sh 一致，但只校验支付宝（page / wap）+ 后端日志，
#       跳过任何 WXPAY_* 相关必填校验。
#
# 用法：
#   SSH_HOST=root@124.221.229.12 DOMAIN=legalai86.com.cn \
#   TOKEN=$(...) USER_EMAIL=... USER_PASS=... \
#   bash deploy/scripts/verify-alipay-only.sh
#
# 可选：
#   PLAN        pro / enterprise（默认 pro）
#   PERIOD      30 / 90 / 365（默认 30）
#   PAY_TYPE    page / wap（默认 page，对应电脑浏览器）
#   ALIPAY_RETURN_URL 默认 https://$DOMAIN/pricing
#
# 输出：每一步 PASS/FAIL，结尾汇总；并给出「真付后回查日志」的命令

set -euo pipefail
IFS=$'\n\t'

SSH_HOST=${SSH_HOST:-root@124.221.229.12}
DOMAIN=${DOMAIN:-legalai86.com.cn}
PROJECT_DIR=${PROJECT_DIR:-/opt/legal-review}
DEPLOY_DIR="$PROJECT_DIR/deploy"
PLAN=${PLAN:-pro}
PERIOD=${PERIOD:-30}
PAY_TYPE=${PAY_TYPE:-page}
TOKEN=${TOKEN:-}
USER_EMAIL=${USER_EMAIL:-}
USER_PASS=${USER_PASS:-}
ALIPAY_RETURN_URL=${ALIPAY_RETURN_URL:-https://$DOMAIN/pricing}
# REMOTE_SUDO=sudo：远端读 .env / docker 用 sudo（非 root 登录时用）
REMOTE_SUDO=${REMOTE_SUDO:-}

RED='\033[1;31m'; GRN='\033[1;32m'; YEL='\033[1;33m'; CYN='\033[1;36m'; NC='\033[0m'
log()  { printf '\n${CYN}== %s ==${NC}\n' "$*"; }
ok()   { printf '${GRN}OK  %s${NC}\n' "$*"; }
warn() { printf '${YEL}WARN %s${NC}\n' "$*"; }
die()  { printf '${RED}!!  %s${NC}\n' "$*" >&2; exit 1; }
PASS=0; FAIL_COUNT=0
step_pass() { printf '  ${GRN}PASS${NC} %s\n' "$*"; PASS=$((PASS+1)); }
step_fail() { printf '  ${RED}FAIL${NC} %s\n' "$*"; FAIL_COUNT=$((FAIL_COUNT+1)); }

# ============================================================
# 0. 预检
# ============================================================
log "[0/7] 预检（仅校验支付宝）"

command -v ssh >/dev/null 2>&1 || die "缺少 ssh 客户端"
command -v curl >/dev/null 2>&1 || die "缺少 curl"
command -v jq >/dev/null 2>&1 || warn "未装 jq，JSON 解析会退化（仍可跑）"

# 远端读 server 当前 ALIPAY_ENABLED / APP_ID（脱敏只看开关）
REMOTE_FLAG=$(ssh "$SSH_HOST" "set -e; cd '$DEPLOY_DIR' && \
    if [[ -f .env ]]; then
        $REMOTE_SUDO awk -F= '/^ALIPAY_ENABLED=/{v=\$2; gsub(/\"/,\"\",v); print v; exit} /^ALIPAY_APP_ID=/{v=\$2; gsub(/\"/,\"\",v); print v; exit} END {print \"(none)\"}' .env | head -2
    else
        echo '(no .env)'
    fi")
log "服务器 ALIPAY 配置：$REMOTE_FLAG"

API="https://$DOMAIN/api/v1"

# ============================================================
# 1. 健康检查
# ============================================================
log "[1/7] 健康检查"

HC=$(curl -sS -o /dev/null -w "%{http_code}" "https://$DOMAIN/health" || echo 000)
[[ "$HC" == "200" ]] && step_pass "/health -> 200" || step_fail "/health -> $HC"

HC2=$(curl -sS -o /dev/null -w "%{http_code}" "$API/billing/pricing" || echo 000)
[[ "$HC2" == "200" ]] && step_pass "/billing/pricing -> 200" || step_fail "/billing/pricing -> $HC2"

# ============================================================
# 2. 拿 JWT
# ============================================================
log "[2/7] 登录拿 JWT"

if [[ -z "$TOKEN" ]]; then
    [[ -n "$USER_EMAIL" && -n "$USER_PASS" ]] || die "TOKEN 与 USER_EMAIL/USER_PASS 都为空，无法登录"
    LOGIN_RESP=$(curl -sS -X POST "$API/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$USER_EMAIL\",\"password\":\"$USER_PASS\"}")
    if command -v jq >/dev/null 2>&1; then
        TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token // .data.access_token // empty')
    else
        TOKEN=$(echo "$LOGIN_RESP" | grep -oE '"access_token":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    fi
fi
[[ -n "$TOKEN" ]] && step_pass "JWT 长度=${#TOKEN}" || step_fail "JWT 仍为空：$LOGIN_RESP"

# ============================================================
# 3. 创建支付宝订单（pay_type=page/wap）
# ============================================================
log "[3/7] 创建支付宝订单（pay_type=${PAY_TYPE}）"

ORDER_RESP=$(curl -sS -X POST "$API/billing/orders" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"plan_tier\":\"$PLAN\",\"period_days\":$PERIOD,\"channel\":\"alipay\",\"pay_type\":\"$PAY_TYPE\"}")

if command -v jq >/dev/null 2>&1; then
    ORDER_ID=$(echo "$ORDER_RESP" | jq -r '.order_id // empty')
    PAY_TYPE_R=$(echo "$ORDER_RESP" | jq -r '.pay_type // empty')
    PAY_URL=$(echo "$ORDER_RESP" | jq -r '.pay_url // empty')
else
    ORDER_ID=$(echo "$ORDER_RESP" | grep -oE '"order_id":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    PAY_TYPE_R=$(echo "$ORDER_RESP" | grep -oE '"pay_type":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    PAY_URL=$(echo "$ORDER_RESP" | grep -oE '"pay_url":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
fi

if [[ -n "$ORDER_ID" ]]; then
    step_pass "下单成功 order_id=$ORDER_ID"
else
    step_fail "下单失败：$ORDER_RESP"
fi

[[ "$PAY_TYPE_R" == "$PAY_TYPE" ]] && step_pass "pay_type 回写=$PAY_TYPE_R" || step_fail "pay_type 不一致（回写=$PAY_TYPE_R 请求=${PAY_TYPE}）"

if [[ -n "$PAY_URL" ]]; then
    step_pass "pay_url 非空（${#PAY_URL} 字符）"
    # 校验 pay_url 是否为支付宝 gateway（page.pay/wap.pay 必须含 alipay 域名 + sign=）
    if [[ "$PAY_URL" =~ openapi\.alipay\.com ]]; then
        step_pass "pay_url 指向 openapi.alipay.com"
    elif [[ "$PAY_URL" =~ mclient\.alipay\.com ]]; then
        step_pass "pay_url 指向 mclient.alipay.com（wap）"
    else
        warn "pay_url 不在已知支付宝域名内，请人工确认"
    fi
    if [[ "$PAY_URL" == *sign=* ]]; then
        step_pass "pay_url 含 sign=（RSA2 签名已附）"
    else
        step_fail "pay_url 缺 sign=（签名未生成）"
    fi
else
    step_fail "pay_url 为空——可能是 ALIPAY_* 配置未生效或应用未签约 page/wap 产品"
fi

# ============================================================
# 4. 轮询订单状态（最多 30s）
# ============================================================
log "[4/7] 轮询 /orders/{id}（最多 30s）"

LAST_STATUS=""
for i in $(seq 1 6); do
    POLL=$(curl -sS -H "Authorization: Bearer $TOKEN" "$API/billing/orders/$ORDER_ID")
    if command -v jq >/dev/null 2>&1; then
        LAST_STATUS=$(echo "$POLL" | jq -r '.status // empty')
    else
        LAST_STATUS=$(echo "$POLL" | grep -oE '"status":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    fi
    printf '    t+%2ds status=%s\n' $((i*5)) "$LAST_STATUS"
    case "$LAST_STATUS" in
        succeeded|closed|refunded) break ;;
    esac
    sleep 5
done

case "$LAST_STATUS" in
    pending)    step_pass "订单 pending（真付后会变 succeeded）" ;;
    succeeded)  step_pass "订单 succeeded（说明你已付过款）" ;;
    closed)     step_warn "订单已 closed（超时关单或主动关单）" ;;
    *)          step_fail "异常状态：$LAST_STATUS" ;;
esac

# ============================================================
# 5. 主动查单补偿（再访问一次 /orders/{id}）
# ============================================================
log "[5/7] 主动查单补偿"

QUERY=$(curl -sS -H "Authorization: Bearer $TOKEN" "$API/billing/orders/$ORDER_ID")
if command -v jq >/dev/null 2>&1; then
    QSTATUS=$(echo "$QUERY" | jq -r '.status // empty')
    QPLAN=$(echo "$QUERY" | jq -r '.plan_tier // empty')
    QAMT=$(echo "$QUERY" | jq -r '.amount_cny // empty')
else
    QSTATUS=$(echo "$QUERY" | grep -oE '"status":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
fi
step_pass "查单回写 status=$QSTATUS plan=${QPLAN:-?} amount=${QAMT:-?}"

# ============================================================
# 6. 真付触发 + 日志查证（不替你扫码）
# ============================================================
log "[6/7] 真付触发（不替你扫码）"

cat <<INFO

  ✅ 服务层全通。下一步你扫码付款一次完成真实验收。

  order_id   = $ORDER_ID
  pay_url    = $PAY_URL
  return_url = $ALIPAY_RETURN_URL?order_id=$ORDER_ID

  操作步骤：
    1) 在浏览器打开 https://$DOMAIN/pricing 用同一账号登录
    2) 选套餐（$PLAN · $PERIOD 天）→ 支付宝 → 收银台扫码付款
    3) 等 5 秒回到终端跑一次 [4/7] 轮询，状态应: pending → succeeded

  真付后查后端日志：
    ssh $SSH_HOST 'cd $DEPLOY_DIR && docker logs --tail=200 legal-backend 2>&1 | grep -E "payment_(success|fail|verify)"'

INFO

# ============================================================
# 7. 汇总
# ============================================================
log "[7/7] 验收汇总"

printf '  PASS=%d  FAIL=%d\n' "$PASS" "$FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    cat <<TXT

  ⚠️  仍有 FAIL 项排查：
   - /health 失败        → ssh $SSH_HOST 'cd $DEPLOY_DIR && docker logs --tail=200 legal-backend'
   - /billing/pricing 失败 → 检查 backend api 路由注册（api/v1/__init__.py）
   - 下单 401/403        → JWT 过期；重跑登录拿新 token
   - pay_url 为空 / 无 sign → 检查 ALIPAY_* 三项是否完整；应用是否签约 page/wap 产品
TXT
    exit 1
fi

cat <<TXT

  ✅  支付宝服务层已通。真实付款环节由你扫码完成。

  订单号（用于查证）: $ORDER_ID

  验收完成后建议清理测试订单：
    ssh $SSH_HOST "cd $DEPLOY_DIR && docker exec legal-backend python -c 'from app.db import database; ...'"

TXT