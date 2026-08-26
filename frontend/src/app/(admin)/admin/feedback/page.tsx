"use client";

import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as Dialog from "@radix-ui/react-dialog";
import {
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Filter,
  Inbox,
  Loader2,
  MessageSquareQuote,
  Reply,
  Send,
  ShieldAlert,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import {
  adminFeedbackSummary,
  adminListFeedback,
  adminUpdateFeedback,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { cn, formatDateTime, formatRelativeTime } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  FeedbackStatus,
  FeedbackTargetKind,
  FeedbackVote,
  UserFeedback,
} from "@/types/api";

/**
 * UI-M13 Admin 反馈管理后台。
 *
 * 设计：
 * - 角色守卫：非 admin 直接展示"无访问权限"卡片
 * - 数据：SummaryChip 4 段 + Filter 行 + 列表 + 翻页
 * - 操作：行内"答复"弹 Modal 写 admin_reply + 改 status;关闭统一走 wontfix
 * - 跳源：target_kind + target_id 拼路由(review / report)
 */

const STATUS_OPTIONS: { value: FeedbackStatus | "all"; label: string }[] = [
  { value: "all", label: "全部" },
  { value: "open", label: "Open" },
  { value: "triaged", label: "Triaged" },
  { value: "resolved", label: "Resolved" },
  { value: "wontfix", label: "Wontfix" },
];

const KIND_OPTIONS: { value: FeedbackTargetKind | "all"; label: string }[] = [
  { value: "all", label: "全部类型" },
  { value: "report", label: "报告" },
  { value: "review", label: "审查" },
  { value: "risk", label: "风险" },
  { value: "assistant", label: "助手" },
];

const STATUS_VARIANT: Record<
  FeedbackStatus,
  "default" | "secondary" | "outline" | "success" | "warning" | "danger"
> = {
  open: "default",
  triaged: "warning",
  resolved: "success",
  wontfix: "danger",
};

const STATUS_LABEL: Record<FeedbackStatus, string> = {
  open: "待处理",
  triaged: "已分诊",
  resolved: "已解决",
  wontfix: "不处理",
};

const KIND_LABEL: Record<FeedbackTargetKind, string> = {
  report: "报告",
  review: "审查",
  risk: "风险",
  assistant: "助手",
};

const PAGE_SIZE = 20;

function targetHref(kind: FeedbackTargetKind, id: string): string | null {
  // target_id 形如 "review:uuid" / "report:uuid" / 原值
  const realId = id.includes(":") ? id.split(":").pop() ?? id : id;
  if (kind === "review" || kind === "risk") return `/review/${realId}`;
  if (kind === "report") return `/report/${realId}`;
  return null;
}

function VoteBadge({ vote }: { vote: FeedbackVote }) {
  if (vote === "up") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-medium text-emerald-700">
        <ThumbsUp className="h-3 w-3" />
        赞
      </span>
    );
  }
  if (vote === "down") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700">
        <ThumbsDown className="h-3 w-3" />
        踩
      </span>
    );
  }
  return (
    <span className="inline-flex items-center rounded-full bg-neutral-100 px-2 py-0.5 text-[11px] font-medium text-neutral-500">
      —
    </span>
  );
}

