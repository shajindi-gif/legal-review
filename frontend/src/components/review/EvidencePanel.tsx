"use client";

import * as React from "react";
import { X, BookOpen, ChevronRight } from "lucide-react";
import type { Evidence } from "@/types/api";
import { Citation } from "@/components/review/Citation";
import { TrustBadge } from "@/components/ui/trust-badge";
import { EmptyState } from "@/components/ui/empty-state";
import { Button } from "@/components/ui/button";

/**
 * EvidencePanel —— 右侧 Context Panel（§C 缺失项）。
 *
 * 形态：固定在右侧 320px 宽的桌面抽屉 + 移动端 sheet。
 * 数据：法规 / 条款 / 上传文件 / 报告引用。
 * 交互：列表 + 详情，单击聚焦时高亮。
 *
 * UI-M3 范围内：
 * - 先支持"证据"类型（已经存在的 Evidence[]）
 * - 预留 "Documents / 报告引用" 分组槽位
 */

export type EvidenceGroup = {
  key: string;
  label: string;
  items: Evidence[];
};

export function EvidencePanel({
  open,
  onClose,
  groups,
  focusedId,
  onFocus,
}: {
  open: boolean;
  onClose: () => void;
  groups: EvidenceGroup[];
  focusedId?: string | null;
  onFocus?: (e: Evidence) => void;
}) {
  // Esc 关闭
  React.useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const totalCount = groups.reduce((acc, g) => acc + g.items.length, 0);
  const isEmpty = totalCount === 0;

  return (
    <>
      {/* 桌面侧栏 */}
      <aside
        aria-label="证据与上下文"
        data-state={open ? "open" : "closed"}
        className={
          "hidden h-full shrink-0 border-l border-neutral-200 bg-white transition-[width] duration-200 lg:block " +
          (open ? "w-[320px]" : "w-0 overflow-hidden")
        }
        data-testid="evidence-panel"
      >
        <PanelBody
          groups={groups}
          focusedId={focusedId}
          onFocus={onFocus}
          isEmpty={isEmpty}
          onClose={onClose}
        />
      </aside>

      {/* 移动 sheet */}
      <div
        aria-hidden={!open}
        className={
          "fixed inset-0 z-40 lg:hidden " +
          (open ? "pointer-events-auto" : "pointer-events-none")
        }
      >
        <div
          onClick={onClose}
          className={
            "absolute inset-0 bg-black/40 transition-opacity " +
            (open ? "opacity-100" : "opacity-0")
          }
        />
        <div
          className={
            "absolute inset-y-0 right-0 flex w-[88vw] max-w-sm flex-col border-l border-neutral-200 bg-white shadow-xl transition-transform " +
            (open ? "translate-x-0" : "translate-x-full")
          }
        >
          <PanelBody
            groups={groups}
            focusedId={focusedId}
            onFocus={onFocus}
            isEmpty={isEmpty}
            onClose={onClose}
          />
        </div>
      </div>
    </>
  );
}

function PanelBody({
  groups,
  focusedId,
  onFocus,
  isEmpty,
  onClose,
}: {
  groups: EvidenceGroup[];
  focusedId?: string | null;
  onFocus?: (e: Evidence) => void;
  isEmpty: boolean;
  onClose: () => void;
}) {
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-neutral-100 px-4 py-3">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-brand-600" />
          <h3 className="text-sm font-semibold text-neutral-900">证据与上下文</h3>
          <span className="rounded-full bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600">
            {groups.reduce((acc, g) => acc + g.items.length, 0)}
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={onClose}
          aria-label="关闭证据面板"
        >
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="flex-1 overflow-y-auto p-3">
        {isEmpty ? (
          <EmptyState
            icon={<BookOpen className="h-6 w-6" />}
            title="尚无证据"
            description="审查进行中或本任务无引用时，证据会出现在这里。"
          />
        ) : (
          <div className="flex flex-col gap-4">
            {groups.map((g) =>
              g.items.length === 0 ? null : (
                <section key={g.key}>
                  <p className="mb-2 px-1 text-[11px] font-medium uppercase tracking-wider text-neutral-400">
                    {g.label}
                  </p>
                  <div className="flex flex-col gap-2">
                    {g.items.map((ev, i) => {
                      const id = `${g.key}#${i}`;
                      return (
                        <Citation
                          key={id}
                          evidence={ev}
                          index={i + 1}
                          focused={focusedId === id}
                          onFocus={(e) => onFocus?.(e)}
                        />
                      );
                    })}
                  </div>
                </section>
              ),
            )}
          </div>
        )}
      </div>
      <div className="border-t border-neutral-100 px-4 py-2 text-meta">
        <div className="flex items-center justify-between">
          <span>所有引用均来自审查证据</span>
          <TrustBadge kind="citation" />
        </div>
      </div>
    </div>
  );
}

// 默认证据分组构造器：UI-M3 阶段只有"法规依据"组
export function buildDefaultEvidenceGroups(
  evidences: Evidence[],
): EvidenceGroup[] {
  return [
    {
      key: "regulation",
      label: "法规依据",
      items: evidences ?? [],
    },
  ];
}

// 占位：未来 Chat / Documents 落地后用
export { ChevronRight };
