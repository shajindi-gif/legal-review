"use client";

import * as React from "react";
import { track } from "@/lib/analytics";

/**
 * PageViewTracker —— 在服务端组件页面中注入一次 page_view 埋点（R1-3）。
 *
 * 服务端组件无法直接调用浏览器埋点，故抽成一个零渲染的客户端组件，
 * 挂载时上报一次（useRef 保证同一挂载周期内只报一次，避免重复渲染重复上报）。
 */
export function PageViewTracker({ page }: { page: string }) {
  const tracked = React.useRef(false);
  React.useEffect(() => {
    if (tracked.current) return;
    tracked.current = true;
    track("page_view", { page });
  }, [page]);
  return null;
}
