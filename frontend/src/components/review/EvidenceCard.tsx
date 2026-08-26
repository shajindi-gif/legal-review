"use client";

import * as React from "react";
import { BookOpen } from "lucide-react";
import type { Evidence } from "@/types/api";
import { Card, CardContent } from "@/components/ui/card";

export function EvidenceCard({ evidence }: { evidence: Evidence }) {
  return (
    <Card className="border-brand-100 bg-brand-50/40">
      <CardContent className="flex flex-col gap-2 p-4">
        <div className="flex flex-wrap items-center gap-2 text-brand-700">
          <BookOpen className="h-4 w-4" />
          <span className="text-sm font-semibold">{evidence.law_name}</span>
          {evidence.article && (
            <span className="rounded bg-brand-100 px-1.5 py-0.5 text-xs text-brand-700">
              {evidence.article}
            </span>
          )}
        </div>
        {evidence.original_text && (
          <blockquote className="border-l-2 border-brand-200 pl-3 text-sm italic leading-relaxed text-gray-600">
            {evidence.original_text}
          </blockquote>
        )}
        {evidence.explanation && (
          <p className="text-sm leading-relaxed text-gray-700">
            {evidence.explanation}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
