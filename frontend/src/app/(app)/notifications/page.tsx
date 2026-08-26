"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  Bell,
  Check,
  CheckCheck,
  Filter,
  Loader2,
  Inbox,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import {
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { cn } from "@/lib/utils";
import type { Notification, NotificationKind } from "@/types/api";

const PAGE_SIZE = 20;

type FilterMode = "all" | "unread";

const KIND_LABEL: Record<NotificationKind, string> = {
  node_running: "节点进行中",
  node_done: "节点完成",
  node_failed: "节点失败",
  review_done: "审查完成",
  risk_found: "风险提示",
  system: "系统消息",
};

const KIND_TONE: Record<NotificationKind, string> = {
  node_running: "bg-blue-50 text-blue-700 border-blue-200",
  node_done: "bg-emerald-50 text-emerald-700 border-emerald-200",
  node_failed: "bg-red-50 text-red-700 border-red-200",
  review_done: "bg-brand-50 text-brand-700 border-brand-200",
  risk_found: "bg-amber-50 text-amber-700 border-amber-200",
  system: "bg-neutral-100 text-neutral-700 border-neutral-200",
};

function formatFull(iso: string): string {
  const t = new Date(iso);
  if (Number.isNaN(t.getTime())) return "";
  return t.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/**
 * /notifications —— 通知中心全量页（UI-M8.4）。
 *
 * 职责：
 *   - 拉当前用户全部通知（默认 20 / 页 + 全部 / 仅未读 切换）
 *   - 行点击 → 标记已读 + 跳 notification.link（或 /review/{task_id}）
 *   - 顶栏「全部已读」+ 翻页
 *   - 30s 轮询未读数与列表，保证有新通知时即时可见
 */
export default function NotificationsPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const queryClient = useQueryClient();
  const [page, setPage] = React.useState(1);
  const [filter, setFilter] = React.useState<FilterMode>("all");

  const listQuery = useQuery({
    queryKey: [
      "notifications",
      "page",
      { page, page_size: PAGE_SIZE, only_unread: filter === "unread" },
    ],
    queryFn: () =>
      fetchNotifications({
        page,
        page_size: PAGE_SIZE,
        only_unread: filter === "unread",
      }),
    enabled: !!token,
    refetchInterval: 30_000,
    placeholderData: (prev) => prev,
  });

  const unreadQuery = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => fetchUnreadCount(),
    enabled: !!token,
    refetchInterval: 30_000,
  });

  const markOne = useMutation({
    mutationFn: (id: string) => markNotificationRead(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const markAll = useMutation({
    mutationFn: () => markAllNotificationsRead(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });

  const items = listQuery.data?.items ?? [];
  const total = listQuery.data?.total ?? 0;
  const unread = unreadQuery.data?.unread_count ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  function handleItemClick(n: Notification) {
    if (!n.read_at) {
      markOne.mutate(n.id);
    }
    if (n.link) {
      router.push(n.link);
    } else if (n.task_id) {
      router.push(`/review/${n.task_id}`);
    }
  }

  function switchFilter(next: FilterMode) {
    setFilter(next);
    setPage(1);
  }

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 px-4 py-6 sm:px-6 lg:px-8">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-sm text-neutral-500">
            <Bell className="h-4 w-4" />
            通知中心
          </div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-neutral-900">
            全部通知
          </h1>
          <p className="mt-1 text-meta text-neutral-500">
            审查节点进度会在此汇总。未读 {unread} 条 / 共 {total} 条。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => markAll.mutate()}
            disabled={unread === 0 || markAll.isPending}
            data-testid="notifications-page-mark-all"
          >
            {markAll.isPending ? (
              <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
            ) : (
              <CheckCheck className="mr-1 h-3.5 w-3.5" />
            )}
            全部已读
          </Button>
        </div>
      </header>

      <div className="flex items-center gap-2">
        <Filter className="h-4 w-4 text-neutral-400" />
        <div className="inline-flex rounded-lg border border-neutral-200 bg-white p-0.5 text-sm">
          {(
            [
              { value: "all", label: "全部" },
              { value: "unread", label: "仅未读" },
            ] as { value: FilterMode; label: string }[]
          ).map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => switchFilter(opt.value)}
              className={cn(
                "rounded-md px-3 py-1.5 transition-colors",
                filter === opt.value
                  ? "bg-brand-600 text-white"
                  : "text-neutral-600 hover:bg-neutral-50",
              )}
              data-testid={`notifications-filter-${opt.value}`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <Card>
        <CardContent className="p-0">
          {listQuery.isLoading && (
            <div className="flex items-center justify-center gap-2 px-4 py-12 text-meta text-neutral-500">
              <Loader2 className="h-4 w-4 animate-spin" />
              加载通知…
            </div>
          )}

          {!listQuery.isLoading && items.length === 0 && (
            <div className="px-4 py-10">
              <EmptyState
                icon={<Inbox className="h-8 w-8" />}
                title={filter === "unread" ? "没有未读通知" : "暂无通知"}
                description={
                  filter === "unread"
                    ? "所有通知都已处理，刷新一下试试？"
                    : "审查任务启动后，节点进度会在这里出现。"
                }
              />
            </div>
          )}

          {!listQuery.isLoading && items.length > 0 && (
            <ul className="divide-y divide-neutral-100" data-testid="notifications-list">
              {items.map((n) => (
                <li key={n.id}>
                  <button
                    type="button"
                    onClick={() => handleItemClick(n)}
                    className={cn(
                      "flex w-full items-start gap-4 px-4 py-4 text-left transition-colors hover:bg-neutral-50",
                      !n.read_at && "bg-brand-50/40",
                    )}
                    data-testid="notifications-item"
                  >
                    <span
                      className={cn(
                        "mt-0.5 inline-flex shrink-0 items-center rounded border px-2 py-0.5 text-[11px] font-medium",
                        KIND_TONE[n.kind] ?? KIND_TONE.system,
                      )}
                    >
                      {KIND_LABEL[n.kind] ?? n.kind}
                    </span>
                    <span className="min-w-0 flex-1">
                      <span
                        className={cn(
                          "block text-sm",
                          n.read_at ? "text-neutral-700" : "font-semibold text-neutral-900",
                        )}
                      >
                        {n.title}
                      </span>
                      {n.body && (
                        <span className="mt-1 block text-meta text-neutral-500">
                          {n.body}
                        </span>
                      )}
                      <span className="mt-1 block text-[11px] text-neutral-400">
                        {formatFull(n.created_at)}
                        {n.task_id && (
                          <>
                            {" · "}
                            <Link
                              href={`/review/${n.task_id}`}
                              prefetch={false}
                              onClick={(e) => e.stopPropagation()}
                              className="text-brand-600 hover:underline"
                            >
                              查看任务
                            </Link>
                          </>
                        )}
                      </span>
                    </span>
                    <span className="ml-2 flex shrink-0 items-center gap-2 self-center">
                      {n.read_at ? (
                        <Check className="h-3.5 w-3.5 text-neutral-300" />
                      ) : (
                        <span className="inline-block h-2 w-2 rounded-full bg-brand-500" />
                      )}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-meta text-neutral-600">
          <span>
            第 {page} / {totalPages} 页 · 每页 {PAGE_SIZE} 条
          </span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page === 1 || listQuery.isFetching}
            >
              上一页
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages || listQuery.isFetching}
            >
              下一页
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
