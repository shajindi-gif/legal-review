"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import * as Dialog from "@radix-ui/react-dialog";
import { Sparkles, X } from "lucide-react";
import { track } from "@/lib/analytics";

/**
 * UpgradeDialog —— 额度耗尽升级引导（R1-2）。
 *
 * 触发场景：免费用户累计体验额度用尽（后端返回区分码 quota_exceeded）。
 * 埋点：打开上报 upgrade_dialog_view，点击升级上报 upgrade_click（pricing_view 由定价页负责）。
 */
export function UpgradeDialog({
  open,
  onOpenChange,
  source = "upload",
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** 触发来源（埋点归因用，如 upload / dashboard）。 */
  source?: string;
}) {
  const router = useRouter();
  const [viewTracked, setViewTracked] = React.useState(false);

  React.useEffect(() => {
    if (open && !viewTracked) {
      track("upgrade_dialog_view", { source });
      setViewTracked(true);
    }
    if (!open) setViewTracked(false);
  }, [open, viewTracked, source]);

  function goPricing() {
    track("upgrade_click", { source });
    onOpenChange(false);
    router.push("/pricing");
  }

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:animate-fade-in" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[min(480px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-xl"
          data-testid="upgrade-dialog"
        >
          <div className="flex items-center justify-between border-b border-neutral-100 px-6 py-4">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                <Sparkles className="h-4 w-4" />
              </div>
              <Dialog.Title className="text-section-title">
                免费体验额度已用尽
              </Dialog.Title>
            </div>
            <Dialog.Close
              className="rounded-md p-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
              aria-label="关闭"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <div className="space-y-4 px-6 py-5">
            <Dialog.Description className="text-body">
              体验版包含 2 次完整审查。升级专业版即可无限次审查，并解锁全量法规库与深度审查报告。
            </Dialog.Description>
            <div className="flex flex-col gap-2 sm:flex-row sm:justify-end">
              <button
                type="button"
                onClick={() => onOpenChange(false)}
                className="inline-flex items-center justify-center rounded-md border border-neutral-200 bg-white px-4 py-2 text-sm font-medium text-neutral-700 hover:bg-neutral-50"
                data-testid="upgrade-dialog-later"
              >
                稍后再说
              </button>
              <button
                type="button"
                onClick={goPricing}
                className="inline-flex items-center justify-center gap-1.5 rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
                data-testid="upgrade-dialog-cta"
              >
                查看升级方案
              </button>
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
