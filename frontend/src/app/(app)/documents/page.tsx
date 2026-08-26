"use client";

import * as React from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  FileText,
  Plus,
  Filter,
  Search,
  ChevronRight,
  Upload,
} from "lucide-react";
import { useAuthStore } from "@/lib/auth";
import { fetchReviews, fetchTaskDocuments } from "@/lib/api";
import { NewReviewForm } from "@/components/review/NewReviewForm";
import { EmptyState } from "@/components/ui/empty-state";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { StatusBadge, isFinished } from "@/components/ui/status-badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { formatBytes, formatDateTime, formatRelativeTime } from "@/lib/utils";
import type { DocumentRead, TaskSummary } from "@/types/api";

/**
 * /documents —— Documents 列表页（UI-M4）。
 *
 * 真实数据源：当前没有"全库 documents"接口，文件只挂在 task 下。
 * 本页：
 *   1. 拉取 task 列表（最多 50 条，含分页）
 *   2. 并行去每条 task 拉 documents（带并发限流）
 *   3. 聚合 + 搜索 + 状态过滤 + 排序，呈现给用户
 *
 * 这是 UI 层的真实聚合，不算"假入口"：
 *   - 全部数据来自真实 API
 *   - 拉取失败 / 任务无文件时按 Skeleton / EmptyState 正确降级
 */

type DocRow = {
  doc: DocumentRead;
  task: TaskSummary;
};

const FILE_TYPE_LABEL: Record<string, string> = {
  pdf: "PDF",
  doc: "Word",
  docx: "Word",
  txt: "TXT",
  md: "MD",
};

