"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  MessageSquareQuote,
  ThumbsUp,
  ThumbsDown,
  Check,
  CheckCircle2,
  Filter,
  Inbox,
  Loader2,
  ArrowRight,
  Reply,
} from "lucide-react";
import {
  closeMyFeedback,
  fetchMyFeedback,
  fetchMyFeedbackSummary,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton, SkeletonCard } from "@/components/ui/skeleton";
import { cn, formatRelativeTime } from "@/lib/utils";
import type {
  FeedbackStatus,
  FeedbackTargetKind,
  FeedbackVote,
  UserFeedback,
} from "@/types/api";

const PAGE_SIZE = 20;

type FilterMode = "all" | "open" | "resolved";

const STATUS_LABEL: Record<FeedbackStatus, string> = {
  open: "待处理",
  triaged: "已分诊",
  resolved: "已解决",
  wontfix: "暂不处理",
};

const STATUS_VARIANT: Record<
  FeedbackStatus,
  "default" | "secondary" | "success" | "warning" | "danger" | "outline"
> = {
  open: "warning",
  triaged: "default",
  resolved: "success",
  wontfix: "secondary",
};

const TARGET_LABEL: Record<FeedbackTargetKind, string> = {
  report: "审查报告",
  review: "审查任务",
  risk: "风险条目",
  assistant: "AI 助手",
};

function targetHref(kind: FeedbackTargetKind, id: string): string | null {
  const innerId = id.includes(":") ? id.split(":").slice(1).join(":") : id;
  switch (kind) {
    case "report":
      return `/report/${innerId}`;
    case "review":
      return `/review/${innerId}`;
    case "risk":
    case "assistant":
      return null;
    default:
      return null;
  }
}

function isOpenStatus(s: FeedbackStatus) {
  return s === "open" || s === "triaged";
}

