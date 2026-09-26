"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Loader2, QrCode } from "lucide-react";
import { QRCodeSVG } from "qrcode.react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { fetchPricing, createOrder, fetchOrderStatus, fetchWechatOauthUrl } from "@/lib/api";
import type {
  CreateOrderResponse,
  OrderStatusResponse,
  PaymentChannel,
  PayType,
  PlanTier,
  PricingItem,
} from "@/types/api";
import { cn } from "@/lib/utils";

const isWeChatBrowser = () =>
  typeof window !== "undefined" && /MicroMessenger/i.test(navigator.userAgent);

const isMobile = () =>
  typeof window !== "undefined" &&
  /Android|iPhone|iPad|iPod|Mobile|Windows Phone/i.test(navigator.userAgent);

/** 按渠道 + 设备 / 环境分流支付场景。 */
function resolvePayType(channel: PaymentChannel): PayType {
  if (channel === "wechat") {
    if (isWeChatBrowser()) return "jsapi";
    if (isMobile()) return "h5";
    return "native";
  }
  return isMobile() ? "wap" : "page";
}

const planFeatures: Record<PlanTier, string[]> = {
  free: [
    "每日 3 次审查",
    "基础法规库（国家法律 + 行政法规）",
    "标准审查报告",
    "社区支持",
  ],
  pro: [
    "无限审查次数",
    "全量法规库（含地方性法规）",
    "深度审查报告 + 修改建议",
    "优先支持（工作日 8h 响应）",
    "API 访问（1000 次/月）",
  ],
  enterprise: [
    "无限审查次数",
    "全量法规库 + 自定义法规",
    "团队账号（最多 50 人）",
    "专属客户经理",
    "私有化部署支持",
    "SLA 99.9%",
  ],
};

const planLabels: Record<PlanTier, string> = {
  free: "体验版",
  pro: "专业版",
  enterprise: "企业版",
};

