/**
 * 前端埋点最小集：track() 上报用户行为事件到 /api/v1/analytics/events。
 *
 * 原则：
 * - best-effort：任何失败静默吞掉，绝不影响主流程
 * - 无 PII：只带匿名 ID（localStorage 随机 UUID），不带任何身份/联系方式
 * - keepalive: true 保证页面跳转时请求也能发出
 */

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "";

const ANONYMOUS_ID_KEY = "lr_anonymous_id";

/** 服务端事件白名单（与 backend/app/api/v1/analytics.py 保持一致） */
export type AnalyticsEventName =
  | "page_view"
  | "pricing_view"
  | "signup_submit"
  | "first_task_started"
  | "task_completed"
  | "quota_exhausted"
  | "upgrade_dialog_view"
  | "upgrade_click"
  | "order_created"
  | "order_paid"
  | "landing_view"
  | "custom_error"
  // ---- 认证转化漏斗（P0 升级）----
  | "auth_page_view"
  | "signup_start"
  | "signup_success"
  | "login_success"
  | "login_failed"
  | "verification_sent"
  | "verification_success"
  | "verification_failed"
  | "password_reset_success"
  | "onboarding_completed";

/** 读取/生成并持久化匿名 ID（非 PII，随机 UUID） */
function getAnonymousId(): string {
  if (typeof window === "undefined") return "";
  try {
    let id = window.localStorage.getItem(ANONYMOUS_ID_KEY);
    if (!id) {
      id =
        typeof crypto !== "undefined" && "randomUUID" in crypto
          ? crypto.randomUUID()
          : `anon-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      window.localStorage.setItem(ANONYMOUS_ID_KEY, id);
    }
    return id;
  } catch {
    // localStorage 不可用（隐私模式等）时放弃匿名 ID，事件仍可上报
    return "";
  }
}

/** 上报一次埋点事件（fire-and-forget，静默失败） */
export function track(
  event: AnalyticsEventName,
  props?: Record<string, unknown>,
): void {
  if (typeof window === "undefined") return;
  try {
    void fetch(`${API_BASE_URL}/api/v1/analytics/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event,
        properties: props ?? {},
        anonymous_id: getAnonymousId(),
      }),
      keepalive: true,
    }).catch(() => {
      // 静默：埋点失败不提示、不重试
    });
  } catch {
    // 静默：fetch 构造失败同样不影响主流程
  }
}
