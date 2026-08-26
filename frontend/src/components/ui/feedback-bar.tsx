"use client";

import * as React from "react";
import { ThumbsUp, ThumbsDown, Check, Loader2, X } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { cn } from "@/lib/utils";
import { submitUserFeedback } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import type { FeedbackTargetKind, FeedbackVote } from "@/types/api";

/**
 * 用户反馈条（UI-M11）。
 *
 * 行为：
 * - 单击 👍 → 直接以 vote=up 提交（无文本）
 * - 单击 👎 → 弹文本框，提交 vote=down + 可选 comment
 * - 选后写入 localStorage（key 含 targetId）保证刷新仍生效
 * - 提交成功：toast + query 失效（feedback-center 页可即时拉新）
 * - 提交失败：保留按钮可重试，不假装成功
 *
 * Props：
 * - targetKind: 反馈目标类型（report / review / risk / assistant）
 * - targetId:   目标 id 字符串（与 FeedbackBar.targetId 旧行为兼容）
 * - targetLabel:人类可读标签（落库冗余）
 * - context:    JSONB 上下文（节点名 / 风险id 等，便于溯源）
 */

const STORAGE_PREFIX = "lr_feedback_v2:";

type StoredVote = "up" | "down" | null;

interface StoredRecord {
  vote: StoredVote;
  comment: string | null;
  feedbackId: string | null;
}

function readStored(targetId: string): StoredRecord {
  if (typeof window === "undefined") return { vote: null, comment: null, feedbackId: null };
  const raw = window.localStorage.getItem(STORAGE_PREFIX + targetId);
  if (!raw) return { vote: null, comment: null, feedbackId: null };
  try {
    const parsed = JSON.parse(raw) as Partial<StoredRecord>;
    return {
      vote: parsed.vote === "up" || parsed.vote === "down" ? parsed.vote : null,
      comment: typeof parsed.comment === "string" ? parsed.comment : null,
      feedbackId: typeof parsed.feedbackId === "string" ? parsed.feedbackId : null,
    };
  } catch {
    return { vote: null, comment: null, feedbackId: null };
  }
}
function writeStored(targetId: string, rec: StoredRecord) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_PREFIX + targetId, JSON.stringify(rec));
}

export interface FeedbackBarProps {
  targetId: string;
  targetKind: FeedbackTargetKind;
  targetLabel: string;
  context?: Record<string, unknown>;
  className?: string;
  /** 评论字符上限，默认 500。 */
  maxCommentLength?: number;
}

