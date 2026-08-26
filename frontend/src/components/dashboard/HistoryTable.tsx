"use client";

import * as React from "react";
import Link from "next/link";
import type { ReviewStatus, TaskSummary } from "@/types/api";
import { StatusBadge, isFinished } from "@/components/ui/status-badge";
import { formatDateTime } from "@/lib/utils";

export function HistoryTable({
  reviews,
  loading,
  emptyHint = "暂无审查记录",
}: {
  reviews: TaskSummary[];
  loading?: boolean;
  emptyHint?: string;
}) {
  if (loading) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-gray-400">
        加载中…
      </div>
    );
  }
  if (reviews.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-gray-400">
        {emptyHint}
      </div>
    );
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
            <th className="px-3 py-2 font-medium">标题</th>
            <th className="px-3 py-2 font-medium">状态</th>
            <th className="px-3 py-2 font-medium">当前节点</th>
            <th className="px-3 py-2 font-medium">提交时间</th>
            <th className="px-3 py-2 font-medium">操作</th>
          </tr>
        </thead>
        <tbody>
          {reviews.map((r) => {
            const done = isFinished(r.status);
            return (
              <tr key={r.id} className="border-b border-gray-100 last:border-0">
                <td className="max-w-[260px] truncate px-3 py-2 font-medium text-gray-800">
                  {r.title}
                </td>
                <td className="px-3 py-2">
                  <StatusBadge status={r.status} withDot />
                </td>
                <td className="px-3 py-2 text-gray-500">
                  {r.current_node ?? "—"}
                </td>
                <td className="px-3 py-2 text-gray-500">
                  {formatDateTime(r.submitted_at)}
                </td>
                <td className="px-3 py-2">
                  {done ? (
                    <Link
                      href={`/report/${r.id}`}
                      prefetch={false}
                      className="text-brand-600 hover:underline"
                    >
                      查看报告
                    </Link>
                  ) : (
                    <Link
                      href={`/review/${r.id}`}
                      prefetch={false}
                      className="text-brand-600 hover:underline"
                    >
                      实时跟踪
                    </Link>
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
