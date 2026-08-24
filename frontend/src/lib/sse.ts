import type { SSEEvent } from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "";

interface SSEClientOptions {
  token: string;
  onEvent: (event: SSEEvent) => void;
  onError?: (err: Event) => void;
  onOpen?: () => void;
}

/**
 * SSE 客户端：订阅任务节点流转事件。
 * 后端目前未提供 SSE 端点（由 /api/v1/tasks/{id}/status 轮询兜底），
 * 此处仍按契约约定拼 URL，便于后端实现时无缝对接。
 *
 * EventSource 不支持自定义 header，故通过 query 透传 token。
 */
export function subscribeReviewStream(
  taskId: string,
  opts: SSEClientOptions,
): () => void {
  const url = `${API_BASE_URL}/api/v1/tasks/${taskId}/stream?token=${encodeURIComponent(
    opts.token,
  )}`;
  let es: EventSource | null = null;
  try {
    es = new EventSource(url);
    es.onopen = () => opts.onOpen?.();
    es.onmessage = (msg) => {
      if (!msg.data) return;
      try {
        const event = JSON.parse(msg.data) as SSEEvent;
        opts.onEvent(event);
      } catch {
        // 忽略非 JSON 帧（如心跳注释）
      }
    };
    es.onerror = (err) => {
      opts.onError?.(err as unknown as Event);
    };
  } catch (err) {
    // SSE 在某些浏览器/网络下抛错时直接 onError 即可
    opts.onError?.(err as unknown as Event);
  }
  return () => {
    es?.close();
  };
}