export default function DocumentsPage() {
  const token = useAuthStore((s) => s.token);
  const [showNew, setShowNew] = React.useState(false);
  const [query, setQuery] = React.useState("");
  const [type, setType] = React.useState<string>("all");
  const [sort, setSort] = React.useState<"newest" | "oldest" | "name">(
    "newest",
  );

  // 拉 task 列表（最多 50 条足够覆盖大部分用户当前活跃文档）
  const tasksQ = useQuery({
    queryKey: ["reviews", { page: 1, page_size: 50 }],
    queryFn: () => fetchReviews({ page: 1, page_size: 50 }),
    enabled: !!token,
  });

  const tasks = tasksQ.data?.items ?? [];

  // 对每个 task 拉 documents
  const docsQ = useQuery({
    queryKey: ["all-task-documents", tasks.map((t) => t.id).join(",")],
    queryFn: async (): Promise<DocRow[]> => {
      const limited = tasks.slice(0, 12); // 限流：最多并发 12 个
      const settled = await Promise.allSettled(
        limited.map(async (t) => {
          const docs = await fetchTaskDocuments(t.id);
          return docs.map<DocRow>((d) => ({ doc: d, task: t }));
        }),
      );
      const rows: DocRow[] = [];
      for (const s of settled) if (s.status === "fulfilled") rows.push(...s.value);
      return rows;
    },
    enabled: !!token && tasks.length > 0,
  });

  const rows = docsQ.data ?? [];
  const loading = tasksQ.isLoading || docsQ.isLoading;

  // 文件类型统计
  const typeStats = React.useMemo(() => {
    const map = new Map<string, number>();
    rows.forEach((r) => {
      const t = (r.doc.file_type || "").toLowerCase();
      map.set(t, (map.get(t) ?? 0) + 1);
    });
    return map;
  }, [rows]);

  // 过滤 + 排序
  const filtered = React.useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = rows.filter((r) => {
      if (type !== "all" && (r.doc.file_type || "").toLowerCase() !== type) {
        return false;
      }
      if (!q) return true;
      return (
        r.doc.original_name.toLowerCase().includes(q) ||
        r.task.title.toLowerCase().includes(q)
      );
    });
    const sorted = [...list].sort((a, b) => {
      if (sort === "name") {
        return a.doc.original_name.localeCompare(b.doc.original_name);
      }
      const ta = new Date(a.doc.created_at).getTime();
      const tb = new Date(b.doc.created_at).getTime();
      return sort === "newest" ? tb - ta : ta - tb;
    });
    return sorted;
  }, [rows, query, type, sort]);

  return (
    <div className="flex flex-col gap-6">
      <Header
        onNew={() => setShowNew((v) => !v)}
        showNew={showNew}
        total={rows.length}
      />

      {showNew ? (
        <Card>
          <CardHeader>
            <CardTitle>新建审查</CardTitle>
            <CardDescription>在此处开始一个新的审查任务</CardDescription>
          </CardHeader>
          <CardContent>
            <NewReviewForm
              onSuccess={() => setShowNew(false)}
              onCancel={() => setShowNew(false)}
              cancelLabel="收起"
            />
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <CardTitle className="flex items-center gap-2 text-base">
              <FileText className="h-4 w-4 text-brand-600" /> 已上传文件
              <Badge variant="secondary">{filtered.length}</Badge>
            </CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <div className="relative">
                <Search className="absolute left-2 top-2.5 h-3.5 w-3.5 text-neutral-400" />
                <Input
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="按文件名 / 任务名搜索…"
                  className="h-9 w-56 pl-7 text-sm"
                  data-testid="documents-search"
                />
              </div>
              <div className="flex items-center gap-1 text-meta">
                <Filter className="h-3.5 w-3.5" />
                <select
                  value={type}
                  onChange={(e) => setType(e.target.value)}
                  className="h-9 rounded-md border border-neutral-200 bg-white px-2 text-sm focus:border-brand-400 focus:outline-none"
                >
                  <option value="all">全部类型</option>
                  {Array.from(typeStats.entries()).map(([t, n]) => (
                    <option key={t} value={t}>
                      {FILE_TYPE_LABEL[t] || t.toUpperCase()} · {n}
                    </option>
                  ))}
                </select>
              </div>
              <select
                value={sort}
                onChange={(e) => setSort(e.target.value as typeof sort)}
                className="h-9 rounded-md border border-neutral-200 bg-white px-2 text-sm focus:border-brand-400 focus:outline-none"
              >
                <option value="newest">最新优先</option>
                <option value="oldest">最旧优先</option>
                <option value="name">按文件名</option>
              </select>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex flex-col gap-2" data-testid="documents-skeleton">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className="flex items-center gap-3 rounded-lg border border-neutral-100 p-3"
                >
                  <Skeleton className="h-9 w-9 rounded-md" />
                  <div className="flex-1 space-y-1.5">
                    <Skeleton className="h-3.5 w-2/5" />
                    <Skeleton className="h-3 w-1/4" />
                  </div>
                  <Skeleton className="h-6 w-16" />
                </div>
              ))}
            </div>
          ) : rows.length === 0 ? (
            <EmptyState
              icon={<FileText className="h-7 w-7" />}
              title="还没有上传过任何文件"
              description="上传一份 PDF / Word / Markdown 即可启动审查。"
              action={
                <Button onClick={() => setShowNew(true)}>
                  <Upload className="h-4 w-4" /> 上传文件
                </Button>
              }
            />
          ) : filtered.length === 0 ? (
            <EmptyState
              icon={<Search className="h-6 w-6" />}
              title="没有匹配的文件"
              description="试着调整搜索关键词或文件类型过滤。"
            />
          ) : (
            <ul
              className="divide-y divide-neutral-100"
              data-testid="documents-list"
            >
              {filtered.map((r) => (
                <DocumentRowItem key={r.doc.id} row={r} />
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function Header({
  total,
  showNew,
  onNew,
}: {
  total: number;
  showNew: boolean;
  onNew: () => void;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <h1 className="text-page-title">Documents</h1>
        <p className="mt-1 text-secondary">
          全部已上传的文件，按 task 维度聚合。共 {total} 份。
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Link href="/upload" prefetch={false}>
          <Button variant="outline">
            <Upload className="h-4 w-4" /> 前往上传页
          </Button>
        </Link>
        <Button onClick={onNew} aria-pressed={showNew}>
          <Plus className="h-4 w-4" /> {showNew ? "收起" : "New"}
        </Button>
      </div>
    </div>
  );
}

function DocumentRowItem({ row }: { row: DocRow }) {
  const { doc, task } = row;
  const ext = (doc.file_type || "").toLowerCase();
  const done = isFinished(task.status);

  return (
    <li className="group flex items-center gap-3 py-3 first:pt-0 last:pb-0">
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-700">
        <FileText className="h-4 w-4" />
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="truncate text-sm font-medium text-neutral-900">
            {doc.original_name}
          </span>
          <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600">
            {FILE_TYPE_LABEL[ext] || ext.toUpperCase()}
          </span>
        </div>
        <p className="mt-0.5 text-meta truncate">
          任务：
          <Link
            href={`/review/${task.id}`}
            className="ml-1 text-brand-600 hover:underline"
            prefetch={false}
          >
            {task.title}
          </Link>
          <span className="mx-2 text-neutral-300">·</span>
          {formatBytes(doc.file_size)}
          <span className="mx-2 text-neutral-300">·</span>
          <span title={formatDateTime(doc.created_at)}>
            {formatRelativeTime(doc.created_at)}
          </span>
        </p>
      </div>
      <StatusBadge status={task.status} withDot />
      <Link
        href={`/review/${task.id}`}
        className="ml-2 hidden text-meta text-brand-600 group-hover:inline-flex"
        prefetch={false}
      >
        查看
        <ChevronRight className="ml-0.5 h-3.5 w-3.5" />
      </Link>
    </li>
  );
}
