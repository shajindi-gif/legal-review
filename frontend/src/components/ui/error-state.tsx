import { type ReactNode } from "react";
import { AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ErrorStateProps {
  title?: string;
  description?: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

/**
 * 统一错误状态：用于接口失败 / 解析失败 / SSE 中断等场景。
 * 与 EmptyState 的区别：颜色用 danger、必带图标与"重试 / 返回"动作位。
 *
 * 使用：
 *   <ErrorState
 *     title="实时连接中断"
 *     description="节点流推送失败，可手动刷新重试"
 *     action={<Button size="sm" onClick={refetch}>重试</Button>}
 *   />
 */
export function ErrorState({
  title = "出错了",
  description,
  icon,
  action,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cn(
        "flex flex-col items-center justify-center gap-3 rounded-xl border border-danger-200 bg-danger-50/50 px-6 py-10 text-center",
        className,
      )}
    >
      <div className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-danger-600 shadow-sm">
        {icon ?? <AlertCircle className="h-5 w-5" aria-hidden />}
      </div>
      <div className="space-y-1">
        <p className="text-card-title text-danger-900">{title}</p>
        {description ? (
          <p className="text-meta max-w-sm text-danger-700">{description}</p>
        ) : null}
      </div>
      {action ? <div className="pt-2">{action}</div> : null}
    </div>
  );
}
