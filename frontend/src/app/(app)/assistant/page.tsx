"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  Sparkles,
  Upload,
  ArrowRight,
  Compass,
  History as HistoryIcon,
  ShieldCheck,
  Lightbulb,
  BookOpen,
  CheckCircle2,
  Upload as UploadIcon,
  Home as HomeIcon,
  Clock,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton, SkeletonCard } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { useAuthStore } from "@/lib/auth";
import { fetchReviews } from "@/lib/api";
import {
  useAssistantStore,
  type AssistantAction,
  type Conversation,
} from "@/lib/assistant-store";
import { findMatchingConversation } from "@/lib/assistant-match";
import { formatRelativeTime, formatDateTime } from "@/lib/utils";
import { preferenceLabel, useUserPreference } from "@/lib/preferences";
import { ConversationList } from "@/components/assistant/ConversationList";

/**
 * /assistant ——  专业提问工作台（UI-M6）。
 *
 * UI-M6 范围：
 *   - 左侧改为多草稿会话列表（ConversationList）
 *   - 中间主区按当前 active conversation 加载草稿
 *   - 右侧仍是"后续行动"——从历史 task 拉最近 4 条
 *   - 顶部 URL ?q= 预填只影响"新会话"创建；不会污染已有会话
 *
 * 严禁：没有真正 chat 后端时不渲染"假"对话气泡（Section 2）。
 * 现在每条会话 = 一份问题草稿 + 它的真实后续动作轨迹。
 */
export default function AssistantPage() {
  const router = useRouter();
  const params = useSearchParams();
  const initialQ = params.get("q") ?? "";
  const token = useAuthStore((s) => s.token);
  const { pref } = useUserPreference();

  const hydrated = useAssistantStore((s) => s.hydrated);
  const conversations = useAssistantStore((s) => s.conversations);
  const activeId = useAssistantStore((s) => s.activeId);
  const create = useAssistantStore((s) => s.create);
  const setDraft = useAssistantStore((s) => s.setDraft);

  // URL ?q= 引导（UI-M6.6：与 Home 跨页联动）
  //  1. 优先"反查已有会话"——如果存在高匹配已有会话，跳到 ?c=<id>，不再开新草稿。
  //  2. 仅在"没有任何会话"时落地新建一份（这是 ?q= 的核心能力：保证冷启动也有地方可写）。
  //  3. source="home" 落到该会话的 action 轨迹里——"这次提问是从 Home 来的"。
  const seeded = React.useRef(false);
  React.useEffect(() => {
    if (!hydrated || seeded.current) return;
    seeded.current = true;
    if (!initialQ) return;
    if (conversations.length === 0) {
      // 冷启动：直接用 ?q= 新建一份会话
      const id = create({ draft: initialQ });
      useAssistantStore.getState().recordAction(
        id,
        "open_dashboard",
        { query: initialQ, via: "home" },
        "home",
      );
      router.replace(`/assistant?c=${id}`, { scroll: false });
      return;
    }
    // 已有会话：再走一次匹配，命中则改写 URL
    const match = findMatchingConversation(conversations, initialQ);
    if (match) {
      useAssistantStore.getState().setActive(match.conversation.id);
      useAssistantStore.getState().recordAction(
        match.conversation.id,
        "open_dashboard",
        { query: initialQ, matched: match.strength, via: "home" },
        "home",
      );
      router.replace(`/assistant?c=${match.conversation.id}`, { scroll: false });
    }
    // 不命中且已有会话：保留 ?q= 留在 URL，让用户在当前 active 会话里手动决定是否合用
    // （不主动把 q 灌进别人草稿，避免破坏）
  }, [hydrated, initialQ, conversations, create, router]);

  const activeConv = conversations.find((c) => c.id === activeId) ?? null;

  // 受控草稿：每个会话维护一份本地 draftState
  const [localDraft, setLocalDraft] = React.useState(activeConv?.draft ?? "");
  React.useEffect(() => {
    setLocalDraft(activeConv?.draft ?? "");
  }, [activeConv?.id, activeConv?.draft]);

  // 把 activeId / draft 变更同步回 store（debounce 一拍，避免每键写 localStorage）
  const lastWrittenRef = React.useRef<string>("");
  React.useEffect(() => {
    if (!activeConv) return;
    if (localDraft === lastWrittenRef.current) return;
    const t = setTimeout(() => {
      setDraft(activeConv.id, localDraft);
      lastWrittenRef.current = localDraft;
    }, 350);
    return () => clearTimeout(t);
  }, [activeConv, localDraft, setDraft]);

  const { data: tasks, isLoading: tasksLoading } = useQuery({
    queryKey: ["reviews", { page: 1, page_size: 4 }],
    queryFn: () => fetchReviews({ page: 1, page_size: 4 }),
    enabled: !!token,
  });
  const recent = tasks?.items ?? [];

  // 主操作：带入 /upload
  const onSubmitToUpload = React.useCallback(() => {
    if (!activeConv) return;
    const q = localDraft.trim();
    if (!q) return;
    useAssistantStore
      .getState()
      .recordAction(activeConv.id, "open_upload", { title: q.slice(0, 80) });
    router.push(`/upload?title=${encodeURIComponent(q.slice(0, 80))}`);
  }, [activeConv, localDraft, router]);

  // 主操作：带入 /dashboard
  const onSubmitToHome = React.useCallback(() => {
    if (!activeConv) return;
    const q = localDraft.trim();
    if (!q) return;
    useAssistantStore
      .getState()
      .recordAction(activeConv.id, "open_dashboard", { query: q.slice(0, 80) });
    router.push(`/dashboard?q=${encodeURIComponent(q)}`);
  }, [activeConv, localDraft, router]);

  return (
    <div className="flex h-full flex-col gap-6">
      <Header prefLabel={pref ? preferenceLabel[pref] : null} />

      <div className="grid flex-1 grid-cols-1 gap-4 lg:grid-cols-[280px_minmax(0,1fr)_300px]">
        <Card className="h-fit overflow-hidden">
          <CardContent className="p-3">
            <ConversationList />
          </CardContent>
        </Card>

        <CenterPane
          conv={activeConv}
          draft={localDraft}
          onChange={setLocalDraft}
          onSubmitToUpload={onSubmitToUpload}
          onSubmitToHome={onSubmitToHome}
        />

        <RightPane
          recent={recent}
          loading={tasksLoading}
          onPick={(q) => {
            if (activeConv) {
              setLocalDraft(q);
              setDraft(activeConv.id, q);
            }
          }}
        />
      </div>
    </div>
  );
}

