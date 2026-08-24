"use client";

import * as React from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { AlertCircle, Lightbulb, ShieldAlert } from "lucide-react";
import { fetchReport, fetchReviewDetail, fetchTaskStatus } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { subscribeReviewStream } from "@/lib/sse";
import type { Evidence, ReviewNode, RiskItem } from "@/types/api";
import { NodeFlowChart } from "@/components/review/NodeFlowChart";
import { RiskList } from "@/components/review/RiskList";
import { EvidenceCard } from "@/components/review/EvidenceCard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

export default function ReviewPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const token = useAuthStore((s) => s.token);

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

  // 状态查询里直接有 progress / current_node，作为兜底
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
  }, [status]);

  // 报告是否就绪：拉一次 report，404 表示还没到
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

  // 订阅 SSE 节点流转
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
          case "error":
            setSseError(ev.message);
            break;
        }
      },
      onError: () => setSseError("实时连接中断，可刷新重试"),
    });
    return unsubscribe;
  }, [id, token]);

  // 报告就绪后回填风险/证据（report 端点同时返回）
  React.useEffect(() => {
    if (!report) return;
    if (report.risks?.length) setRisks(report.risks);
    if (report.evidences?.length) setEvidence(report.evidences);
  }, [report]);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">
            {detail?.title ?? "审查进行中"}
          </h1>
          <p className="mt-1 text-sm text-gray-500">审查编号：{id}</p>
        </div>
        <div className="flex items-center gap-2">
          {completed ? (
            <Badge variant="success">审查完成</Badge>
          ) : (
            <Badge variant="warning">
              审查中{status?.progress ? ` ${Math.round(status.progress * 100)}%` : ""}
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

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* 左：节点流转图 */}
        <Card className="lg:col-span-1 lg:sticky lg:top-24 h-fit">
          <CardHeader>
            <CardTitle className="text-base">审查节点流转</CardTitle>
          </CardHeader>
          <CardContent>
            <NodeFlowChart nodes={nodes} />
          </CardContent>
        </Card>

        {/* 右：风险 / 证据 / 建议 */}
        <div className="flex flex-col gap-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldAlert className="h-4 w-4 text-red-500" /> 风险清单
                <Badge variant="secondary">{risks.length}</Badge>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <RiskList risks={risks} />
            </CardContent>
          </Card>

          {evidence.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">法规依据</CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-2">
                {evidence.map((ev, i) => (
                  <EvidenceCard key={i} evidence={ev} />
                ))}
              </CardContent>
            </Card>
          )}

          {suggestions.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-base">
                  <Lightbulb className="h-4 w-4 text-amber-500" /> 修改建议
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="flex flex-col gap-2">
                  {suggestions.map((s, i) => (
                    <li
                      key={i}
                      className="rounded-lg bg-amber-50 p-3 text-sm text-gray-700"
                    >
                      {s}
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      </div>
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
