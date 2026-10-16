import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import type { ReactNode } from "react";

/**
 * 认证页共享布局：品牌区 + 卡片容器 + 页脚合规链接。
 * 深浅色随系统（prefers-color-scheme）适配；排版克制、无装饰动画。
 */
export function AuthLayout({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="flex min-h-screen flex-col bg-neutral-50 px-4 py-12 dark:bg-neutral-950 sm:px-6">
      <Link
        href="/"
        className="absolute left-6 top-6 inline-flex items-center gap-1.5 text-sm text-neutral-500 transition-colors hover:text-neutral-900 dark:text-neutral-400 dark:hover:text-neutral-200"
      >
        <ArrowLeft className="h-4 w-4" /> 返回首页
      </Link>

      <div className="flex flex-1 flex-col items-center justify-center">
        <div className="mb-8 text-center">
          <Link
            href="/"
            className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 font-display text-xl font-bold text-white shadow-sm"
            aria-label="智审 LegalReview 首页"
          >
            法
          </Link>
          <h1 className="font-display text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50">
            {title}
          </h1>
          <p className="mt-1.5 text-sm text-neutral-500 dark:text-neutral-400">
            {subtitle}
          </p>
        </div>

        <div className="w-full max-w-md">{children}</div>

        {footer ? (
          <div className="mt-6 w-full max-w-md text-center">{footer}</div>
        ) : null}
      </div>

      <footer className="mt-10 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-neutral-400 dark:text-neutral-500">
        <span>© {new Date().getFullYear()} 智审 · LegalReview</span>
        <Link href="/terms" target="_blank" className="hover:text-neutral-600 dark:hover:text-neutral-300">
          服务条款
        </Link>
        <Link href="/privacy" target="_blank" className="hover:text-neutral-600 dark:hover:text-neutral-300">
          隐私政策
        </Link>
      </footer>
    </div>
  );
}
