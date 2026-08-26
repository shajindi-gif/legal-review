import * as React from "react";
import { Loader2 } from "lucide-react";
import type { ReviewStatus } from "@/types/api";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/**
 * StatusBadge —— 审查状态的单一来源（UI-M5.2）。
 *
 * 合并此前散落在 Home / Documents / HistoryTable 的 statusMap。
 * 任何"把 ReviewStatus 渲染为视觉标签"的地方必须走这个组件。
 *
 * 用法：
 *   <StatusBadge status={t.status} />             // 静态
 *   <StatusBadge status={t.status} withDot />     // 带状态色点（用于列表/卡片）
 *   <StatusBadge status={t.status} withSpinner /> // 进行中带旋转图标（Hero 区域）
 */

type Variant = "default" | "success" | "warning" | "danger" | "secondary" | "outline";

const STATUS_META: Record<
  ReviewStatus,
  { label: string; variant: Variant; dot: string }
> = {
  pending: { label: "排队中", variant: "secondary", dot: "bg-neutral-400" },
  parsing: { label: "解析中", variant: "warning", dot: "bg-warning-500" },
  running: { label: "审查中", variant: "warning", dot: "bg-warning-500" },
  completed: { label: "已完成", variant: "success", dot: "bg-success-500" },
  done: { label: "已完成", variant: "success", dot: "bg-success-500" },
  failed: { label: "失败", variant: "danger", dot: "bg-danger-500" },
};

const IN_PROGRESS: ReadonlySet<ReviewStatus> = new Set([
  "pending",
  "parsing",
  "running",
]);

export function statusMeta(status: ReviewStatus | string) {
  return (
    STATUS_META[status as ReviewStatus] ?? {
      label: String(status),
      variant: "secondary" as Variant,
      dot: "bg-neutral-400",
    }
  );
}

export function isFinished(status: ReviewStatus | string) {
  return status === "completed" || status === "done";
}

export function isInProgress(status: ReviewStatus | string) {
  return IN_PROGRESS.has(status as ReviewStatus);
}

export function StatusBadge({
  status,
  withDot = false,
  withSpinner = false,
  className,
}: {
  status: ReviewStatus | string;
  withDot?: boolean;
  withSpinner?: boolean;
  className?: string;
}) {
  const m = statusMeta(status);
  const showSpinner = withSpinner && isInProgress(status);
  return (
    <Badge variant={m.variant} className={cn("inline-flex items-center gap-1.5", className)}>
      {showSpinner ? (
        <Loader2 className="h-3 w-3 shrink-0 animate-spin" aria-hidden />
      ) : withDot ? (
        <span
          className={cn("h-1.5 w-1.5 shrink-0 rounded-full", m.dot)}
          aria-hidden
        />
      ) : null}
      {m.label}
    </Badge>
  );
}
