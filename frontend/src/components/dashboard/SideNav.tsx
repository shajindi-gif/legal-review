"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Home,
  Upload,
  Shield,
  History as HistoryIcon,
  Sparkles,
  FileText,
  Library,
  ListChecks,
  BarChart3,
  Activity,
  Bell,
  MessageSquareQuote,
  Settings,
  User as UserIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/auth";

/**
 * Sidebar 一级导航分组。
 *
 * UI-M14 落地状态（2026-08）：
 *   - primary 中 Home / Assistant / Documents / Tasks / Notifications / Feedback / Reports
 *     均为真链接（7 个真页面入口），全部 5 个旧标 comingSoon 已解锁为真页面。
 *   - Agents / Knowledge / History 仍为 comingSoon: true，遵 Section 2
 *     "没有真正实现的模块不要展示假入口"——禁止点击、显示"即将"角标。
 *   - bottom：底部 3 项（Usage / Settings / Account），其中 Settings / Account 仅走
 *     TopBar 头像下拉；Usage 当前跳 /dashboard（无独立页，UI-M15 候选）。
 */
type NavItem = {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  comingSoon?: boolean;
};

const primaryItems: NavItem[] = [
  { href: "/dashboard", label: "Home", icon: Home },
  { href: "/assistant", label: "Assistant", icon: Sparkles },
  { href: "/agents", label: "Agents", icon: ListChecks, comingSoon: true },
  { href: "/documents", label: "Documents", icon: FileText },
  { href: "/knowledge", label: "Knowledge", icon: Library, comingSoon: true },
  { href: "/tasks", label: "Tasks", icon: Activity },
  { href: "/notifications", label: "Notifications", icon: Bell },
  { href: "/dashboard/feedback", label: "Feedback", icon: MessageSquareQuote },
  { href: "/reports", label: "Reports", icon: BarChart3 },
  { href: "/history", label: "History", icon: HistoryIcon, comingSoon: true },
];

interface SideNavProps {
  /** 移动端 drawer 打开状态。 */
  open?: boolean;
  /** 移动端 drawer 关闭回调。 */
  onNavigate?: () => void;
}

export function SideNav({ open = true, onNavigate }: SideNavProps) {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);

  return (
    <nav
      aria-label="主导航"
      data-state={open ? "open" : "closed"}
      className={cn(
        "flex w-60 shrink-0 flex-col border-r border-neutral-200 bg-white",
        "h-full",
      )}
    >
      <div className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
        <NavGroup title="Workspace" items={primaryItems} pathname={pathname} onNavigate={onNavigate} />
        {user?.role === "admin" && (
          <NavGroup
            title="管理"
            items={[
              { href: "/admin", label: "管理后台", icon: Shield },
              { href: "/admin/feedback", label: "用户反馈", icon: MessageSquareQuote },
            ]}
            pathname={pathname}
            onNavigate={onNavigate}
          />
        )}
      </div>

      <div className="space-y-1 border-t border-neutral-200 px-3 py-3">
        <BottomItem
          href="/dashboard"
          label="Usage"
          icon={Activity}
          active={pathname === "/dashboard"}
          onNavigate={onNavigate}
        />
        <BottomItem
          href="/dashboard"
          label="Settings"
          icon={Settings}
          active={false}
          onNavigate={onNavigate}
          comingSoon
        />
        <BottomItem
          href="/dashboard"
          label="Account"
          icon={UserIcon}
          active={false}
          onNavigate={onNavigate}
          comingSoon
        />
      </div>
    </nav>
  );
}

function NavGroup({
  title,
  items,
  pathname,
  onNavigate,
}: {
  title: string;
  items: NavItem[];
  pathname: string;
  onNavigate?: () => void;
}) {
  return (
    <div>
      <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
        {title}
      </p>
      <ul className="space-y-0.5">
        {items.map((item) => {
          const active =
            pathname === item.href || pathname.startsWith(item.href + "/");
          return (
            <li key={item.href}>
              <NavLink item={item} active={active} onNavigate={onNavigate} />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: NavItem;
  active: boolean;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const cls = cn(
    "group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
    active
      ? "bg-brand-50 text-brand-700"
      : "text-neutral-600 hover:bg-neutral-50 hover:text-neutral-900",
    item.comingSoon && "cursor-not-allowed opacity-60 hover:bg-transparent hover:text-neutral-600",
  );

  if (item.comingSoon) {
    return (
      <div
        aria-disabled
        title="即将上线（UI-M2 之后）"
        className={cls}
        data-testid={`nav-${item.label.toLowerCase()}-soon`}
      >
        <Icon className="h-4 w-4" />
        <span className="flex-1 truncate">{item.label}</span>
        <span className="rounded-full border border-neutral-200 bg-white px-1.5 py-0.5 text-[10px] font-medium text-neutral-500">
          即将
        </span>
      </div>
    );
  }

  return (
    <Link
      href={item.href}
      prefetch={false}
      onClick={onNavigate}
      className={cls}
      data-testid={`nav-${item.label.toLowerCase()}`}
    >
      <Icon className="h-4 w-4" />
      <span className="flex-1 truncate">{item.label}</span>
    </Link>
  );
}

function BottomItem({
  href,
  label,
  icon: Icon,
  active,
  onNavigate,
  comingSoon,
}: {
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  active: boolean;
  onNavigate?: () => void;
  comingSoon?: boolean;
}) {
  const cls = cn(
    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
    active
      ? "bg-brand-50 text-brand-700"
      : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-900",
    comingSoon && "cursor-not-allowed opacity-60 hover:bg-transparent hover:text-neutral-500",
  );

  if (comingSoon) {
    return (
      <div aria-disabled title="即将上线" className={cls}>
        <Icon className="h-4 w-4" />
        <span className="flex-1 truncate">{label}</span>
      </div>
    );
  }

  return (
    <Link href={href} prefetch={false} onClick={onNavigate} className={cls}>
      <Icon className="h-4 w-4" />
      <span className="flex-1 truncate">{label}</span>
    </Link>
  );
}
