"use client";

import * as React from "react";
import { ChevronDown, AlertTriangle } from "lucide-react";
import type { RiskItem, RiskSeverity } from "@/types/api";
import { Badge } from "@/components/ui/badge";
import { EvidenceCard } from "./EvidenceCard";

const severityOrder: Record<RiskSeverity, number> = {
  high: 0,
  medium: 1,
  low: 2,
  info: 3,
};

const severityMeta: Record<
  RiskSeverity,
  { label: string; variant: "danger" | "warning" | "secondary" | "outline" }
> = {
  high: { label: "高风险", variant: "danger" },
  medium: { label: "中风险", variant: "warning" },
  low: { label: "低风险", variant: "secondary" },
  info: { label: "提示", variant: "outline" },
};

export function RiskList({ risks }: { risks: RiskItem[] }) {
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
    <ul className="flex flex-col gap-3">
      {sorted.map((risk) => (
        <RiskRow key={risk.id} risk={risk} />
      ))}
    </ul>
  );
}

function RiskRow({ risk }: { risk: RiskItem }) {
  const [open, setOpen] = React.useState(false);
  const meta = severityMeta[risk.severity];
  return (
    <li className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left hover:bg-gray-50"
      >
        <AlertTriangle
          className={
            risk.severity === "high"
              ? "h-5 w-5 text-red-500"
              : risk.severity === "medium"
                ? "h-5 w-5 text-amber-500"
                : "h-5 w-5 text-gray-400"
          }
        />
        <div className="flex flex-1 flex-col">
          <div className="flex items-center gap-2">
            <Badge variant={meta.variant}>{meta.label}</Badge>
            <span className="text-xs text-gray-400">{risk.category}</span>
          </div>
          <p className="mt-1 text-sm text-gray-800">{risk.description}</p>
        </div>
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
          {risk.evidence && risk.evidence.length > 0 && (
            <div>
              <div className="mb-2 text-xs font-medium text-brand-700">
                法规依据
              </div>
              <div className="flex flex-col gap-2">
                {risk.evidence.map((ev, i) => (
                  <EvidenceCard key={i} evidence={ev} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </li>
  );
}
