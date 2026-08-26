"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Bell,
  Command as CommandIcon,
  CornerDownLeft,
  FileText,
  Gavel,
  Home,
  ListChecks,
  MessageSquareQuote,
  Search,
  Sparkles,
  Upload,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { fetchGlobalSearch } from "@/lib/api";
import type {
  SearchDocumentHit,
  SearchReportHit,
  SearchResponse,
  SearchTaskHit,
} from "@/types/api";
import { useAuthStore } from "@/lib/auth";
import { cn, formatRelativeTime } from "@/lib/utils";

/**
 * UI-M12 ⌘K 全局搜索 / 跳转面板。
 *
 * 设计原则：
 * - 复用 @radix-ui/react-dialog（已在依赖中），与 OnboardingDialog 同款
 * - 单端点聚合 tasks / documents / reports（与后端 /api/v1/search 对齐）
 * - 空查询 → 渲染静态"快捷导航"，避免空状态空洞
 * - 键盘：↑↓ 选中、Enter 跳转、Esc 关闭、⌘K 关闭/打开
 * - 选中态用 data-active（与 keyboard navigation 同步）
 */

interface QuickItem {
  id: string;
  label: string;
  hint: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  adminOnly?: boolean;
}

const QUICK_ITEMS: QuickItem[] = [
  { id: "home", label: "Home", hint: "返回工作台", href: "/dashboard", icon: Home },
  { id: "upload", label: "上传审查", hint: "新建 11 节点审查流水线", href: "/upload", icon: Upload },
  { id: "assistant", label: "Assistant", hint: "进入专业提问工作台", href: "/assistant", icon: Sparkles },
  { id: "documents", label: "Documents", hint: "查看已上传文件", href: "/documents", icon: FileText },
  { id: "tasks", label: "Tasks", hint: "查看全部审查任务", href: "/tasks", icon: Activity },
  { id: "reports", label: "Reports", hint: "已生成的审查报告", href: "/reports", icon: BarChart3 },
  { id: "notifications", label: "Notifications", hint: "查看系统通知", href: "/notifications", icon: Bell },
  { id: "feedback", label: "Feedback", hint: "我提交的反馈与处理进度", href: "/dashboard/feedback", icon: MessageSquareQuote },
  { id: "admin", label: "管理后台", hint: "用户 / 审查统计", href: "/admin", icon: ListChecks, adminOnly: true },
];

type FlatItem =
  | { kind: "quick"; item: QuickItem }
  | { kind: "task"; item: SearchTaskHit }
  | { kind: "doc"; item: SearchDocumentHit }
  | { kind: "report"; item: SearchReportHit };

interface CommandPaletteProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CommandPalette({ open, onOpenChange }: CommandPaletteProps) {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const [q, setQ] = React.useState("");
  const [debouncedQ, setDebouncedQ] = React.useState("");
  const [activeIndex, setActiveIndex] = React.useState(0);
  const inputRef = React.useRef<HTMLInputElement | null>(null);
  const listRef = React.useRef<HTMLDivElement | null>(null);

