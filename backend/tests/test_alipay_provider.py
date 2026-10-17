"""支付宝 Provider 单元测试：RSA2 签名规则 + 回调验签 + GBK 兼容。

覆盖回归点：
- sign_type 必须参与签名（V2 规则），否则支付宝网关返回 isv.invalid-signature
- 回调验签兼容 V2（主）/ V1（兜底）两种规则
- timestamp 使用东八区时间
- 查单响应为 GBK 编码时不抛 UnicodeDecodeError
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa

from app.services.payment.providers import AlipayProvider

_BEIJING_TZ = timezone(timedelta(hours=8))
_PRIVATE_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _provider() -> AlipayProvider:
    """绕开 get_settings（lru_cache + 真实密钥），手工注入测试密钥。"""
    p = AlipayProvider.__new__(AlipayProvider)
    p._app_id = "2021000000000000"
    p._private_key = _PRIVATE_KEY
    p._alipay_public_key = _PRIVATE_KEY.public_key()
    p._gateway = "https://openapi.alipay.com/gateway.do"
    return p


def _rsa2_sign(provider: AlipayProvider, string_to_sign: str) -> str:
    sig = provider._private_key.sign(
        string_to_sign.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
    )
    return base64.b64encode(sig).decode()


# ============== 待签名字符串构造 ==============

def test_string_to_sign_includes_sign_type() -> None:
    """回归：sign_type 必须参与签名（RSA2 V2 规则）。"""
    params = {"app_id": "1", "sign_type": "RSA2", "sign": "XXX", "method": "m"}
    s = AlipayProvider._string_to_sign(params)
    assert "sign_type=RSA2" in s
    assert "sign=" not in s


def test_string_to_sign_excludes_empty_and_none() -> None:
    params = {"a": "1", "b": "", "c": None, "app_id": "1"}
    s = AlipayProvider._string_to_sign(params)
    assert s == "a=1&app_id=1"


def test_string_to_sign_v1_variant_excludes_sign_type() -> None:
    params = {"app_id": "1", "sign_type": "RSA2"}
    s = AlipayProvider._string_to_sign(params, include_sign_type=False)
    assert "sign_type" not in s


# ============== timestamp 东八区 ==============

def test_timestamp_is_beijing_time() -> None:
    p = _provider()
    params = p._build_common_params(
        "alipay.trade.page.pay", {"out_trade_no": "o1"}, "https://x/notify"
    )
    ts = datetime.strptime(params["timestamp"], "%Y-%m-%d %H:%M:%S").replace(
        tzinfo=_BEIJING_TZ
    )
    delta = abs((datetime.now(_BEIJING_TZ) - ts).total_seconds())
    assert delta < 120


# ============== 签名/验签回环 ==============

def _notify_form() -> dict:
    return {
        "app_id": "2021000000000000",
        "method": "alipay.trade.page.pay",
        "format": "JSON",
        "charset": "utf-8",
        "sign_type": "RSA2",
        "timestamp": "2026-10-16 16:00:00",
        "version": "1.0",
        "notify_url": "https://legalai86.com.cn/api/v1/billing/alipay/notify",
        "biz_content": json.dumps({"out_trade_no": "o1"}, ensure_ascii=False),
        "gmt_create": "2026-10-16 16:00:01",
        "trade_status": "TRADE_SUCCESS",
        "total_amount": "0.01",
        "seller_email": "",  # 空值参数不参与签名
        "trade_no": "2026101622001400001234567890",
    }


def test_sign_and_verify_callback_roundtrip() -> None:
    """V2 规则签名 → 验签通过，金额/状态正确解析。"""
    p = _provider()
    form = _notify_form()
    string_to_sign = AlipayProvider._string_to_sign(
        {k: v for k, v in form.items() if k != "sign"}
    )
    form["sign"] = _rsa2_sign(p, string_to_sign)
    result = p.verify_callback(form)
    assert result is not None
    assert result.is_success is True
    assert result.amount_cents == 1
    assert result.channel_trade_no == form["trade_no"]


def test_verify_callback_accepts_v1_style_sign() -> None:
    """兜底：V1 规则（剔除 sign_type）签名的通知也能验签通过。"""
    p = _provider()
    form = _notify_form()
    string_to_sign = AlipayProvider._string_to_sign(
        {k: v for k, v in form.items() if k != "sign"}, include_sign_type=False
    )
    form["sign"] = _rsa2_sign(p, string_to_sign)
    assert p.verify_callback(form) is not None


def test_verify_callback_rejects_tampered_sign() -> None:
    p = _provider()
    form = _notify_form()
    string_to_sign = AlipayProvider._string_to_sign(
        {k: v for k, v in form.items() if k != "sign"}
    )
    sig = bytearray(base64.b64decode(_rsa2_sign(p, string_to_sign)))
    sig[10] ^= 0xFF
    form["sign"] = base64.b64encode(bytes(sig)).decode()
    assert p.verify_callback(form) is None


def test_verify_callback_missing_sign_returns_none() -> None:
    p = _provider()
    assert p.verify_callback(_notify_form()) is None


# ============== create_order ==============

def test_create_order_builds_signed_page_pay_url() -> None:
    p = _provider()
    result = __import__("asyncio").run(
        p.create_order(
            order_no="ORD-1", amount_cents=1, subject="专业版·月付",
            notify_url="https://x/notify", pay_type="page",
            return_url="https://x/pricing",
        )
    )
    assert result.pay_type == "page"
    assert "sign=" in result.pay_url
    assert "alipay.trade.page.pay" in result.pay_url
    assert "total_amount" in result.pay_url  # biz_content 内含金额


# ============== query_order GBK 兼容 ==============

class _FakeGBKResponse:
    status_code = 200

    def __init__(self) -> None:
        body = {"alipay_trade_query_response": {
            "code": "40004", "msg": "Business Failed",
            "sub_code": "ACQ.TRADE_NOT_EXIST", "sub_msg": "交易不存在",
        }}
        self.content = json.dumps(body, ensure_ascii=False).encode("gbk")

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        raise json.JSONDecodeError("Expecting value", "<gbk>", 0)


class _FakeAsyncClient:
    def __init__(self, **_kw) -> None:
        pass

    async def __aenter__(self) -> _FakeAsyncClient:
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, *_args, **_kw) -> _FakeGBKResponse:
        return _FakeGBKResponse()


@pytest.mark.asyncio
async def test_query_order_handles_gbk_error_body(monkeypatch: pytest.MonkeyPatch) -> None:
    """未支付订单查单返回 GBK 编码业务失败响应 → 返回 None 而非抛异常。"""
    import app.services.payment.providers as mod

    monkeypatch.setattr(mod.httpx, "AsyncClient", _FakeAsyncClient)
    p = _provider()
    result = await p.query_order("NOT-EXIST-ORDER")
    assert result is None
