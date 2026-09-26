"""支付渠道 Provider 抽象层。

每个 Provider 实现：
- create_order()     → 下单，返回渠道交易号 + 支付凭据（二维码 / 跳转 URL / JSAPI 参数）
- query_order()      → 主动查单（回调可能不来时的补偿）
- verify_callback()  → 验签，返回标准化结果
- decrypt（微信 V3 需要 AES-256-GCM）

设计原则：
- Provider 不写 DB，只负责与第三方 API 交互
- 业务层（PaymentService）负责幂等 + 订单状态流转
"""

from __future__ import annotations

import base64
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlencode

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_pem_public_key

from app.core.config import get_settings


# ============== 通用数据结构 ==============

@dataclass
class CreateOrderResult:
    """下单结果（渠道无关）。根据 pay_type 决定前端用哪个字段：

    - native → 前端展示 qr_code
    - page / wap / h5 → 前端 location.href = pay_url 跳转
    - jsapi → 前端调 WeixinJSBridge.invoke("getBrandWCPayRequest", jsapi_params)
    """

    channel_trade_no: str                    # 渠道交易号（微信 prepay_id / 支付宝 下单时为空）
    pay_type: str                            # native / jsapi / h5 / page / wap
    qr_code: str = ""                        # Native 扫码内容（code_url）
    pay_url: str = ""                        # 跳转支付地址（page/wap/h5）
    jsapi_params: dict = field(default_factory=dict)  # JSAPI 调起参数
    raw_response: dict = field(default_factory=dict)


@dataclass
class CallbackResult:
    """回调 / 查单的标准化结果。"""

    is_success: bool           # 支付是否成功
    channel_trade_no: str      # 渠道交易号（微信 transaction_id / 支付宝 trade_no）
    amount_cents: int          # 金额（分）
    paid_at: str | None        # 支付时间（ISO 8601）
    raw_callback: dict         # 原始响应（存 DB raw_callback）


# ============== 微信支付 V3（Native / JSAPI / H5）==============

