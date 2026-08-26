"use client";

import { type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * 统一空状态：用于 Documents / Knowledge / Tasks / History 等列表。
 * 原则：永远给用户一个"下一步"——不要只说"无数据"。
 */
export function EmptyState({
  title,
  description,
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-neutral-200 bg-neutral-50/50 px-6 py-12 text-center",
        className,
      )}
    >
      {icon ? (
        <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-neutral-500 shadow-sm">
          {icon}
        </div>
      ) : null}
      <div className="space-y-1">
        <p className="text-card-title">{title}</p>
        {description ? <p className="text-meta max-w-sm">{description}</p> : null}
      </div>
      {action ? <div className="pt-2">{action}</div> : null}
    </div>
  );
}
