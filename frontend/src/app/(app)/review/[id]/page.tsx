"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  AlertCircle,
  Lightbulb,
  ShieldAlert,
  PanelRight,
  PanelRightClose,
  FileText,
} from "lucide-react";
import {
  fetchReport,
  fetchReviewDetail,
  fetchTaskDocuments,
  fetchTaskStatus,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { useQueryClient } from "@tanstack/react-query";
import { subscribeReviewStream } from "@/lib/sse";
import type { Evidence, ParagraphItem, ReviewNode, RiskItem } from "@/types/api";
import { NodeFlowChart } from "@/components/review/NodeFlowChart";
import { RiskList } from "@/components/review/RiskList";
import {
  DocumentBody,
  groupRisksByAnchor,
  paragraphDomId,
} from "@/components/review/DocumentBody";
import {
  EvidencePanel,
  buildDefaultEvidenceGroups,
} from "@/components/review/EvidencePanel";
import { FeedbackBar } from "@/components/ui/feedback-bar";
import { TrustBadge } from "@/components/ui/trust-badge";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

const SEVERITY_BADGE: Record<RiskItem["severity"], string> = {
  critical: "bg-red-100 text-red-700",
  high: "bg-red-100 text-red-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-neutral-100 text-neutral-600",
  info: "bg-neutral-100 text-neutral-500",
};

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const token = useAuthStore((s) => s.token);
  const qc = useQueryClient();

  const { data: detail } = useQuery({
    queryKey: ["review", id],
    queryFn: () => fetchReviewDetail(id),
    enabled: !!token && !!id,
  });
  const { data: status } = useQuery({
    queryKey: ["review-status", id],
    queryFn: () => fetchTaskStatus(id),
    enabled: !!token && !!id,
    refetchInterval: (q) => {
      const s = q.state.data?.status;
      return s === "done" || s === "completed" || s === "failed" ? false : 3000;
    },
  });

  const [nodes, setNodes] = React.useState<ReviewNode[]>([]);
  const [risks, setRisks] = React.useState<RiskItem[]>([]);
  const [evidence, setEvidence] = React.useState<Evidence[]>([]);
  const [suggestions, setSuggestions] = React.useState<string[]>([]);
  const [sseError, setSseError] = React.useState<string | null>(null);

  // 3 栏：左节点流 / 中正文+批注 / 右证据
  const [leftOpen, setLeftOpen] = React.useState(true);
  const [panelOpen, setPanelOpen] = React.useState(true);

  // 联动：风险 ↔ 段落
  const [selectedAnchor, setSelectedAnchor] = React.useState<string | null>(null);
  const [focusedRiskKey, setFocusedRiskKey] = React.useState<string | null>(null);
  const [focusedEvidenceKey, setFocusedEvidenceKey] = React.useState<
    string | null
  >(null);

  // 拉取任务关联文件，拿 body_paragraphs
  const { data: documents } = useQuery({
    queryKey: ["review-documents", id],
    queryFn: () => fetchTaskDocuments(id),
    enabled: !!token && !!id,
  });

  const paragraphs: ParagraphItem[] = React.useMemo(() => {
    if (!documents) return [];
    const out: ParagraphItem[] = [];
    for (const doc of documents) {
      const pj = doc.parsed_json;
      if (!pj?.body_paragraphs) continue;
      for (const p of pj.body_paragraphs) {
        out.push(p);
      }
    }
    return out;
  }, [documents]);

  const risksByAnchor = React.useMemo(
    () => groupRisksByAnchor(risks),
    [risks],
  );

  const handleSelectRisk = React.useCallback((r: RiskItem) => {
    setFocusedRiskKey(`${r.dimension}-${r.risk_type}-${r.paragraph_anchor ?? ""}`);
    if (r.paragraph_anchor) {
      setSelectedAnchor(r.paragraph_anchor);
      if (typeof window !== "undefined") {
        window.setTimeout(() => {
          const el = document.getElementById(paragraphDomId({ id: r.paragraph_anchor!.replace(/^#/, ""), text: "", anchor: r.paragraph_anchor! }));
          if (el) el.scrollIntoView({ behavior: "smooth", block: "center" });
        }, 30);
      }
    }
  }, []);

  const handleParagraphClick = React.useCallback(
    (_p: ParagraphItem, matched: RiskItem[]) => {
      if (matched.length > 0) {
        setFocusedRiskKey(
          `${matched[0].dimension}-${matched[0].risk_type}-${matched[0].paragraph_anchor ?? ""}`,
        );
        setSelectedAnchor(_p.anchor);
        // 滚动到右栏风险卡
        if (typeof window !== "undefined") {
          window.setTimeout(() => {
            const el = document.querySelector(
              `[data-testid="risk-card"][data-risk-key="${CSS.escape(
                `${matched[0].dimension}-${matched[0].risk_type}-${matched[0].paragraph_anchor ?? ""}`,
              )}"]`,
            );
            if (el)
              (el as HTMLElement).scrollIntoView({
                behavior: "smooth",
                block: "center",
              });
          }, 30);
        }
      }
    },
    [],
  );

  const handleRiskClickOnParagraph = React.useCallback((r: RiskItem) => {
    setFocusedRiskKey(`${r.dimension}-${r.risk_type}-${r.paragraph_anchor ?? ""}`);
    if (r.evidence) {
      const idx = evidence.findIndex(
        (e) =>
          e.law_name === r.evidence!.law_name &&
          e.article === r.evidence!.article,
      );
      setFocusedEvidenceKey(idx >= 0 ? `regulation#${idx}` : null);
      setPanelOpen(true);
    }
  }, [evidence]);

  React.useEffect(() => {
    if (!status) return;
    if (status.current_node && status.progress > 0) {
      setNodes((prev) => {
        const idx = prev.findIndex((n) => n.id === status.current_node);
        if (idx >= 0) return prev;
        return [
          ...prev,
          {
            id: status.current_node as string,
            name: status.current_node as string,
            label: status.current_node as string,
            status: "running",
          },
        ];
      });
    }
    if (
      status.status === "completed" ||
      status.status === "done" ||
      status.status === "failed"
    ) {
      qc.invalidateQueries({ queryKey: ["reviews"] });
    }
  }, [status, qc]);

  const { data: report } = useQuery({
    queryKey: ["report", id],
    queryFn: () => fetchReport(id),
    enabled: !!token && !!id,
    retry: false,
    refetchInterval: (q) => {
      const has = !!q.state.data;
      return has ? false : 5000;
    },
  });
  const completed = !!report;

  React.useEffect(() => {
    if (!id || !token) return;
    setSseError(null);
    const unsubscribe = subscribeReviewStream(id, {
      token,
      onEvent: (ev) => {
        switch (ev.type) {
          case "node_start":
            setNodes((prev) =>
              upsertNode(prev, {
                id: ev.node_id,
                name: ev.node_name,
                label: ev.node_name,
                status: "running",
                started_at: ev.ts,
              }),
            );
            break;
          case "node_finish":
            setNodes((prev) =>
              upsertNode(prev, {
                id: ev.node_id,
                name: ev.node_name,
                label: ev.node_name,
                status: "done",
                finished_at: ev.ts,
                detail: ev.detail,
              }),
            );
            break;
          case "risk_found":
            setRisks((prev) => [...prev, ev.risk]);
            break;
          case "evidence":
            setEvidence((prev) => [...prev, ev.evidence]);
            break;
          case "suggestion":
            setSuggestions((prev) => [...prev, ev.suggestion]);
            break;
          case "complete":
            qc.invalidateQueries({ queryKey: ["reviews"] });
            qc.invalidateQueries({ queryKey: ["review", ev.review_id] });
            qc.invalidateQueries({ queryKey: ["review-status", ev.review_id] });
            qc.invalidateQueries({ queryKey: ["report", ev.review_id] });
            qc.invalidateQueries({
              queryKey: ["review-documents", ev.review_id],
            });
            break;
          case "error":
            setSseError(ev.message);
            break;
        }
      },
      onError: () => setSseError("实时连接中断，可刷新重试"),
    });
    return unsubscribe;
  }, [id, token, qc]);

  React.useEffect(() => {
    if (!report) return;
    if (report.risks?.length) setRisks(report.risks);
    if (report.evidences?.length) setEvidence(report.evidences);
  }, [report]);

  const evidenceGroups = buildDefaultEvidenceGroups(evidence);

  // 按 paragraph_anchor 命中的风险数统计
  const anchoredCount = risks.filter((r) => !!r.paragraph_anchor).length;
  const unanchoredCount = risks.length - anchoredCount;

  return (
    <div className="flex h-full min-h-0 gap-4">
      {/* 左：节点流转 + 摘要 */}
      <aside
        className={cn(
          "flex shrink-0 flex-col gap-4 transition-all",
          leftOpen ? "w-72" : "w-12",
        )}
        data-testid="review-left"
      >
        <div className="flex items-center justify-between">
          {leftOpen && (
            <span className="text-xs font-medium text-neutral-500">审查节点</span>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setLeftOpen((v) => !v)}
            aria-label={leftOpen ? "折叠节点栏" : "展开节点栏"}
            className="ml-auto h-7 w-7 p-0"
          >
            {leftOpen ? "«" : "»"}
          </Button>
        </div>
        {leftOpen ? (
          <>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">流转进度</CardTitle>
              </CardHeader>
              <CardContent>
                <NodeFlowChart nodes={nodes} />
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-sm">批注概览</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2 text-sm">
                <div className="flex items-center justify-between">
                  <span className="text-neutral-500">风险总数</span>
                  <span className="font-semibold text-neutral-900">
                    {risks.length}
                  </span>
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-neutral-500">已定位段落</span>
                  <span className="font-semibold text-neutral-900">
                    {anchoredCount}
                  </span>
                </div>
                {unanchoredCount > 0 && (
                  <div className="flex items-center justify-between">
                    <span className="text-neutral-500">未定位</span>
                    <span className="text-neutral-500">{unanchoredCount}</span>
                  </div>
                )}
                <div className="mt-2 flex flex-wrap gap-1">
                  {(["critical", "high", "medium", "low", "info"] as const).map(
                    (s) => {
                      const n = risks.filter((r) => r.severity === s).length;
                      if (n === 0) return null;
                      return (
                        <span
                          key={s}
                          className={cn(
                            "rounded-full px-2 py-0.5 text-[10px] font-medium",
                            SEVERITY_BADGE[s],
                          )}
                        >
                          {s} · {n}
                        </span>
                      );
                    },
                  )}
                </div>
              </CardContent>
            </Card>
            {suggestions.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-1.5 text-sm">
                    <Lightbulb className="h-3.5 w-3.5 text-amber-500" /> 修改建议
                    <TrustBadge kind="ai" className="ml-1" />
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <ul className="flex flex-col gap-2">
                    {suggestions.map((s, i) => (
                      <li
                        key={i}
                        className="rounded-md bg-amber-50 p-2 text-xs text-gray-700"
                      >
                        {s}
                      </li>
                    ))}
                  </ul>
                </CardContent>
              </Card>
            )}
          </>
        ) : null}
      </aside>

      {/* 中：标题 + 风险清单 + 正文+批注 */}
      <div
        className="flex min-w-0 flex-1 flex-col gap-4"
        data-testid="review-main"
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-page-title">
                {detail?.title ?? "审查进行中"}
              </h1>
              {/* UI-M9.3: 审查结果由 AI 产出 */}
              <TrustBadge kind="ai" />
            </div>
            <p className="mt-1 text-meta">审查编号：{id}</p>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setPanelOpen((v) => !v)}
              aria-pressed={panelOpen}
              aria-label={panelOpen ? "隐藏证据面板" : "显示证据面板"}
            >
              {panelOpen ? (
                <>
                  <PanelRightClose className="h-4 w-4" /> 隐藏证据
                </>
              ) : (
                <>
                  <PanelRight className="h-4 w-4" /> 证据
                </>
              )}
            </Button>
            {completed ? (
              <Badge variant="success">审查完成</Badge>
            ) : (
              <Badge variant="warning">
                审查中
                {status?.progress
                  ? ` ${Math.round(status.progress * 100)}%`
                  : ""}
              </Badge>
            )}
            {completed && (
              <Link href={`/report/${id}`}>
                <Button size="sm" variant="outline">
                  查看完整报告
                </Button>
              </Link>
            )}
          </div>
        </div>

        {sseError && (
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-4 py-2 text-sm text-amber-700">
            <AlertCircle className="h-4 w-4" /> {sseError}
          </div>
        )}

        {/* 风险清单（可滚动区） */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <ShieldAlert className="h-4 w-4 text-red-500" /> 风险清单
              <Badge variant="secondary">{risks.length}</Badge>
              <span className="ml-auto text-xs font-normal text-neutral-400">
                点击"定位"跳转正文
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex max-h-[42vh] flex-col gap-3 overflow-y-auto pr-1">
              {risks.length === 0 ? (
                <li className="flex h-24 items-center justify-center rounded-lg border border-dashed border-gray-200 text-sm text-gray-400">
                  暂无风险批注
                </li>
              ) : (
                risks.map((r, idx) => {
                  const key = `${r.dimension}-${r.risk_type}-${r.paragraph_anchor ?? ""}-${idx}`;
                  return (
                    <li
                      key={key}
                      data-testid="risk-card"
                      data-risk-key={`${r.dimension}-${r.risk_type}-${r.paragraph_anchor ?? ""}`}
                      className={cn(
                        "rounded-lg border bg-white transition-colors",
                        focusedRiskKey ===
                          `${r.dimension}-${r.risk_type}-${r.paragraph_anchor ?? ""}`
                          ? "border-brand-500 ring-2 ring-brand-100"
                          : "border-gray-200",
                      )}
                    >
                      <RiskCardBody
                        risk={r}
                        isFocused={
                          focusedRiskKey ===
                          `${r.dimension}-${r.risk_type}-${r.paragraph_anchor ?? ""}`
                        }
                        onLocate={() => handleSelectRisk(r)}
                        onOpenEvidence={() => {
                          if (r.evidence) {
                            const idx = evidence.findIndex(
                              (e) =>
                                e.law_name === r.evidence!.law_name &&
                                e.article === r.evidence!.article,
                            );
                            setFocusedEvidenceKey(
                              idx >= 0 ? `regulation#${idx}` : null,
                            );
                            setPanelOpen(true);
                          }
                        }}
                      />
                    </li>
                  );
                })
              )}
            </ul>
          </CardContent>
        </Card>

        {/* 正文 + 批注（核心） */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-brand-600" /> 文档原文与审查批注
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DocumentBody
              paragraphs={paragraphs}
              risksByAnchor={risksByAnchor}
              selectedAnchor={selectedAnchor}
              onParagraphClick={handleParagraphClick}
              onRiskClick={handleRiskClickOnParagraph}
            />
          </CardContent>
        </Card>

        {completed && id ? (
          <FeedbackBar
            targetId={`review:${id}`}
            targetKind="review"
            targetLabel={detail?.title ?? `审查 #${id}`}
            context={{ riskCount: risks.length }}
            className="px-1"
          />
        ) : null}
      </div>

      {/* 右：证据面板 */}
      <EvidencePanel
        open={panelOpen}
        onClose={() => setPanelOpen(false)}
        groups={evidenceGroups}
        focusedId={focusedEvidenceKey}
        onFocus={(e) => {
          const idx = evidence.findIndex(
            (x) => x.law_name === e.law_name && x.article === e.article,
          );
          if (idx >= 0) setFocusedEvidenceKey(`regulation#${idx}`);
          // 找对应风险（按 evidence 内容匹配），并高亮
          const matched = risks.find(
            (r) =>
              r.evidence?.law_name === e.law_name &&
              r.evidence?.article === e.article,
          );
          if (matched) handleSelectRisk(matched);
        }}
      />
    </div>
  );
}

function RiskCardBody({
  risk,
  isFocused,
  onLocate,
  onOpenEvidence,
}: {
  risk: RiskItem;
  isFocused: boolean;
  onLocate: () => void;
  onOpenEvidence: () => void;
}) {
  const sevBadge = SEVERITY_BADGE[risk.severity] ?? SEVERITY_BADGE.info;
  return (
    <div className="p-4">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 text-[10px] font-semibold",
            sevBadge,
          )}
        >
          {risk.severity}
        </span>
        <span className="text-xs text-neutral-700">{risk.risk_type}</span>
        {risk.confidence !== undefined && (
          <span className="text-xs text-neutral-400">
            置信度 {Math.round(risk.confidence * 100)}%
          </span>
        )}
        {/* UI-M9.3: 风险由 AI 识别，必须打 Trust 角标 */}
        <TrustBadge kind="ai" className="ml-0.5" />
        <span className="ml-auto flex items-center gap-2">
          {risk.paragraph_anchor && (
            <button
              type="button"
              onClick={onLocate}
              className="inline-flex items-center gap-1 rounded-md border border-brand-200 px-2 py-0.5 text-xs text-brand-700 hover:bg-brand-50"
              data-testid="risk-locate"
            >
              定位 → {risk.paragraph_anchor}
            </button>
          )}
          {risk.evidence && (
            <button
              type="button"
              onClick={onOpenEvidence}
              className="inline-flex items-center gap-1 rounded-md border border-neutral-200 px-2 py-0.5 text-xs text-neutral-700 hover:bg-neutral-50"
              data-testid="risk-open-evidence"
            >
              查看法规 →
            </button>
          )}
        </span>
      </div>
      {risk.evidence?.explanation && (
        <p className="mt-2 text-sm text-neutral-800">
          {risk.evidence.explanation}
        </p>
      )}
      {risk.suggestion && (
        <p className="mt-1 text-xs text-neutral-500">
          建议：{risk.suggestion}
        </p>
      )}
      {isFocused && (
        <p className="mt-1 text-[10px] text-brand-600">已选中 · 与右侧证据联动</p>
      )}
    </div>
  );
}

function upsertNode(prev: ReviewNode[], node: ReviewNode): ReviewNode[] {
  const idx = prev.findIndex((n) => n.id === node.id);
  if (idx === -1) return [...prev, node];
  const next = [...prev];
  next[idx] = { ...next[idx], ...node };
  return next;
}
