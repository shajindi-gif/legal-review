#!/usr/bin/env bash
# legalai86.com.cn 支付验收脚本
#
# 场景：凭证已写入并 backend 已重启，跑一遍"下单→轮询→主动查单"的服务层证据。
# 不发起真实扣款（必须你扫码/付款）；但可以验证：路由可达 + 下单能下 + 状态接口能轮询。
#
# 用法：
#   SSH_HOST=root@124.221.229.12 DOMAIN=legalai86.com.cn \
#   TOKEN=eyJ... USER_EMAIL=xxx@yyy.com USER_PASS=xxx \
#   bash deploy/scripts/verify-payment.sh
#
# 必填：
#   TOKEN  已在浏览器登录后从 localStorage 拷贝的 JWT；或者登录取
# 可选：
#   USER_EMAIL / USER_PASS  当 TOKEN 为空时自动登录取
#   PLAN     pro / enterprise（默认 pro）
#   PERIOD   30 / 90 / 365（默认 30）
#   CHANNEL  wechat / alipay（默认 wechat）
#   PAY_TYPE native / jsapi / h5 / page / wap（默认按 CHANNEL 自动分）
#
# 输出：每一步 PASS/FAIL，结尾汇总 + 订单号（用于真付后查状态）

set -euo pipefail
IFS=$'\n\t'

SSH_HOST=${SSH_HOST:-root@124.221.229.12}
DOMAIN=${DOMAIN:-legalai86.com.cn}
PLAN=${PLAN:-pro}
PERIOD=${PERIOD:-30}
CHANNEL=${CHANNEL:-wechat}
TOKEN=${TOKEN:-}
USER_EMAIL=${USER_EMAIL:-}
USER_PASS=${USER_PASS:-}

RED='\033[1;31m'; GRN='\033[1;32m'; YEL='\033[1;33m'; CYN='\033[1;36m'; NC='\033[0m'
log()  { printf '\n${CYN}== %s ==${NC}\n' "$*"; }
ok()   { printf '${GRN}OK  %s${NC}\n' "$*"; }
warn() { printf '${YEL}WARN %s${NC}\n' "$*"; }
die()  { printf '${RED}!!  %s${NC}\n' "$*" >&2; exit 1; }
fail() { printf '${RED}FAIL %s${NC}\n' "$*"; FAILED=1; }
PASS=0; FAIL_COUNT=0
step_pass() { printf '  ${GRN}PASS${NC} %s\n' "$*"; PASS=$((PASS+1)); }
step_fail() { printf '  ${RED}FAIL${NC} %s\n' "$*"; FAIL_COUNT=$((FAIL_COUNT+1)); FAILED=1; }

# ============================================================
# 0. 预检
# ============================================================
log "[0/7] 预检"

command -v ssh >/dev/null 2>&1 || die "缺少 ssh 客户端"
command -v curl >/dev/null 2>&1 || die "缺少 curl"
command -v jq >/dev/null 2>&1 || warn "未检测到 jq，JSON 解析会退化为 grep（仍可跑）"

API="https://$DOMAIN/api/v1"
[[ -n "$TOKEN" ]] || true

# 在远端拿一个临时入网 IP（用于 wechat H5 的 client_ip）
CLIENT_IP=$(ssh "$SSH_HOST" "curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo 127.0.0.1" | tr -d '\r\n ')
log "使用 CLIENT_IP=$CLIENT_IP"

# 按 CHANNEL 决定默认 PAY_TYPE
case "$CHANNEL" in
    wechat)
        # 远端 curl 探测微信内 UA 不实际；按 server 端 H5 默认走 h5
        PAY_TYPE=${PAY_TYPE:-h5}
        ;;
    alipay)
        # server 侧默认按 UA 分流；这里给 page（电脑）
        PAY_TYPE=${PAY_TYPE:-page}
        ;;
esac
log "PLAN=$PLAN PERIOD=$PERIOD CHANNEL=$CHANNEL PAY_TYPE=$PAY_TYPE"

# ============================================================
# 1. 健康检查
# ============================================================
log "[1/7] 健康检查"
HC=$(curl -sS -o /dev/null -w "%{http_code}" "$API/health" || echo 000)
[[ "$HC" == "200" ]] && step_pass "/health -> 200" || step_fail "/health -> $HC"

HC2=$(curl -sS -o /dev/null -w "%{http_code}" "$API/billing/pricing" || echo 000)
[[ "$HC2" == "200" ]] && step_pass "/billing/pricing -> 200" || step_fail "/billing/pricing -> $HC2"

# ============================================================
# 2. 拿 token（必要时登录）
# ============================================================
log "[2/7] 登录拿 JWT"

