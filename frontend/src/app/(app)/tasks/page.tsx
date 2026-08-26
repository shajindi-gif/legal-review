"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  Clock as ClockIcon,
  Search,
  Filter,
  ChevronRight,
  XCircle,
  Plus,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { fetchReviews } from "@/lib/api";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge, isFinished, isInProgress } from "@/components/ui/status-badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { formatDateTime, formatRelativeTime } from "@/lib/utils";
import type { ReviewStatus, TaskSummary } from "@/types/api";

/**
 * /tasks —— Tasks 中心页（UI-M5.3）。
 *
 * 职责：列出当前用户的所有审查任务，支持：
 *   - 4 个状态统计（总数 / 进行中 / 已完成 / 失败）
 *   - 状态过滤（chips + select 同步）
 *   - 标题搜索
 *   - 进行中任务存在时自动每 3s 刷新
 *   - 行点击进入 /review/{id}；已完成的 task 行直接给"查看报告"入口
 *
 * 数据源：`fetchReviews` —— 与 Home / Documents / Reports 共享同一份 React Query 缓存。
 *   通过 queryKey `["reviews", { page, page_size, status? }]` 与其他页保持一致：
 *   - NewReviewForm 成功 → invalidate ["reviews"]，本页自动更新
 *   - Review SSE complete → invalidate ["reviews"]，本页自动更新
 */

type StatusFilter = "all" | ReviewStatus | "in_progress" | "finished" | "failed";

const FILTER_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "in_progress", label: "进行中" },
  { value: "finished", label: "已完成" },
  { value: "failed", label: "失败" },
  { value: "pending", label: "排队" },
  { value: "running", label: "审查" },
  { value: "parsing", label: "解析" },
];

function matchesFilter(s: ReviewStatus, f: StatusFilter): boolean {
  if (f === "all") return true;
  if (f === "in_progress") return isInProgress(s);
  if (f === "finished") return isFinished(s);
  if (f === "failed") return s === "failed";
  return s === f;
}

const PAGE_SIZE = 50;

