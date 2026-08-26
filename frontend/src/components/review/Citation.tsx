"use client";

import * as React from "react";
import { BookOpen, ChevronRight } from "lucide-react";
import type { Evidence } from "@/types/api";
import { cn, truncateMiddle } from "@/lib/utils";
import { TrustBadge } from "@/components/ui/trust-badge";

/**
 * Citation（§C 缺失项）：法规/条款引用卡片。
 *
 * 设计要点：
 * - 紧凑模式：放在风险条目 / 报告段落后的 `[1]` 角标
 * - 详情模式：作为 EvidencePanel 中的展开卡
 * - 点击可在右侧 EvidencePanel 中"聚焦"
 */

export type CitationProps = {
  evidence: Evidence;
  index?: number;
  focused?: boolean;
  compact?: boolean;
  onFocus?: (e: Evidence) => void;
  className?: string;
};

export function Citation({
  evidence,
  index,
  focused = false,
  compact = false,
  onFocus,
  className,
}: CitationProps) {
  if (compact) {
    return (
      <button
        type="button"
        onClick={() => onFocus?.(evidence)}
        className={cn(
          "inline-flex h-5 min-w-5 items-center justify-center rounded-md border px-1 text-[10px] font-semibold transition-colors",
          focused
            ? "border-brand-600 bg-brand-600 text-white"
            : "border-neutral-200 bg-white text-neutral-600 hover:border-brand-400 hover:text-brand-700",
          className,
        )}
        data-testid="citation-compact"
        title={evidence.law_name}
      >
        [{index ?? "·"}]
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={() => onFocus?.(evidence)}
      className={cn(
        "group flex w-full flex-col gap-2 rounded-lg border bg-white p-3 text-left transition-colors",
        focused
          ? "border-brand-500 ring-2 ring-brand-100"
          : "border-neutral-200 hover:border-brand-300",
        className,
      )}
      data-testid="citation-detail"
    >
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[10px] font-semibold",
            focused ? "bg-brand-600 text-white" : "bg-brand-50 text-brand-700",
          )}
        >
          {index ?? "·"}
        </span>
        <BookOpen className="h-3.5 w-3.5 text-brand-600" />
        <span className="truncate text-sm font-semibold text-neutral-900">
          {evidence.law_name}
        </span>
        {evidence.article ? (
          <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-700">
            {evidence.article}
          </span>
        ) : null}
        <ChevronRight className="ml-auto h-3.5 w-3.5 shrink-0 text-neutral-300 group-hover:text-brand-600" />
      </div>
      {evidence.original_text ? (
        <p className="line-clamp-2 border-l-2 border-neutral-200 pl-2 text-meta italic text-neutral-500">
          {truncateMiddle(evidence.original_text, 80)}
        </p>
      ) : null}
      {evidence.explanation ? (
        <p className="line-clamp-3 text-sm leading-relaxed text-neutral-700">
          {evidence.explanation}
        </p>
      ) : null}
      <div className="flex items-center justify-between">
        <TrustBadge kind="citation" />
      </div>
    </button>
  );
}