export function FeedbackBar({
  targetId,
  targetKind,
  targetLabel,
  context,
  className,
  maxCommentLength = 500,
}: FeedbackBarProps) {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();

  const [hydrated, setHydrated] = React.useState(false);
  const [stored, setStored] = React.useState<StoredRecord>({
    vote: null,
    comment: null,
    feedbackId: null,
  });
  const [showComment, setShowComment] = React.useState(false);
  const [draft, setDraft] = React.useState("");

  React.useEffect(() => {
    setStored(readStored(targetId));
    setShowComment(false);
    setDraft("");
    setHydrated(true);
  }, [targetId]);

  const mutation = useMutation({
    mutationFn: async (input: { vote: FeedbackVote; comment: string | null }) => {
      return submitUserFeedback({
        target_kind: targetKind,
        target_id: targetId,
        target_label: targetLabel,
        vote: input.vote,
        comment: input.comment,
        context: context ?? {},
      });
    },
    onSuccess: (data, input) => {
      const next: StoredRecord = {
        vote: input.vote === "up" || input.vote === "down" ? input.vote : null,
        comment: input.comment,
        feedbackId: data.id,
      };
      setStored(next);
      writeStored(targetId, next);
      qc.invalidateQueries({ queryKey: ["my-feedback"] });
    },
  });

  const isAuthed = !!token && !!user;
  const vote = stored.vote;
  const disabled = !hydrated || !isAuthed || mutation.isPending;

  function pick(v: "up" | "down") {
    if (disabled) return;
    if (v === "up") {
      // 再次点击 = 撤销（M11 暂未实现后端 DELETE，先只在前端清除）
      if (vote === "up") {
        const cleared: StoredRecord = { vote: null, comment: null, feedbackId: null };
        setStored(cleared);
        writeStored(targetId, cleared);
        setShowComment(false);
        return;
      }
      // 直接提交
      mutation.mutate({ vote: "up", comment: null });
      setShowComment(false);
      return;
    }
    // v === "down"
    if (vote === "down") {
      // 撤销
      const cleared: StoredRecord = { vote: null, comment: null, feedbackId: null };
      setStored(cleared);
      writeStored(targetId, cleared);
      setShowComment(false);
      setDraft("");
      return;
    }
    // 首次点 👎：弹文本框
    setShowComment(true);
  }

  function submitDown() {
    if (disabled) return;
    const text = draft.trim();
    mutation.mutate({
      vote: "down",
      comment: text.length > 0 ? text : null,
    });
  }

  return (
    <div
      className={cn("flex flex-col gap-2 text-meta", className)}
      data-testid="feedback-bar"
      data-target={targetId}
      data-vote={vote ?? ""}
    >
      <div className="flex flex-wrap items-center gap-2">
        <span>这条结果对你有帮助吗？</span>
        <button
          type="button"
          onClick={() => pick("up")}
          aria-label="有用"
          aria-pressed={vote === "up"}
          disabled={disabled}
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-md border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
            vote === "up"
              ? "border-success-500 bg-success-50 text-success-700"
              : "border-neutral-200 bg-white text-neutral-500 hover:border-success-300 hover:text-success-600",
          )}
        >
          {mutation.isPending && mutation.variables?.vote === "up" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ThumbsUp className="h-3.5 w-3.5" />
          )}
        </button>
        <button
          type="button"
          onClick={() => pick("down")}
          aria-label="没用"
          aria-pressed={vote === "down"}
          disabled={disabled}
          className={cn(
            "inline-flex h-7 w-7 items-center justify-center rounded-md border transition-colors disabled:cursor-not-allowed disabled:opacity-50",
            vote === "down"
              ? "border-danger-500 bg-danger-50 text-danger-700"
              : "border-neutral-200 bg-white text-neutral-500 hover:border-danger-300 hover:text-danger-600",
          )}
        >
          {mutation.isPending && mutation.variables?.vote === "down" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <ThumbsDown className="h-3.5 w-3.5" />
          )}
        </button>
        {vote ? (
          <span
            className="ml-1 inline-flex items-center gap-1 text-success-600"
            aria-live="polite"
          >
            <Check className="h-3 w-3" />
            已记录
          </span>
        ) : null}
        {!isAuthed ? (
          <span className="text-neutral-400" aria-live="polite">
            · 登录后可记录反馈
          </span>
        ) : null}
        {mutation.isError ? (
          <span className="text-danger-600" aria-live="polite">
            提交失败，可重试
          </span>
        ) : null}
      </div>

      {showComment && vote === null ? (
        <div
          className="flex flex-col gap-2 rounded-lg border border-danger-200 bg-danger-50/40 p-3"
          data-testid="feedback-comment-form"
        >
          <div className="flex items-center justify-between">
            <label
              htmlFor={`fb-comment-${targetId}`}
              className="text-sm font-medium text-danger-800"
            >
              告诉我们哪里不准（可选）
            </label>
            <button
              type="button"
              onClick={() => {
                setShowComment(false);
                setDraft("");
              }}
              className="text-neutral-400 hover:text-neutral-600"
              aria-label="取消"
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <textarea
            id={`fb-comment-${targetId}`}
            value={draft}
            onChange={(e) => setDraft(e.target.value.slice(0, maxCommentLength))}
            placeholder="例如：风险分级不准确 / 漏掉了某条法规引用 / 总结与原文矛盾…"
            className="min-h-[72px] w-full rounded-md border border-neutral-300 bg-white p-2 text-sm placeholder:text-neutral-400 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
            maxLength={maxCommentLength}
            disabled={mutation.isPending}
          />
          <div className="flex items-center justify-between">
            <span className="text-xs text-neutral-500">
              {draft.length} / {maxCommentLength}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => {
                  setShowComment(false);
                  setDraft("");
                }}
                className="inline-flex h-8 items-center rounded-md border border-neutral-200 bg-white px-3 text-sm text-neutral-600 hover:bg-neutral-50"
                disabled={mutation.isPending}
              >
                取消
              </button>
              <button
                type="button"
                onClick={submitDown}
                className="inline-flex h-8 items-center rounded-md bg-danger-600 px-3 text-sm font-medium text-white hover:bg-danger-700 disabled:opacity-50"
                disabled={mutation.isPending}
                data-testid="feedback-submit-down"
              >
                {mutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                ) : (
                  "提交"
                )}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {vote === "down" && stored.comment ? (
        <p
          className="rounded-md bg-danger-50 px-3 py-2 text-meta text-danger-700"
          data-testid="feedback-comment-shown"
        >
          你的反馈：{stored.comment}
        </p>
      ) : null}
    </div>
  );
}
