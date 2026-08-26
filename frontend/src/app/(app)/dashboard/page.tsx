"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import {
  Upload,
  Sparkles,
  FileSearch,
  ShieldCheck,
  GitCompare,
  BarChart3,
  Building2,
  ArrowRight,
  Clock,
  ChevronRight,
} from "lucide-react";
import { fetchQuota, fetchReviews } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { preferenceLabel, useUserPreference } from "@/lib/preferences";
import { useAssistantStore } from "@/lib/assistant-store";
import { findMatchingConversation } from "@/lib/assistant-match";
import { UsageCard } from "@/components/dashboard/UsageCard";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton, SkeletonCard } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatRelativeTime } from "@/lib/utils";

const planLabel = {
  free: "体验版",
  pro: "专业版",
  enterprise: "企业版",
} as const;

type SuggestedTask = {
  key: string;
  label: string;
  hint: string;
  icon: React.ComponentType<{ className?: string }>;
  href: string;
  query?: string;
};

const suggestedTasks: SuggestedTask[] = [
  {
    key: "review",
    label: "审查一份文件",
    hint: "上传文件，自动跑 11 节点审查流水线",
    icon: ShieldCheck,
    href: "/upload",
  },
  {
    key: "regulation",
    label: "查询法规依据",
    hint: "在 Assistant 中提问，按条款定位",
    icon: FileSearch,
    href: "/assistant",
    query: "请帮我定位关于[请补充主题]的法律依据",
  },
  {
    key: "risk",
    label: "分析法律风险",
    hint: "上传材料后，AI 标注高 / 中 / 低风险",
    icon: Sparkles,
    href: "/assistant",
    query: "请帮我分析这份材料中可能存在的法律风险",
  },
  {
    key: "compare",
    label: "比较两个文件",
    hint: "上传两份材料，自动对比差异",
    icon: GitCompare,
    href: "/upload",
  },
  {
    key: "report",
    label: "生成审查报告",
    hint: "已有任务，可直接查看结构化报告",
    icon: BarChart3,
    href: "/report",
  },
  {
    key: "compliance",
    label: "企业合规检查",
    hint: "对照法规逐项核验内部制度",
    icon: Building2,
    href: "/assistant",
    query: "请帮我做一次企业合规体检，重点关注[请补充领域]",
  },
];

export default function DashboardPage() {
  const router = useRouter();
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  const { data: quota, isLoading: quotaLoading } = useQuery({
    queryKey: ["quota"],
    queryFn: fetchQuota,
    enabled: !!token,
  });
  const { data: tasksResp, isLoading: tasksLoading } = useQuery({
    queryKey: ["reviews", { page: 1, page_size: 5 }],
    queryFn: () => fetchReviews({ page: 1, page_size: 5 }),
    enabled: !!token,
  });

  const recent = tasksResp?.items ?? [];
  const total = tasksResp?.total ?? 0;
  const planTier = user?.plan_tier ?? quota?.tier ?? "free";
  const { pref } = useUserPreference();

  const greeting = greetingFor(user?.real_name || user?.email);
  const recommended = React.useMemo(() => {
    if (!pref) return suggestedTasks;
    // 高亮用户首选项
    return [
      ...suggestedTasks.filter((t) => t.key === pref),
      ...suggestedTasks.filter((t) => t.key !== pref),
    ];
  }, [pref]);

  // Home Hero 提问 → 反查"最近匹配会话"（UI-M6.6）
  // - 命中：跳到该会话 ?c=<id>，并写入一条 source="home" 的 recordAction（不重复创建）。
  // - 不命中：跳到 /assistant?q=<query>，由 Assistant 落地时新建并接管。
  const handleAsk = React.useCallback(
    (q: string) => {
      const query = q.trim();
      if (!query) return;
      const state = useAssistantStore.getState();
      if (!state.hydrated) {
        // store 还没就绪（首屏 hydration 未跑完）—— 退化为旧逻辑
        router.push(`/assistant?q=${encodeURIComponent(query)}`);
        return;
      }
      const match = findMatchingConversation(state.conversations, query);
      if (match) {
        state.setActive(match.conversation.id);
        state.recordAction(
          match.conversation.id,
          "open_dashboard",
          { query, matched: match.strength, via: "home" },
          "home",
        );
        router.push(`/assistant?c=${match.conversation.id}`);
        return;
      }
      router.push(`/assistant?q=${encodeURIComponent(query)}`);
    },
    [router],
  );

  return (
    <div className="flex flex-col gap-8">
      {/* 顶部 Hero：主操作区 */}
      <HeroInput
        greeting={greeting}
        onAsk={handleAsk}
        onUpload={() => router.push("/upload")}
        prefLabel={pref ? preferenceLabel[pref] : null}
      />

      {/* 关键指标条 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <UsageCard quota={quota} loading={quotaLoading} />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Clock className="h-4 w-4 text-brand-600" /> 累计审查
            </CardTitle>
          </CardHeader>
          <CardContent>
            {tasksLoading ? (
              <Skeleton className="h-8 w-20" />
            ) : (
              <span className="text-2xl font-semibold text-brand-700">{total}</span>
            )}
            <span className="text-sm text-gray-400"> 次</span>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-base">当前套餐</CardTitle>
          </CardHeader>
          <CardContent>
            <span className="text-2xl font-semibold text-brand-700">
              {planLabel[planTier]}
            </span>
            <p className="mt-1 text-xs text-gray-400">
              {planTier === "free" ? "可升级至专业版获取更多额度" : "感谢您的订阅"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* 推荐任务 */}
      <section>
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-section-title">推荐任务</h2>
          <p className="text-meta">点击直接开始</p>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {recommended.map((t, i) => {
            const Icon = t.icon;
            return (
              <button
                key={t.key}
                type="button"
                onClick={() => router.push(t.href)}
                className="group flex items-start gap-3 rounded-xl border border-neutral-200 bg-white p-4 text-left transition-colors hover:border-brand-300 hover:bg-brand-50/30"
                data-testid={`suggested-${t.key}`}
              >
                <div
                  className={
                    "flex h-9 w-9 shrink-0 items-center justify-center rounded-lg " +
                    (i === 0 && pref
                      ? "bg-brand-600 text-white"
                      : "bg-brand-50 text-brand-700")
                  }
                >
                  <Icon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-card-title truncate">{t.label}</p>
                  <p className="mt-0.5 line-clamp-2 text-meta">{t.hint}</p>
                </div>
                <ChevronRight className="h-4 w-4 shrink-0 text-neutral-300 transition-colors group-hover:text-brand-600" />
              </button>
            );
          })}
        </div>
      </section>

      {/* Recent Work */}
      <section>
        <div className="mb-3 flex items-end justify-between">
          <h2 className="text-section-title">最近任务</h2>
          <div className="flex items-center gap-3 text-sm">
            <Link
              href="/documents"
              prefetch={false}
              className="inline-flex items-center gap-1 text-neutral-600 hover:text-brand-600 hover:underline"
            >
              全部文件
            </Link>
            <span className="text-neutral-300">·</span>
            <Link
              href="/upload"
              prefetch={false}
              className="inline-flex items-center gap-1 text-brand-600 hover:underline"
            >
              新建 <ArrowRight className="h-3.5 w-3.5" />
            </Link>
          </div>
        </div>
        {tasksLoading ? (
          <SkeletonCard />
        ) : recent.length === 0 ? (
          <EmptyState
            title="还没有审查记录"
            description="上传合同、法规或企业材料，LegalAI 可以帮你分析、检索并生成结构化报告。"
            action={
              <Link href="/upload">
                <Button>
                  <Upload className="h-4 w-4" /> 上传第一个文件
                </Button>
              </Link>
            }
          />
        ) : (
          <Card>
            <CardContent className="divide-y divide-neutral-100 p-0">
              {recent.map((t) => (
                <Link
                  key={t.id}
                  href={`/review/${t.id}`}
                  className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-neutral-50"
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-neutral-900">
                      {t.title}
                    </p>
                    <p className="mt-0.5 text-meta">
                      审查 · {formatRelativeTime(t.submitted_at)}
                    </p>
                  </div>
                  <StatusBadge status={t.status} withSpinner />
                </Link>
              ))}
            </CardContent>
          </Card>
        )}
      </section>
    </div>
  );
}

