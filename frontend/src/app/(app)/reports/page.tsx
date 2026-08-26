"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  Search,
  FileText,
  CalendarClock,
  CheckCircle2,
  ChevronRight,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { fetchReviews } from "@/lib/api";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { StatusBadge, isFinished } from "@/components/ui/status-badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";
import type { TaskSummary } from "@/types/api";

/**
 * /reports —— Reports 中心页（UI-M5.4）。
 *
 * 职责：列出已生成的审查报告。
 *   - 数据源：fetchReviews({status: "completed"})，再用 isFinished() 在客户端做兜底
 *     （防御后端返回 "done" 混入）；与 Home / Tasks / Documents 共享 React Query 缓存。
 *   - 行点 → /report/{id} 打开已有的报告详情页。
 *   - 排序：按 completed_at 倒序（无 completed_at 时回退到 submitted_at）。
 *
 * 之所以不做分页：
 *   - 已完成任务通常 < 50 条，首页足够覆盖；
 *   - 简化 UI；后续若单用户报告数 > 50 再补分页。
 */

const PAGE_SIZE = 50;

export default function ReportsPage() {
  const token = useAuthStore((s) => s.token);
  const [query, setQuery] = React.useState("");

  // 用后端 status 过滤 = "completed"；客户端再做 isFinished 兜底（处理 "done"）
  const reviewsQ = useQuery({
    queryKey: ["reviews", { page: 1, page_size: PAGE_SIZE, status: "completed" }],
    queryFn: () => fetchReviews({ page: 1, page_size: PAGE_SIZE, status: "completed" }),
    enabled: !!token,
  });

  const all = (reviewsQ.data?.items ?? []).filter((t) => isFinished(t.status));
  const total = reviewsQ.data?.total ?? 0;
  const loading = reviewsQ.isLoading;

  // 排序：completed_at 降序（无则 submitted_at）
  const sorted = React.useMemo(() => {
    return [...all].sort((a, b) => {
      const ta = new Date(a.completed_at ?? a.submitted_at).getTime();
      const tb = new Date(b.completed_at ?? b.submitted_at).getTime();
      return tb - ta;
    });
  }, [all]);

  // 搜索（标题）
  const visible = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter(
      (t) =>
        t.title.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        (t.current_node ?? "").toLowerCase().includes(q),
    );
  }, [sorted, query]);

  // 30 天内报告数（轻统计）
  const recent30d = React.useMemo(() => {
    const cutoff = Date.now() - 30 * 24 * 60 * 60 * 1000;
    return all.filter(
      (t) => new Date(t.completed_at ?? t.submitted_at).getTime() >= cutoff,
    ).length;
  }, [all]);

  return (
    <div className="flex flex-col gap-6">
      <Header total={all.length} recent30d={recent30d} />

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <BarChart3 className="h-4 w-4 text-brand-600" /> 报告列表
              <Badge variant="secondary">{visible.length}</Badge>
            </CardTitle>
            <div className="relative">
              <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-neutral-400" />
              <Input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="按标题 / ID 搜索…"
                className="h-9 w-56 pl-7 text-sm"
                data-testid="reports-search"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col gap-2" data-testid="reports-skeleton">
              {Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg border border-neutral-100 p-3"
                >
                  <Skeleton className="h-10 w-10 rounded-md" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-2/5" />
                    <Skeleton className="h-3 w-1/4" />
                  </div>
                  <Skeleton className="h-6 w-20" />
                </div>
              ))}
            </div>
          ) : all.length === 0 ? (
            <EmptyState
              icon={<FileText className="h-7 w-7" />}
              title="还没有任何报告"
              description="审查任务完成后，报告会自动出现在这里。"
              action={
                <Link
                  href="/upload"
                  prefetch={false}
                  className="text-sm text-brand-600 hover:underline"
                >
                  前往新建审查 →
                </Link>
              }
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<Search className="h-6 w-6" />}
              title="没有匹配的报告"
              description="试着调整搜索关键词。"
            />
          ) : (
            <ul
              className="divide-y divide-neutral-100"
              data-testid="reports-list"
            >
              {visible.map((t) => (
                <ReportRow key={t.id} task={t} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <p className="text-meta text-center text-xs text-neutral-400">
        {total > all.length
          ? `已显示最近 ${all.length} 条报告（后端共 ${total} 条），后续将支持分页。`
          : `共 ${all.length} 条报告。`}
      </p>
    </div>
  );
}

function Header({ total, recent30d }: { total: number; recent30d: number }) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-page-title">Reports</h1>
        <p className="mt-1 text-secondary">
          已完成审查的结构化报告集合。共 {total} 份，近 30 天新增 {recent30d} 份。
        </p>
      </div>
    </div>
  );
}

function ReportRow({ task }: { task: TaskSummary }) {
  const finishedAt = task.completed_at ?? task.submitted_at;
  // 审查耗时：submitted_at → completed_at
  const duration =
    task.started_at && task.completed_at
      ? formatDuration(
          new Date(task.completed_at).getTime() - new Date(task.started_at).getTime(),
        )
      : null;

  return (
    <li>
      <Link
        href={`/report/${task.id}`}
        prefetch={false}
        className="group flex items-center gap-3 py-3 transition-colors hover:bg-neutral-50"
        data-testid={`report-row-${task.id}`}
      >
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-emerald-50 text-emerald-700">
          <CheckCircle2 className="h-4 w-4" />
        </div>
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-neutral-900">
            {task.title}
          </p>
          <p className="mt-0.5 flex flex-wrap items-center gap-x-2 text-meta">
            <CalendarClock className="h-3 w-3 shrink-0" />
            <span title={formatDateTime(finishedAt)}>
              {formatRelativeTime(finishedAt)}
            </span>
            {duration ? (
              <>
                <span className="text-neutral-300">·</span>
                <span>耗时 {duration}</span>
              </>
            ) : null}
            <span className="text-neutral-300">·</span>
            <span className="font-mono text-[10px] text-neutral-400">
              {task.id.slice(0, 8)}
            </span>
          </p>
        </div>
        <StatusBadge status={task.status} withDot />
        <ChevronRight className="ml-2 h-4 w-4 shrink-0 text-neutral-300 transition-colors group-hover:text-brand-600" />
      </Link>
    </li>
  );
}

function formatDuration(ms: number): string {
  if (ms < 0 || !Number.isFinite(ms)) return "—";
  const sec = Math.round(ms / 1000);
  if (sec < 60) return `${sec} 秒`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} 分 ${sec % 60} 秒`;
  const hr = Math.floor(min / 60);
  return `${hr} 时 ${min % 60} 分`;
}
