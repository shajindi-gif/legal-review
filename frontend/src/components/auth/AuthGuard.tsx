"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { useAuthStore } from "@/lib/auth";

/**
 * 路由守卫（客户端层）：无 token 重定向 /login。
 * 配合 src/proxy.ts（路由层）双重保护。
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const hydrated = useAuthStore((s) => s.hydrated);

  React.useEffect(() => {
    if (hydrated && !token) {
      router.replace("/login");
    }
  }, [hydrated, token, router]);

  if (!hydrated) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600" />
      </div>
    );
  }

  if (!token) {
    return (
      <div className="flex h-screen items-center justify-center text-sm text-gray-500">
        正在跳转登录…
      </div>
    );
  }

  return <>{children}</>;
}
