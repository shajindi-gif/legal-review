"use client";

import * as React from "react";
import { useRouter, useSearchParams } from "next/navigation";
import {
  MessageSquarePlus,
  MoreHorizontal,
  Pencil,
  Trash2,
  Check,
  X as XIcon,
  MessageSquare,
} from "lucide-react";
import { useAssistantStore, type Conversation } from "@/lib/assistant-store";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { formatRelativeTime } from "@/lib/utils";
import { cn } from "@/lib/utils";

/**
 * Assistant 多草稿会话列表（UI-M6.2 + M6.3）。
 *
 * 行为：
 *   - 顶部「+ 新建会话」：调用 store.create()
 *   - 行点击：setActive + 同步 ?c=<id> 到 URL
 *   - 行右侧菜单：重命名 / 删除
 *   - URL ?c=<id> 解析：
 *       - 命中 store → 激活
 *       - 未命中（被人分享了一个不属于自己的 id）→ 静默 fallback 到首条
 *   - hydrated=false 时显示 skeleton（不闪烁空态）
 *
 * 排序：updatedAt 倒序（store 自身已经按创建顺序 prepend，
 *       create/recordAction 都会 bump updatedAt）。
 */
export function ConversationList() {
  const router = useRouter();
  const params = useSearchParams();

  const hydrated = useAssistantStore((s) => s.hydrated);
  const conversations = useAssistantStore((s) => s.conversations);
  const activeId = useAssistantStore((s) => s.activeId);
  const setActive = useAssistantStore((s) => s.setActive);
  const create = useAssistantStore((s) => s.create);

  // URL → store 同步（仅单向：URL 是 source of truth 用于深链）
  // 注意：组件挂载时 params 已是当前 URL，因此不需要等 useEffect
  const urlCid = params.get("c");
  React.useEffect(() => {
    if (!hydrated) return;
    if (!urlCid) {
      // 没有任何 ?c= —— 不主动改 store activeId（保留用户上次选择）
      return;
    }
    const exists = conversations.some((c) => c.id === urlCid);
    if (exists && urlCid !== activeId) {
      setActive(urlCid);
    } else if (!exists && conversations.length > 0) {
      // URL 给了不存在的 id（链接失效 / 跨账号）—— 静默修正
      const first = conversations[0]?.id;
      if (first) {
        setActive(first);
        replaceUrlParam(router, "c", first);
      }
    }
  }, [hydrated, urlCid, conversations, activeId, setActive, router]);

  // store → URL 同步（activeId 改变时写回 ?c=，使用 replace 不污染历史栈）
  const lastWrittenCid = React.useRef<string | null>(null);
  React.useEffect(() => {
    if (!hydrated) return;
    if (!activeId) return;
    if (activeId === lastWrittenCid.current) return;
    if (urlCid === activeId) {
      lastWrittenCid.current = activeId;
      return;
    }
    replaceUrlParam(router, "c", activeId);
    lastWrittenCid.current = activeId;
  }, [hydrated, activeId, urlCid, router]);

  // 排序
  const sorted = React.useMemo(
    () => [...conversations].sort((a, b) => b.updatedAt - a.updatedAt),
    [conversations],
  );

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between gap-2 px-1 pb-2">
        <h3 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wider text-neutral-500">
          <MessageSquare className="h-3.5 w-3.5" />
          会话
          {sorted.length > 0 ? (
            <span className="ml-1 rounded bg-neutral-100 px-1.5 text-[10px] text-neutral-600">
              {sorted.length}
            </span>
          ) : null}
        </h3>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => create({})}
          className="h-7 px-2 text-xs"
          data-testid="assistant-new"
        >
          <MessageSquarePlus className="h-3.5 w-3.5" />
          新建
        </Button>
      </div>

      <div className="-mx-1 flex-1 overflow-y-auto">
        {!hydrated ? (
          <ListSkeleton />
        ) : sorted.length === 0 ? (
          <EmptyState
            onCreate={() => {
              const id = create({});
              replaceUrlParam(router, "c", id);
            }}
          />
        ) : (
          <ul className="flex flex-col gap-0.5">
            {sorted.map((c) => (
              <ConversationRow
                key={c.id}
                conv={c}
                active={c.id === activeId}
                onSelect={() => {
                  setActive(c.id);
                  replaceUrlParam(router, "c", c.id);
                }}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function ListSkeleton() {
  return (
    <ul className="flex flex-col gap-1.5">
      {Array.from({ length: 4 }).map((_, i) => (
        <li
          key={i}
          className="flex flex-col gap-1.5 rounded-lg border border-transparent p-2"
        >
          <Skeleton className="h-3.5 w-3/5" />
          <Skeleton className="h-3 w-2/5" />
        </li>
      ))}
    </ul>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-neutral-200 p-4 text-center text-meta">
      <MessageSquare className="h-5 w-5 text-neutral-300" />
      <p>还没有会话</p>
      <Button
        variant="outline"
        size="sm"
        onClick={onCreate}
        className="h-7 text-xs"
      >
        <MessageSquarePlus className="h-3.5 w-3.5" />
        新建第一个会话
      </Button>
    </div>
  );
}

function ConversationRow({
  conv,
  active,
  onSelect,
}: {
  conv: Conversation;
  active: boolean;
  onSelect: () => void;
}) {
  const rename = useAssistantStore((s) => s.rename);
  const remove = useAssistantStore((s) => s.remove);

  const [editing, setEditing] = React.useState(false);
  const [draft, setDraft] = React.useState(conv.title);
  const [menuOpen, setMenuOpen] = React.useState(false);
  const menuRef = React.useRef<HTMLDivElement>(null);

  // 关闭菜单
  React.useEffect(() => {
    if (!menuOpen) return;
    function onDoc(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setMenuOpen(false);
      }
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [menuOpen]);

  React.useEffect(() => {
    setDraft(conv.title);
  }, [conv.title]);

  function commitRename() {
    const v = draft.trim();
    if (v && v !== conv.title) rename(conv.id, v);
    setEditing(false);
  }

  function handleDelete() {
    if (
      typeof window !== "undefined" &&
      !window.confirm(`删除会话"${conv.title}"？该操作不可撤销。`)
    ) {
      return;
    }
    remove(conv.id);
    setMenuOpen(false);
  }

  return (
    <li>
      <div
        className={cn(
          "group relative flex items-center gap-2 rounded-lg border px-2 py-1.5 text-sm transition-colors",
          active
            ? "border-brand-200 bg-brand-50/60 text-neutral-900"
            : "border-transparent text-neutral-700 hover:border-neutral-200 hover:bg-neutral-50",
        )}
        data-testid={`assistant-conv-${conv.id}`}
        data-active={active ? "true" : "false"}
      >
        {editing ? (
          <form
            className="flex flex-1 items-center gap-1"
            onSubmit={(e) => {
              e.preventDefault();
              commitRename();
            }}
          >
            <Input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  setDraft(conv.title);
                  setEditing(false);
                }
              }}
              className="h-7 flex-1 text-xs"
              maxLength={64}
            />
            <button
              type="submit"
              className="rounded p-1 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-700"
              aria-label="保存"
            >
              <Check className="h-3.5 w-3.5" />
            </button>
            <button
              type="button"
              onClick={() => {
                setDraft(conv.title);
                setEditing(false);
              }}
              className="rounded p-1 text-neutral-500 hover:bg-neutral-200 hover:text-neutral-700"
              aria-label="取消"
            >
              <XIcon className="h-3.5 w-3.5" />
            </button>
          </form>
        ) : (
          <>
            <button
              type="button"
              onClick={onSelect}
              className="min-w-0 flex-1 text-left"
            >
              <p className="truncate text-[13px] font-medium">
                {conv.title}
              </p>
              <p className="mt-0.5 truncate text-[10px] text-neutral-400">
                {conv.draft ? `${conv.draft.slice(0, 32)}…` : "空白草稿"}
                <span className="mx-1">·</span>
                {formatRelativeTime(new Date(conv.updatedAt).toISOString())}
                {conv.actions.length > 0 ? (
                  <>
                    <span className="mx-1">·</span>
                    {conv.actions.length} 个动作
                  </>
                ) : null}
              </p>
            </button>

            <div className="relative" ref={menuRef}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  setMenuOpen((v) => !v);
                }}
                className={cn(
                  "rounded p-1 text-neutral-400 hover:bg-neutral-200 hover:text-neutral-700",
                  menuOpen && "bg-neutral-200 text-neutral-700",
                  !active && "opacity-0 group-hover:opacity-100",
                )}
                aria-label="会话操作"
                data-testid={`assistant-conv-menu-${conv.id}`}
              >
                <MoreHorizontal className="h-3.5 w-3.5" />
              </button>
              {menuOpen ? (
                <div
                  className="absolute right-0 top-7 z-30 w-32 overflow-hidden rounded-md border border-neutral-200 bg-white shadow-lg"
                  role="menu"
                >
                  <button
                    type="button"
                    onClick={() => {
                      setEditing(true);
                      setMenuOpen(false);
                    }}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-neutral-700 hover:bg-neutral-50"
                    role="menuitem"
                  >
                    <Pencil className="h-3.5 w-3.5" /> 重命名
                  </button>
                  <button
                    type="button"
                    onClick={handleDelete}
                    className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs text-red-600 hover:bg-red-50"
                    role="menuitem"
                  >
                    <Trash2 className="h-3.5 w-3.5" /> 删除
                  </button>
                </div>
              ) : null}
            </div>
          </>
        )}
      </div>
    </li>
  );
}

function replaceUrlParam(
  router: ReturnType<typeof useRouter>,
  key: string,
  value: string,
) {
  if (typeof window === "undefined") return;
  const url = new URL(window.location.href);
  if (url.searchParams.get(key) === value) return;
  url.searchParams.set(key, value);
  // 不污染 history
  router.replace(`${url.pathname}${url.search}`, { scroll: false });
}