export default function FeedbackCenterPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const qc = useQueryClient();
  const [filter, setFilter] = React.useState<FilterMode>("all");
  const [page, setPage] = React.useState(1);

  const isAuthed = !!token;

  const summaryQuery = useQuery({
    queryKey: ["my-feedback-summary"],
    queryFn: () => fetchMyFeedbackSummary(),
    enabled: isAuthed,
    staleTime: 30_000,
  });

  const listQuery = useQuery({
    queryKey: ["my-feedback", filter, page],
    queryFn: () =>
      fetchMyFeedback({
        status: filter === "all" ? undefined : filter,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: isAuthed,
    placeholderData: (prev) => prev,
  });

  const closeMutation = useMutation({
    mutationFn: (id: string) => closeMyFeedback(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["my-feedback"] });
      qc.invalidateQueries({ queryKey: ["my-feedback-summary"] });
    },
  });

  const items = listQuery.data?.items ?? [];
  const total = listQuery.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div
      className="mx-auto flex w-full max-w-4xl flex-col gap-6 py-6"
      data-testid="feedback-center"
    >
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-page-title">
            <MessageSquareQuote className="h-5 w-5 text-brand-600" />
            反馈中心
          </h1>
          <p className="mt-1 text-meta">
            这里汇总了你对报告、审查与 AI 助手的全部反馈。
            管理员处理后会在此处出现回复。
          </p>
        </div>
        <div
          className="flex flex-wrap items-center gap-2"
          aria-label="汇总"
          data-testid="feedback-summary"
        >
          {summaryQuery.isLoading ? (
            <Skeleton className="h-5 w-24" />
          ) : (
            <>
              <SummaryChip
                label="待处理"
                value={summaryQuery.data?.by_status?.open ?? 0}
                tone="warning"
              />
              <SummaryChip
                label="已分诊"
                value={summaryQuery.data?.by_status?.triaged ?? 0}
                tone="default"
              />
              <SummaryChip
                label="已解决"
                value={summaryQuery.data?.by_status?.resolved ?? 0}
                tone="success"
              />
              <SummaryChip
                label="暂不处理"
                value={summaryQuery.data?.by_status?.wontfix ?? 0}
                tone="secondary"
              />
            </>
          )}
        </div>
      </header>

      <div className="flex flex-wrap items-center gap-2" role="tablist" aria-label="状态筛选">
        <Filter className="h-4 w-4 text-neutral-400" aria-hidden />
        {(
          [
            { value: "all", label: "全部" },
            { value: "open", label: "进行中" },
            { value: "resolved", label: "已关闭" },
          ] as const
        ).map((opt) => {
          const active = filter === opt.value;
          return (
            <button
              key={opt.value}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => {
                setFilter(opt.value);
                setPage(1);
              }}
              className={cn(
                "inline-flex h-8 items-center rounded-md border px-3 text-sm transition-colors",
                active
                  ? "border-brand-500 bg-brand-50 text-brand-700"
                  : "border-neutral-200 bg-white text-neutral-600 hover:border-neutral-300",
              )}
              data-testid={`feedback-filter-${opt.value}`}
            >
              {opt.label}
            </button>
          );
        })}
      </div>

      {!isAuthed ? (
        <Card>
          <CardContent className="py-10">
            <EmptyState
              icon={<MessageSquareQuote className="h-5 w-5" />}
              title="登录后查看你的反馈"
              description="反馈中心仅对登录用户开放，去登录后即可看到你提交过的所有意见。"
              action={
                <Button
                  variant="default"
                  onClick={() => router.push("/login?redirect=/dashboard/feedback")}
                >
                  去登录
                </Button>
              }
            />
          </CardContent>
        </Card>
      ) : listQuery.isLoading ? (
        <div className="space-y-3" data-testid="feedback-loading">
          {Array.from({ length: 3 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-10">
            <EmptyState
              icon={<Inbox className="h-5 w-5" />}
              title={filter === "all" ? "还没有反馈" : "这一栏是空的"}
              description={
                filter === "all"
                  ? "在审查、报告或 AI 助手页底部的反馈条即可提交第一条意见。"
                  : "试试切换到「全部」看看。"
              }
            />
          </CardContent>
        </Card>
      ) : (
        <ul className="space-y-3" data-testid="feedback-list">
          {items.map((it) => (
            <FeedbackRow
              key={it.id}
              item={it}
              onClose={(id) => closeMutation.mutate(id)}
              closing={closeMutation.isPending && closeMutation.variables === it.id}
            />
          ))}
        </ul>
      )}

      {totalPages > 1 ? (
        <nav
          className="flex items-center justify-center gap-2 pt-2"
          aria-label="分页"
        >
          <Button
            variant="outline"
            size="sm"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            上一页
          </Button>
          <span className="text-meta">
            第 {page} / {totalPages} 页
          </span>
          <Button
            variant="outline"
            size="sm"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            下一页
          </Button>
        </nav>
      ) : null}
    </div>
  );
}

function SummaryChip({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "default" | "secondary" | "success" | "warning";
}) {
  return (
    <Badge variant={tone} className="gap-1.5">
      <span className="font-semibold">{value}</span>
      <span className="opacity-80">{label}</span>
    </Badge>
  );
}

function FeedbackRow({
  item,
  onClose,
  closing,
}: {
  item: UserFeedback;
  onClose: (id: string) => void;
  closing: boolean;
}) {
  const href = targetHref(item.target_kind, item.target_id);
  const isOpen = isOpenStatus(item.status);
  return (
    <li data-testid="feedback-row" data-feedback-id={item.id}>
      <Card className="transition-colors hover:border-neutral-300">
        <CardContent className="space-y-3 py-4">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2 text-meta">
              <Badge variant={STATUS_VARIANT[item.status]}>
                {STATUS_LABEL[item.status]}
              </Badge>
              <span className="text-neutral-500">
                {TARGET_LABEL[item.target_kind]}
              </span>
              <VoteIcon vote={item.vote} />
              <span className="text-neutral-700" data-testid="feedback-target-label">
                {item.target_label || item.target_id}
              </span>
              {href ? (
                <Link
                  href={href}
                  prefetch={false}
                  className="inline-flex items-center gap-1 text-brand-600 hover:text-brand-700"
                  data-testid="feedback-jump"
                >
                  查看源
                  <ArrowRight className="h-3 w-3" />
                </Link>
              ) : (
                <span className="text-neutral-400">（仅作记录，无对应页面）</span>
              )}
            </div>
            <span className="text-xs text-neutral-400" title={item.created_at}>
              {formatRelativeTime(item.created_at)}
            </span>
          </div>

          {item.comment ? (
            <p
              className="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-800"
              data-testid="feedback-comment"
            >
              {item.comment}
            </p>
          ) : (
            <p className="text-meta text-neutral-400">（未填写文字）</p>
          )}

          {item.admin_reply ? (
            <div
              className="flex items-start gap-2 rounded-md border border-brand-200 bg-brand-50/60 px-3 py-2 text-sm"
              data-testid="feedback-admin-reply"
            >
              <Reply className="mt-0.5 h-3.5 w-3.5 shrink-0 text-brand-600" />
              <div>
                <p className="text-meta text-brand-700">管理员回复</p>
                <p className="mt-0.5 text-neutral-800">{item.admin_reply}</p>
              </div>
            </div>
          ) : null}

          <div className="flex items-center justify-end">
            {isOpen && !item.closed_at ? (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => onClose(item.id)}
                disabled={closing}
                className="text-neutral-500"
                data-testid="feedback-close"
              >
                {closing ? (
                  <Loader2 className="mr-1 h-3.5 w-3.5 animate-spin" />
                ) : (
                  <Check className="mr-1 h-3.5 w-3.5" />
                )}
                标记为已解决
              </Button>
            ) : item.closed_at ? (
              <span className="inline-flex items-center gap-1 text-meta text-success-600">
                <CheckCircle2 className="h-3.5 w-3.5" /> 已关闭
              </span>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </li>
  );
}

function VoteIcon({ vote }: { vote: FeedbackVote }) {
  if (vote === "up") {
    return (
      <ThumbsUp
        className="h-3.5 w-3.5 text-success-600"
        aria-label="正面反馈"
      />
    );
  }
  if (vote === "down") {
    return (
      <ThumbsDown
        className="h-3.5 w-3.5 text-danger-600"
        aria-label="负面反馈"
      />
    );
  }
  return (
    <span
      className="inline-flex h-3.5 w-3.5 items-center justify-center rounded-full border border-neutral-300"
      aria-label="中性反馈"
      title="中性"
    />
  );
}
