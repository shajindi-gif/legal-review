import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

/** 合并 Tailwind 类名，处理冲突。 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/** 格式化日期为 YYYY-MM-DD HH:mm。 */
export function formatDateTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(
    d.getHours(),
  )}:${pad(d.getMinutes())}`;
}

/** 文件大小人类可读。 */
export function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

/**
 * 相对时间（如 "10 分钟前"、"3 天前"）。
 * 用于 Recent Work / History / Activity 列表。
 */
export function formatRelativeTime(iso?: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const diffMs = Date.now() - d.getTime();
  const sec = Math.round(diffMs / 1000);
  if (sec < 60) return "刚刚";
  const min = Math.round(sec / 60);
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.round(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.round(hr / 24);
  if (day < 7) return `${day} 天前`;
  const wk = Math.round(day / 7);
  if (wk < 4) return `${wk} 周前`;
  const mo = Math.round(day / 30);
  if (mo < 12) return `${mo} 个月前`;
  const yr = Math.round(day / 365);
  return `${yr} 年前`;
}

/**
 * 截断字符串中间，常用于长文件名 / 任务 ID。
 * 例：truncateMiddle("verylongfilename_v123.pdf", 14) → "verylo…123.pdf"
 */
export function truncateMiddle(text: string, max = 20): string {
  if (!text || text.length <= max) return text;
  const keep = Math.max(2, Math.floor((max - 1) / 2));
  return `${text.slice(0, keep)}…${text.slice(-keep)}`;
}

/**
 * 风险等级（high / medium / low）→ Tailwind 类。
 * 单一来源：所有 UI 风险色必须走这里，避免散落。
 */
export function riskClasses(level: "high" | "medium" | "low") {
  switch (level) {
    case "high":
      return {
        text: "text-[color:var(--color-risk-high)]",
        bg: "bg-[color:var(--color-risk-high-bg)]",
        border: "border-[color:var(--color-risk-high)]",
      };
    case "medium":
      return {
        text: "text-[color:var(--color-risk-medium)]",
        bg: "bg-[color:var(--color-risk-medium-bg)]",
        border: "border-[color:var(--color-risk-medium)]",
      };
    case "low":
      return {
        text: "text-[color:var(--color-risk-low)]",
        bg: "bg-[color:var(--color-risk-low-bg)]",
        border: "border-[color:var(--color-risk-low)]",
      };
  }
}