class WechatPayProvider:
    """微信支付 V3 下单 + 主动查单 + 回调验签 + 回调解密。

    三端分流：Native 扫码 / JSAPI（微信内）/ H5（手机浏览器）。
    参考：https://pay.weixin.qq.com/doc/v3/merchant/4012070796
    """

    BASE_URL = "https://api.mch.weixin.qq.com"
    ORDER_URLS = {
        "native": "/v3/pay/transactions/native",
        "jsapi": "/v3/pay/transactions/jsapi",
        "h5": "/v3/pay/transactions/h5",
    }
    # 静默授权（snsapi_base）仅拿 openid，不弹窗
    OAUTH_AUTHORIZE_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
    OAUTH_ACCESS_TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"

    def __init__(self) -> None:
        self.cfg = get_settings()
        self._mchid = self.cfg.wxpay_mchid
        self._appid = self.cfg.wxpay_appid
        self._appsecret = self.cfg.wxpay_appsecret
        self._api_v3_key = self.cfg.wxpay_api_v3_key
        self._serial_no = self.cfg.wxpay_mch_serial_no
        self._private_key_pem = self.cfg.wxpay_mch_private_key
        self._public_key_pem = self.cfg.wxpay_public_key
        self._public_key_id = self.cfg.wxpay_public_key_id
        if not all([self._mchid, self._appid, self._api_v3_key, self._serial_no, self._private_key_pem]):
            raise RuntimeError("微信支付配置不完整：需要 mchid / appid / api_v3_key / serial_no / private_key")
        self._private_key = load_pem_private_key(
            self._private_key_pem.encode("utf-8"), password=None,
        )
        # 回调验签公钥（微信支付公钥，非商户 apiclient 证书）
        if self._public_key_pem:
            self._public_key = load_pem_public_key(
                self._ensure_pem(self._public_key_pem, is_private=False).encode("utf-8"),
            )
        else:
            self._public_key = None

    @staticmethod
    def _ensure_pem(key: str, is_private: bool = True) -> str:
        """裸 base64 体包成 PEM；已是 PEM 则原样返回。"""
        if key.startswith("-----"):
            return key
        if is_private:
            return f"-----BEGIN PRIVATE KEY-----\n{key}\n-----END PRIVATE KEY-----"
        return f"-----BEGIN PUBLIC KEY-----\n{key}\n-----END PUBLIC KEY-----"

    # ---- 签名 ----
    def _sign(self, method: str, url_path: str, body: str = "") -> str:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        ts = str(int(time.time()))
        nonce = hashlib.sha256(f"{ts}{uuid.uuid4().hex}".encode()).hexdigest()[:32]
        sign_str = f"{method}\n{url_path}\n{ts}\n{nonce}\n{body}\n"
        sig = self._private_key.sign(sign_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return f"WECHATPAY2-SHA256-RSA2048 mchid=\"{self._mchid}\",nonce_str=\"{nonce}\",timestamp=\"{ts}\",serial_no=\"{self._serial_no}\",signature=\"{base64.b64encode(sig).decode()}\""

    def _headers(self, method: str, url_path: str, body: str = "") -> dict:
        return {
            "Authorization": self._sign(method, url_path, body),
            "Accept": "application/json",
            "Content-Type": "application/json",
            # 微信支付要求显式 Accept-Language + 自定义 UA，否则可能 406
            "Accept-Language": "zh-CN",
            "User-Agent": "legal-review/1.0",
        }

    async def create_order(
        self,
        order_no: str,
        amount_cents: int,
        description: str,
        notify_url: str,
        pay_type: str = "native",
        openid: str = "",
        client_ip: str = "",
    ) -> CreateOrderResult:
        """下单 → 按 pay_type 返回 Native 二维码 / H5 跳转 URL / JSAPI 调起参数。"""
        url_path = self.ORDER_URLS[pay_type]
        body: dict = {
            "mchid": self._mchid,
            "appid": self._appid,
            "description": description,
            "out_trade_no": order_no,
            "notify_url": notify_url,
            "amount": {"total": amount_cents, "currency": "CNY"},
        }
        if pay_type == "jsapi":
            if not openid:
                raise RuntimeError("微信 JSAPI 下单需要 openid（先走静默 OAuth）")
            body["payer"] = {"openid": openid}
        elif pay_type == "h5":
            body["scene_info"] = {
                "payer_client_ip": client_ip or "127.0.0.1",
                "h5_info": {"type": "Wap"},
            }

        body_str = json.dumps(body, ensure_ascii=False)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{self.BASE_URL}{url_path}",
                headers=self._headers("POST", url_path, body_str),
                content=body_str,
            )
            resp.raise_for_status()
            data = resp.json()

        prepay_id = data.get("prepay_id", "")
        if pay_type == "native":
            return CreateOrderResult(
                channel_trade_no=prepay_id,
                pay_type=pay_type,
                qr_code=data.get("code_url", ""),
                raw_response=data,
            )
        if pay_type == "h5":
            return CreateOrderResult(
                channel_trade_no=prepay_id,
                pay_type=pay_type,
                pay_url=data.get("h5_url", ""),
                raw_response=data,
            )
        # jsapi
        return CreateOrderResult(
            channel_trade_no=prepay_id,
            pay_type=pay_type,
            jsapi_params=self._build_jsapi_params(prepay_id) if prepay_id else {},
            raw_response=data,
        )

    def _build_jsapi_params(self, prepay_id: str) -> dict:
        """构建前端 getBrandWCPayRequest 所需参数。"""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        timestamp = str(int(time.time()))
        nonce = hashlib.sha256(f"{timestamp}{uuid.uuid4().hex}".encode()).hexdigest()[:32]
        package = f"prepay_id={prepay_id}"
        sign_str = f"{self._appid}\n{timestamp}\n{nonce}\n{package}\n"
        sig = self._private_key.sign(sign_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return {
            "appId": self._appid,
            "timeStamp": timestamp,
            "nonceStr": nonce,
            "package": package,
            "signType": "RSA",
            "paySign": base64.b64encode(sig).decode(),
        }

    # ---- 主动查单（补偿回调缺失）----
    async def query_order(self, out_trade_no: str) -> CallbackResult | None:
        """按商户订单号查单。返回 None 表示查不到（未支付/不存在），其余返回标准化结果。"""
        url_path = f"/v3/pay/transactions/out-trade-no/{out_trade_no}?mchid={self._mchid}"
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self.BASE_URL}{url_path}",
                headers=self._headers("GET", url_path, ""),
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
        if data.get("trade_state") == "SUCCESS":
            return CallbackResult(
                is_success=True,
                channel_trade_no=data.get("transaction_id", ""),
                amount_cents=data.get("amount", {}).get("total", 0),
                paid_at=data.get("success_time"),
                raw_callback=data,
            )
        return None

    # ---- 静默 OAuth（JSAPI 换 openid）----
    def oauth_authorize_url(self, redirect_uri: str, state: str) -> str:
        params = {
            "appid": self._appid,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "snsapi_base",
            "state": state,
        }
        return f"{self.OAUTH_AUTHORIZE_URL}?{urlencode(params)}#wechat_redirect"

    async def oauth_get_openid(self, code: str) -> str:
        """用 code 换 openid（snsapi_base 静默授权）。"""
        params = {
            "appid": self._appid,
            "secret": self._appsecret,
            "code": code,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(self.OAUTH_ACCESS_TOKEN_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        openid = data.get("openid", "")
        if not openid or data.get("errcode"):
            raise RuntimeError(f"微信 OAuth 换 openid 失败: {data.get('errmsg', 'unknown')}")
        return openid

    def verify_callback(self, headers: dict, body: str) -> CallbackResult | None:
        """验签微信回调。返回 None 表示验签失败。

        新商户验签用「微信支付公钥」（无平台证书，回调头 serial=PUB_KEY_ID_xxx）。
        """
        timestamp = headers.get("Wechatpay-Timestamp", "")
        nonce = headers.get("Wechatpay-Nonce", "")
        signature = headers.get("Wechatpay-Signature", "")
        serial = headers.get("Wechatpay-Serial", "")
        # 校验回调签名来源：serial 必须匹配微信支付公钥 ID
        if not self._public_key:
            return None
        if not self._public_key_id or serial != self._public_key_id:
            return None
        sign_str = f"{timestamp}\n{nonce}\n{body}\n"
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        try:
            self._public_key.verify(
                base64.b64decode(signature),
                sign_str.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception:
            return None
        # 验签通过，解密 resource
        try:
            payload = json.loads(body)
            resource = payload.get("resource", {})
            ciphertext = base64.b64decode(resource.get("ciphertext", ""))
            nonce_bytes = resource.get("nonce", "").encode("utf-8")
            associated_data = resource.get("associated_data", "").encode("utf-8")
            aesgcm = AESGCM(self._api_v3_key.encode("utf-8"))
            plaintext = aesgcm.decrypt(nonce_bytes, ciphertext, associated_data)
            decrypted = json.loads(plaintext.decode("utf-8"))
        except Exception:
            return None
        return CallbackResult(
            is_success=decrypted.get("trade_state") == "SUCCESS",
            channel_trade_no=decrypted.get("transaction_id", ""),
            amount_cents=decrypted.get("amount", {}).get("total", 0),
            paid_at=decrypted.get("success_time"),
            raw_callback=decrypted,
        )


# ============== 支付宝（电脑网站 page.pay / 手机网站 wap.pay，RSA2）==============

class AlipayProvider:
    """支付宝电脑网站 / 手机网站支付下单 + 主动查单 + 回调验签。

    纯线上网站签约「电脑网站支付 + 手机网站支付」，不使用「当面付」（需门店资质）。
    参考：https://opendocs.alipay.com/open/270/105898 / 105899
    """

    def __init__(self) -> None:
        self.cfg = get_settings()
        self._app_id = self.cfg.alipay_app_id
        self._private_key_pem = self.cfg.alipay_private_key
        self._public_key_pem = self.cfg.alipay_public_key
        self._gateway = self.cfg.alipay_gateway
        if not all([self._app_id, self._private_key_pem, self._public_key_pem]):
            raise RuntimeError("支付宝配置不完整：需要 app_id / private_key / public_key")
        self._private_key = load_pem_private_key(
            self._ensure_pem(self._private_key_pem).encode("utf-8"), password=None,
        )
        self._alipay_public_key = load_pem_public_key(
            self._ensure_pem(self._public_key_pem, is_private=False).encode("utf-8"),
        )

    @staticmethod
    def _ensure_pem(key: str, is_private: bool = True) -> str:
        """裸 base64 体包成 PEM；已是 PEM 则原样返回。"""
        if key.startswith("-----"):
            return key
        if is_private:
            return f"-----BEGIN PRIVATE KEY-----\n{key}\n-----END PRIVATE KEY-----"
        return f"-----BEGIN PUBLIC KEY-----\n{key}\n-----END PUBLIC KEY-----"

    def _sign(self, params: dict) -> str:
        """RSA2 签名（SHA256WithRSA）。"""
        sorted_str = "&".join(
            f"{k}={v}" for k, v in sorted(params.items())
            if v is not None and k != "sign" and k != "sign_type"
        )
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        sig = self._private_key.sign(sorted_str.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256())
        return base64.b64encode(sig).decode()

    def _build_common_params(self, method: str, biz_content: dict, notify_url: str, return_url: str = "") -> dict:
        params: dict = {
            "app_id": self._app_id,
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "notify_url": notify_url,
            "biz_content": json.dumps(biz_content, ensure_ascii=False),
        }
        if return_url:
            params["return_url"] = return_url
        params["sign"] = self._sign(params)
        return params

    async def create_order(
        self,
        order_no: str,
        amount_cents: int,
        subject: str,
        notify_url: str,
        pay_type: str = "page",
        return_url: str = "",
    ) -> CreateOrderResult:
        """page / wap 下单 → 返回跳转支付 URL（前端 location.href 跳转）。"""
        method = "alipay.trade.wap.pay" if pay_type == "wap" else "alipay.trade.page.pay"
        product_code = "QUICK_WAP_WAY" if pay_type == "wap" else "FAST_INSTANT_TRADE_PAY"
        biz_content = {
            "out_trade_no": order_no,
            "total_amount": f"{amount_cents / 100:.2f}",
            "subject": subject,
            "product_code": product_code,
        }
        params = self._build_common_params(method, biz_content, notify_url, return_url)
        # URL 跳转式下单：gateway.do + 签名 query string，前端直接跳转
        pay_url = f"{self._gateway}?{urlencode(params)}"
        return CreateOrderResult(
            channel_trade_no="",  # page/wap 下单不返回 trade_no，支付成功才有
            pay_type=pay_type,
            pay_url=pay_url,
            raw_response={"method": method, "product_code": product_code, "params": params},
        )

    # ---- 主动查单（补偿回调缺失）----
    async def query_order(self, out_trade_no: str) -> CallbackResult | None:
        """按商户订单号查单。返回 None 表示未支付/不存在。"""
        biz_content = {"out_trade_no": out_trade_no}
        params: dict = {
            "app_id": self._app_id,
            "method": "alipay.trade.query",
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "biz_content": json.dumps(biz_content, ensure_ascii=False),
        }
        params["sign"] = self._sign(params)
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(self._gateway, data=params)
            resp.raise_for_status()
            data = resp.json()
        alipay_resp = data.get("alipay_trade_query_response", {})
        if alipay_resp.get("code") != "10000":
            return None
        trade_status = alipay_resp.get("trade_status", "")
        return CallbackResult(
            is_success=trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"),
            channel_trade_no=alipay_resp.get("trade_no", ""),
            amount_cents=int(float(alipay_resp.get("total_amount", "0")) * 100),
            paid_at=alipay_resp.get("send_pay_date"),
            raw_callback=alipay_resp,
        )

    def verify_callback(self, form_data: dict) -> CallbackResult | None:
        """验签支付宝异步通知。"""
        params = dict(form_data)
        sign = params.pop("sign", "")
        params.pop("sign_type", None)
        if not sign:
            return None
        sorted_str = "&".join(
            f"{k}={v}" for k, v in sorted(params.items()) if v is not None
        )
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding
        try:
            self._alipay_public_key.verify(
                base64.b64decode(sign),
                sorted_str.encode("utf-8"),
                padding.PKCS1v15(),
                hashes.SHA256(),
            )
        except Exception:
            return None
        # 金额：total_amount 是字符串，防止浮点误差
        try:
            amount_cents = int(round(float(form_data.get("total_amount", "0")) * 100))
        except (TypeError, ValueError):
            amount_cents = 0
        trade_status = form_data.get("trade_status", "")
        return CallbackResult(
            is_success=trade_status in ("TRADE_SUCCESS", "TRADE_FINISHED"),
            channel_trade_no=form_data.get("trade_no", ""),
            amount_cents=amount_cents,
            paid_at=form_data.get("gmt_payment"),
            raw_callback=form_data,
        )