export default function PricingPage() {
  const { data: pricing, isLoading } = useQuery({
    queryKey: ["pricing"],
    queryFn: fetchPricing,
  });

  const [proPeriod, setProPeriod] = React.useState(30);
  const [entPeriod, setEntPeriod] = React.useState(30);

  if (isLoading) {
    return (
      <div className="container mx-auto py-12">
        <div className="flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
      </div>
    );
  }

  const proItems = pricing?.filter((p) => p.plan_tier === "pro") ?? [];
  const enterpriseItems = pricing?.filter((p) => p.plan_tier === "enterprise") ?? [];
  const proSelected = proItems.find((i) => i.period_days === proPeriod) ?? proItems[0];
  const entSelected = enterpriseItems.find((i) => i.period_days === entPeriod) ?? enterpriseItems[0];

  const periodLabel = (days: number) =>
    days === 30 ? "月付" : days === 90 ? "季付" : "年付";
  const periodUnit = (days: number) =>
    days === 365 ? "年" : days === 90 ? "季" : "月";

  return (
    <div className="container mx-auto py-12">
      <div className="mx-auto max-w-5xl text-center">
        <h1 className="text-4xl font-bold tracking-tight">选择适合您的套餐</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          按审查量灵活选择，随时升级或降级
        </p>
      </div>

      <div className="mt-12 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
        {/* Free */}
        <Card>
          <CardHeader>
            <CardTitle>{planLabels.free}</CardTitle>
            <CardDescription>适合个人体验</CardDescription>
            <div className="mt-4">
              <span className="text-4xl font-bold">¥0</span>
              <span className="text-muted-foreground"> / 永久</span>
            </div>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {planFeatures.free.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-600" />
                  <span className="text-sm">{f}</span>
                </li>
              ))}
            </ul>
          </CardContent>
          <CardFooter>
            <Button variant="outline" className="w-full" disabled>
              当前套餐
            </Button>
          </CardFooter>
        </Card>

        {/* Pro */}
        <Card className="border-primary">
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>{planLabels.pro}</CardTitle>
              <Badge>推荐</Badge>
            </div>
            <CardDescription>适合专业律师 / 法务</CardDescription>
            <div className="mt-4">
              <span className="text-4xl font-bold">
                ¥{proSelected?.amount_cny ?? 0}
              </span>
              <span className="text-muted-foreground">
                {" "}
                / {proSelected ? periodUnit(proSelected.period_days) : "月"}
              </span>
            </div>
            <div className="mt-3 flex gap-2">
              {proItems.map((item) => (
                <Button
                  key={item.period_days}
                  variant={proPeriod === item.period_days ? "default" : "outline"}
                  size="sm"
                  className="flex-1"
                  onClick={() => setProPeriod(item.period_days)}
                >
                  {periodLabel(item.period_days)}
                </Button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {planFeatures.pro.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-600" />
                  <span className="text-sm">{f}</span>
                </li>
              ))}
            </ul>
          </CardContent>
          <CardFooter>
            <UpgradeButton planTier="pro" items={proItems} />
          </CardFooter>
        </Card>

        {/* Enterprise */}
        <Card>
          <CardHeader>
            <CardTitle>{planLabels.enterprise}</CardTitle>
            <CardDescription>适合律所 / 企业法务部</CardDescription>
            <div className="mt-4">
              {entSelected && (
                <>
                  <span className="text-4xl font-bold">¥{entSelected.amount_cny}</span>
                  <span className="text-muted-foreground">
                    {" "}
                    / {periodUnit(entSelected.period_days)}
                  </span>
                </>
              )}
            </div>
            <div className="mt-3 flex gap-2">
              {enterpriseItems.map((item) => (
                <Button
                  key={item.period_days}
                  variant={entPeriod === item.period_days ? "default" : "outline"}
                  size="sm"
                  className="flex-1"
                  onClick={() => setEntPeriod(item.period_days)}
                >
                  {periodLabel(item.period_days)}
                </Button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            <ul className="space-y-3">
              {planFeatures.enterprise.map((f) => (
                <li key={f} className="flex items-start gap-2">
                  <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-green-600" />
                  <span className="text-sm">{f}</span>
                </li>
              ))}
            </ul>
          </CardContent>
          <CardFooter>
            <UpgradeButton planTier="enterprise" items={enterpriseItems} />
          </CardFooter>
        </Card>
      </div>

      <div className="mt-16 text-center text-sm text-muted-foreground">
        <p>
          线上支付与开票功能正在接入中，当前阶段下单可能无法完成。
          如需正式购买，请联系我们获得报价与人工开票安排。
        </p>
      </div>
    </div>
  );
}

function UpgradeButton({
  planTier,
  items,
}: {
  planTier: PlanTier;
  items: PricingItem[];
}) {
  const [selectedPeriod, setSelectedPeriod] = React.useState(items[0]?.period_days ?? 30);
  const [channel, setChannel] = React.useState<PaymentChannel>("wechat");
  const [order, setOrder] = React.useState<CreateOrderResponse | null>(null);
  const [orderStatus, setOrderStatus] = React.useState<OrderStatusResponse | null>(null);
  const [loading, setLoading] = React.useState(false);
  // 微信内 JSAPI：OAuth 回调回跳后 URL 上带 openid
  const [openid] = React.useState<string>(() =>
    typeof window !== "undefined"
      ? new URLSearchParams(window.location.search).get("openid") ?? ""
      : "",
  );
  const pollRef = React.useRef<ReturnType<typeof setInterval> | null>(null);

  React.useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  const selectedItem = items.find((i) => i.period_days === selectedPeriod);
  if (!selectedItem) return null;

  const startPolling = (orderId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const status = await fetchOrderStatus(orderId);
        setOrderStatus(status);
        if (status.status === "succeeded" || status.status === "closed" || status.status === "refunded") {
          if (pollRef.current) clearInterval(pollRef.current);
          if (status.status === "succeeded") {
            setTimeout(() => window.location.reload(), 2000);
          }
        }
      } catch {
        // ignore
      }
    }, 2000);
  };

  const handleCreateOrder = async () => {
    setLoading(true);
    const payType = resolvePayType(channel);
    try {
      // 微信内且无 openid → 先走静默 OAuth 拿 openid
      if (payType === "jsapi" && !openid) {
        const url = await fetchWechatOauthUrl("/pricing");
        window.location.href = url;
        return;
      }

      const res = await createOrder({
        plan_tier: planTier,
        period_days: selectedPeriod,
        channel,
        pay_type: payType,
        openid: openid || undefined,
      });
      setOrder(res);

      if (res.pay_type === "native") {
        startPolling(res.order_id);
      } else if (res.pay_type === "jsapi" && res.jsapi_params?.package) {
        startPolling(res.order_id);
        invokeWechatPay(res.jsapi_params);
      } else if (res.pay_url) {
        // page / wap / h5：跳转到收银台
        window.location.href = res.pay_url;
      }
    } catch (err) {
      alert(err instanceof Error ? err.message : "创建订单失败");
    } finally {
      setLoading(false);
    }
  };

  if (order) {
    if (order.pay_type === "native") {
      return (
        <div className="w-full space-y-4">
          <div className="flex items-center justify-center rounded-lg border bg-white p-4">
            <QRCodeSVG value={order.qr_code} size={192} />
          </div>
          <p className="text-center text-sm text-muted-foreground">微信扫码支付</p>
          <OrderStatusHint status={orderStatus} />
        </div>
      );
    }
    if (order.pay_type === "jsapi") {
      return (
        <div className="w-full space-y-4">
          <div className="flex items-center justify-center">
            <QrCode className="h-32 w-32 text-muted-foreground" />
          </div>
          <p className="text-center text-sm text-muted-foreground">正在微信内发起支付...</p>
          <OrderStatusHint status={orderStatus} />
        </div>
      );
    }
    // page / wap / h5：已跳转收银台（理论上不会停留在此）
    return (
      <div className="w-full space-y-4">
        <div className="flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin" />
        </div>
        <p className="text-center text-sm text-muted-foreground">正在跳转到收银台...</p>
      </div>
    );
  }

  return (
    <div className="w-full space-y-3">
      <div className="flex gap-2">
        <Button
          variant={channel === "wechat" ? "default" : "outline"}
          size="sm"
          className="flex-1"
          onClick={() => setChannel("wechat")}
        >
          微信支付
        </Button>
        <Button
          variant={channel === "alipay" ? "default" : "outline"}
          size="sm"
          className="flex-1"
          onClick={() => setChannel("alipay")}
        >
          支付宝
        </Button>
      </div>
      <Button
        className="w-full"
        onClick={handleCreateOrder}
        disabled={loading}
      >
        {loading ? (
          <>
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            创建订单...
          </>
        ) : (
          `升级至${planLabels[planTier]} · ¥${selectedItem.amount_cny}`
        )}
      </Button>
      <Separator />
      <div className="flex gap-2">
        {items.map((item) => (
          <Button
            key={item.period_days}
            variant={selectedPeriod === item.period_days ? "default" : "ghost"}
            size="sm"
            className="flex-1"
            onClick={() => setSelectedPeriod(item.period_days)}
          >
            {item.period_days === 30 ? "月付" : item.period_days === 90 ? "季付" : "年付"}
          </Button>
        ))}
      </div>
    </div>
  );
}