function Header({ prefLabel }: { prefLabel: string | null }) {
  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center gap-2 text-meta">
        <Sparkles className="h-3.5 w-3.5 text-brand-600" />
        <span>Assistant</span>
        {prefLabel ? (
          <span className="ml-2 rounded-full border border-brand-200 bg-white px-2 py-0.5 text-[10px] font-medium text-brand-700">
            当前方向：{prefLabel}
          </span>
        ) : null}
      </div>
      <h1 className="text-page-title">专业提问工作台</h1>
      <p className="max-w-2xl text-secondary">
        左侧保存你的问题草稿，中间编辑当前会话，右侧挑一个动作把它带进审查流程。所有会话仅存于本机，跨刷新保留。
      </p>
    </div>
  );
}

function CenterPane({
  conv,
  draft,
  onChange,
  onSubmitToUpload,
  onSubmitToHome,
}: {
  conv: Conversation | null;
  draft: string;
  onChange: (v: string) => void;
  onSubmitToUpload: () => void;
  onSubmitToHome: () => void;
}) {
  if (!conv) {
    return (
      <Card className="flex h-full flex-col">
        <CardContent className="flex flex-1 flex-col items-center justify-center gap-3 text-center text-meta">
          <Lightbulb className="h-6 w-6 text-neutral-300" />
          <p>左侧还没有会话</p>
          <p className="max-w-sm text-xs text-neutral-400">
            点击"新建"开始一份问题草稿；之后你的所有编辑与跳转动作都会绑定到该会话。
          </p>
        </CardContent>
      </Card>
    );
  }
  return (
    <Card className="flex h-full flex-col">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            <Lightbulb className="h-4 w-4 text-brand-600" />
            <span className="truncate">{conv.title}</span>
          </CardTitle>
          <span className="text-[10px] text-neutral-400">
            创建于 {formatDateTime(new Date(conv.createdAt).toISOString())}
          </span>
        </div>
      </CardHeader>
      <CardContent className="flex flex-1 flex-col gap-4">
        <textarea
          value={draft}
          onChange={(e) => onChange(e.target.value)}
          placeholder={
            "尽量描述清楚场景，例如：\n请审查这份采购合同，重点关注违约金、知识产权与争议解决条款。\n（问题会作为任务标题带入 /upload）"
          }
          className="min-h-[180px] w-full resize-y rounded-xl border border-neutral-200 bg-white p-3 text-sm leading-6 shadow-sm outline-none placeholder:text-neutral-400 focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
          data-testid="assistant-draft"
        />
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-end">
          <Button
            type="button"
            variant="outline"
            onClick={onSubmitToHome}
            disabled={!draft.trim()}
          >
            <BookOpen className="h-4 w-4" /> 作为首页问题带入
          </Button>
          <Button
            type="button"
            onClick={onSubmitToUpload}
            disabled={!draft.trim()}
            data-testid="assistant-submit-upload"
          >
            <Upload className="h-4 w-4" /> 带入上传并启动审查
          </Button>
        </div>

        {/* 动作轨迹 —— 只展示"用户真实发起的跳转"，绝不显示假 AI 回复 */}
        <ActionTimeline conv={conv} />
      </CardContent>
    </Card>
  );
}

