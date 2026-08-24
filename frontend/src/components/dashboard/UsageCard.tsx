"use client";

import * as React from "react";
import type { PlanTier, Quota } from "@/types/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const planLabel: Record<PlanTier, string> = {
  free: "体验版",
  pro: "专业版",
  enterprise: "企业版",
};

export function UsageCard({
  quota,
  loading,
}: {
  quota?: Quota;
  loading?: boolean;
}) {
  if (!quota) {
    return (
      <Card className="w-full">
        <CardHeader>
          <CardTitle>审查配额</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="h-4 w-24 animate-pulse rounded bg-gray-100" />
        </CardContent>
      </Card>
    );
  }

  const used = quota.used_today;
  const total = quota.quota_daily;
  const remaining = quota.unlimited ? Number.POSITIVE_INFINITY : quota.remaining;
  const pct = quota.unlimited
    ? 0
    : total > 0
      ? Math.min(100, Math.round((used / total) * 100))
      : 0;
  const warn = !quota.unlimited && pct >= 80;

  return (
    <Card className="w-full">
      <CardHeader className="flex-row items-center justify-between">
        <CardTitle>审查配额</CardTitle>
        <Badge variant="secondary">{planLabel[quota.tier]}</Badge>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        {loading ? (
          <div className="h-4 w-24 animate-pulse rounded bg-gray-100" />
        ) : quota.unlimited ? (
          <div className="flex items-end justify-between">
            <span className="text-2xl font-semibold text-brand-700">
              {used}
              <span className="text-base text-gray-400"> / ∞</span>
            </span>
            <span className="text-sm text-gray-500">今日不限次</span>
          </div>
        ) : (
          <div className="flex items-end justify-between">
            <span className="text-2xl font-semibold text-brand-700">
              {used}
              <span className="text-base text-gray-400"> / {total}</span>
            </span>
            <span className={cn("text-sm", warn ? "text-red-600" : "text-gray-500")}>
              已用 {pct}%
            </span>
          </div>
        )}
        <Progress value={pct} />
        <p className="text-xs text-gray-500">
          {quota.unlimited
            ? "Pro / Enterprise 套餐今日不限次"
            : `套餐内剩余 ${Math.max(0, remaining)} 次审查额度${
                quota.reset_date ? `（重置日：${quota.reset_date}）` : ""
              }`}
        </p>
      </CardContent>
    </Card>
  );
}