function OrderStatusHint({ status }: { status: OrderStatusResponse | null }) {
  if (!status) return null;
  const succeeded = status.status === "succeeded";
  const closed = status.status === "closed" || status.status === "refunded";
  return (
    <p
      className={cn(
        "text-center text-sm font-medium",
        succeeded ? "text-green-600" : closed ? "text-red-500" : "text-muted-foreground",
      )}
    >
      {succeeded
        ? "支付成功，正在开通套餐..."
        : closed
          ? "订单已关闭，请重新下单"
          : "等待支付..."}
    </p>
  );
}

/** 微信内置浏览器调起 JSAPI 支付。 */
function invokeWechatPay(params: Record<string, string>) {
  const bridge = (window as unknown as {
    WeixinJSBridge?: {
      invoke: (name: string, p: Record<string, string>, cb: (res: { err_msg?: string }) => void) => void;
    };
  }).WeixinJSBridge;
  if (!bridge) {
    alert("请用微信客户端打开本页面完成支付");
    return;
  }
  bridge.invoke("getBrandWCPayRequest", params, (res) => {
    if (res.err_msg === "get_brand_wcpay_request:ok") {
      // 支付成功，轮询会感知状态并刷新
    } else if (res.err_msg === "get_brand_wcpay_request:cancel") {
      // 用户取消
    } else {
      alert("支付未完成，请重试");
    }
  });
}
