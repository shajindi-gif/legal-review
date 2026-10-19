"use client";

import * as React from "react";
import { AuthGuard } from "@/components/auth/AuthGuard";
import { TopBar } from "@/components/dashboard/TopBar";
import { SideNav } from "@/components/dashboard/SideNav";
import { ContextPanel } from "@/components/dashboard/ContextPanel";
import { OnboardingDialog } from "@/components/dashboard/OnboardingDialog";
import {
  WorkspaceProvider,
} from "@/lib/workspace-context";
import {
  useAssistantStore,
  useAssistantCrossTabSync,
} from "@/lib/assistant-store";
import { cn } from "@/lib/utils";

/**
 * AppShell：受保护布局的"应用容器"。
 *
 * - Desktop（≥ lg）：左侧固定 SideNav 240px + 顶部 TopBar 56px + 右侧滚动主区
 *   + 可开合的 Context Panel（第三栏，宽 320px）。
 * - Mobile（< lg）：TopBar 含汉堡按钮，点击后 Sidebar 变 Drawer，遮罩可关闭；
 *   Context Panel 在窄屏隐藏。
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
      <WorkspaceProvider>
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

            {/* Main */}
            <main
              id="main-content"
              className="flex-1 overflow-y-auto"
            >
              <div className="mx-auto w-full max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
                {children}
              </div>
            </main>

            {/* Context Panel（第三栏） */}
            <ContextPanel />
          </div>
        </div>
      </WorkspaceProvider>
    </AuthGuard>
  );
}

