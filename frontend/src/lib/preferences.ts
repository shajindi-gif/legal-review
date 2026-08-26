import { useCallback, useEffect, useState } from "react";

/**
 * 用户首选项（Onboarding 用）。
 *
 * - 仅前端持久化（localStorage），用于驱动 Home 推荐的"最常做任务"卡片
 *   高亮与 Assistant 默认 persona。
 * - 服务端不感知此字段，避免引入后端 schema 变更。
 */
export type UserPreference =
  | "regulation"
  | "review"
  | "contract"
  | "compliance"
  | "research";

const PREF_KEY = "lr_user_pref";

export const preferenceLabel: Record<UserPreference, string> = {
  regulation: "法规查询",
  review: "文件审查",
  contract: "合同分析",
  compliance: "企业合规",
  research: "法律研究",
};

export const preferenceOptions: { value: UserPreference; label: string; hint: string }[] = [
  { value: "regulation", label: "法规查询", hint: "快速定位法律依据、条款" },
  { value: "review", label: "文件审查", hint: "自动审查规范性文件合法性" },
  { value: "contract", label: "合同分析", hint: "合同条款风险与漏洞分析" },
  { value: "compliance", label: "企业合规", hint: "对照法规检查企业制度" },
  { value: "research", label: "法律研究", hint: "专题研究、案例梳理" },
];

function readPref(): UserPreference | null {
  if (typeof window === "undefined") return null;
  const v = window.localStorage.getItem(PREF_KEY);
  if (!v) return null;
  if (Object.prototype.hasOwnProperty.call(preferenceLabel, v)) {
    return v as UserPreference;
  }
  return null;
}

export function useUserPreference() {
  const [pref, setPrefState] = useState<UserPreference | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setPrefState(readPref());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    function onStorage(e: StorageEvent) {
      if (e.key !== PREF_KEY) return;
      setPrefState(readPref());
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setPref = useCallback((value: UserPreference | null) => {
    setPrefState(value);
    if (typeof window === "undefined") return;
    if (value) {
      window.localStorage.setItem(PREF_KEY, value);
    } else {
      window.localStorage.removeItem(PREF_KEY);
    }
    window.dispatchEvent(
      new StorageEvent("storage", { key: PREF_KEY, newValue: value ?? null }),
    );
  }, []);

  return { pref, setPref, hydrated };
}
