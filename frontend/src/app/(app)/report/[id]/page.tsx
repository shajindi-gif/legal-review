"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  PanelRight,
  PanelRightClose,
} from "lucide-react";
import { fetchReport, fetchReviewDetail } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { ReportViewer } from "@/components/review/ReportViewer";
import { FeedbackBar } from "@/components/ui/feedback-bar";
import {
  EvidencePanel,
  buildDefaultEvidenceGroups,
} from "@/components/review/EvidencePanel";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

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

  // Context Panel：报告页也常驻，按钮可折叠
  const [panelOpen, setPanelOpen] = React.useState(true);
  const evidenceGroups = buildDefaultEvidenceGroups(report?.evidences ?? []);

  return (
    <div className="flex h-full gap-4">
      <div
        className={cn(
          "flex min-w-0 flex-1 flex-col gap-6",
        )}
        data-testid="report-main"
      >
        <div className="flex items-center justify-between">
          <Link href="/dashboard">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="h-4 w-4" /> 返回 Home
            </Button>
          </Link>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPanelOpen((v) => !v)}
              aria-pressed={panelOpen}
            >
              {panelOpen ? (
                <>
                  <PanelRightClose className="h-4 w-4" /> 隐藏证据
                </>
              ) : (
                <>
                  <PanelRight className="h-4 w-4" /> 证据
                </>
              )}
            </Button>
            {detail?.status && (
              <Badge variant={isDone ? "success" : "warning"}>
                {isDone ? "已完成" : "进行中"}
              </Badge>
            )}
          </div>
        </div>

        <h1 className="text-page-title">
          {detail?.title ?? "审查报告"}
        </h1>

        <ReportViewer
          markdown={report?.report_markdown}
          loading={isLoading}
          error={report ? null : errMsg}
        />

        {/* 报告反馈：仅当报告存在时显示 */}
        {report && id ? (
          <FeedbackBar
            targetId={`report:${id}`}
            targetKind="report"
            targetLabel={detail?.title ?? `报告 #${id}`}
          />
        ) : null}
      </div>

      <EvidencePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        groups={evidenceGroups}
      />
    </div>
  );
}
