"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { Bell, Check, Loader2 } from "lucide-react";
import {
  fetchNotifications,
  fetchUnreadCount,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/lib/api";
import type { Notification } from "@/types/api";
import { cn } from "@/lib/utils";

const REFRESH_INTERVAL_MS = 30_000;

const KIND_LABEL: Record<Notification["kind"], string> = {
  node_running: "节点进行中",
  node_done: "节点完成",
  node_failed: "节点失败",
  review_done: "审查完成",
  risk_found: "风险提示",
  system: "系统消息",
};

const KIND_TONE: Record<Notification["kind"], string> = {
  node_running: "bg-blue-50 text-blue-700 border-blue-200",
  node_done: "bg-emerald-50 text-emerald-700 border-emerald-200",
  node_failed: "bg-red-50 text-red-700 border-red-200",
  review_done: "bg-brand-50 text-brand-700 border-brand-200",
  risk_found: "bg-amber-50 text-amber-700 border-amber-200",
  system: "bg-neutral-100 text-neutral-700 border-neutral-200",
};

function formatRelative(iso: string): string {
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const diff = Date.now() - t;
  if (diff < 60_000) return "刚刚";
  if (diff < 3_600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86_400_000) return `${Math.floor(diff / 3_600_000)} 小时前`;
  return `${Math.floor(diff / 86_400_000)} 天前`;
}

/**
 * 通知中心铃铛（UI-M8.3）。
 * - 30s 轮询未读数显示 badge
 * - 点击展开下拉，预览 5 条最新 + 「全部已读」+ 跳全部页
 * - 跳转 link 走 notification.link，否则跳 /notifications
 */
export function NotificationBell() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [open, setOpen] = React.useState(false);
  const [markingAll, setMarkingAll] = React.useState(false);

  const unreadQuery = useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => fetchUnreadCount(),
    refetchInterval: REFRESH_INTERVAL_MS,
    staleTime: 10_000,
  });

  const listQuery = useQuery({
    queryKey: ["notifications", "preview", { page: 1, page_size: 5 }],
    queryFn: () => fetchNotifications({ page: 1, page_size: 5 }),
    enabled: open,
    staleTime: 5_000,
  });

  const items = listQuery.data?.items ?? [];
  const unread = unreadQuery.data?.unread_count ?? 0;

  async function handleMarkAll() {
    if (markingAll) return;
    setMarkingAll(true);
    try {
      await markAllNotificationsRead();
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["notifications"] }),
        queryClient.refetchQueries({ queryKey: ["notifications", "unread-count"] }),
      ]);
    } finally {
      setMarkingAll(false);
    }
  }

  async function handleItemClick(n: Notification) {
    if (!n.read_at) {
      try {
        await markNotificationRead(n.id);
        queryClient.invalidateQueries({ queryKey: ["notifications"] });
      } catch {
        // 标记失败不影响跳转
      }
    }
    setOpen(false);
    if (n.link) {
      router.push(n.link);
    } else {
      router.push("/notifications");
    }
  }

  return (
    <DropdownMenu.Root open={open} onOpenChange={setOpen}>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label="通知中心"
          title="通知中心"
          className={cn(
            "relative inline-flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 transition-colors hover:bg-neutral-100",
          )}
          data-testid="notification-bell"
        >
          <Bell className="h-[18px] w-[18px]" />
          {unread > 0 && (
            <span
              data-testid="notification-bell-badge"
              className="absolute -right-0.5 -top-0.5 inline-flex min-w-[18px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-semibold leading-[18px] text-white"
            >
              {unread > 99 ? "99+" : unread}
            </span>
          )}
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 w-[360px] overflow-hidden rounded-lg border border-neutral-200 bg-white shadow-lg"
          data-testid="notification-bell-content"
        >
          <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3">
            <div>
              <div className="text-sm font-semibold text-neutral-900">通知</div>
              <div className="text-meta text-neutral-500">
                {unread > 0 ? `${unread} 条未读` : "全部已读"}
              </div>
            </div>
            <button
              type="button"
              onClick={handleMarkAll}
              disabled={unread === 0 || markingAll}
              className={cn(
                "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs",
                unread === 0
                  ? "cursor-not-allowed text-neutral-400"
                  : "text-brand-700 hover:bg-brand-50",
              )}
              data-testid="notification-bell-mark-all"
            >
              {markingAll ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Check className="h-3.5 w-3.5" />
              )}
              全部已读
            </button>
          </div>

          <div className="max-h-[420px] overflow-y-auto">
            {listQuery.isLoading && (
              <div className="flex items-center justify-center gap-2 px-4 py-8 text-meta text-neutral-500">
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
                加载中…
              </div>
            )}
            {!listQuery.isLoading && items.length === 0 && (
              <div className="px-4 py-10 text-center text-meta text-neutral-500">
                暂无通知
              </div>
            )}
            {!listQuery.isLoading &&
              items.map((n) => (
                <button
                  type="button"
                  key={n.id}
                  onClick={() => handleItemClick(n)}
                  className={cn(
                    "flex w-full items-start gap-3 border-b border-neutral-100 px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-neutral-50",
                    !n.read_at && "bg-brand-50/40",
                  )}
                  data-testid="notification-bell-item"
                >
                  <span
                    className={cn(
                      "mt-0.5 inline-flex shrink-0 items-center rounded border px-1.5 py-0.5 text-[10px] font-medium",
                      KIND_TONE[n.kind] ?? KIND_TONE.system,
                    )}
                  >
                    {KIND_LABEL[n.kind] ?? n.kind}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className={cn(
                        "block truncate text-sm",
                        n.read_at ? "text-neutral-700" : "font-medium text-neutral-900",
                      )}
                    >
                      {n.title}
                    </span>
                    {n.body && (
                      <span className="mt-0.5 line-clamp-2 block text-meta text-neutral-500">
                        {n.body}
                      </span>
                    )}
                    <span className="mt-1 block text-[11px] text-neutral-400">
                      {formatRelative(n.created_at)}
                    </span>
                  </span>
                  {!n.read_at && (
                    <span className="mt-1.5 inline-block h-2 w-2 shrink-0 rounded-full bg-brand-500" />
                  )}
                </button>
              ))}
          </div>

          <div className="border-t border-neutral-100 bg-neutral-50/50 px-4 py-2">
            <Link
              href="/notifications"
              prefetch={false}
              onClick={() => setOpen(false)}
              className="block text-center text-meta font-medium text-brand-700 hover:text-brand-800"
              data-testid="notification-bell-view-all"
            >
              查看全部通知 →
            </Link>
          </div>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  );
}
