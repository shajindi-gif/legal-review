"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { cn } from "@/lib/utils";
import { useAuthStore } from "@/lib/auth";
import {
  ADMIN_ITEMS,
  BOTTOM_ITEMS,
  PRIMARY_MODULES,
  SECONDARY_ITEMS,
  filterByRole,
  navTestId,
  type NavModule,
} from "@/lib/nav";

/**
 * Sidebar 一级导航。
 *
 * - 11 个一级模块由 `@/lib/nav` 单一事实源驱动，按登录角色显隐。
 * - 未真正实现的模块 `comingSoon: true`：禁止点击、显示「即将」角标，不展示假入口。
 * - 底部为计费 / 账户入口；管理员额外看到「管理」分组。
 */
interface SideNavProps {
  /** 移动端 drawer 打开状态。 */
  open?: boolean;
  /** 移动端 drawer 关闭回调。 */
  onNavigate?: () => void;
}

export function SideNav({ open = true, onNavigate }: SideNavProps) {
  const pathname = usePathname();
  const user = useAuthStore((s) => s.user);
  const role = user?.role ?? null;

  const primary = filterByRole(PRIMARY_MODULES, role);
  const secondary = filterByRole(SECONDARY_ITEMS, role);
  const bottom = filterByRole(BOTTOM_ITEMS, role);
  const admin = filterByRole(ADMIN_ITEMS, role);

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
        <NavGroup title="工作台" items={primary} pathname={pathname} onNavigate={onNavigate} />
        {secondary.length > 0 && (
          <NavGroup title="更多" items={secondary} pathname={pathname} onNavigate={onNavigate} />
        )}
        {user?.role === "admin" && (
          <NavGroup title="管理" items={admin} pathname={pathname} onNavigate={onNavigate} />
        )}
      </div>

      <div className="space-y-1 border-t border-neutral-200 px-3 py-3">
        {bottom.map((item) => (
          <BottomItem key={item.key} item={item} pathname={pathname} onNavigate={onNavigate} />
        ))}
      </div>
    </nav>
  );
}

function isActive(item: NavModule, pathname: string): boolean {
  const prefixes = [item.href, ...(item.matchPaths ?? [])];
  return prefixes.some((p) => pathname === p || pathname.startsWith(p + "/"));
}

function NavGroup({
  title,
  items,
  pathname,
  onNavigate,
}: {
  title: string;
  items: NavModule[];
  pathname: string;
  onNavigate?: () => void;
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <p className="px-3 pb-2 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
        {title}
      </p>
      <ul className="space-y-0.5">
        {items.map((item) => (
          <li key={item.key}>
            <NavLink
              item={item}
              active={isActive(item, pathname)}
              onNavigate={onNavigate}
            />
          </li>
        ))}
      </ul>
    </div>
  );
}

function NavLink({
  item,
  active,
  onNavigate,
}: {
  item: NavModule;
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
        title={`${item.labelEn} · 即将上线`}
        className={cls}
        data-testid={`nav-${navTestId(item)}-soon`}
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
      title={item.labelEn}
      className={cls}
      data-testid={`nav-${navTestId(item)}`}
    >
      <Icon className="h-4 w-4" />
      <span className="flex-1 truncate">{item.label}</span>
    </Link>
  );
}

function BottomItem({
  item,
  pathname,
  onNavigate,
}: {
  item: NavModule;
  pathname: string;
  onNavigate?: () => void;
}) {
  const Icon = item.icon;
  const active = pathname === item.href || pathname.startsWith(item.href + "/");
  const cls = cn(
    "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
    active
      ? "bg-brand-50 text-brand-700"
      : "text-neutral-500 hover:bg-neutral-50 hover:text-neutral-900",
  );

  return (
    <Link
      href={item.href}
      prefetch={false}
      onClick={onNavigate}
      title={item.labelEn}
      className={cls}
      data-testid={`nav-${navTestId(item)}`}
    >
      <Icon className="h-4 w-4" />
      <span className="flex-1 truncate">{item.label}</span>
    </Link>
  );
}
