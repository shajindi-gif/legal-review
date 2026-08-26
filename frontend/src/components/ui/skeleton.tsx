import { cn } from "@/lib/utils";

interface SkeletonProps {
  className?: string;
}

/**
 * 通用占位骨架。后续 UI-M2 起所有列表 / 卡片加载态统一使用。
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      aria-hidden
      className={cn(
        "animate-pulse rounded-md bg-neutral-200/70",
        className,
      )}
    />
  );
}

export function SkeletonText({ className }: { className?: string }) {
  return <Skeleton className={cn("h-3.5 w-full", className)} />;
}

export function SkeletonCard() {
  return (
    <div className="space-y-3 rounded-xl border border-neutral-200 bg-white p-5">
      <Skeleton className="h-4 w-1/3" />
      <Skeleton className="h-3 w-full" />
      <Skeleton className="h-3 w-5/6" />
      <Skeleton className="h-3 w-2/3" />
    </div>
  );
}
