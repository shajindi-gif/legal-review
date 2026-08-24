"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import * as DropdownMenu from "@radix-ui/react-dropdown-menu";
import { ChevronDown, LogOut, Shield, User as UserIcon } from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { Badge } from "@/components/ui/badge";

const planLabel = {
  free: "体验版",
  pro: "专业版",
  enterprise: "企业版",
} as const;

export function TopBar() {
  const router = useRouter();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <header className="sticky top-0 z-30 flex h-16 items-center justify-between border-b border-gray-200 bg-white/80 px-6 backdrop-blur">
      <Link href="/dashboard" prefetch={false} className="flex items-center gap-2">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
          法
        </div>
        <span className="text-lg font-semibold text-brand-700">
          智审 · LegaReview
        </span>
      </Link>

      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button className="inline-flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm hover:bg-brand-50">
            <UserIcon className="h-4 w-4 text-gray-500" />
            <span className="max-w-[160px] truncate">{user?.email ?? "未登录"}</span>
            <ChevronDown className="h-3.5 w-3.5 text-gray-400" />
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            sideOffset={8}
            className="z-50 min-w-[200px] overflow-hidden rounded-lg border border-gray-200 bg-white p-1 shadow-md"
          >
            <div className="px-3 py-2 text-xs text-gray-500">
              <div className="truncate">{user?.email}</div>
              <div className="mt-1">
                {user?.role === "admin" && (
                  <Badge variant="secondary" className="mr-1">
                    管理员
                  </Badge>
                )}
                <Badge variant="outline">套餐：{user?.plan_tier ? planLabel[user.plan_tier] : "—"}</Badge>
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
    </header>
  );
}
