"use client";

import * as React from "react";
import { BookOpen, ExternalLink } from "lucide-react";
import type { Evidence } from "@/types/api";
import { Card, CardContent } from "@/components/ui/card";

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  return (
    <Card className="border-brand-100 bg-brand-50/40">
      <CardContent className="flex flex-col gap-2 p-4">
        <div className="flex items-center gap-2 text-brand-700">
          <BookOpen className="h-4 w-4" />
          <span className="text-sm font-semibold">{evidence.title}</span>
          {evidence.article && (
            <span className="rounded bg-brand-100 px-1.5 py-0.5 text-xs text-brand-700">
              {evidence.article}
            </span>
          )}
        </div>
        {evidence.source && (
          <span className="text-xs text-gray-500">来源：{evidence.source}</span>
        )}
        <p className="text-sm leading-relaxed text-gray-700">
          {evidence.content}
        </p>
        {evidence.url && (
          <a
            href={evidence.url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-brand-600 hover:underline"
          >
            <ExternalLink className="h-3 w-3" /> 查看原文
          </a>
        )}
      </CardContent>
    </Card>
  );
}
