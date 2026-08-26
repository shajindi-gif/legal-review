"use client";

import * as React from "react";
import { ChevronDown, AlertTriangle, MapPin, Sparkles } from "lucide-react";
import type { RiskItem, RiskSeverity, RiskDimension, Evidence } from "@/types/api";
import { Badge } from "@/components/ui/badge";
import { TrustBadge } from "@/components/ui/trust-badge";
import { Citation } from "@/components/review/Citation";
import { cn } from "@/lib/utils";

const severityOrder: Record<RiskSeverity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
  info: 4,
};

const severityMeta: Record<
  RiskSeverity,
  { label: string; variant: "danger" | "warning" | "secondary" | "outline" }
> = {
  critical: { label: "严重", variant: "danger" },
  high: { label: "高风险", variant: "danger" },
  medium: { label: "中风险", variant: "warning" },
  low: { label: "低风险", variant: "secondary" },
  info: { label: "提示", variant: "outline" },
};

const dimensionLabel: Record<RiskDimension, string> = {
  authority: "主体权限",
  procedure: "程序合规",
  content: "合同内容",
  prohibition: "禁止性规定",
  interest: "利益冲突",
};

function stableKey(risk: RiskItem, idx: number): string {
  if (risk.paragraph_anchor) return `${risk.paragraph_anchor}-${idx}`;
  return `${risk.dimension}-${risk.risk_type}-${idx}`;
}

export function RiskList({
  risks,
  onSelect,
  onOpenEvidence,
  selectedAnchor,
  className,
}: {
  risks: RiskItem[];
  onSelect?: (risk: RiskItem) => void;
  /**
   * 用户点击法规依据时回调：把 evidence 推到 EvidencePanel 聚焦。
   * 缺省时仅做内联展示（点 Citation 不会联动）。
   */
  onOpenEvidence?: (risk: RiskItem, evidence: Evidence) => void;
  selectedAnchor?: string | null;
  className?: string;
}) {
  const sorted = React.useMemo(
    () =>
      [...risks].sort(
        (a, b) => severityOrder[a.severity] - severityOrder[b.severity],
      ),
    [risks],
  );

  if (risks.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center rounded-lg border border-dashed border-gray-200 text-sm text-gray-400">
        未识别到法律风险
      </div>
    );
  }

  return (
    <ul className={cn("flex flex-col gap-3", className)}>
      {sorted.map((risk, idx) => (
        <RiskRow
          key={stableKey(risk, idx)}
          risk={risk}
          isSelected={
            !!selectedAnchor && selectedAnchor === risk.paragraph_anchor
          }
          onSelect={onSelect}
          onOpenEvidence={onOpenEvidence}
        />
      ))}
    </ul>
  );
}

function RiskRow({
  risk,
  isSelected,
  onSelect,
  onOpenEvidence,
}: {
  risk: RiskItem;
  isSelected: boolean;
  onSelect?: (risk: RiskItem) => void;
  onOpenEvidence?: (risk: RiskItem, evidence: Evidence) => void;
}) {
  const [open, setOpen] = React.useState(false);
  const meta = severityMeta[risk.severity] ?? severityMeta.info;
  const dimLabel = dimensionLabel[risk.dimension] ?? risk.dimension;

  const handleJump = () => {
    if (risk.paragraph_anchor && onSelect) {
      onSelect(risk);
    }
  };

  return (
    <li
      className={`overflow-hidden rounded-lg border bg-white transition-colors ${
        isSelected ? "border-brand-500 ring-2 ring-brand-100" : "border-gray-200"
      }`}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left hover:bg-gray-50"
      >
        <AlertTriangle
          className={
            risk.severity === "critical" || risk.severity === "high"
              ? "h-5 w-5 text-red-500"
              : risk.severity === "medium"
                ? "h-5 w-5 text-amber-500"
                : "h-5 w-5 text-gray-400"
          }
        />
        <div className="flex flex-1 flex-col">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={meta.variant}>{meta.label}</Badge>
            <span className="text-xs text-gray-500">{dimLabel}</span>
            <span className="text-xs text-gray-400">·</span>
            <span className="text-xs text-gray-700">{risk.risk_type}</span>
            {risk.confidence !== undefined && (
              <span className="text-xs text-gray-400">
                置信度 {Math.round(risk.confidence * 100)}%
              </span>
            )}
            {/* UI-M9.3: 风险由 AI 识别，必须打 Trust 角标 */}
            <TrustBadge kind="ai" className="ml-1" />
          </div>
          {risk.evidence?.explanation && (
            <p className="mt-1 text-sm text-gray-800">
              {risk.evidence.explanation}
            </p>
          )}
        </div>
        {risk.paragraph_anchor && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              handleJump();
            }}
            className="inline-flex items-center gap-1 rounded-md border border-brand-200 bg-white px-2 py-1 text-xs text-brand-700 hover:bg-brand-50"
            title="定位到正文段落"
            data-testid="risk-jump-anchor"
          >
            <MapPin className="h-3 w-3" />
            定位
          </button>
        )}
        <ChevronDown
          className={`h-4 w-4 shrink-0 text-gray-400 transition-transform ${
            open ? "rotate-180" : ""
          }`}
        />
      </button>
      {open && (
        <div className="flex flex-col gap-3 border-t border-gray-100 bg-gray-50/50 p-4">
          {risk.suggestion && (
            <div>
              <div className="text-xs font-medium text-brand-700">审查建议</div>
              <p className="mt-1 text-sm text-gray-700">{risk.suggestion}</p>
            </div>
          )}
          {risk.evidence && (
            <div>
              <div className="mb-2 flex items-center gap-1.5 text-xs font-medium text-brand-700">
                <Sparkles className="h-3 w-3" />
                法规依据
                <span className="font-normal text-neutral-400">
                  {onOpenEvidence ? "· 点击 Citation 联动右侧证据面板" : ""}
                </span>
              </div>
              {/* UI-M9.2: 法规依据统一用 Citation，与 EvidencePanel 联动 */}
              <Citation
                evidence={risk.evidence}
                index={1}
                onFocus={(e) => onOpenEvidence?.(risk, e)}
              />
            </div>
          )}
        </div>
      )}
    </li>
  );
}