  React.useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q.trim()), 200);
    return () => window.clearTimeout(t);
  }, [q]);

  const trimmed = debouncedQ;
  const enabled = trimmed.length > 0;
  const search = useQuery<SearchResponse>({
    queryKey: ["global-search", trimmed],
    queryFn: () => fetchGlobalSearch(trimmed, 8),
    enabled: enabled && open,
    staleTime: 30_000,
  });

  const flat: FlatItem[] = React.useMemo(() => {
    if (!enabled) {
      return QUICK_ITEMS.filter(
        (it) => !it.adminOnly || user?.role === "admin",
      ).map((item) => ({ kind: "quick", item }));
    }
    const out: FlatItem[] = [];
    const data = search.data;
    if (data) {
      data.tasks.forEach((t) => out.push({ kind: "task", item: t }));
      data.documents.forEach((d) => out.push({ kind: "doc", item: d }));
      data.reports.forEach((r) => out.push({ kind: "report", item: r }));
    }
    return out;
  }, [enabled, search.data, user?.role]);

  React.useEffect(() => {
    if (activeIndex >= flat.length) setActiveIndex(0);
  }, [flat.length, activeIndex]);

  React.useEffect(() => {
    if (open) {
      setActiveIndex(0);
      const t = window.setTimeout(() => inputRef.current?.focus(), 30);
      return () => window.clearTimeout(t);
    }
    setQ("");
  }, [open]);

  function navigate(item: FlatItem) {
    if (item.kind === "quick") router.push(item.item.href);
    else if (item.kind === "task") router.push(`/review/${item.item.id}`);
    else if (item.kind === "doc") router.push(`/review/${item.item.task_id}`);
    else if (item.kind === "report") router.push(`/report/${item.item.task_id}`);
    onOpenChange(false);
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIndex((i) => (flat.length === 0 ? 0 : (i + 1) % flat.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIndex((i) =>
        flat.length === 0 ? 0 : (i - 1 + flat.length) % flat.length,
      );
    } else if (e.key === "Enter") {
      e.preventDefault();
      const cur = flat[activeIndex];
      if (cur) navigate(cur);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onOpenChange(false);
    }
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in"
          data-testid="command-palette-overlay"
        />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-[15%] z-50 w-[min(640px,calc(100vw-32px))] -translate-x-1/2 overflow-hidden rounded-xl border border-neutral-200 bg-white shadow-2xl"
          data-testid="command-palette"
        >
          <div className="flex items-center gap-2 border-b border-neutral-100 px-4 py-3">
            <Search className="h-4 w-4 text-neutral-400" />
            <input
              ref={inputRef}
              type="text"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={onKeyDown}
              placeholder="搜索任务、文件、报告，或跳转页面…"
              className="flex-1 bg-transparent text-sm text-neutral-900 placeholder:text-neutral-400 focus:outline-none"
              data-testid="command-palette-input"
              aria-label="全局搜索"
            />
            <kbd className="inline-flex h-5 items-center rounded border border-neutral-200 bg-neutral-50 px-1.5 font-mono text-[10px] text-neutral-500">
              ESC
            </kbd>
          </div>

          <div
            ref={listRef}
            className="max-h-[60vh] overflow-y-auto py-2"
            data-testid="command-palette-list"
            role="listbox"
          >
            {!enabled ? (
              <QuickNavList
                items={QUICK_ITEMS.filter(
                  (it) => !it.adminOnly || user?.role === "admin",
                )}
                activeIndex={activeIndex}
                onHover={setActiveIndex}
                onSelect={(it) => navigate({ kind: "quick", item: it })}
              />
            ) : search.isFetching ? (
              <SkeletonRows />
            ) : flat.length === 0 ? (
              <EmptyState q={trimmed} />
            ) : (
              <SearchResults
                items={flat}
                activeIndex={activeIndex}
                onHover={setActiveIndex}
                onSelect={navigate}
              />
            )}
          </div>

          <div className="flex items-center justify-between border-t border-neutral-100 bg-neutral-50/60 px-3 py-2 text-[11px] text-neutral-500">
            <div className="flex items-center gap-3">
              <span className="inline-flex items-center gap-1">
                <CornerDownLeft className="h-3 w-3" />
                打开
              </span>
              <span className="inline-flex items-center gap-1">
                <ArrowRight className="h-3 w-3 rotate-90" />
                选择
              </span>
              <span className="inline-flex items-center gap-1">
                <CommandIcon className="h-3 w-3" />K 随时唤起
              </span>
            </div>
            <span>{enabled ? `${flat.length} 个结果` : "快捷导航"}</span>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function QuickNavList({
  items,
  activeIndex,
  onHover,
  onSelect,
}: {
  items: QuickItem[];
  activeIndex: number;
  onHover: (i: number) => void;
  onSelect: (it: QuickItem) => void;
}) {
  return (
    <ul className="px-2">
      <GroupHeader icon={Sparkles} title="快捷导航" />
      {items.map((item, idx) => {
        const Icon = item.icon;
        const active = idx === activeIndex;
        return (
          <li
            key={item.id}
            data-active={active ? "true" : undefined}
            onMouseMove={() => onHover(idx)}
            onClick={() => onSelect(item)}
            className={cn(
              "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
              active
                ? "bg-brand-50 text-brand-700"
                : "text-neutral-700 hover:bg-neutral-50",
            )}
            data-testid={`command-palette-quick-${item.id}`}
          >
            <span
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
                active
                  ? "bg-brand-100 text-brand-700"
                  : "bg-neutral-100 text-neutral-600",
              )}
            >
              <Icon className="h-4 w-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate font-medium">{item.label}</span>
              <span className="block truncate text-meta text-neutral-500">
                {item.hint}
              </span>
            </span>
            <ArrowRight className="h-3.5 w-3.5 text-neutral-400" />
          </li>
        );
      })}
    </ul>
  );
}

function SearchResults({
  items,
  activeIndex,
  onHover,
  onSelect,
}: {
  items: FlatItem[];
  activeIndex: number;
  onHover: (i: number) => void;
  onSelect: (it: FlatItem) => void;
}) {
  const groups: { kind: "task" | "doc" | "report"; label: string; icon: React.ComponentType<{ className?: string }> }[] = [
    { kind: "task", label: "任务", icon: Activity },
    { kind: "doc", label: "文件", icon: FileText },
    { kind: "report", label: "报告", icon: Gavel },
  ];

  let cursor = 0;
  return (
    <div>
      {groups.map((g) => {
        const list = items.filter((it) => it.kind === g.kind);
        if (list.length === 0) return null;
        const Icon = g.icon;
        return (
          <ul key={g.kind} className="px-2 pb-1">
            <GroupHeader icon={Icon} title={g.label} count={list.length} />
            {list.map((entry) => {
              const myIdx = cursor;
              cursor += 1;
              const active = myIdx === activeIndex;
              return (
                <Row
                  key={`${g.kind}-${myIdx}`}
                  entry={entry}
                  active={active}
                  onHover={() => onHover(myIdx)}
                  onSelect={onSelect}
                />
              );
            })}
          </ul>
        );
      })}
    </div>
  );
}