function ActionTimeline({ conv }: { conv: Conversation }) {
  if (conv.actions.length === 0) {
    return (
      <div className="mt-2 rounded-lg bg-neutral-50 p-3 text-meta">
        <p className="mb-1 font-medium text-neutral-700">动作轨迹</p>
        <p>
          还没有动作。当你在本会话点击「带入上传」或「作为首页问题带入」时，会在这里留下真实跳转记录。
        </p>
      </div>
    );
  }
  const items = [...conv.actions].reverse(); // 最新在前
  return (
    <div className="mt-2 rounded-lg border border-neutral-100 bg-neutral-50/60 p-3">
      <p className="mb-2 flex items-center gap-1 text-meta font-medium text-neutral-700">
        <Clock className="h-3 w-3" /> 动作轨迹 · {items.length}
      </p>
      <ul className="space-y-1.5">
        {items.map((a) => (
          <li
            key={a.id}
            className="flex items-start gap-2 text-xs text-neutral-600"
          >
            {a.kind === "open_upload" ? (
              <UploadIcon className="mt-0.5 h-3 w-3 shrink-0 text-brand-600" />
            ) : a.kind === "open_dashboard" ? (
              <HomeIcon className="mt-0.5 h-3 w-3 shrink-0 text-brand-600" />
            ) : (
              <CheckCircle2 className="mt-0.5 h-3 w-3 shrink-0 text-neutral-400" />
            )}
            <span className="min-w-0 flex-1">
              <span className="font-medium text-neutral-800">
                {a.kind === "open_upload"
                  ? "带入上传并启动审查"
                  : a.kind === "open_dashboard"
                    ? "作为首页问题带入"
                    : a.kind === "pick_recent"
                      ? "从历史任务选了一条"
                      : "已重命名"}
              </span>
              {a.payload ? (
                <span className="ml-1 text-neutral-500">
                  {summarizePayload(a)}
                </span>
              ) : null}
              <span className="ml-2 text-neutral-400">
                {formatRelativeTime(new Date(a.at).toISOString())}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function summarizePayload(a: AssistantAction): string {
  if (!a.payload) return "";
  if (a.kind === "open_upload" && typeof a.payload.title === "string") {
    return `→ ${a.payload.title}`;
  }
  if (a.kind === "open_dashboard" && typeof a.payload.query === "string") {
    const via = a.payload.via === "home" ? "（来自首页）" : "";
    const matched =
      typeof a.payload.matched === "string" ? ` · 命中${a.payload.matched}` : "";
    return `→ ${a.payload.query}${via}${matched}`;
  }
  return "";
}

function RightPane({
  recent,
  loading,
  onPick,
}: {
  recent: { id: string; title: string; submitted_at: string; status: string }[];
  loading: boolean;
  onPick: (q: string) => void;
}) {
  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <ShieldCheck className="h-4 w-4 text-brand-600" /> 后续行动
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm">
        <Action
          icon={<Compass className="h-4 w-4" />}
          title="从历史任务继续"
          desc="复用上一份任务的上下文"
        />
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-3/4" />
            <Skeleton className="h-4 w-2/3" />
            <Skeleton className="h-4 w-1/2" />
          </div>
        ) : recent.length === 0 ? (
          <p className="text-meta">还没有历史任务。</p>
        ) : (
          <ul className="divide-y divide-neutral-100">
            {recent.map((t) => (
              <li key={t.id}>
                <button
                  type="button"
                  onClick={() => onPick(t.title)}
                  className="flex w-full items-start gap-2 py-2 text-left transition-colors hover:bg-neutral-50"
                >
                  <HistoryIcon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-neutral-400" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-neutral-900">
                      {t.title}
                    </span>
                    <span className="block text-meta">
                      {formatRelativeTime(t.submitted_at)}
                    </span>
                  </span>
                  <ArrowRight className="mt-0.5 h-3.5 w-3.5 text-neutral-300" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <div className="border-t border-neutral-100 pt-3 text-meta">
          <p>需要更结构化的工作流？直接前往</p>
          <div className="mt-2 flex flex-wrap gap-2">
            <Link href="/upload">
              <Button variant="outline" size="sm">
                <Upload className="h-3.5 w-3.5" /> 上传
              </Button>
            </Link>
            <Link href="/dashboard">
              <Button variant="outline" size="sm">
                <Sparkles className="h-3.5 w-3.5" /> 首页
              </Button>
            </Link>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Action({
  icon,
  title,
  desc,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
}) {
  return (
    <div className="flex items-start gap-2">
      <span className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-700">
        {icon}
      </span>
      <div>
        <p className="text-card-title">{title}</p>
        <p className="text-meta">{desc}</p>
      </div>
    </div>
  );
}

// 防止 lint 在某些分支下报告 unused
export { SkeletonCard };