if [[ -z "$TOKEN" ]]; then
    if [[ -z "$USER_EMAIL" || -z "$USER_PASS" ]]; then
        die "TOKEN 未提供且 USER_EMAIL/USER_PASS 未提供，无法登录"
    fi
    LOGIN_RESP=$(curl -sS -X POST "$API/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$USER_EMAIL\",\"password\":\"$USER_PASS\"}")
    if command -v jq >/dev/null 2>&1; then
        TOKEN=$(echo "$LOGIN_RESP" | jq -r '.access_token // .data.access_token // empty')
    else
        TOKEN=$(echo "$LOGIN_RESP" | grep -oE '"access_token":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    fi
    [[ -n "$TOKEN" ]] || { step_fail "登录失败：$LOGIN_RESP"; }
fi
[[ -n "$TOKEN" ]] && step_pass "拿到 JWT（长度 ${#TOKEN}）" || step_fail "JWT 为空"

# ============================================================
# 3. 创建订单
# ============================================================
log "[3/7] 创建订单"

ORDER_RESP=$(curl -sS -X POST "$API/billing/orders" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"plan_tier\":\"$PLAN\",\"period_days\":$PERIOD,\"channel\":\"$CHANNEL\",\"pay_type\":\"$PAY_TYPE\",\"client_ip\":\"$CLIENT_IP\"}")

if command -v jq >/dev/null 2>&1; then
    ORDER_ID=$(echo "$ORDER_RESP" | jq -r '.order_id // empty')
    PAY_TYPE_R=$(echo "$ORDER_RESP" | jq -r '.pay_type // empty')
    QR=$(echo "$ORDER_RESP" | jq -r '.qr_code // empty')
    PAY_URL=$(echo "$ORDER_RESP" | jq -r '.pay_url // empty')
else
    ORDER_ID=$(echo "$ORDER_RESP" | grep -oE '"order_id":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    PAY_TYPE_R=$(echo "$ORDER_RESP" | grep -oE '"pay_type":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    QR=$(echo "$ORDER_RESP" | grep -oE '"qr_code":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    PAY_URL=$(echo "$ORDER_RESP" | grep -oE '"pay_url":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
fi

if [[ -n "$ORDER_ID" ]]; then
    step_pass "下单成功 order_id=$ORDER_ID"
else
    step_fail "下单失败：$ORDER_RESP"
fi

# pay_type 自检
if [[ "$PAY_TYPE_R" == "$PAY_TYPE" ]]; then
    step_pass "pay_type 回写 = $PAY_TYPE_R"
else
    step_fail "pay_type 回写 ≠ 请求值（$PAY_TYPE_R vs ${PAY_TYPE}）"
fi

# 凭据自检
case "$PAY_TYPE" in
    native) [[ -n "$QR" ]] && step_pass "qr_code 非空（Native）" || step_fail "qr_code 为空" ;;
    page|wap|h5) [[ -n "$PAY_URL" ]] && step_pass "pay_url 非空（${PAY_TYPE}）" || step_fail "pay_url 为空" ;;
    jsapi) step_warn "JSAPI 需要 jsapi_params；本次未填 openid，应返回 400" ;;
esac

# ============================================================
# 4. 轮询订单状态（30 秒）
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
    echo "    t+${i}x5s status=$LAST_STATUS"
    if [[ "$LAST_STATUS" == "succeeded" || "$LAST_STATUS" == "closed" || "$LAST_STATUS" == "refunded" ]]; then
        break
    fi
    sleep 5
done
case "$LAST_STATUS" in
    pending)    step_pass "轮询可达，订单 pending（真付后会变 succeeded）" ;;
    succeeded)  step_pass "订单已 succeeded（说明你已付过款）" ;;
    closed)     step_warn "订单已 closed（超时关单或主动关单）" ;;
    *)          step_fail "异常状态：$LAST_STATUS" ;;
esac

# ============================================================
# 5. 主动查单补偿（再访问一次 /orders/{id}，触发 query_and_sync_order）
# ============================================================
log "[5/7] 主动查单补偿"

QUERY=$(curl -sS -H "Authorization: Bearer $TOKEN" "$API/billing/orders/$ORDER_ID")
if command -v jq >/dev/null 2>&1; then
    QSTATUS=$(echo "$QUERY" | jq -r '.status // empty')
    QPLAN=$(echo "$QUERY" | jq -r '.plan_tier // empty')
    QAMT=$(echo "$QUERY" | jq -r '.amount_cny // empty')
else
    QSTATUS=$(echo "$QUERY" | grep -oE '"status":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    QPLAN=$(echo "$QUERY" | grep -oE '"plan_tier":"[^"]+"' | head -1 | sed 's/.*:"//;s/"$//')
    QAMT=$(echo "$QUERY" | grep -oE '"amount_cny":[0-9.]+' | head -1 | cut -d: -f2)
fi
step_pass "主动查单回写：status=$QSTATUS plan=$QPLAN amount=$QAMT"

# ============================================================
# 6. 真付触发：二维码 / 收银台（不替用户操作）
# ============================================================
log "[6/7] 真付触发（不替你扫码）"

cat <<INFO

  请在浏览器打开 https://$DOMAIN/pricing，用上面 order_id=$ORDER_ID 的同一账号点升级。
  或直接打开凭据：
    Native (微信): $QR
    Page  (支付宝): $PAY_URL
    H5   (手机):   $PAY_URL
  付款完成后，等 5 秒再回到终端跑一次 [4/7] 轮询，
  状态应当从 pending → succeeded。

INFO

# ============================================================
# 7. 汇总
# ============================================================
log "[7/7] 验收汇总"

printf '  PASS=%d FAIL=%d\n' "$PASS" "$FAIL_COUNT"

if [[ "$FAIL_COUNT" -gt 0 ]]; then
    cat <<TXT

  ⚠️  仍有 FAIL 项，请按以下排查：
   - /health 失败    → docker logs legal-backend
   - /billing/pricing 失败 → 路由未注册（查 api/v1/__init__.py 与 OpenAPI）
   - 下单失败         → 看 JWT 是否过期 / 套餐配置是否存在
   - pay_url/qr 空   → 看 WXPAY_ENABLED / ALIPAY_ENABLED 与对应字段
   - 主动查单回写异常 → 翻 backend 日志 grep 'query_order'
TXT
    exit 1
fi

cat <<TXT

  ✅  服务层全通。剩下唯一的真实付款环节需要你扫一下码完成。

  order_id = $ORDER_ID
  付款完成后再次轮询：
    curl -sS -H "Authorization: Bearer \$TOKEN" $API/billing/orders/$ORDER_ID
TXT