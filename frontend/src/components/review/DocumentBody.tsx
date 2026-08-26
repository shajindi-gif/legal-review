"use client";

import * as React from "react";
import { FileText, ExternalLink } from "lucide-react";
import type { ParagraphItem, RiskItem, RiskSeverity } from "@/types/api";
import { cn } from "@/lib/utils";

/**
 * DocumentBody（UI-M7）：按 document_json.body_paragraphs 渲染带 anchor 的段落。
 *
 * - 每段挂载一个稳定的 `id={paragraph.anchor}`（如 #p3），AnnotationLayer 与风险清单的"定位"按钮
 *   都通过 selector 滚动到对应段落。
 * - 对带有 paragraph_anchor 命中的段落，按"最高严重度"叠色（critical/high → 红；medium → 琥珀；low/info → 灰）
 *   并展示该段命中的风险数量。
 * - 段被"选中"（来自右侧风险卡点击）时高亮 + 轻微 ring。
 * - 用户点击段落标题旁的"#"链接，复制 anchor 到剪贴板并平滑滚动。
 *
 * 关键约定（与后端对齐）：
 * - anchor 形如 "#p3"；DOM id 写作 `paragraph.anchor`（"#p3"），CSS 选择器记得用 `[id="#p3"]` 或 escape。
 * - paragraph_id 是去掉 "#" 的纯 id（"p3"）。
 */

const severityRingClass: Record<RiskSeverity, string> = {
  critical: "ring-1 ring-red-400/70 bg-red-50/40",
  high: "ring-1 ring-red-300/60 bg-red-50/30",
  medium: "ring-1 ring-amber-300/60 bg-amber-50/30",
  low: "ring-1 ring-neutral-200 bg-neutral-50/30",
  info: "ring-1 ring-neutral-200 bg-neutral-50/30",
};

const severityDotClass: Record<RiskSeverity, string> = {
  critical: "bg-red-600",
  high: "bg-red-500",
  medium: "bg-amber-500",
  low: "bg-neutral-400",
  info: "bg-neutral-300",
};

const severityLabel: Record<RiskSeverity, string> = {
  critical: "严重",
  high: "高风险",
  medium: "中风险",
  low: "低风险",
  info: "提示",
};

function pickTopSeverity(risks: RiskItem[]): RiskSeverity {
  if (risks.length === 0) return "info";
  const order: RiskSeverity[] = ["critical", "high", "medium", "low", "info"];
  for (const s of order) {
    if (risks.some((r) => r.severity === s)) return s;
  }
  return "info";
}

export function paragraphDomId(p: ParagraphItem): string {
  // "#p3" → "#p3"（与 anchor 一致，方便 location.hash 跳转）
  return p.anchor;
}

export type DocumentBodyProps = {
  paragraphs: ParagraphItem[];
  risksByAnchor: Record<string, RiskItem[]>;
  selectedAnchor?: string | null;
  onParagraphClick?: (paragraph: ParagraphItem, risks: RiskItem[]) => void;
  onRiskClick?: (risk: RiskItem) => void;
  emptyHint?: string;
};

export function DocumentBody({
  paragraphs,
  risksByAnchor,
  selectedAnchor,
  onParagraphClick,
  onRiskClick,
  emptyHint = "正文暂未解析，可在文件管理中重新上传",
}: DocumentBodyProps) {
  if (!paragraphs || paragraphs.length === 0) {
    return (
      <div className="flex h-40 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-neutral-200 text-sm text-neutral-400">
        <FileText className="h-5 w-5" />
        {emptyHint}
      </div>
    );
  }

  return (
    <article
      className="flex flex-col gap-3"
      data-testid="document-body"
      aria-label="审查正文"
    >
      {paragraphs.map((p) => {
        const matched = risksByAnchor[p.anchor] ?? [];
        const top = pickTopSeverity(matched);
        const isSelected =
          !!selectedAnchor && selectedAnchor === p.anchor && matched.length > 0;
        return (
          <ParagraphBlock
            key={p.id}
            paragraph={p}
            matched={matched}
            topSeverity={top}
            isSelected={isSelected}
            onParagraphClick={onParagraphClick}
            onRiskClick={onRiskClick}
          />
        );
      })}
    </article>
  );
}

