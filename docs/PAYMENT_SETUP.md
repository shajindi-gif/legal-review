# 支付接入配置指引（Sprint 8.2）

本文档指导如何在微信商户平台 + 支付宝开放平台完成配置，使 `legalai86.com.cn` 能接收微信支付和支付宝付款。

> 支付实现已完成改造，支持三端分流与主动查单补偿。关键结论（来自《支付闭环标准操作手册》）：
> 1. 支付宝纯线上网站签约 **电脑网站支付 + 手机网站支付**，**不要签「当面付」**（需门店资质，会卡死）。
> 2. 微信三端分流：电脑 Native 扫码、微信内 JSAPI、手机浏览器 H5。
> 3. 回调可能不来，**主动查单补偿**是标配；pending 订单超 2h **自动关单**；回调/查单/发权益共用同一原子核销防双发。

---

## 前置条件

- [x] 公司已注册（营业执照）
- [x] 对公银行账户已开立
- [x] 域名 `legalai86.com.cn` 已完成 ICP 备案（沪ICP备2026045851号-4）
- [x] 服务器公网 IP `124.221.229.12` 已绑定域名
- [x] HTTPS 证书已配置（Let's Encrypt 或 Cloudflare）

---

## 一、微信支付 V3（Native / JSAPI / H5 三端分流）

### 1.1 开通产品

