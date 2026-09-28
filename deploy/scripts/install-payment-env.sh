#!/usr/bin/env bash
# legalai86.com.cn 支付凭证安装脚本
#
# 场景：服务器已经在跑，需要把真实支付凭证写进 deploy/.env（容器注入用），
#       然后只重启 backend 让它生效。
#
# 设计原则（来自 deploy/.env.example 注释 + 项目记忆）：
#   - 私钥绝不进代码/日志/仓库；本脚本只 echo 写入 deploy/.env，密钥长度/前缀统计后丢弃
#   - 仅替换支付相关字段，绝不覆盖 JWT_SECRET / POSTGRES_PASSWORD
#   - 不重启 nginx / frontend / postgres，避免把无关服务打翻
#   - 写入前备份旧 .env 为 deploy/.env.bak-YYYYMMDD-HHMMSS
#
# 用法（在你的本地机器上）：
#   SSH_HOST=root@124.221.229.12 PROJECT_DIR=/opt/legal-review \
#   bash deploy/scripts/install-payment-env.sh
#
# 凭证来源（按变量名匹配，环境变量注入；不写日志）：
#   WXPAY_MCHID / WXPAY_APPID / WXPAY_APPSECRET / WXPAY_API_V3_KEY
#   WXPAY_MCH_SERIAL_NO / WXPAY_MCH_PRIVATE_KEY / WXPAY_PUBLIC_KEY / WXPAY_PUBLIC_KEY_ID
#   ALIPAY_APP_ID / ALIPAY_PRIVATE_KEY / ALIPAY_PUBLIC_KEY
#   WXPAY_ENABLED=true / ALIPAY_ENABLED=true
#
# 注意：
#   - WXPAY_MCH_PRIVATE_KEY / WXPAY_PUBLIC_KEY / ALIPAY_PRIVATE_KEY / ALIPAY_PUBLIC_KEY
#     多行 PEM 必须单行存储（真实换行转字面 \n），与 backend 配置解析约定一致
#   - 建议从本地 .env.payment-template 拷贝，或者用 openssl / 平台下载直接 paste

set -euo pipefail
IFS=$'\n\t'

SSH_HOST=${SSH_HOST:-root@124.221.229.12}
PROJECT_DIR=${PROJECT_DIR:-/opt/legal-review}
DEPLOY_DIR="$PROJECT_DIR/deploy"
ENV_FILE="$DEPLOY_DIR/.env"
# ALIPAY_ONLY=1：跳过 WXPAY_* 全部必填校验（只验 ALIPAY_* 三项）
ALIPAY_ONLY=${ALIPAY_ONLY:-0}

RED='\033[1;31m'; GRN='\033[1;32m'; YEL='\033[1;33m'; CYN='\033[1;36m'; NC='\033[0m'
log()  { printf '\n${CYN}== %s ==${NC}\n' "$*"; }
ok()   { printf '${GRN}OK  %s${NC}\n' "$*"; }
warn() { printf '${YEL}WARN %s${NC}\n' "$*"; }
die()  { printf '${RED}!!  %s${NC}\n' "$*" >&2; exit 1; }

# ============================================================
# 0. 预检
# ============================================================
log "[0/4] 预检"

command -v ssh >/dev/null 2>&1 || die "缺少 ssh 客户端"

# 必填项检查（标量字段；私钥类允许为空，提示缺失）
if [[ "$ALIPAY_ONLY" == "1" ]]; then
    log "ALIPAY_ONLY=1：只校验 ALIPAY_*，跳过全部 WXPAY_*"
    REQUIRED=(ALIPAY_ENABLED ALIPAY_APP_ID ALIPAY_PRIVATE_KEY ALIPAY_PUBLIC_KEY)
else
    REQUIRED=(WXPAY_ENABLED ALIPAY_ENABLED
               WXPAY_MCHID WXPAY_APPID WXPAY_APPSECRET WXPAY_API_V3_KEY
               WXPAY_MCH_SERIAL_NO WXPAY_MCH_PRIVATE_KEY
               WXPAY_PUBLIC_KEY WXPAY_PUBLIC_KEY_ID
               ALIPAY_APP_ID ALIPAY_PRIVATE_KEY ALIPAY_PUBLIC_KEY)
fi
MISSING=()
for k in "${REQUIRED[@]}"; do
    if [[ -z "${!k:-}" ]]; then
        MISSING+=("$k")
    fi
