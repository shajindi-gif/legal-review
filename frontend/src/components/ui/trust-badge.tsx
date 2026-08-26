import * as React from "react";
import { Sparkles, Quote } from "lucide-react";
import { cn } from "@/lib/utils";

/**
 * Trust Layer 标识（§C 缺失项）：
 * 凡是 AI 生成内容 / 引用来源，都必须在视觉上打上角标，让用户清楚"这是模型说的，
 * 不是平台声明"。这是 Vertical AI 的底线：可追溯 + 可识别。
 */

export function TrustBadge({
  kind,
  className,
}: {
  kind: "ai" | "citation";
  className?: string;
}) {
  if (kind === "ai") {
    return (
      <span
        className={cn(
          "inline-flex items-center gap-1 rounded-full border border-brand-200 bg-brand-50 px-2 py-0.5 text-[10px] font-medium text-brand-700",
          className,
        )}
        data-testid="trust-badge-ai"
      >
        <Sparkles className="h-3 w-3" />
        AI 生成
      </span>
    );
  }
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full border border-info-200 bg-info-50 px-2 py-0.5 text-[10px] font-medium text-info-700",
        className,
      )}
      data-testid="trust-badge-citation"
    >
      <Quote className="h-3 w-3" />
      引用来源
    </span>
  );
}