function ParagraphBlock({
  paragraph,
  matched,
  topSeverity,
  isSelected,
  onParagraphClick,
  onRiskClick,
}: {
  paragraph: ParagraphItem;
  matched: RiskItem[];
  topSeverity: RiskSeverity;
  isSelected: boolean;
  onParagraphClick?: (p: ParagraphItem, risks: RiskItem[]) => void;
  onRiskClick?: (r: RiskItem) => void;
}) {
  const [copied, setCopied] = React.useState(false);

  const handleCopy = React.useCallback(
    async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (typeof window === "undefined") return;
      try {
        await window.navigator.clipboard.writeText(paragraph.anchor);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1500);
      } catch {
        // 兜底：选中段落文本
        const el = document.getElementById(paragraph.anchor);
        if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    },
    [paragraph.anchor],
  );

  const clickable = matched.length > 0;

  return (
    <section
      id={paragraphDomId(paragraph)}
      data-paragraph-id={paragraph.id}
      data-testid="document-paragraph"
      className={cn(
        "group scroll-mt-32 rounded-lg border border-neutral-200 bg-white p-4 transition-shadow",
        clickable && severityRingClass[topSeverity],
        isSelected && "ring-2 ring-brand-500",
      )}
      onClick={
        clickable && onParagraphClick
          ? () => onParagraphClick(paragraph, matched)
          : undefined
      }
      role={clickable ? "button" : undefined}
      tabIndex={clickable ? 0 : -1}
    >
      <header className="mb-1 flex items-center gap-2 text-meta text-neutral-400">
        <span className="font-mono">#{paragraph.id}</span>
        <button
          type="button"
          onClick={handleCopy}
          className="inline-flex items-center gap-0.5 rounded text-neutral-400 hover:text-brand-600"
          title="复制锚点链接"
          aria-label="复制锚点链接"
        >
          <ExternalLink className="h-3 w-3" />
          {copied ? "已复制" : "锚点"}
        </button>
        {matched.length > 0 && (
          <span
            className={cn(
              "ml-auto inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
              topSeverity === "critical" || topSeverity === "high"
                ? "bg-red-100 text-red-700"
                : topSeverity === "medium"
                  ? "bg-amber-100 text-amber-700"
                  : "bg-neutral-100 text-neutral-600",
            )}
          >
            <span
              className={cn("h-1.5 w-1.5 rounded-full", severityDotClass[topSeverity])}
            />
            {matched.length} 处风险 · {severityLabel[topSeverity]}
          </span>
        )}
      </header>
      <p className="whitespace-pre-wrap text-base leading-7 text-neutral-800">
        {paragraph.text}
      </p>
      {matched.length > 0 && (
        <ul className="mt-3 flex flex-col gap-1.5 border-t border-neutral-100 pt-3">
          {matched.map((r, i) => (
            <li key={`${paragraph.id}-${i}`}>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onRiskClick?.(r);
                }}
                className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-neutral-50"
                data-testid="paragraph-risk-chip"
              >
                <span
                  className={cn(
                    "mt-1 h-1.5 w-1.5 shrink-0 rounded-full",
                    severityDotClass[r.severity],
                  )}
                />
                <span className="flex-1">
                  <span className="text-neutral-900">{r.risk_type}</span>
                  {r.evidence?.explanation && (
                    <span className="ml-1 text-neutral-500">
                      · {r.evidence.explanation}
                    </span>
                  )}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/**
 * 把 risks 列表按 paragraph_anchor 分桶；未命中任何段落的风险被忽略（前端只展示能定位的批注）。
 */
export function groupRisksByAnchor(risks: RiskItem[]): Record<string, RiskItem[]> {
  const out: Record<string, RiskItem[]> = {};
  for (const r of risks) {
    if (!r.paragraph_anchor) continue;
    if (!out[r.paragraph_anchor]) out[r.paragraph_anchor] = [];
    out[r.paragraph_anchor].push(r);
  }
  return out;
}
