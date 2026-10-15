"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Check, Loader2, QrCode, ShieldCheck } from "lucide-react";
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
import {
  fetchPricing,
  createOrder,
  fetchOrderStatus,
  fetchWechatOauthUrl,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { track } from "@/lib/analytics";
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
    "免费体验 2 次完整审查",
    "基础法规库（国家法律 + 行政法规）",
    "标准审查报告在线查看",
    "无需信用卡，注册即用",
  ],
  pro: [
    "无限审查次数",
    "全量法规库（含地方性法规）",
    "深度审查报告 + 修改建议",
    "优先支持（工作日 8h 响应）",
  ],
  enterprise: [
    "无限审查次数",
    "全量法规库 + 自定义法规",
    "团队账号（最多 50 人）",
    "专属客户经理",
    "私有化部署支持",
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

  // 商业化埋点：定价页浏览（页面挂载时上报一次）
  React.useEffect(() => {
    track("pricing_view");
  }, []);

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
    <div className="flex min-h-screen flex-col bg-white">
      {/* 公开定价页顶部：游客可完整浏览价格 */}
      <header className="sticky top-0 z-30 border-b border-neutral-200/60 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
              法
            </div>
            <span className="text-base font-semibold tracking-tight text-neutral-900">
              智审 <span className="font-normal text-neutral-500">·</span> LegaReview
            </span>
          </Link>
          <PricingHeaderActions />
        </div>
      </header>

      <main className="container mx-auto py-12">
        <div className="mx-auto max-w-3xl text-center">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-neutral-400">
            Pricing
          </p>
          <h1 className="mt-3 font-display text-4xl font-semibold tracking-tight text-neutral-900 sm:text-5xl">
            选择适合您的套餐
          </h1>
          <p className="mt-4 text-base leading-relaxed text-neutral-600 sm:text-lg">
            先免费体验 2 次完整审查，再决定是否升级
          </p>
        </div>

        <div className="mt-12 grid gap-8 md:grid-cols-2 lg:grid-cols-3">
          {/* Free */}
          <Card className="border-neutral-200/70 shadow-none">
            <CardHeader>
              <CardTitle className="text-base text-neutral-900">{planLabels.free}</CardTitle>
              <CardDescription>先试后买，完整流程</CardDescription>
              <div className="mt-4">
                <span className="text-4xl font-semibold tabular-nums tracking-tight text-neutral-900">¥0</span>
                <span className="text-muted-foreground"> / 体验</span>
              </div>
            </CardHeader>
            <CardContent>
              <ul className="space-y-3">
                {planFeatures.free.map((f) => (
                  <li key={f} className="flex items-start gap-2">
                    <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand-600" />
                    <span className="text-sm text-neutral-600">{f}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
            <CardFooter>
              <FreeCardButton />
            </CardFooter>
          </Card>

          {/* Pro：推荐卡用 brand 细 ring */}
          <Card className="border-brand-200 shadow-none ring-1 ring-brand-200/70">
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle className="text-base text-neutral-900">{planLabels.pro}</CardTitle>
                <Badge>推荐</Badge>
              </div>
              <CardDescription>适合县级司法局 / 法制科室日常审查</CardDescription>
              <div className="mt-4">
                <span className="text-4xl font-semibold tabular-nums tracking-tight text-neutral-900">
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
                    <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand-600" />
                    <span className="text-sm text-neutral-600">{f}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
            <CardFooter>
              <UpgradeButton planTier="pro" items={proItems} />
            </CardFooter>
          </Card>

          {/* Enterprise */}
          <Card className="border-neutral-200/70 shadow-none">
            <CardHeader>
              <CardTitle className="text-base text-neutral-900">{planLabels.enterprise}</CardTitle>
              <CardDescription>适合多部门协同与政府法制机构</CardDescription>
              <div className="mt-4">
                {entSelected && (
                  <>
                    <span className="text-4xl font-semibold tabular-nums tracking-tight text-neutral-900">¥{entSelected.amount_cny}</span>
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
                    <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-brand-600" />
                    <span className="text-sm text-neutral-600">{f}</span>
                  </li>
                ))}
              </ul>
            </CardContent>
            <CardFooter>
              <UpgradeButton planTier="enterprise" items={enterpriseItems} />
            </CardFooter>
          </Card>
        </div>

        <div className="mt-16 text-center text-sm text-neutral-500">
          <p className="flex items-center justify-center gap-1.5">
            <ShieldCheck className="h-4 w-4 text-brand-600" />
            在线支付由支付宝提供安全保障，支付成功即时开通
          </p>
        </div>
      </main>
    </div>
  );
}

/** 顶栏右侧动作：登录态感知。 */
function PricingHeaderActions() {
  const token = useAuthStore((s) => s.token);
  const hydrate = useAuthStore((s) => s.hydrate);
  React.useEffect(() => {
    hydrate();
  }, [hydrate]);

  if (token) {
    return (
      <Link href="/dashboard">
        <Button size="sm" variant="outline">
          进入控制台
        </Button>
      </Link>
    );
  }
  return (
    <div className="flex items-center gap-3">
      <Link
        href="/login?redirect=%2Fpricing"
        className="text-sm text-neutral-600 hover:text-neutral-900"
      >
        登录
      </Link>
      <Link href="/register">
        <Button size="sm">免费开始</Button>
      </Link>
    </div>
  );
}

/** 免费卡按钮：游客去注册，已登录回控制台。 */
function FreeCardButton() {
  const token = useAuthStore((s) => s.token);
  const hydrate = useAuthStore((s) => s.hydrate);
  React.useEffect(() => {
    hydrate();
  }, [hydrate]);

  if (token) {
    return (
      <Link href="/dashboard" className="w-full">
        <Button variant="outline" className="w-full">
          进入控制台
        </Button>
      </Link>
    );
  }
  return (
    <Link href="/register" className="w-full">
      <Button variant="outline" className="w-full">
        免费开始
      </Button>
    </Link>
  );
}

function UpgradeButton({
  planTier,
  items,
}: {
  planTier: PlanTier;
  items: PricingItem[];
}) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const hydrate = useAuthStore((s) => s.hydrate);
  const [selectedPeriod, setSelectedPeriod] = React.useState(items[0]?.period_days ?? 30);
  // 微信支付商户资质未就绪，默认且仅开放支付宝（禁止假入口）
  const [channel, setChannel] = React.useState<PaymentChannel>("alipay");
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
    hydrate();
  }, [hydrate]);

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
    // 游客先注册/登录，回跳回本页
    if (!token) {
      router.push("/login?redirect=%2Fpricing");
      return;
    }
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
      // 商业化埋点：下单成功（order_created）
      track("order_created", {
        plan_tier: planTier,
        period_days: selectedPeriod,
        channel,
      });

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
          variant={channel === "alipay" ? "default" : "outline"}
          size="sm"
          className="flex-1"
          onClick={() => setChannel("alipay")}
        >
          支付宝
        </Button>
        <Button
          variant="outline"
          size="sm"
          className="flex-1 opacity-60"
          disabled
          title="微信支付商户资质开通后可用"
        >
          微信支付（即将开通）
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
        ) : token ? (
          `升级至${planLabels[planTier]} · ¥${selectedItem.amount_cny}`
        ) : (
          `注册后升级${planLabels[planTier]} · ¥${selectedItem.amount_cny}`
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
