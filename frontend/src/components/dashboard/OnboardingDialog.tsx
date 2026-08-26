"use client";

import * as React from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { Sparkles, X } from "lucide-react";
import {
  preferenceOptions,
  useUserPreference,
  type UserPreference,
} from "@/lib/preferences";
import { cn } from "@/lib/utils";

/**
 * Onboarding：只问 1 个问题（Section 33 明确要求"不要做 8 页教程"）。
 * 选完即进入 Home，preference 用于驱动后续推荐任务与 Assistant persona。
 */
export function OnboardingDialog() {
  const { pref, setPref, hydrated } = useUserPreference();
  const [open, setOpen] = React.useState(false);

  React.useEffect(() => {
    if (!hydrated) return;
    if (!pref) setOpen(true);
  }, [hydrated, pref]);

  function pick(v: UserPreference) {
    setPref(v);
    setOpen(false);
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm data-[state=open]:animate-in data-[state=open]:fade-in" />
        <Dialog.Content
          className="fixed left-1/2 top-1/2 z-50 w-[min(560px,calc(100vw-32px))] -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border border-neutral-200 bg-white shadow-xl"
          data-testid="onboarding-dialog"
        >
          <div className="flex items-center justify-between border-b border-neutral-100 px-6 py-4">
            <div className="flex items-center gap-2">
              <div className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-50 text-brand-700">
                <Sparkles className="h-4 w-4" />
              </div>
              <Dialog.Title className="text-section-title">欢迎使用 LegalAI</Dialog.Title>
            </div>
            <Dialog.Close
              className="rounded-md p-1 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700"
              aria-label="跳过"
            >
              <X className="h-4 w-4" />
            </Dialog.Close>
          </div>

          <div className="space-y-4 px-6 py-5">
            <p className="text-body">
              你主要需要 LegalAI 做什么？选一个开始，后续随时可在「Account」中调整。
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {preferenceOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => pick(opt.value)}
                  className={cn(
                    "group flex flex-col items-start gap-1 rounded-lg border border-neutral-200 bg-white px-4 py-3 text-left transition-colors",
                    "hover:border-brand-300 hover:bg-brand-50/40",
                  )}
                  data-testid={`onboarding-option-${opt.value}`}
                >
                  <span className="text-card-title text-neutral-900 group-hover:text-brand-700">
                    {opt.label}
                  </span>
                  <span className="text-meta">{opt.hint}</span>
                </button>
              ))}
            </div>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