export default function TasksPage() {
  const token = useAuthStore((s) => s.token);
  const [query, setQuery] = React.useState("");
  const [filter, setFilter] = React.useState<StatusFilter>("all");

  // 拉当前页（无 status 过滤；过滤在客户端做 —— 简单、零额外请求、避免 N 次翻页）
  const tasksQ = useQuery({
    queryKey: ["reviews", { page: 1, page_size: PAGE_SIZE }],
    queryFn: () => fetchReviews({ page: 1, page_size: PAGE_SIZE }),
    enabled: !!token,
    refetchInterval: (q) => {
      // 任意一条任务在 in-progress 状态则每 3s 心跳；否则停止
      const data = q.state.data as { items?: TaskSummary[] } | undefined;
      const items = data?.items ?? [];
      return items.some((t) => isInProgress(t.status)) ? 3_000 : false;
    },
  });

  const items = tasksQ.data?.items ?? [];
  const total = tasksQ.data?.total ?? 0;

  // 是否有进行中任务 —— 决定是否显示"自动刷新"提示
  const hasInProgress = React.useMemo(
    () => items.some((t) => isInProgress(t.status)),
    [items],
  );

  // 过滤 + 搜索
  const visible = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    return items.filter((t) => {
      if (!matchesFilter(t.status, filter)) return false;
      if (!q) return true;
      return (
        t.title.toLowerCase().includes(q) ||
        t.id.toLowerCase().includes(q) ||
        (t.current_node ?? "").toLowerCase().includes(q)
      );
    });
  }, [items, query, filter]);

  // 4 个统计 —— 限定在当前页（total 是后端给的真实总数，但分类计数我们只看当前页更直观）
  const stats = React.useMemo(() => {
    let inProgress = 0;
    let finished = 0;
    let failed = 0;
    for (const t of items) {
      if (isFinished(t.status)) finished++;
      else if (t.status === "failed") failed++;
      else inProgress++;
    }
    return { total, inProgress, finished, failed };
  }, [items, total]);

  const loading = tasksQ.isLoading;

  return (
    <div className="flex flex-col gap-6">
      <Header />

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          icon={<Activity className="h-4 w-4" />}
          label="总任务"
          value={stats.total}
          tone="brand"
          loading={loading}
        />
        <StatCard
          icon={<ClockIcon className="h-4 w-4" />}
          label="进行中"
          value={stats.inProgress}
          tone="warning"
          loading={loading}
          hint={hasInProgress ? "自动刷新中" : undefined}
        />
        <StatCard
          icon={<CheckCircle2 className="h-4 w-4" />}
          label="已完成"
          value={stats.finished}
          tone="success"
          loading={loading}
        />
        <StatCard
          icon={<XCircle className="h-4 w-4" />}
          label="失败"
          value={stats.failed}
          tone="danger"
          loading={loading}
        />
      </div>

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <Activity className="h-4 w-4 text-brand-600" /> 任务列表
              <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[11px] text-neutral-600">
                {visible.length} / {items.length}
              </span>
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-neutral-400" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="按标题 / 节点 / ID 搜索…"
                  className="h-9 w-56 pl-7 text-sm"
                  data-testid="tasks-search"
                />
              </div>
              <div className="flex items-center gap-1 text-meta">
                <Filter className="h-3.5 w-3.5" />
                <select
                  value={filter}
                  onChange={(e) => setFilter(e.target.value as StatusFilter)}
                  className="h-9 rounded-md border border-neutral-200 bg-white px-2 text-sm focus:border-brand-400 focus:outline-none"
                  data-testid="tasks-status-filter"
                >
                  {FILTER_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col gap-2" data-testid="tasks-skeleton">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg border border-neutral-100 p-3"
                >
                  <Skeleton className="h-9 w-9 rounded-md" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-2/5" />
                    <Skeleton className="h-3 w-1/3" />
                  </div>
                  <Skeleton className="h-6 w-20" />
                </div>
              ))}
            </div>
          ) : items.length === 0 ? (
            <EmptyState
              icon={<Activity className="h-7 w-7" />}
              title="还没有任何审查任务"
              description="上传合同、法规或企业材料，LegalAI 会在此列出所有审查任务。"
              action={
                <Link href="/upload" prefetch={false}>
                  <Button>
                    <Plus className="h-4 w-4" /> 新建审查
                  </Button>
                </Link>
              }
            />
          ) : visible.length === 0 ? (
            <EmptyState
              icon={<Search className="h-6 w-6" />}
              title="没有匹配的任务"
              description="试着调整状态过滤或搜索关键词。"
            />
          ) : (
            <ul
              className="divide-y divide-neutral-100"
              data-testid="tasks-list"
            >
              {visible.map((t) => (
                <TaskRow key={t.id} task={t} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Header() {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-page-title">Tasks</h1>
        <p className="mt-1 text-secondary">
          所有审查任务集中管理：跟踪进度、查看报告、重跑失败任务。
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Link href="/upload" prefetch={false}>
          <Button>
            <Plus className="h-4 w-4" /> 新建审查
          </Button>
        </Link>
      </div>
    </div>
  );
}

function StatCard({
  icon,
  label,
  value,
  tone,
  loading,
  hint,
}: {
  icon: React.ReactNode;
  label: string;
  value: number;
  tone: "brand" | "success" | "warning" | "danger";
  loading?: boolean;
  hint?: string;
}) {
  const toneCls: Record<typeof tone, string> = {
    brand: "bg-brand-50 text-brand-700",
    success: "bg-emerald-50 text-emerald-700",
    warning: "bg-amber-50 text-amber-700",
    danger: "bg-red-50 text-red-700",
  };
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg ${toneCls[tone]}`}
        >
          {icon}
        </div>
        <div className="min-w-0">
          {loading ? (
            <Skeleton className="h-6 w-12" />
          ) : (
            <div className="text-2xl font-semibold leading-none text-neutral-900">
              {value}
            </div>
          )}
          <p className="mt-1 text-xs text-neutral-500">{label}</p>
          {hint ? (
            <p className="mt-0.5 text-[10px] text-amber-600">{hint}</p>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

function TaskRow({ task }: { task: TaskSummary }) {
  const done = isFinished(task.status);
  const inProgress = isInProgress(task.status);
  const href = done ? `/report/${task.id}` : `/review/${task.id}`;
  return (
    <li>
      <Link
        href={href}
        prefetch={false}
        className="group flex items-center gap-3 py-3 transition-colors hover:bg-neutral-50"
        data-testid={`task-row-${task.id}`}
      >
        <div
          className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${
            inProgress ? "bg-amber-50 text-amber-700" : "bg-brand-50 text-brand-700"
          }`}
        >
          {done ? (
            <CheckCircle2 className="h-4 w-4" />
          ) : task.status === "failed" ? (
            <AlertTriangle className="h-4 w-4" />
          ) : (
            <Activity className="h-4 w-4" />
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate text-sm font-medium text-neutral-900">
              {task.title}
            </span>
            {inProgress && task.iteration > 0 ? (
              <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] text-amber-700">
                迭代 {task.iteration}/{task.max_iteration}
              </span>
            ) : null}
          </div>
          <p className="mt-0.5 text-meta truncate">
            {task.current_node ? (
              <>
                <span className="text-neutral-700">{task.current_node}</span>
                <span className="mx-2 text-neutral-300">·</span>
              </>
            ) : null}
            提交于
            <span className="ml-1" title={formatDateTime(task.submitted_at)}>
              {formatRelativeTime(task.submitted_at)}
            </span>
            <span className="mx-2 text-neutral-300">·</span>
            <span className="font-mono text-[10px] text-neutral-400">
              {task.id.slice(0, 8)}
            </span>
          </p>
        </div>
        <StatusBadge status={task.status} withDot={!inProgress} withSpinner={inProgress} />
        <span className="ml-2 hidden text-meta text-brand-600 group-hover:inline-flex">
          {done ? "查看报告" : "跟踪"}
          <ChevronRight className="ml-0.5 h-3.5 w-3.5" />
        </span>
      </Link>
    </li>
  );
}
