"use client";

import * as React from "react";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { TopBar } from "@/components/dashboard/TopBar";
import { SideNav } from "@/components/dashboard/SideNav";
import { OnboardingDialog } from "@/components/dashboard/OnboardingDialog";
import {
  useAssistantStore,
  useAssistantCrossTabSync,
} from "@/lib/assistant-store";
import { cn } from "@/lib/utils";

/**
 * AppShell：受保护布局的"应用容器"。
 *
 * - Desktop（≥ lg）：左侧固定 SideNav 240px + 顶部 TopBar 56px + 右侧滚动主区。
 * - Mobile（< lg）：TopBar 含汉堡按钮，点击后 Sidebar 变 Drawer，遮罩可关闭。
 *
 * UI-M1 范围内：
 * - 保留了所有旧业务路由（/dashboard / /upload / /review/[id] / /report/[id]）
 * - 引入 `nav-open` 状态管理移动端 Drawer
 * - 主区背景从 gray-50 改为更克制的 neutral-50
 * - 预留 Context Panel 槽位（暂时不渲染，避免 UI 假位）
 */
export function AppShell({ children }: { children: React.ReactNode }) {
  const [navOpen, setNavOpen] = React.useState(false);

  // Assistant 多草稿会话 store —— 在 AppShell 挂载点统一 hydrate，
  // 避免每个使用 store 的组件各自做一次 localStorage 读取。
  const hydrateAssistant = useAssistantStore((s) => s.hydrate);
  useAssistantCrossTabSync();
  React.useEffect(() => {
    hydrateAssistant();
  }, [hydrateAssistant]);

  // Esc 关闭 drawer
  React.useEffect(() => {
    if (!navOpen) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setNavOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navOpen]);

  return (
    <AuthGuard>
      <div className="flex h-screen flex-col bg-neutral-50">
        <TopBar onMenuClick={() => setNavOpen(true)} />
        <OnboardingDialog />

        <div className="relative flex flex-1 overflow-hidden">
          {/* Desktop sidebar */}
          <div className="hidden lg:block">
            <SideNav />
          </div>

          {/* Mobile drawer */}
          <div
            aria-hidden={!navOpen}
            className={cn(
              "fixed inset-0 z-40 lg:hidden",
              navOpen ? "pointer-events-auto" : "pointer-events-none",
            )}
          >
            <div
              onClick={() => setNavOpen(false)}
              className={cn(
                "absolute inset-0 bg-black/40 transition-opacity",
                navOpen ? "opacity-100" : "opacity-0",
              )}
            />
            <div
              className={cn(
                "absolute inset-y-0 left-0 transition-transform",
                navOpen ? "translate-x-0" : "-translate-x-full",
              )}
            >
              <SideNav open={navOpen} onNavigate={() => setNavOpen(false)} />
            </div>
          </div>

          {/* Main + (未来) Context Panel */}
          <main
            id="main-content"
            className="flex-1 overflow-y-auto"
          >
            <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
              {children}
            </div>
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
