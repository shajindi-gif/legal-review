"use client";

import * as React from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/**
 * 共享 Markdown 渲染器（UI-M9.1）。
 *
 * 设计目标：
 *   - 所有 AI 输出文本（报告正文、审查摘要、Assistant 消息、节点流说明）共用同一组件
 *   - 默认开启 GFM（表格 / 任务列表 / 删除线 / autolink）
 *   - 默认走 rehype-sanitize，XSS-safe
 *   - prose 样式与设计系统对齐（brand 紫主色 / neutral 灰文本 / 4xl 间距）
 *   - size 切换：sm (聊天) / md (默认) / lg (报告) — 改字号/行高，不改结构
 *
 * 视觉对齐：避免使用 Tailwind @tailwindcss/typography 插件（未装），
 * 用 arbitrary variant 写一套等价的 prose 样式，零额外依赖。
 */

const sizeClass: Record<NonNullable<MarkdownContentProps["size"]>, string> = {
  sm: "text-sm leading-6 [&_h1]:text-base [&_h2]:text-[15px] [&_h3]:text-sm [&_p]:my-1 [&_ul]:my-1 [&_ol]:my-1",
  md: "text-sm leading-7 [&_p]:my-1.5 [&_ul]:my-1.5 [&_ol]:my-1.5",
  lg: "text-[15px] leading-[1.85] [&_h1]:text-2xl [&_h2]:text-xl [&_h3]:text-lg [&_p]:my-2 [&_ul]:my-2 [&_ol]:my-2",
};

export type MarkdownContentProps = {
  children: string;
  className?: string;
  size?: "sm" | "md" | "lg";
  /**
   * 覆盖默认组件渲染，例如在 Report 视图里把 [n] 文本角标换成 Citation 链接。
   * 缺省时使用保守的纯排版映射（h1-h3 / p / ul / ol / code / blockquote / a / table / hr / input）。
   */
  components?: Components;
};

const defaultComponents: Components = {
  a: ({ node, ...props }) => (
    <a
      {...props}
      className="text-brand-700 underline decoration-brand-300 underline-offset-2 hover:text-brand-800"
      target={props.href?.startsWith("http") ? "_blank" : undefined}
      rel={props.href?.startsWith("http") ? "noopener noreferrer" : undefined}
    />
  ),
  code: ({ node, className, children, ...props }) => {
    const isBlock = !!className?.includes("language-");
    if (isBlock) {
      return (
        <code
          {...props}
          className={cn(
            "block overflow-x-auto rounded-md bg-neutral-900 px-4 py-3 text-[12.5px] leading-6 text-neutral-100",
            className,
          )}
        >
          {children}
        </code>
      );
    }
    return (
      <code
        {...props}
        className={cn(
          "rounded bg-neutral-100 px-1 py-0.5 text-[12.5px] text-neutral-800",
          className,
        )}
      >
        {children}
      </code>
    );
  },
  pre: ({ node, children, ...props }) => (
    <pre
      {...props}
      className="my-3 overflow-x-auto rounded-md border border-neutral-800 [&_code]:bg-transparent [&_code]:p-0"
    >
      {children}
    </pre>
  ),
  blockquote: ({ node, ...props }) => (
    <blockquote
      {...props}
      className="my-2 border-l-2 border-brand-300 pl-3 text-neutral-600 italic"
    />
  ),
  hr: () => <hr className="my-4 border-neutral-200" />,
  input: ({ node, ...props }) => (
    // GFM 任务列表里的复选框，禁用即可
    <input
      {...props}
      type="checkbox"
      disabled
      className="mr-1 h-3.5 w-3.5 accent-brand-600"
    />
  ),
};

const baseClass = cn(
  "text-neutral-800 break-words",
  // 标题
  "[&_h1]:mt-6 [&_h1]:mb-2 [&_h1]:text-xl [&_h1]:font-semibold [&_h1]:text-neutral-900",
  "[&_h2]:mt-5 [&_h2]:mb-1 [&_h2]:text-lg [&_h2]:font-semibold [&_h2]:text-neutral-900",
  "[&_h3]:mt-4 [&_h3]:mb-1 [&_h3]:text-base [&_h3]:font-semibold [&_h3]:text-neutral-900",
  "[&_h4]:mt-3 [&_h4]:mb-1 [&_h4]:text-sm [&_h4]:font-semibold",
  // 段落与列表
  "[&_p]:my-1.5",
  "[&_ul]:my-1.5 [&_ul]:list-disc [&_ul]:pl-5 [&_ul>li]:my-1 [&_ul>li]:leading-7",
  "[&_ol]:my-1.5 [&_ol]:list-decimal [&_ol]:pl-5 [&_ol>li]:my-1 [&_ol>li]:leading-7",
  "[&_li>p]:my-1",
  // 强调
  "[&_strong]:font-semibold [&_strong]:text-neutral-900",
  "[&_em]:italic",
  // 链接
  "[&_a]:text-brand-700 [&_a]:underline [&_a]:decoration-brand-300 [&_a]:underline-offset-2 hover:[&_a]:text-brand-800",
  // 行内代码
  "[&_:not(pre)>code]:rounded [&_:not(pre)>code]:bg-neutral-100 [&_:not(pre)>code]:px-1 [&_:not(pre)>code]:py-0.5 [&_:not(pre)>code]:text-[12.5px]",
  // 引用
  "[&_blockquote]:my-2 [&_blockquote]:border-l-2 [&_blockquote]:border-brand-300 [&_blockquote]:pl-3 [&_blockquote]:text-neutral-600",
  // 表格 (GFM)
  "[&_table]:my-3 [&_table]:w-full [&_table]:border-collapse [&_table]:text-sm",
  "[&_th]:border [&_th]:border-neutral-200 [&_th]:bg-neutral-50 [&_th]:px-3 [&_th]:py-2 [&_th]:text-left [&_th]:font-semibold",
  "[&_td]:border [&_td]:border-neutral-200 [&_td]:px-3 [&_td]:py-2 [&_td]:align-top",
  // 任务列表 (GFM)
  "[&_li]:list-none [&_li>input[type=checkbox]]:mr-1.5",
  // 分隔线
  "[&_hr]:my-4 [&_hr]:border-neutral-200",
);

export function MarkdownContent({
  children,
  className,
  size = "md",
  components,
}: MarkdownContentProps) {
  if (!children || typeof children !== "string") {
    return null;
  }
  return (
    <div
      data-testid="markdown-content"
      data-size={size}
      className={cn(baseClass, sizeClass[size], className)}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeSanitize]}
        components={{ ...defaultComponents, ...components }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
