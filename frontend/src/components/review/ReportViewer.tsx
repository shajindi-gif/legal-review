"use client";

import * as React from "react";
import { TrustBadge } from "@/components/ui/trust-badge";
import { Skeleton } from "@/components/ui/skeleton";
import { MarkdownContent } from "@/components/ui/markdown-content";

/**
 * ReportViewer —— 审查意见书渲染器。
 *
 * 旧实现：`dangerouslySetInnerHTML` + 手写 markdown 解析（§D 删除项）。
 * 中间实现：react-markdown + rehype-sanitize（§M3/M6 阶段）。
 * 当前实现：MarkdownContent（UI-M9.1）：开启 GFM，XSS-safe，
 * 报告尺寸 lg（标题更大、行高更松），无 TrustBadge 缺位。
 */

export function ReportViewer({
  markdown,
  loading,
  error,
}: {
  markdown?: string;
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <h2 className="text-lg font-semibold text-brand-700">审查意见书</h2>
          <TrustBadge kind="ai" />
        </div>
      </div>
      {loading ? (
        <div className="space-y-3 rounded-lg border border-neutral-200 bg-white p-6">
          <Skeleton className="h-5 w-1/2" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="mt-3 h-5 w-1/3" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
        </div>
      ) : error ? (
        <div
          role="alert"
          className="flex h-40 items-center justify-center rounded-lg border border-amber-200 bg-amber-50 text-sm text-amber-700"
        >
          {error}
        </div>
      ) : markdown ? (
        <article
          data-testid="report-markdown"
          className="rounded-lg border border-neutral-200 bg-white p-6"
        >
          <MarkdownContent size="lg">{markdown}</MarkdownContent>
        </article>
      ) : (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-neutral-200 text-sm text-neutral-400">
          报告暂未生成
        </div>
      )}
    </div>
  );
}
