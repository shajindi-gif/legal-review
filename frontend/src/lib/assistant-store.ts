import { create } from "zustand";
import { useEffect } from "react";

/**
 * Assistant 多草稿会话 Store（UI-M6.1 + UI-M6.6）。
 *
 * 数据模型：
 *   Conversation = { id, title, draft, createdAt, updatedAt, actions[] }
 *   Action = { id, kind, at, source, payload }
 *     kind:   "open_upload" | "open_dashboard" | "pick_recent" | "rename"
 *     source: "home" | "assistant" | "recent" | "unknown"
 *
 * 持久化：localStorage 单 key（"lr_assistant_conversations"）+ schema version。
 * 跨 tab：监听 window 'storage' 事件。
 *
 * 合规声明（Section 2）：
 *   - 不渲染任何"假"AI 回复气泡。
 *   - 列表里的每一条都是用户真实发起的"问题草稿" + 它的真实后续动作轨迹。
 *   - 后端 Conversation API 落地后，仅需替换 persist() 的写入目标，
 *     组件层不需要改。
 */

const STORE_KEY = "lr_assistant_conversations";
const SCHEMA_VERSION = 1;

export type AssistantActionKind =
  | "open_upload"
  | "open_dashboard"
  | "pick_recent"
  | "rename";

/**
 * AssistantAction 的来源（UI-M6.6 引入）。
 * - `home`     ：从 Home Hero 提问发起
 * - `assistant`：在 Assistant 内部主动创建 / 编辑
 * - `recent`   ：从右侧"历史任务"挑选
 * - `unknown`  ：兜底（默认 / 旧数据）
 */
export type AssistantActionSource =
  | "home"
  | "assistant"
  | "recent"
  | "unknown";

export interface AssistantAction {
  id: string;
  kind: AssistantActionKind;
  at: number;
  source?: AssistantActionSource;
  /** 跳转时附带的 query 摘要，便于 UI 列表展示 */
  payload?: Record<string, unknown>;
}

export interface Conversation {
  id: string;
  title: string;
  draft: string;
  createdAt: number;
  updatedAt: number;
  actions: AssistantAction[];
}

interface PersistedShape {
  version: number;
  conversations: Conversation[];
}

interface AssistantState {
  hydrated: boolean;
  conversations: Conversation[];
  activeId: string | null;

  // === lifecycle ===
  hydrate: () => void;

  // === CRUD ===
  create: (init?: { draft?: string; title?: string }) => string;
  setActive: (id: string | null) => void;
  rename: (id: string, title: string) => void;
  remove: (id: string) => void;
  setDraft: (id: string, draft: string) => void;
  recordAction: (
    id: string,
    kind: AssistantActionKind,
    payload?: Record<string, unknown>,
    source?: AssistantActionSource,
  ) => void;
  clearAll: () => void;
}

// ----- helpers -----

function newId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `c_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

function defaultTitle(draft: string): string {
  const t = draft.trim().replace(/\s+/g, " ");
  if (!t) return "新会话";
  return t.length > 24 ? `${t.slice(0, 24)}…` : t;
}

function readPersisted(): PersistedShape | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(STORE_KEY);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as PersistedShape;
    if (!parsed || typeof parsed !== "object") return null;
    if (parsed.version !== SCHEMA_VERSION) return null;
    if (!Array.isArray(parsed.conversations)) return null;
    // 简单形状校验
    const cleaned: Conversation[] = parsed.conversations
      .filter(
        (c) =>
          c &&
          typeof c.id === "string" &&
          typeof c.title === "string" &&
          typeof c.draft === "string" &&
          typeof c.createdAt === "number" &&
          typeof c.updatedAt === "number" &&
          Array.isArray(c.actions),
      )
      .slice(0, 200); // 防御：单用户最多保留 200 条
    return { version: SCHEMA_VERSION, conversations: cleaned };
  } catch {
    return null;
  }
}

function writePersisted(conversations: Conversation[]) {
  if (typeof window === "undefined") return;
  const payload: PersistedShape = {
    version: SCHEMA_VERSION,
    conversations,
  };
  try {
    window.localStorage.setItem(STORE_KEY, JSON.stringify(payload));
  } catch (err) {
    // quota exceeded 或隐私模式：静默降级，会话仍在内存中工作
    console.warn("[assistant-store] persist failed", err);
  }
}

// ----- store -----

export const useAssistantStore = create<AssistantState>((set, get) => ({
  hydrated: false,
  conversations: [],
  activeId: null,

  hydrate: () => {
    if (typeof window === "undefined") return;
    if (get().hydrated) return;
    const data = readPersisted();
    set({
      hydrated: true,
      conversations: data?.conversations ?? [],
      activeId: data?.conversations?.[0]?.id ?? null,
    });
  },

  create: (init) => {
    const draft = init?.draft ?? "";
    const now = Date.now();
    const conv: Conversation = {
      id: newId(),
      title: init?.title ?? defaultTitle(draft),
      draft,
      createdAt: now,
      updatedAt: now,
      actions: [],
    };
    const list = [conv, ...get().conversations];
    set({ conversations: list, activeId: conv.id });
    writePersisted(list);
    return conv.id;
  },

  setActive: (id) => {
    set({ activeId: id });
  },

  rename: (id, title) => {
    const list = get().conversations.map((c) =>
      c.id === id
        ? { ...c, title: title.trim() || c.title, updatedAt: Date.now() }
        : c,
    );
    set({ conversations: list });
    writePersisted(list);
  },

  remove: (id) => {
    const list = get().conversations.filter((c) => c.id !== id);
    const activeId =
      get().activeId === id ? (list[0]?.id ?? null) : get().activeId;
    set({ conversations: list, activeId });
    writePersisted(list);
  },

  setDraft: (id, draft) => {
    const list = get().conversations.map((c) =>
      c.id === id ? { ...c, draft, updatedAt: Date.now() } : c,
    );
    set({ conversations: list });
    writePersisted(list);
  },

  recordAction: (id, kind, payload, source) => {
    const list = get().conversations.map((c) =>
      c.id === id
        ? {
            ...c,
            actions: [
              ...c.actions,
              {
                id: newId(),
                kind,
                at: Date.now(),
                payload,
                source: source ?? "unknown",
              },
            ].slice(-50), // 单会话最多 50 条动作
            updatedAt: Date.now(),
          }
        : c,
    );
    set({ conversations: list });
    writePersisted(list);
  },

  clearAll: () => {
    set({ conversations: [], activeId: null });
    writePersisted([]);
  },
}));

// ----- cross-tab sync -----

/**
 * 监听 localStorage 变化，把其他 tab 的更新同步进来。
 * 调用方应在 (app) 布局挂载一次即可。
 */
export function useAssistantCrossTabSync() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    function onStorage(e: StorageEvent) {
      if (e.key !== STORE_KEY) return;
      const data = readPersisted();
      if (!data) return;
      // 其他 tab 修改了 store —— 完整覆盖当前内存
      const cur = useAssistantStore.getState();
      // 保留 activeId（用户在当前 tab 的选择），其他全量替换
      useAssistantStore.setState({
        conversations: data.conversations,
        activeId:
          cur.activeId &&
          data.conversations.some((c) => c.id === cur.activeId)
            ? cur.activeId
            : (data.conversations[0]?.id ?? null),
      });
    }
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);
}