function HeroInput({
  greeting,
  onAsk,
  onUpload,
  prefLabel,
}: {
  greeting: string;
  onAsk: (q: string) => void;
  onUpload: () => void;
  prefLabel: string | null;
}) {
  const [q, setQ] = React.useState("");
  return (
    <section className="rounded-2xl border border-neutral-200 bg-gradient-to-br from-white to-brand-50/40 p-6 sm:p-8">
      <div className="mb-1 flex items-center gap-2 text-meta">
        <Sparkles className="h-3.5 w-3.5 text-brand-600" />
        <span>{greeting}</span>
        {prefLabel ? (
          <span className="ml-2 rounded-full border border-brand-200 bg-white px-2 py-0.5 text-[10px] font-medium text-brand-700">
            主要方向：{prefLabel}
          </span>
        ) : null}
      </div>
      <h1 className="text-page-title">今天让 LegalAI 做什么？</h1>
      <p className="mt-1 max-w-2xl text-secondary">
        提问、上传文件或选择一项推荐任务。LegalAI 会检索法规、阅读文件、给出可追溯的结论与证据。
      </p>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (q.trim()) onAsk(q.trim());
        }}
        className="mt-5 flex flex-col gap-2 sm:flex-row sm:items-center"
      >
        <div className="flex h-12 flex-1 items-center gap-2 rounded-xl border border-neutral-200 bg-white px-3 shadow-sm focus-within:border-brand-400 focus-within:ring-2 focus-within:ring-brand-100">
          <Sparkles className="h-4 w-4 text-brand-600" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="例：请审查这份合同是否存在条款风险"
            className="h-full w-full bg-transparent text-sm outline-none placeholder:text-neutral-400"
            aria-label="向 LegalAI 提问"
            data-testid="home-ask-input"
          />
        </div>
        <Button type="submit" disabled={!q.trim()}>
          Ask LegalAI
        </Button>
        <Button type="button" variant="outline" onClick={onUpload}>
          <Upload className="h-4 w-4" /> 上传文件
        </Button>
      </form>
    </section>
  );
}

function greetingFor(name?: string) {
  const h = new Date().getHours();
  const tod = h < 6 ? "夜深了" : h < 12 ? "早上好" : h < 18 ? "下午好" : "晚上好";
  return name ? `${tod}，${name}` : tod;
}

// 避免 unused 警告
export { greetingFor };