done
if [[ ${#MISSING[@]} -gt 0 ]]; then
    die "缺少环境变量：${MISSING[*]}
请按 deploy/.env.example 末尾的支付字段注入，或参考 docs/PAYMENT_SETUP.md §1.4 / §2.5"
fi

# 私钥格式校验：单行 + 字面 \n 转义（与 backend 解析约定一致）
check_pem_oneline() {
    local k="$1" v="${!1:-}"
    [[ -z "$v" ]] && return 0
    if [[ "$v" == *$'\n'* ]]; then
        die "$k 包含真实换行；请把换行转义为字面 \\n 单行"
    fi
    local n=${#v}
    if [[ $n -lt 100 ]]; then
        die "$k 长度 $n 异常短（应 ≥ 100 字符）"
    fi
}
if [[ "$ALIPAY_ONLY" != "1" ]]; then
    check_pem_oneline WXPAY_MCH_PRIVATE_KEY
    check_pem_oneline WXPAY_PUBLIC_KEY
fi
check_pem_oneline ALIPAY_PRIVATE_KEY
check_pem_oneline ALIPAY_PUBLIC_KEY

ok "凭证格式自检通过（密钥长度仅本地校验，值不上日志）"

# ============================================================
# 1. 备份旧 .env
# ============================================================
log "[1/4] 备份旧 .env"

ssh "$SSH_HOST" "set -e
    if [[ -f '$ENV_FILE' ]]; then
        cp '$ENV_FILE' '$ENV_FILE.bak-\$(date -u +%Y%m%d-%H%M%S)'
        echo '备份完成'
    else
        echo '$ENV_FILE 不存在，将新建'
    fi"
ok "已备份（如存在）"

# ============================================================
# 2. 写入支付字段（用 here-doc + 局部 sed，保证只动支付段）
# ============================================================
log "[2/4] 写入支付字段到 $ENV_FILE"

# 把多行 PEM 转成 .env 单行格式（真实换行 → \n，外面包双引号）
to_env_value() {
    local s="$1"
    s="${s//\\/\\\\}"        # 反斜杠先转义
    s="${s//\"/\\\"}"        # 双引号转义
    s="${s//$'\n'/\\n}"      # 真实换行 → 字面 \n
    printf '"%s"' "$s"
}

WXPAY_ENABLED_E=$(to_env_value "$WXPAY_ENABLED")
WXPAY_MCHID_E=$(to_env_value "$WXPAY_MCHID")
WXPAY_APPID_E=$(to_env_value "$WXPAY_APPID")
WXPAY_APPSECRET_E=$(to_env_value "$WXPAY_APPSECRET")
WXPAY_API_V3_KEY_E=$(to_env_value "$WXPAY_API_V3_KEY")
WXPAY_MCH_SERIAL_NO_E=$(to_env_value "$WXPAY_MCH_SERIAL_NO")
WXPAY_MCH_PRIVATE_KEY_E=$(to_env_value "$WXPAY_MCH_PRIVATE_KEY")
WXPAY_PUBLIC_KEY_E=$(to_env_value "$WXPAY_PUBLIC_KEY")
WXPAY_PUBLIC_KEY_ID_E=$(to_env_value "$WXPAY_PUBLIC_KEY_ID")

ALIPAY_ENABLED_E=$(to_env_value "$ALIPAY_ENABLED")
ALIPAY_APP_ID_E=$(to_env_value "$ALIPAY_APP_ID")
ALIPAY_PRIVATE_KEY_E=$(to_env_value "$ALIPAY_PRIVATE_KEY")
ALIPAY_PUBLIC_KEY_E=$(to_env_value "$ALIPAY_PUBLIC_KEY")

# 在远端：用 python3 做精确合并（保留其他字段不动）
PAYMENT_BLOCK=$(cat <<EOF
# === 支付凭证自动写入于 $(date -u +%Y-%m-%dT%H:%M:%SZ) ===
WXPAY_ENABLED=${WXPAY_ENABLED_E}
WXPAY_MCHID=${WXPAY_MCHID_E}
WXPAY_APPID=${WXPAY_APPID_E}
WXPAY_APPSECRET=${WXPAY_APPSECRET_E}
WXPAY_API_V3_KEY=${WXPAY_API_V3_KEY_E}
WXPAY_MCH_SERIAL_NO=${WXPAY_MCH_SERIAL_NO_E}
WXPAY_MCH_PRIVATE_KEY=${WXPAY_MCH_PRIVATE_KEY_E}
WXPAY_PUBLIC_KEY=${WXPAY_PUBLIC_KEY_E}
WXPAY_PUBLIC_KEY_ID=${WXPAY_PUBLIC_KEY_ID_E}
WXPAY_NOTIFY_PATH=/api/v1/billing/wechat/notify
WXPAY_OAUTH_REDIRECT_URL=https://legalai86.com.cn/api/v1/billing/wechat/oauth/callback

ALIPAY_ENABLED=${ALIPAY_ENABLED_E}
ALIPAY_APP_ID=${ALIPAY_APP_ID_E}
ALIPAY_PRIVATE_KEY=${ALIPAY_PRIVATE_KEY_E}
ALIPAY_PUBLIC_KEY=${ALIPAY_PUBLIC_KEY_E}
ALIPAY_GATEWAY=https://openapi.alipay.com/gateway.do
ALIPAY_NOTIFY_PATH=/api/v1/billing/alipay/notify
ALIPAY_RETURN_URL=https://legalai86.com.cn/pricing
# === 支付凭证结束 ===
EOF
)

# 转义 here-doc 给远端 python：把 ${}、反引号、单双引号妥善处理
PAYMENT_BLOCK_ESC=$(printf '%s' "$PAYMENT_BLOCK" | python3 -c '
import sys, base64
data = sys.stdin.read()
sys.stdout.write(base64.b64encode(data.encode("utf-8")).decode("ascii"))
')

# 把支付字段先 upsert 到 .env（基于 key 名替换/追加；其他字段完全不动）
MERGE_SCRIPT=$(cat <<'PYEOF'
import sys, os, base64, re
env_path = os.environ["ENV_FILE"]
new_b64 = os.environ["PAYMENT_B64"]
new_block = base64.b64decode(new_b64).decode("utf-8")

# 解析 .env：保留所有非支付 key
keep_keys_prefix = ("WXPAY_", "ALIPAY_")
lines = open(env_path, "r", encoding="utf-8").read().splitlines() if os.path.exists(env_path) else []
kept = []
for ln in lines:
    s = ln.strip()
    if not s or s.startswith("#") or "=" not in s:
        kept.append(ln); continue
    k = s.split("=", 1)[0].strip()
    if any(k.startswith(p) for p in keep_keys_prefix):
        continue  # 删除旧支付字段
    kept.append(ln)

# 末尾追加新支付块
out = "\n".join(kept).rstrip("\n") + "\n\n" + new_block
# 强制 600
fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write(out)
print("merged", len(new_block), "chars of payment block")
PYEOF
)

ENV_FILE_B64=$(printf '%s' "$ENV_FILE" | base64)
ssh "$SSH_HOST" "set -e
    export ENV_FILE='$ENV_FILE'
    export PAYMENT_B64='$PAYMENT_BLOCK_ESC'
    python3 - <<'PYEOF_REMOTE'
$MERGE_SCRIPT
PYEOF_REMOTE"
ok "已写入（仅替换 WXPAY_*/ALIPAY_* 字段，其他字段原样保留）"

# ============================================================
# 3. 重启 backend（让它读新 .env）
# ============================================================
log "[3/4] 重启 backend"

ssh "$SSH_HOST" "set -e; cd '$DEPLOY_DIR' && \
    docker compose -f docker-compose.prod.yml up -d --no-deps backend"
ok "backend 已重启"

log "[verify] 等 backend /health（最多 60s）"
HEALTHY=0
for i in $(seq 1 20); do
    if ssh "$SSH_HOST" "docker exec legal-backend python -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=3).status==200 else 1)\"" >/dev/null 2>&1; then
        HEALTHY=1; break
    fi
    sleep 3
done
[[ "$HEALTHY" -eq 1 ]] || die "backend 60s 内未 healthy；ssh $SSH_HOST 'docker logs --tail=200 legal-backend'"
ok "backend /health 200"

cat <<'TXT'

==============================================================
  支付凭证已写入服务器并生效
==============================================================
  ENV_FILE  : deploy/.env（chmod 600，root 独占）
  备份      : deploy/.env.bak-YYYYMMDD-HHMMSS
  已重启    : backend（仅 backend）
  健康检查  : /health 200

  下一步：
    bash deploy/scripts/verify-payment.sh
    在定价页点"升级"，扫二维码付款一次，验闭环

==============================================================
TXT