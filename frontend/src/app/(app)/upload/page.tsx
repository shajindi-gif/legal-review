"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { UploadCloud, FileText, X } from "lucide-react";
import { createReview } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { cn, formatBytes } from "@/lib/utils";

const ACCEPTED = ".pdf,.doc,.docx,.txt,.md";

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = React.useState<File | null>(null);
  const [title, setTitle] = React.useState("");
  const [priority, setPriority] = React.useState<"low" | "normal" | "high" | "urgent">(
    "normal",
  );
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [dragging, setDragging] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  function pickFile(f: File | null) {
    if (!f) return;
    setFile(f);
    if (!title) setTitle(f.name.replace(/\.[^.]+$/, ""));
    setError(null);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer.files?.[0];
    if (f) pickFile(f);
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!file) {
      setError("请先选择待审查文件");
      return;
    }
    if (!title.trim()) {
      setError("请填写文件标题");
      return;
    }
    setLoading(true);
    try {
      const res = await createReview(file, { title: title.trim(), priority });
      router.push(`/review/${res.task_id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "提交失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">上传待审查文件</h1>
        <p className="mt-1 text-sm text-gray-500">
          支持 PDF / Word / TXT / Markdown，系统将自动解析并启动 11 节点审查流水线。
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>新建审查</CardTitle>
          <CardDescription>填写标题并上传文件后提交</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="flex flex-col gap-5">
            <div className="flex flex-col gap-2">
              <Label htmlFor="title">文件标题</Label>
              <Input
                id="title"
                placeholder="如：XX县关于XX事项的管理办法"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
            </div>

            <div className="flex flex-col gap-2">
              <Label htmlFor="priority">优先级</Label>
              <select
                id="priority"
                value={priority}
                onChange={(e) =>
                  setPriority(e.target.value as "low" | "normal" | "high" | "urgent")
                }
                className="rounded-md border border-gray-200 bg-white px-3 py-2 text-sm focus:border-brand-400 focus:outline-none"
              >
                <option value="low">低</option>
                <option value="normal">普通</option>
                <option value="high">高</option>
                <option value="urgent">紧急</option>
              </select>
            </div>

            <div className="flex flex-col gap-2">
              <Label>待审查文件</Label>
              <input
                ref={inputRef}
                type="file"
                accept={ACCEPTED}
                className="hidden"
                onChange={(e) => pickFile(e.target.files?.[0] ?? null)}
              />
              {!file ? (
                <button
                  type="button"
                  onClick={() => inputRef.current?.click()}
                  onDragOver={(e) => {
                    e.preventDefault();
                    setDragging(true);
                  }}
                  onDragLeave={() => setDragging(false)}
                  onDrop={onDrop}
                  className={cn(
                    "flex h-40 flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed text-sm transition-colors",
                    dragging
                      ? "border-brand-400 bg-brand-50 text-brand-700"
                      : "border-gray-300 text-gray-500 hover:border-brand-300 hover:bg-brand-50/40",
                  )}
                >
                  <UploadCloud className="h-8 w-8 text-brand-500" />
                  <span>点击或拖拽文件到此处上传</span>
                  <span className="text-xs text-gray-400">支持 {ACCEPTED}</span>
                </button>
              ) : (
                <div className="flex items-center justify-between rounded-xl border border-gray-200 bg-gray-50 p-3">
                  <div className="flex items-center gap-3">
                    <FileText className="h-6 w-6 text-brand-600" />
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-gray-800">
                        {file.name}
                      </span>
                      <span className="text-xs text-gray-400">
                        {formatBytes(file.size)}
                      </span>
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => setFile(null)}
                    className="rounded p-1 text-gray-400 hover:bg-gray-200 hover:text-gray-600"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              )}
            </div>

            {error && (
              <p className="text-sm text-red-600" role="alert">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-3">
              <Button
                type="button"
                variant="outline"
                onClick={() => router.back()}
              >
                取消
              </Button>
              <Button type="submit" disabled={loading || !file}>
                {loading ? "提交中…" : "提交并开始审查"}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