function Row({
  entry,
  active,
  onHover,
  onSelect,
}: {
  entry: FlatItem;
  active: boolean;
  onHover: () => void;
  onSelect: (it: FlatItem) => void;
}) {
  if (entry.kind === "task") {
    const t = entry.item;
    return (
      <li
        data-active={active ? "true" : undefined}
        onMouseMove={onHover}
        onClick={() => onSelect(entry)}
        className={cn(
          "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
          active ? "bg-brand-50 text-brand-700" : "text-neutral-700 hover:bg-neutral-50",
        )}
        data-testid={`command-palette-row-task-${t.id}`}
      >
        <span
          className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
            active ? "bg-brand-100 text-brand-700" : "bg-neutral-100 text-neutral-600",
          )}
        >
          <Activity className="h-4 w-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{t.title}</span>
          <span className="block truncate text-meta text-neutral-500">
            任务 · {t.status} · {t.priority}
          </span>
        </span>
        <span className="text-meta text-neutral-400">
          {formatRelativeTime(t.submitted_at)}
        </span>
      </li>
    );
  }
  if (entry.kind === "doc") {
    const d = entry.item;
    return (
      <li
        data-active={active ? "true" : undefined}
        onMouseMove={onHover}
        onClick={() => onSelect(entry)}
        className={cn(
          "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
          active ? "bg-brand-50 text-brand-700" : "text-neutral-700 hover:bg-neutral-50",
        )}
        data-testid={`command-palette-row-doc-${d.id}`}
      >
        <span
          className={cn(
            "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
            active ? "bg-brand-100 text-brand-700" : "bg-neutral-100 text-neutral-600",
          )}
        >
          <FileText className="h-4 w-4" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate font-medium">{d.original_name}</span>
          <span className="block truncate text-meta text-neutral-500">
            文件 · {d.file_type} · {d.parse_status}
          </span>
        </span>
        <span className="text-meta text-neutral-400">
          {formatRelativeTime(d.created_at)}
        </span>
      </li>
    );
  }
  if (entry.kind !== "report") return null;
  const r = entry.item;
  return (
    <li
      data-active={active ? "true" : undefined}
      onMouseMove={onHover}
      onClick={() => onSelect(entry)}
      className={cn(
        "flex cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-sm",
        active ? "bg-brand-50 text-brand-700" : "text-neutral-700 hover:bg-neutral-50",
      )}
      data-testid={`command-palette-row-report-${r.task_id}`}
    >
      <span
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-md",
          active ? "bg-brand-100 text-brand-700" : "bg-neutral-100 text-neutral-600",
        )}
      >
        <Gavel className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-medium">{r.title}</span>
        <span className="block truncate text-meta text-neutral-500">
          报告 · {r.status}
        </span>
      </span>
      <span className="text-meta text-neutral-400">
        {r.completed_at ? formatRelativeTime(r.completed_at) : ""}
      </span>
    </li>
  );
}

function GroupHeader({
  icon: Icon,
  title,
  count,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  count?: number;
}) {
  return (
    <li className="flex items-center gap-2 px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
      <Icon className="h-3 w-3" />
      {title}
      {typeof count === "number" && (
        <span className="rounded-full bg-neutral-100 px-1.5 text-[10px] font-medium text-neutral-500">
          {count}
        </span>
      )}
    </li>
  );
}

function SkeletonRows() {
  return (
    <ul className="px-2">
      {Array.from({ length: 4 }).map((_, i) => (
        <li
          key={i}
          className="flex animate-pulse items-center gap-3 rounded-lg px-3 py-2"
        >
          <div className="h-7 w-7 rounded-md bg-neutral-100" />
          <div className="flex-1 space-y-1.5">
            <div className="h-3 w-1/2 rounded bg-neutral-100" />
            <div className="h-2.5 w-1/3 rounded bg-neutral-100" />
          </div>
        </li>
      ))}
    </ul>
  );
}

function EmptyState({ q }: { q: string }) {
  return (
    <div className="flex flex-col items-center gap-2 px-6 py-10 text-center">
      <Search className="h-6 w-6 text-neutral-300" />
      <p className="text-sm text-neutral-600">没有匹配 “{q}” 的结果</p>
      <p className="text-meta text-neutral-500">
        试试只搜文件名前缀，或检查关键词拼写
      </p>
    </div>
  );
}
