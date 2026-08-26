"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import {
  ChevronDown,
  LogOut,
  Shield,
  User as UserIcon,
  Search,
  Plus,
  Menu,
  FileUp,
  Sparkles,
  Keyboard,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { NotificationBell } from "@/components/dashboard/NotificationBell";
import { CommandPalette } from "@/components/dashboard/CommandPalette";

const planLabel = {
  free: "体验版",
  pro: "专业版",
  enterprise: "企业版",
} as const;

interface TopBarProps {
  /** 移动端：触发 Sidebar drawer。 */
  onMenuClick?: () => void;
}

/**
 * ⌘N 弹出菜单（UI-M4.4 / M4.5）。
 * - 顶栏 +New 按钮触发 DropdownMenu：两个真实出口（新建审查 / 提问 Assistant）
 * - 全局 ⌘N（macOS）/ Ctrl+N（其他）打开菜单
 * - 菜单项中显示快捷键提示
 * - 跳 Assistant 时带 ?q= 走原路径
 */
export function TopBar({ onMenuClick }: TopBarProps) {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const newTriggerRef = React.useRef<HTMLButtonElement | null>(null);
  const [searchOpen, setSearchOpen] = React.useState(false);

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  function openNewMenu() {
    newTriggerRef.current?.click();
  }

  // ⌘K 搜索 / ⌘N 新建 快捷键
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const k = e.key.toLowerCase();
      const isMod = e.metaKey || e.ctrlKey;
      if (!isMod) return;
      if (k === "k") {
        e.preventDefault();
        setSearchOpen((v) => !v);
        return;
      }
      if (k === "n") {
        e.preventDefault();
        openNewMenu();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center justify-between border-b border-neutral-200 bg-white/85 px-4 backdrop-blur supports-[backdrop-filter]:bg-white/70 sm:px-6">
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          aria-label="打开导航"
          className="inline-flex h-9 w-9 items-center justify-center rounded-lg text-neutral-600 hover:bg-neutral-100 lg:hidden"
        >
          <Menu className="h-5 w-5" />
        </button>

        <Link href="/dashboard" prefetch={false} className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-600 text-xs font-bold text-white">
            法
          </div>
          <span className="text-base font-semibold text-brand-700 hidden sm:inline">
            智审 · LegaReview
          </span>
        </Link>
      </div>

      <div className="flex flex-1 items-center justify-end gap-2 sm:gap-3">
        {/* ⌘K 全局搜索（UI-M12 调起 CommandPalette） */}
        <button
          id="global-search-trigger"
          type="button"
          onClick={() => setSearchOpen(true)}
          aria-label="全局搜索"
          title="全局搜索（⌘K）"
          className={cn(
            "hidden h-9 w-full max-w-xs items-center gap-2 rounded-lg border border-neutral-200 bg-neutral-50 px-3 text-sm text-neutral-500 transition-colors hover:bg-white hover:text-neutral-700 md:flex",
          )}
          data-testid="global-search-trigger"
        >
          <Search className="h-4 w-4" />
          <span className="flex-1 text-left">搜索对话、文件、报告…</span>
          <kbd className="hidden items-center gap-0.5 rounded border border-neutral-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-neutral-500 sm:inline-flex">
            ⌘K
          </kbd>
        </button>

        {/* ⌘N 弹出菜单 */}
        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              ref={newTriggerRef}
              type="button"
              title="新建（⌘N）"
              aria-label="新建"
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand-600 px-3 text-sm font-medium text-white shadow-sm transition-colors hover:bg-brand-700"
              data-testid="new-menu-trigger"
            >
              <Plus className="h-4 w-4" />
              <span className="hidden sm:inline">New</span>
              <ChevronDown className="h-3.5 w-3.5" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={8}
              className="z-50 w-[280px] overflow-hidden rounded-lg border border-neutral-200 bg-white p-1 shadow-lg"
              data-testid="new-menu-content"
            >
              <div className="px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
                开始新工作
              </div>
              <DropdownMenu.Item
                onSelect={() => router.push("/upload")}
                className="flex cursor-pointer items-start gap-3 rounded px-3 py-2 outline-none data-[highlighted]:bg-brand-50"
                data-testid="new-menu-review"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                  <FileUp className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-neutral-900">
                    新建审查
                  </span>
                  <span className="block text-meta text-neutral-500">
                    上传文件，启动 11 节点审查流水线
                  </span>
                </span>
                <KbdHint label="N" />
              </DropdownMenu.Item>
              <DropdownMenu.Item
                onSelect={() => router.push("/assistant")}
                className="flex cursor-pointer items-start gap-3 rounded px-3 py-2 outline-none data-[highlighted]:bg-brand-50"
                data-testid="new-menu-assistant"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                  <Sparkles className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-neutral-900">
                    提问 Assistant
                  </span>
                  <span className="block text-meta text-neutral-500">
                    把问题带到专业提问工作台
                  </span>
                </span>
                <KbdHint label="N" />
              </DropdownMenu.Item>
              <div className="my-1 border-t border-neutral-100" />
              <DropdownMenu.Item
                onSelect={() => router.push("/documents")}
                className="flex cursor-pointer items-start gap-3 rounded px-3 py-2 outline-none data-[highlighted]:bg-brand-50"
                data-testid="new-menu-documents"
              >
                <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-neutral-100 text-neutral-700">
                  <Plus className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-medium text-neutral-900">
                    查看已上传文件
                  </span>
                  <span className="block text-meta text-neutral-500">
                    跳到 Documents 列表
                  </span>
                </span>
              </DropdownMenu.Item>
              <div className="border-t border-neutral-100 px-3 py-2 text-meta text-neutral-500">
                <div className="flex items-center gap-2">
                  <Keyboard className="h-3.5 w-3.5" />
                  快捷键：
                  <KbdHint label="N" small /> 新建 ·
                  <KbdHint label="K" small /> 搜索
                </div>
              </div>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>

        {/* UI-M8.3 通知中心铃铛 */}
        <NotificationBell />

        <DropdownMenu.Root>
          <DropdownMenu.Trigger asChild>
            <button
              aria-label="账户菜单"
              className="inline-flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-brand-50"
            >
              <UserIcon className="h-4 w-4 text-neutral-500" />
              <span className="hidden max-w-[160px] truncate sm:inline">
                {user?.email ?? "未登录"}
              </span>
              <ChevronDown className="h-3.5 w-3.5 text-neutral-400" />
            </button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Portal>
            <DropdownMenu.Content
              align="end"
              sideOffset={8}
              className="z-50 min-w-[220px] overflow-hidden rounded-lg border border-neutral-200 bg-white p-1 shadow-md"
            >
              <div className="px-3 py-2 text-xs text-neutral-500">
                <div className="truncate text-neutral-700">{user?.email}</div>
                <div className="mt-1 flex flex-wrap gap-1">
                  {user?.role === "admin" && (
                    <Badge variant="secondary" className="mr-1">
                      管理员
                    </Badge>
                  )}
                  <Badge variant="outline">
                    套餐：
                    {user?.plan_tier ? planLabel[user.plan_tier] : "—"}
                  </Badge>
                </div>
              </div>
              {user?.role === "admin" && (
                <DropdownMenu.Item
                  onSelect={() => router.push("/admin")}
                  className="flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-sm outline-none data-[highlighted]:bg-brand-50"
                >
                  <Shield className="h-4 w-4" /> 管理后台
                </DropdownMenu.Item>
              )}
              <DropdownMenu.Item
                onSelect={handleLogout}
                className="flex cursor-pointer items-center gap-2 rounded px-3 py-2 text-sm text-red-600 outline-none data-[highlighted]:bg-red-50"
              >
                <LogOut className="h-4 w-4" /> 退出登录
              </DropdownMenu.Item>
            </DropdownMenu.Content>
          </DropdownMenu.Portal>
        </DropdownMenu.Root>
      </div>

      {/* UI-M12 ⌘K 全局搜索面板 */}
      <CommandPalette open={searchOpen} onOpenChange={setSearchOpen} />
    </header>
  );
}

function KbdHint({ label, small }: { label: string; small?: boolean }) {
  return (
    <kbd
      className={cn(
        "inline-flex shrink-0 items-center rounded border border-neutral-200 bg-white font-mono font-medium text-neutral-500",
        small
          ? "h-5 px-1 text-[10px]"
          : "h-6 px-1.5 text-[11px]",
      )}
    >
      ⌘{label}
    </kbd>
  );
}
