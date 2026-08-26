"use client";

import * as React from "react";
import { useSearchParams } from "next/navigation";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { NewReviewForm } from "@/components/review/NewReviewForm";

/**
 * /upload —— 新建审查。
 * UI-M4 之后，Upload 不再是 page 内的表单，而是 NewReviewForm 的容器。
 * 真实"开始任务"的入口在 Home / SideNav / TopBar / ⌘N 多处，统一引用同一组件。
 */
export default function UploadPage() {
  const searchParams = useSearchParams();
  const presetTitle = searchParams.get("title") ?? "";

  return (
    <div className="flex max-w-3xl flex-col gap-6">
      <div>
        <h1 className="text-page-title">上传待审查文件</h1>
        <p className="mt-1 text-secondary">
          支持 PDF / Word / TXT / Markdown，系统将自动解析并启动 11 节点审查流水线。
        </p>
      </div>
      <Card>
        <CardHeader>
          <CardTitle>新建审查</CardTitle>
          <CardDescription>填写标题并上传文件后提交</CardDescription>
        </CardHeader>
        <CardContent>
          <NewReviewForm presetTitle={presetTitle} />
        </CardContent>
      </Card>
    </div>
  );
}
