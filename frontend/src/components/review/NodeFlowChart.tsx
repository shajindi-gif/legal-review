"use client";

import * as React from "react";
import { Check, Loader2 } from "lucide-react";
import type { NodeStatus, ReviewNode } from "@/types/api";
import { cn } from "@/lib/utils";

/** 11 节点 LangGraph 审查流水线（canonical 顺序）。 */
const FLOW: { id: string; label: string; desc: string }[] = [
  { id: "parse", label: "文档解析", desc: "提取文本与结构" },
  { id: "doc_classify", label: "文档分类", desc: "识别文件类型" },
  { id: "legal_query", label: "法规检索", desc: "BGE-M3 检索匹配法规" },
  { id: "authority_review", label: "主体审查", desc: "审查制定主体权限" },
  { id: "content_review", label: "内容审查", desc: "审查条款合法性" },
  { id: "procedure_review", label: "程序审查", desc: "审查制定程序" },
  { id: "risk_assessment", label: "风险评估", desc: "识别法律风险" },
  { id: "evidence_verify", label: "证据核验", desc: "核验法规依据原文" },
  { id: "synthesize", label: "综合研判", desc: "汇总审查结论" },
  { id: "report_generation", label: "报告生成", desc: "生成审查意见书" },
  { id: "human_review", label: "人工复核", desc: "人工把关闭环" },
];

function statusOf(
  id: string,
  runtime: Map<string, ReviewNode>,
  currentIndex: number,
  activeIndex: number,
): NodeStatus {
  const r = runtime.get(id);
  if (r) return r.status;
  if (currentIndex < 0) return "pending";
  if (currentIndex < activeIndex) return "done";
  if (currentIndex === activeIndex) return "running";
  return "pending";
}

function StatusDot({ status }: { status: NodeStatus }) {
  if (status === "done") {
    return (
      <svg viewBox="0 0 24 24" className="h-5 w-5 text-green-600" fill="none">
        <circle cx="12" cy="12" r="10" fill="currentColor" opacity="0.15" />
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
        <path
          d="M8 12.5l2.5 2.5L16 9.5"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    );
  }
  if (status === "running") {
    return <Loader2 className="h-5 w-5 animate-spin text-brand-600" />;
  }
  if (status === "skipped") {
    return (
      <svg viewBox="0 0 24 24" className="h-5 w-5 text-gray-300" fill="none">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      </svg>
    );
  }
  return (
    <svg viewBox="0 0 24 24" className="h-5 w-5 text-gray-300" fill="none">
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeWidth="2" />
      <circle cx="12" cy="12" r="3" fill="currentColor" />
    </svg>
  );
}

export function NodeFlowChart({ nodes }: { nodes: ReviewNode[] }) {
  const runtime = React.useMemo(() => {
    const m = new Map<string, ReviewNode>();
    nodes.forEach((n) => m.set(n.id, n));
    return m;
  }, [nodes]);

  // 推断当前激活节点（最后一个 running 或首个非 done）
  const activeIndex = React.useMemo(() => {
    const running = FLOW.findIndex((f) => runtime.get(f.id)?.status === "running");
    if (running >= 0) return running;
    const firstPending = FLOW.findIndex((f) => {
      const s = runtime.get(f.id)?.status;
      return s !== "done" && s !== "skipped";
    });
    return firstPending >= 0 ? firstPending : FLOW.length;
  }, [runtime]);

  return (
    <div className="flex flex-col">
      <div className="relative pl-2">
        {/* 左侧连接线（SVG） */}
        <svg
          className="absolute left-[26px] top-3 h-[calc(100%-1.5rem)] w-px"
          preserveAspectRatio="none"
        >
          <line x1="0" y1="0" x2="0" y2="100%" stroke="#e5e7eb" strokeWidth="2" />
        </svg>
        {FLOW.map((f, i) => {
          const status = statusOf(f.id, runtime, i, activeIndex);
          const isRunning = status === "running";
          return (
            <div
              key={f.id}
              className={cn(
                "relative flex items-start gap-3 rounded-lg p-2 transition-colors",
                isRunning && "bg-brand-50 ring-1 ring-brand-200",
              )}
            >
              <div className="z-10 mt-0.5 shrink-0 bg-white">
                <StatusDot status={status} />
              </div>
              <div className="flex flex-col">
                <span
                  className={cn(
                    "text-sm font-medium",
                    status === "done"
                      ? "text-gray-500"
                      : isRunning
                        ? "text-brand-700"
                        : "text-gray-700",
                  )}
                >
                  {f.label}
                </span>
                <span className="text-xs text-gray-400">{f.desc}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
