"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Upload, Clock } from "lucide-react";
import { fetchQuota, fetchReviews } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { UsageCard } from "@/components/dashboard/UsageCard";
import { HistoryTable } from "@/components/dashboard/HistoryTable";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const planLabel = {
  free: "体验版",
  pro: "专业版",
  enterprise: "企业版",
} as const;

export default function DashboardPage() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  const { data: quota, isLoading: quotaLoading } = useQuery({
    queryKey: ["quota"],
    queryFn: fetchQuota,
    enabled: !!token,
  });
  const { data: tasksResp, isLoading: tasksLoading } = useQuery({
    queryKey: ["reviews", { page: 1, page_size: 5 }],
    queryFn: () => fetchReviews({ page: 1, page_size: 5 }),
    enabled: !!token,
  });

  const recent = tasksResp?.items ?? [];
  const total = tasksResp?.total ?? 0;
  const planTier = user?.plan_tier ?? quota?.tier ?? "free";

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">控制台</h1>
          <p className="mt-1 text-sm text-gray-500">
            欢迎回来{user ? `，${user.real_name || user.email}` : ""}，开始一次新的合法性审查。
          </p>
        </div>
        <Link href="/upload">
          <Button>
            <Upload className="h-4 w-4" /> 上传新文件
          </Button>
        </Link>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <UsageCard quota={quota} loading={quotaLoading} />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock className="h-4 w-4 text-brand-600" /> 累计审查
            </CardTitle>
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-semibold text-brand-700">
              {total}
            </span>
            <span className="text-sm text-gray-400"> 次</span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">当前套餐</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-semibold text-brand-700">
              {planLabel[planTier]}
            </span>
            <p className="mt-1 text-xs text-gray-400">
              {planTier === "free"
                ? "可升级至专业版获取更多额度"
                : "感谢您的订阅"}
            </p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex-row items-center justify-between">
          <CardTitle>最近审查</CardTitle>
          <Link
            href="/upload"
            prefetch={false}
            className="text-sm text-brand-600 hover:underline"
          >
            查看全部
          </Link>
        </CardHeader>
        <CardContent>
          <HistoryTable
            reviews={recent}
            loading={tasksLoading}
            emptyHint="还没有审查记录，点击「上传新文件」开始"
          />
        </CardContent>
      </Card>
    </div>
  );
}
