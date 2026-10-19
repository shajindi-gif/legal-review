"use client";

import * as React from "react";

/**
 * 统一工作台 · 右侧 Context Panel 状态。
 *
 * 三栏布局的第三栏由页面通过 `useRegisterContextPanel` 注入内容：
 * 挂载时注册、卸载时清除，避免页面各自维护一份布局。
 */
export interface ContextPanelContent {
  /** 面板标题 */
  title: string;
  /** 可选副标题 */
  subtitle?: string;
  /** 面板主体 */
  body: React.ReactNode;
}

interface WorkspaceContextValue {
  open: boolean;
  setOpen: React.Dispatch<React.SetStateAction<boolean>>;
  toggle: () => void;
  content: ContextPanelContent | null;
  setContent: React.Dispatch<React.SetStateAction<ContextPanelContent | null>>;
}

const WorkspaceContext = React.createContext<WorkspaceContextValue | null>(null);

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  const [open, setOpen] = React.useState(false);
  const [content, setContent] = React.useState<ContextPanelContent | null>(null);
  const toggle = React.useCallback(() => setOpen((v) => !v), []);

  const value = React.useMemo<WorkspaceContextValue>(
    () => ({ open, setOpen, toggle, content, setContent }),
    [open, toggle, content],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const ctx = React.useContext(WorkspaceContext);
  if (!ctx) {
    throw new Error("useWorkspace 必须在 WorkspaceProvider 内使用");
  }
  return ctx;
}

/**
 * 页面注册 Context Panel 内容。
 *
 * 仅在挂载/卸载时生效（不随每次渲染的对象字面量抖动），
 * 传入一个惰性构造函数以避免无谓 re-render 循环。
 */
export function useRegisterContextPanel(render: () => ContextPanelContent) {
  const { setContent } = useWorkspace();
  const renderRef = React.useRef(render);
  renderRef.current = render;

  React.useEffect(() => {
    setContent(renderRef.current());
    return () => setContent(null);
  }, [setContent]);
}
