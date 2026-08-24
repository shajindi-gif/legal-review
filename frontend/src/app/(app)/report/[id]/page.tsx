"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { fetchReport, fetchReviewDetail } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { ReportViewer } from "@/components/review/ReportViewer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";

export default function ReportPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const token = useAuthStore((s) => s.token);

  const { data: detail } = useQuery({
    queryKey: ["review", id],
    queryFn: () => fetchReviewDetail(id),
    enabled: !!token && !!id,
  });
  const { data: report, isLoading, error } = useQuery({
    queryKey: ["report", id],
    queryFn: () => fetchReport(id),
    enabled: !!token && !!id,
    retry: false,
  });

  const isDone = detail?.status === "completed" || detail?.status === "done";
  const errMsg = error
    ? (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
      "报告尚未生成或当前任务仍在审查中"
    : null;

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6">
      <div className="flex items-center justify-between">
        <Link href="/dashboard">
          <Button variant="ghost" size="sm">
            <ArrowLeft className="h-4 w-4" /> 返回控制台
          </Button>
        </Link>
        {detail?.status && (
          <Badge variant={isDone ? "success" : "warning"}>
            {isDone ? "已完成" : "进行中"}
          </Badge>
        )}
      </div>

      <h1 className="text-2xl font-bold text-gray-900">
        {detail?.title ?? "审查报告"}
      </h1>

      <ReportViewer
        markdown={report?.report_markdown}
        loading={isLoading}
        error={report ? null : errMsg}
      />
    </div>
  );
}
