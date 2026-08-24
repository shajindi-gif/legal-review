"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function renderMarkdown(md: string): string {
  const lines = escapeHtml(md).split(/\r?\n/);
  const html: string[] = [];
  let inList = false;
  const closeList = () => {
    if (inList) {
      html.push("</ul>");
      inList = false;
    }
  };
  for (const raw of lines) {
    const line = raw.trim();
    if (/^#{3}\s+/.test(line)) {
      closeList();
      html.push(`<h3 class="text-base font-semibold mt-4 mb-1">${line.slice(4)}</h3>`);
    } else if (/^#{2}\s+/.test(line)) {
      closeList();
      html.push(`<h2 class="text-lg font-semibold mt-5 mb-1">${line.slice(3)}</h2>`);
    } else if (/^#\s+/.test(line)) {
      closeList();
      html.push(`<h1 class="text-xl font-bold mt-6 mb-2">${line.slice(2)}</h1>`);
    } else if (/^[-*]\s+/.test(line)) {
      if (!inList) {
        html.push('<ul class="list-disc pl-5 my-1 space-y-1">');
        inList = true;
      }
      html.push(`<li>${line.replace(/^[-*]\s+/, "")}</li>`);
    } else if (line === "") {
      closeList();
    } else {
      closeList();
      const inline = line
        .replace(/\*\*(.+?)\*\*/g, '<strong class="font-semibold">$1</strong>')
        .replace(/`([^`]+)`/g, '<code class="rounded bg-gray-100 px-1 text-sm">$1</code>');
      html.push(`<p class="my-1.5 leading-relaxed">${inline}</p>`);
    }
  }
  closeList();
  return html.join("\n");
}

export function ReportViewer({
  markdown,
  loading,
  error,
}: {
  markdown?: string;
  loading?: boolean;
  error?: string | null;
}) {
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold text-brand-700">审查意见书</h2>
      </div>
      {loading ? (
        <div className="flex h-40 items-center justify-center text-sm text-gray-400">
          报告生成中…
        </div>
      ) : error ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-amber-200 bg-amber-50 text-sm text-amber-700">
          {error}
        </div>
      ) : markdown ? (
        <div
          className={cn(
            "prose prose-sm max-w-none rounded-lg border border-gray-200 bg-white p-6",
            "[&_ul]:my-1.5 [&_ol]:my-1.5",
          )}
          dangerouslySetInnerHTML={{ __html: renderMarkdown(markdown) }}
        />
      ) : (
        <div className="flex h-40 items-center justify-center rounded-lg border border-dashed border-gray-200 text-sm text-gray-400">
          报告暂未生成
        </div>
      )}
    </div>
  );
}