1. 登录 [微信商户平台](https://pay.weixin.qq.com)
2. 进入 **产品中心** → **我的产品**
3. 依次申请开通 **Native 支付** / **JSAPI 支付** / **H5 支付**（按需要）
4. 填写应用场景说明（示例）：
   > "法律审查 SaaS 平台，用户购买专业版/企业版套餐时通过微信扫码/公众号内/H5 支付，支付成功后自动开通套餐权限。"
5. 等待审核（通常 1-3 个工作日）

### 1.2 配置 API 安全

1. 进入 **账户中心** → **API 安全**
2. **设置 APIv3 密钥**（32 字符，`openssl rand -hex 16`）→ `WXPAY_API_V3_KEY`
3. **申请商户 API 证书** → 得到 `apiclient_key.pem`（私钥，请求签名用）→ `WXPAY_MCH_PRIVATE_KEY`；证书序列号 → `WXPAY_MCH_SERIAL_NO`
4. **获取微信支付公钥**（新商户验签回调用，无平台证书）：
   - 进入 **账户中心** → **API 安全** → **微信支付公钥**
   - 记录公钥全文 → `WXPAY_PUBLIC_KEY`
   - 记录公钥 ID（`PUB_KEY_ID_xxx`）→ `WXPAY_PUBLIC_KEY_ID`
5. 公众号（服务号）AppID/AppSecret → `WXPAY_APPID` / `WXPAY_APPSECRET`（JSAPI 静默 OAuth 换 openid 用）

> 重要：回调验签用「微信支付公钥」（`WXPAY_PUBLIC_KEY` + `WXPAY_PUBLIC_KEY_ID`），
> **不是**商户自己的 `apiclient` 证书。`/v3/certificates` 对新商户返回 404 属正常。

### 1.3 配置回调 URL 与授权域名

1. 进入各支付产品 → **开发配置**
2. **支付回调 URL** 一律填写：
   ```
   https://legalai86.com.cn/api/v1/billing/wechat/notify
   ```
3. JSAPI **网页授权域名** 填写：`legalai86.com.cn`（与 `WXPAY_OAUTH_REDIRECT_URL` 一致）

### 1.4 填写环境变量

```bash
# .env.local
WXPAY_ENABLED=true
WXPAY_MCHID=1234567890
WXPAY_APPID=wx1234567890abcdef
WXPAY_APPSECRET=your_appsecret
WXPAY_API_V3_KEY=your_32_char_api_v3_key_here
WXPAY_MCH_SERIAL_NO=ABCDEF1234567890ABCDEF1234567890ABCDEF12
WXPAY_MCH_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
WXPAY_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
WXPAY_PUBLIC_KEY_ID=PUB_KEY_ID_0123456789
WXPAY_OAUTH_REDIRECT_URL=https://legalai86.com.cn/api/v1/billing/wechat/oauth/callback
WXPAY_NOTIFY_PATH=/api/v1/billing/wechat/notify
```

### 1.5 验证配置

```bash
# 测试 Native 下单（返回 code_url 二维码）
curl -X POST http://localhost:8002/api/v1/billing/orders \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"plan_tier":"pro","period_days":30,"channel":"wechat","pay_type":"native"}'

# 预期返回：pay_type=native 且 qr_code=weixin://wxpay/...
# H5：pay_type=h5 且 pay_url=https://wx.tenpay.com/...
# JSAPI：pay_type=jsapi 且 jsapi_params 含 appId/timeStamp/nonceStr/package/paySign（需先 OAuth 拿 openid）
```

---

## 二、支付宝（电脑网站页面支付 page.pay / 手机网站支付 wap.pay）

### 2.1 创建应用

1. 登录 [支付宝开放平台](https://open.alipay.com)
2. 进入 **控制台** → **网页/移动应用** → **创建应用**
3. 应用名称：`法律审查 SaaS 平台`，应用类型：**网页应用**
4. 等待审核（通常 1 个工作日）

### 2.2 签约产品（关键：不要签「当面付」）

1. 应用审核通过后，进入 **应用详情** → **产品绑定**
2. 绑定 **电脑网站支付**（产品码 `FAST_INSTANT_TRADE_PAY`）与 **手机网站支付**（产物码 `QUICK_WAP_WAY`）
3. 填写应用场景说明（同微信），等待签约（通常 1-3 个工作日）

> 「当面付」需要门店资质，纯线上网站无法签约，代码已弃用。

### 2.3 配置密钥

1. 进入 **应用详情** → **开发设置** → **接口加签方式**
2. 选择 **公钥** 方式、**RSA2(SHA256)**
3. 生成密钥对：`openssl genrsa -out app_private_key.pem 2048` + `openssl rsa -in app_private_key.pem -pubout -out app_public_key.pem`
4. 将 `app_public_key.pem` 内容（不含 BEGIN/END 行）粘贴到支付宝
5. 支付宝返回 **支付宝公钥** → `ALIPAY_PUBLIC_KEY`；应用私钥 → `ALIPAY_PRIVATE_KEY`

### 2.4 配置回调 URL

1. 进入 **应用详情** → **开发设置** → **接口内容加密方式**（可选，保持默认）
2. **异步通知地址** 填写：
   ```
   https://legalai86.com.cn/api/v1/billing/alipay/notify
   ```
3. 同步回跳地址（`ALIPAY_RETURN_URL`）填写 `https://legalai86.com.cn/pricing`（可为空，代码会自动带 `order_id`）

### 2.5 填写环境变量

```bash
# .env.local
ALIPAY_ENABLED=true
ALIPAY_APP_ID=2021001234567890
ALIPAY_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
ALIPAY_PUBLIC_KEY="-----BEGIN PUBLIC KEY-----\n...\n-----END PUBLIC KEY-----"
ALIPAY_GATEWAY=https://openapi.alipay.com/gateway.do
ALIPAY_NOTIFY_PATH=/api/v1/billing/alipay/notify
ALIPAY_RETURN_URL=https://legalai86.com.cn/pricing
```

### 2.6 验证配置

```bash
# page（电脑）/ wap（手机）下单：返回 pay_url，前端 location.href 跳转收银台
curl -X POST http://localhost:8002/api/v1/billing/orders \
  -H "Authorization: Bearer <token>" -H "Content-Type: application/json" \
  -d '{"plan_tier":"pro","period_days":30,"channel":"alipay","pay_type":"page"}'

# 预期返回：pay_type=page 且 pay_url=https://openapi.alipay.com/gateway.do?...
```

---

## 三、生产环境部署

### 3.0 一键脚本（推荐）

仓库已提供三段 SSH 脚本，分别负责「增量推送代码」「安全写入支付凭证」「端到端验收」，从你**本地机器**执行（要求你已经能 SSH 到服务器）：

| 脚本 | 何时跑 | 作用 |
|---|---|---|
| `deploy/scripts/sync.sh` | 改了代码 | git pull → 选择性 build → 重启 backend/frontend → 健康检查 |
| `deploy/scripts/install-payment-env.sh` | 改了支付凭证 | 把支付字段精确写入 `deploy/.env`，只重启 backend |
| `deploy/scripts/verify-payment.sh` | 凭证写完后 | 下单→轮询→主动查单→健康检查，输出 PASS/FAIL |

**最小流程**（在 `legal-review/` 仓库根目录）：

```bash
# 1) 推代码
SSH_HOST=root@124.221.229.12 bash deploy/scripts/sync.sh

# 2) 写支付凭证（一次性把全部 WXPAY_*/ALIPAY_* 环境变量塞进来）
SSH_HOST=root@124.221.229.12 \
  WXPAY_ENABLED=true WXPAY_MCHID=1117431351 WXPAY_APPID=wx0c3559d4d20037d3 \
  WXPAY_APPSECRET=... WXPAY_API_V3_KEY=... \
  WXPAY_MCH_SERIAL_NO=... WXPAY_MCH_PRIVATE_KEY="$(cat apiclient_key.pem)" \
  WXPAY_PUBLIC_KEY=... WXPAY_PUBLIC_KEY_ID=... \
  ALIPAY_ENABLED=true ALIPAY_APP_ID=... \
  ALIPAY_PRIVATE_KEY=... ALIPAY_PUBLIC_KEY=... \
  bash deploy/scripts/install-payment-env.sh

# 3) 验收
SSH_HOST=root@124.221.229.12 DOMAIN=legalai86.com.cn \
  TOKEN=$(...) \
  bash deploy/scripts/verify-payment.sh
```

**重要约定**：
- `install-payment-env.sh` 仅替换 `WXPAY_*/ALIPAY_*` 字段；`JWT_SECRET`、`POSTGRES_PASSWORD` 等其他字段**不动**
- 多行 PEM 必须转成单行（真实换行 → 字面 `\n`）；脚本会自动校验并拒绝带真实换行的私钥
- 写完后 `deploy/.env` 自动 `chmod 600`，旧版本备份为 `deploy/.env.bak-YYYYMMDD-HHMMSS`

### 3.1 手动方式（不推荐）

如果你不想用脚本：

```bash
ssh root@124.221.229.12
cd /opt/legal-review
git pull --ff-only
docker compose -f deploy/docker-compose.prod.yml build backend frontend
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps backend frontend
docker exec legal-backend alembic upgrade head
docker exec legal-backend python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health').status)"
```

支付凭证仍要写到 `deploy/.env`（容器读它），不是 `backend/.env.local`：

```bash
ssh root@124.221.229.12
vim /opt/legal-review/deploy/.env
# 追加 WXPAY_*/ALIPAY_* 段（不要覆盖 JWT_SECRET / POSTGRES_PASSWORD）
docker compose -f deploy/docker-compose.prod.yml up -d --no-deps backend
```

### 3.2 验证回调

```bash
docker compose -f deploy/docker-compose.prod.yml logs -f backend | grep payment
# 预期：payment_success order_id=... user_id=... plan_tier=pro
```

---

## 四、常见问题

### Q1: 微信回调验签失败

- 检查 `WXPAY_PUBLIC_KEY` 是否是**微信支付公钥**、`WXPAY_PUBLIC_KEY_ID` 是否与回调头 `Wechatpay-Serial` 一致（新商户是 `PUB_KEY_ID_xxx`）
- 检查 `WXPAY_API_V3_KEY` 是否正确（32 字符，回调解密用）
- 检查服务器时间与微信服务器误差 < 5 分钟

### Q2: 支付宝回调验签失败

- 检查 `ALIPAY_PUBLIC_KEY` 是否是**支付宝公钥**（不是应用公钥）
- 检查 `ALIPAY_PRIVATE_KEY` 格式正确（RSA2，PEM 全文或纯 base64 体）

### Q3: 回调 URL 无法访问

- 检查防火墙/nignx 是否放行 `/api/v1/billing/` 路由
- `curl https://legalai86.com.cn/api/v1/billing/pricing` 应返回定价 JSON
- 注意健康检查在 `/health`，`/api/v1/health` 返回 404 属正常

### Q4: 支付成功但套餐未开通 / 前端查不到成功状态

- 回调可能没到 → 前端轮询 `GET /billing/orders/{id}` 会触发**主动查单补偿**，命中后自动结算 + 开通套餐
- 检查 `UserPlan` 表与 `Order.status`，日志 grep `payment_success`

---

## 五、安全注意事项

1. **私钥管理**：微信 `apiclient_key.pem`、支付宝 `app_private_key.pem`、微信支付公钥 均**严禁提交 git**，用环境变量注入
2. **回调验签**：必须验签（微信用微信支付公钥，支付宝用支付宝公钥），不要信任回调里的金额（金额以服务端算的整数分为准）
3. **幂等**：微信/支付宝会重试回调；同一渠道交易号命中已 `succeeded` 直接返回成功，避免重复开通套餐
4. **日志脱敏**：日志只打印订单号，不全量打印签名/密钥

---

## 六、测试账号

### 微信沙箱

- 文档：https://pay.weixin.qq.com/wiki/doc/api/jsapi.php?chapter=23_1
- 沙箱商户号与正式相同，沙箱密钥调用 `/sandboxnew/getsignkey` 获取

### 支付宝沙箱

- 文档：https://opendocs.alipay.com/common/02kkv7
- 沙箱网关：`https://openapi-sandbox.dl.alipaydev.com/gateway.do`

---

## 七、上线检查清单

- [ ] 微信 Native / JSAPI / H5 支付已开通
- [ ] 支付宝电脑网站支付 + 手机网站支付已签约（**非当面付**）
- [ ] APIv3 密钥 + 商户 API 证书 + 微信支付公钥 已配置
- [ ] 公众号 AppSecret + 网页授权域名已配置（JSAPI）
- [ ] 回调 URL 已配置为 `/api/v1/billing/{wechat|alipay}/notify`
- [ ] 生产 `.env.local` 已填真实密钥（未提交 git）
- [ ] 真实订单「下单 → 支付成功 → 回调验签 → 状态更新 → 套餐到账」走通
- [ ] 取消 / 失败 / 超时关单 / 主动查单补偿均验证
- [ ] 日志无敏感信息泄露

---

**文档版本**：v1.1（2026-09-26）
**维护者**：开发团队
**更新频率**：每次支付产品变更时更新