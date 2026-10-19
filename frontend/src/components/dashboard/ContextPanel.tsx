"use client";

import * as React from "react";
import { X } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWorkspace } from "@/lib/workspace-context";

/**
 * Context Panel —— 统一工作台三栏布局的第三栏（右侧）。
 *
 * - 桌面端（≥ lg）固定展示，宽度 320px；移动端隐藏（信息在窄屏不适合并排）。
 * - 内容由当前页面通过 `useRegisterContextPanel` 注入；
 *   未注入时展示明确的空状态，而非伪造内容。
 * - 可通过 TopBar 按钮或面板右上角关闭。
 */
export function ContextPanel() {
  const { open, setOpen, content } = useWorkspace();

  if (!open) return null;

  return (
    <aside
      aria-label="上下文面板"
      data-testid="context-panel"
      className={cn(
        "hidden w-80 shrink-0 flex-col border-l border-neutral-200 bg-white",
        "lg:flex",
      )}
    >
      <div className="flex items-start justify-between gap-2 border-b border-neutral-200 px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-neutral-900">
            {content?.title ?? "上下文"}
          </p>
          {content?.subtitle && (
            <p className="mt-0.5 truncate text-meta text-neutral-500">
              {content.subtitle}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setOpen(false)}
          aria-label="关闭上下文面板"
          className="inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {content ? (
          content.body
        ) : (
          <div className="rounded-lg border border-dashed border-neutral-200 px-4 py-6 text-center">
            <p className="text-sm text-neutral-600">当前页面暂无可显示的上下文</p>
            <p className="mt-1 text-meta text-neutral-400">
              打开具体条目后，相关条款、引用与操作会显示在这里。
            </p>
          </div>
        )}
      </div>
    </aside>
  );
}