export default function AdminFeedbackPage() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const [statusFilter, setStatusFilter] = React.useState<FeedbackStatus | "all">(
    "all",
  );
  const [kindFilter, setKindFilter] = React.useState<
    FeedbackTargetKind | "all"
  >("all");
  const [page, setPage] = React.useState(1);
  const [replying, setReplying] = React.useState<UserFeedback | null>(null);

  const authed = !!token && user?.role === "admin";

  const invalidateAll = React.useCallback(() => {
    qc.invalidateQueries({ queryKey: ["admin-feedback-summary"] });
    qc.invalidateQueries({ queryKey: ["admin-feedback-list"] });
  }, [qc]);

  const updateMutation = useMutation({
    mutationFn: (vars: {
      id: string;
      patch: { status?: FeedbackStatus; admin_reply?: string };
    }) => adminUpdateFeedback(vars.id, vars.patch),
    onSuccess: invalidateAll,
  });

  const summary = useQuery({
    queryKey: ["admin-feedback-summary"],
    queryFn: adminFeedbackSummary,
    enabled: authed,
    refetchOnWindowFocus: false,
  });

  const list = useQuery({
    queryKey: [
      "admin-feedback-list",
      statusFilter,
      kindFilter,
      page,
      PAGE_SIZE,
    ],
    queryFn: () =>
      adminListFeedback({
        status: statusFilter === "all" ? undefined : statusFilter,
        target_kind: kindFilter === "all" ? undefined : kindFilter,
        page,
        page_size: PAGE_SIZE,
      }),
    enabled: authed,
    placeholderData: (prev) => prev,
    refetchOnWindowFocus: false,
  });

  const total = list.data?.total ?? 0;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  React.useEffect(() => {
    setPage(1);
  }, [statusFilter, kindFilter]);

  if (user && user.role !== "admin") {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-3 py-20 text-center">
        <ShieldAlert className="h-10 w-10 text-red-500" />
        <h1 className="text-xl font-bold text-gray-900">无访问权限</h1>
        <p className="text-sm text-gray-500">该页面仅对管理员开放。</p>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-6">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold text-gray-900">
            <MessageSquareQuote className="h-6 w-6 text-brand-600" />
            用户反馈管理
          </h1>
          <p className="mt-1 text-sm text-gray-500">
            审阅、答复并处置用户提交的反馈与上下文
          </p>
        </div>
        {summary.data && (
          <div className="text-right text-meta text-neutral-500">
            <div>
              总计 <span className="font-semibold text-neutral-700">{total}</span> 条
            </div>
            <div>最后更新 {formatRelativeTime(new Date(summary.dataUpdatedAt).toISOString())}</div>
          </div>
        )}
      </div>

      <SummaryChips data={summary.data} loading={summary.isLoading} />

      <Card>
        <CardHeader className="flex-row flex-wrap items-center gap-3 space-y-0">
          <div className="flex items-center gap-2 text-sm font-medium text-gray-700">
            <Filter className="h-4 w-4" />
            筛选
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {STATUS_OPTIONS.map((opt) => (
              <Chip
                key={opt.value}
                active={statusFilter === opt.value}
                onClick={() => setStatusFilter(opt.value)}
                testid={`admin-feedback-status-${opt.value}`}
              >
                {opt.label}
              </Chip>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            {KIND_OPTIONS.map((opt) => (
              <Chip
                key={opt.value}
                active={kindFilter === opt.value}
                onClick={() => setKindFilter(opt.value)}
                testid={`admin-feedback-kind-${opt.value}`}
              >
                {opt.label}
              </Chip>
            ))}
          </div>
        </CardHeader>
        <CardContent>
          {list.isLoading ? (
            <div className="flex h-40 items-center justify-center text-sm text-gray-400">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              加载中…
            </div>
          ) : list.data && list.data.items.length > 0 ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                      <th className="px-3 py-2 font-medium">时间</th>
                      <th className="px-3 py-2 font-medium">用户</th>
                      <th className="px-3 py-2 font-medium">类型</th>
                      <th className="px-3 py-2 font-medium">对象</th>
                      <th className="px-3 py-2 font-medium">投票</th>
                      <th className="px-3 py-2 font-medium">状态</th>
                      <th className="px-3 py-2 font-medium">评论 / 答复</th>
                      <th className="px-3 py-2 text-right font-medium">操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {list.data.items.map((fb) => (
                      <FeedbackRow
                        key={fb.id}
                        fb={fb}
                        onReply={() => setReplying(fb)}
                        onClose={() => {
                          updateMutation.mutate({
                            id: fb.id,
                            patch: { status: "wontfix" },
                          });
                        }}
                        pending={
                          updateMutation.isPending &&
                          updateMutation.variables?.id === fb.id
                        }
                      />
                    ))}
                  </tbody>
                </table>
              </div>
              <Pagination
                page={page}
                totalPages={totalPages}
                onPrev={() => setPage((p) => Math.max(1, p - 1))}
                onNext={() => setPage((p) => Math.min(totalPages, p + 1))}
              />
            </>
          ) : (
            <EmptyState />
          )}
        </CardContent>
      </Card>

      <ReplyDialog
        feedback={replying}
        onClose={() => setReplying(null)}
        onSubmit={async (status, reply) => {
          if (!replying) return;
          await updateMutation.mutateAsync({
            id: replying.id,
            patch: { status, admin_reply: reply },
          });
          setReplying(null);
        }}
        pending={updateMutation.isPending}
      />
    </div>
  );
}

function Chip({
  active,
  onClick,
  children,
  testid,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  testid?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-testid={testid}
      className={cn(
        "rounded-full border px-3 py-1 text-xs font-medium transition-colors",
        active
          ? "border-brand-300 bg-brand-50 text-brand-700"
          : "border-neutral-200 bg-white text-neutral-600 hover:bg-neutral-50",
      )}
    >
      {children}
    </button>
  );
}

function SummaryChips({
  data,
  loading,
}: {
  data?: { total: number; by_status: Record<FeedbackStatus, number> };
  loading?: boolean;
}) {
  const items: { key: FeedbackStatus; label: string; tone: string }[] = [
    { key: "open", label: "待处理", tone: "text-brand-700" },
    { key: "triaged", label: "已分诊", tone: "text-amber-700" },
    { key: "resolved", label: "已解决", tone: "text-emerald-700" },
    { key: "wontfix", label: "不处理", tone: "text-neutral-500" },
  ];
  return (
    <div
      className="grid grid-cols-2 gap-3 sm:grid-cols-4"
      data-testid="admin-feedback-summary"
    >
      {items.map((it) => (
        <Card key={it.key}>
          <CardContent className="flex flex-col gap-1 py-4">
            <span className="text-meta text-neutral-500">{it.label}</span>
            <span
              className={cn(
                "text-2xl font-bold",
                loading ? "text-neutral-300" : it.tone,
              )}
            >
              {loading ? "—" : (data?.by_status[it.key] ?? 0)}
            </span>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function FeedbackRow({
  fb,
  onReply,
  onClose,
  pending,
}: {
  fb: UserFeedback;
  onReply: () => void;
  onClose: () => void;
  pending: boolean;
}) {
  const href = targetHref(fb.target_kind, fb.target_id);
  return (
    <tr
      className="border-b border-gray-100 last:border-0 hover:bg-gray-50/60"
      data-testid={`admin-feedback-row-${fb.id}`}
    >
      <td className="px-3 py-3 align-top text-meta text-gray-500">
        {formatDateTime(fb.created_at)}
      </td>
      <td
        className="px-3 py-3 align-top font-mono text-[11px] text-gray-500"
        title={fb.user_id}
      >
        {fb.user_id.slice(0, 8)}…
      </td>
      <td className="px-3 py-3 align-top">
        <Badge variant="outline">{KIND_LABEL[fb.target_kind]}</Badge>
      </td>
      <td className="px-3 py-3 align-top">
        <div className="flex items-start gap-1.5">
          <span className="line-clamp-2 text-sm text-gray-800">
            {fb.target_label}
          </span>
          {href && (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="mt-0.5 inline-flex shrink-0 text-neutral-400 hover:text-brand-600"
              title="打开源对象"
            >
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </td>
      <td className="px-3 py-3 align-top">
        <VoteBadge vote={fb.vote} />
      </td>
      <td className="px-3 py-3 align-top">
        <Badge variant={STATUS_VARIANT[fb.status]}>
          {STATUS_LABEL[fb.status]}
        </Badge>
      </td>
      <td className="px-3 py-3 align-top">
        {fb.comment ? (
          <p className="line-clamp-2 text-sm text-gray-700">{fb.comment}</p>
        ) : (
          <span className="text-meta text-neutral-400">无评论</span>
        )}
        {fb.admin_reply && (
          <p className="mt-1 line-clamp-2 rounded-md bg-brand-50 px-2 py-1 text-[12px] text-brand-700">
            ↳ {fb.admin_reply}
          </p>
        )}
      </td>
      <td className="px-3 py-3 align-top">
        <div className="flex flex-wrap items-center justify-end gap-1.5">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onReply}
            disabled={pending}
            data-testid={`admin-feedback-reply-${fb.id}`}
          >
            <Reply className="h-3.5 w-3.5" />
            答复
          </Button>
          {fb.status !== "wontfix" && (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              onClick={onClose}
              disabled={pending}
              data-testid={`admin-feedback-close-${fb.id}`}
            >
              关闭
            </Button>
          )}
        </div>
      </td>
    </tr>
  );
}

function Pagination({
  page,
  totalPages,
  onPrev,
  onNext,
}: {
  page: number;
  totalPages: number;
  onPrev: () => void;
  onNext: () => void;
}) {
  return (
    <div
      className="mt-3 flex items-center justify-between border-t border-gray-100 pt-3 text-meta text-neutral-500"
      data-testid="admin-feedback-pagination"
    >
      <span>
        第 <span className="font-semibold text-neutral-700">{page}</span> /{" "}
        {totalPages} 页
      </span>
      <div className="flex items-center gap-1.5">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onPrev}
          disabled={page <= 1}
        >
          <ChevronLeft className="h-3.5 w-3.5" />
          上一页
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={onNext}
          disabled={page >= totalPages}
        >
          下一页
          <ChevronRight className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex flex-col items-center gap-2 py-12 text-center">
      <Inbox className="h-6 w-6 text-neutral-300" />
      <p className="text-sm text-gray-500">暂无匹配反馈</p>
    </div>
  );
}

function ReplyDialog({
  feedback,
  onClose,
  onSubmit,
  pending,
}: {
  feedback: UserFeedback | null;
  onClose: () => void;
  onSubmit: (status: FeedbackStatus, reply: string) => Promise<void>;
  pending: boolean;
}) {
  const [reply, setReply] = React.useState("");
  const [status, setStatus] = React.useState<FeedbackStatus>("triaged");

  React.useEffect(() => {
    if (feedback) {
      setReply(feedback.admin_reply ?? "");
      setStatus(feedback.status === "open" ? "triaged" : feedback.status);
    }
  }, [feedback]);

  const open = !!feedback;

  return (
    <Dialog.Root open={open} onOpenChange={(v) => !v && onClose()}>
      <Dialog.Portal>
        <Dialog.Overlay
          className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in"
          data-testid="admin-feedback-reply-dialog"
        />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed left-1/2 top-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-xl"
        >
          <div className="flex items-center justify-between border-b border-neutral-100 px-6 py-4">
            <div>
              <Dialog.Title className="text-base font-semibold text-gray-900">
                答复反馈
              </Dialog.Title>
              {feedback && (
                <Dialog.Description className="mt-0.5 text-meta text-neutral-500">
                  {KIND_LABEL[feedback.target_kind]} · {feedback.target_label}
                </Dialog.Description>
              )}
            </div>
            <Dialog.Close
              className="rounded-md p-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600"
              aria-label="关闭"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>
          <div className="space-y-4 px-6 py-5">
            {feedback?.comment && (
              <div className="rounded-md border border-neutral-200 bg-neutral-50 px-3 py-2 text-sm text-neutral-700">
                {feedback.comment}
              </div>
            )}
            <div className="space-y-2">
              <label className="text-xs font-medium text-neutral-500">
                状态
              </label>
              <div className="flex flex-wrap gap-1.5">
                {STATUS_OPTIONS.filter((o) => o.value !== "all").map((opt) => (
                  <Chip
                    key={opt.value}
                    active={status === opt.value}
                    onClick={() => setStatus(opt.value as FeedbackStatus)}
                    testid={`admin-feedback-reply-status-${opt.value}`}
                  >
                    {opt.label}
                  </Chip>
                ))}
              </div>
            </div>
            <div className="space-y-2">
              <label className="text-xs font-medium text-neutral-500">
                答复
              </label>
              <textarea
                value={reply}
                onChange={(e) => setReply(e.target.value)}
                rows={4}
                placeholder="填写对用户的答复（最多 1000 字符）"
                data-testid="admin-feedback-reply-input"
                maxLength={1000}
                className="w-full resize-none rounded-md border border-neutral-200 bg-white px-3 py-2 text-sm text-neutral-900 placeholder:text-neutral-400 focus:border-brand-400 focus:outline-none focus:ring-2 focus:ring-brand-100"
              />
            </div>
          </div>
          <div className="flex items-center justify-end gap-2 border-t border-neutral-100 bg-neutral-50/60 px-6 py-3">
            <Button variant="ghost" onClick={onClose} disabled={pending}>
              取消
            </Button>
            <Button
              onClick={async () => {
                await onSubmit(status, reply);
              }}
              disabled={pending}
              data-testid="admin-feedback-reply-submit"
            >
              {pending ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Send className="h-3.5 w-3.5" />
              )}
              提交
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
