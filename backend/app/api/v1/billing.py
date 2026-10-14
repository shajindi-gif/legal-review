"""支付 API 路由：下单 / 轮询 / 微信回调 / 支付宝回调。"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.config import get_settings
from app.core.constants import PaymentChannel, PaymentStatus, PlanTier
from app.core.errors import AppError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.services.core_auth_client import CorePrincipal
from app.services.payment.providers import AlipayProvider, WechatPayProvider
from app.services.payment.service import PaymentService

logger = get_logger("billing")

router = APIRouter(prefix="/billing", tags=["billing"])


# ============== 请求/响应模型 ==============

class CreateOrderRequest(BaseModel):
    plan_tier: str = Field(..., description="套餐：pro / enterprise")
    period_days: int = Field(..., description="周期天数：30 / 90 / 365")
    channel: str = Field(..., description="支付渠道：wechat / alipay")
    pay_type: str = Field(default="", description="支付场景：native/jsapi/h5/page/wap，空则按渠道默认")
    openid: str = Field(default="", description="微信 JSAPI 需要的 openid")
    client_ip: str = Field(default="", description="微信 H5 需要的用户 IP")


class CreateOrderResponse(BaseModel):
    order_id: str
    order_no: str
    pay_type: str
    qr_code: str
    pay_url: str
    jsapi_params: dict = Field(default_factory=dict)
    amount_cents: int
    channel: str


class OrderStatusResponse(BaseModel):
    order_id: str
    status: str
    plan_tier: str
    amount_cny: float
    paid_at: str | None


class PricingItem(BaseModel):
    plan_tier: str
    period_days: int
    amount_cents: int
    amount_cny: float
    label: str


# ============== 路由 ==============

@router.get("/pricing", response_model=list[PricingItem], summary="获取套餐定价")
async def list_pricing():
    """返回所有可选套餐 + 价格（前端渲染用）。"""
    from app.core.constants import PLAN_PRICING_CENTS

    items: list[PricingItem] = []
    tier_labels = {"pro": "专业版", "enterprise": "企业版"}
    period_labels = {30: "月付", 90: "季付", 365: "年付"}
    for tier, periods in PLAN_PRICING_CENTS.items():
        for days, cents in periods.items():
            items.append(PricingItem(
                plan_tier=tier,
                period_days=days,
                amount_cents=cents,
                amount_cny=cents / 100,
                label=f"{tier_labels.get(tier, tier)} · {period_labels.get(days, f'{days}天')}",
            ))
    return items


@router.post("/orders", response_model=CreateOrderResponse, summary="创建支付订单")
async def create_order(
    req: CreateOrderRequest,
    request: Request,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """创建订单并返回支付凭据（扫码二维码 / 跳转 URL / JSAPI 参数）。"""
    svc = PaymentService(session)
    client_ip = req.client_ip or (request.client.host if request.client else "")
    result = await svc.create_order(
        user_id=current_user.id,
        plan_tier=req.plan_tier,
        period_days=req.period_days,
        channel=req.channel,
        pay_type=req.pay_type,
        openid=req.openid,
        client_ip=client_ip,
    )
    await session.commit()
    return result


@router.get("/orders/{order_id}", response_model=OrderStatusResponse, summary="查询订单状态")
async def get_order_status(
    order_id: UUID,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """轮询订单状态（前端每 2 秒调一次），附带主动查单补偿 + 超时关单。"""
    svc = PaymentService(session)
    order = await svc.get_order(order_id)
    if order is None:
        raise NotFoundError(f"订单不存在: {order_id}")
    if order.user_id != current_user.id:
        raise AppError("无权查看此订单", code="forbidden", http_status=403)

    # 回调可能没来 → 主动查单补偿；超时则关单
    order = await svc.query_and_sync_order(order)
    await svc.close_if_expired(order)
    await session.commit()

    return OrderStatusResponse(
        order_id=str(order.id),
        status=str(order.status),
        plan_tier=str(order.plan_tier),
        amount_cny=float(order.amount_cny),
        paid_at=order.paid_at.isoformat() if order.paid_at else None,
    )


@router.post("/wechat/notify", summary="微信支付回调")
async def wechat_notify(request: Request, session: AsyncSession = Depends(get_db)):
    """微信支付 V3 异步通知。

    微信会重试多次，必须幂等。
    验签失败返回 401，成功返回 200 + {"code":"SUCCESS","message":"OK"}。
    """
    body = await request.body()
    body_str = body.decode("utf-8")
    headers = dict(request.headers)

    try:
        provider = WechatPayProvider()
    except RuntimeError as e:
        logger.error("wechat_provider_init_failed", error=str(e))
        return {"code": "FAIL", "message": "微信支付未配置"}

    result = provider.verify_callback(headers, body_str)
    svc = PaymentService(session)
    ret = await svc.handle_callback(PaymentChannel.WECHAT, result, {"raw": body_str})
    if ret["status"] == "fail":
        await session.rollback()
        return {"code": "FAIL", "message": ret["message"]}
    await session.commit()
    return {"code": "SUCCESS", "message": "OK"}


@router.post("/alipay/notify", summary="支付宝异步通知")
async def alipay_notify(request: Request, session: AsyncSession = Depends(get_db)):
    """支付宝异步通知（form-data）。

    验签失败返回 "fail"，成功返回 "success"。
    """
    form = await request.form()
    form_data = dict(form)

    try:
        provider = AlipayProvider()
    except RuntimeError as e:
        logger.error("alipay_provider_init_failed", error=str(e))
        return "fail"

    result = provider.verify_callback(form_data)
    svc = PaymentService(session)
    ret = await svc.handle_callback(PaymentChannel.ALIPAY, result, form_data)
    if ret["status"] == "fail":
        await session.rollback()
        return "fail"
    await session.commit()
    return "success"


@router.get("/orders", summary="当前用户订单列表")
async def list_my_orders(
    limit: int = 20,
    current_user: CorePrincipal = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    svc = PaymentService(session)
    orders = await svc.get_user_orders(current_user.id, limit)
    return [
        {
            "order_id": str(o.id),
            "status": str(o.status),
            "plan_tier": str(o.plan_tier),
            "amount_cny": float(o.amount_cny),
            "period_days": o.period_days,
            "channel": o.payment_channel,
            "paid_at": o.paid_at.isoformat() if o.paid_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
        }
        for o in orders
    ]


# ============== 微信 JSAPI 静默 OAuth（换 openid）==============

@router.get("/wechat/oauth/url", summary="获取微信 JSAPI 静默授权跳转地址")
async def wechat_oauth_url(
    state: str = "",
    current_user: CorePrincipal = Depends(get_current_user),
):
    """返回微信 OAuth 授权地址；前端在微信内置浏览器内 location.href 跳转过去。

    state 用于回跳前端目标路径（如 /pricing）。
    """
    try:
        provider = WechatPayProvider()
    except RuntimeError:
        raise AppError("微信支付未配置", code="wxpay_disabled", http_status=503)
    redirect_uri = get_settings().wxpay_oauth_redirect_url
    if not redirect_uri:
        redirect_uri = f"{get_settings().public_base_url}/api/v1/billing/wechat/oauth/callback"
    return {"url": provider.oauth_authorize_url(redirect_uri, state)}


@router.get("/wechat/oauth/callback", summary="微信 JSAPI OAuth 回调（换 openid 后回跳前端）")
async def wechat_oauth_callback(code: str, state: str = ""):
    """微信授权后重定向回来：code 换 openid → 回跳前端 state 指定的页面。"""
    try:
        provider = WechatPayProvider()
    except RuntimeError:
        return JSONResponse({"detail": "微信支付未配置"}, status_code=503)
    try:
        openid = await provider.oauth_get_openid(code)
    except Exception as e:
        logger.error("wechat_oauth_openid_failed", error=str(e))
        return JSONResponse({"detail": "获取 openid 失败"}, status_code=500)
    base = get_settings().public_base_url
    target = state if state else "/pricing"
    if not target.startswith("http"):
        target = f"{base}{target}"
    sep = "&" if "?" in target else "?"
    return RedirectResponse(f"{target}{sep}openid={openid}")
