import axios, {
  AxiosError,
  type AxiosInstance,
  type AxiosRequestConfig,
} from "axios";
import type {
  AdminStats,
  AdminUser,
  AuthResponse,
  DocumentRead,
  DocumentUploadResponse,
  Notification,
  NotificationListResponse,
  NotificationUnreadCount,
  Quota,
  ReviewStatus,
  SearchResponse,
  TaskListResponse,
  TaskReport,
  TaskStatusResponse,
  TaskSummary,
  TokenResponse,
  User,
  UserFeedback,
  UserFeedbackCreate,
  UserFeedbackListResponse,
  UserFeedbackSummary,
  UserFeedbackUpdate,
} from "@/types/api";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "";

export const api: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30_000,
  headers: { "Content-Type": "application/json" },
  // refresh token 走 HttpOnly Cookie（lr_rt），跨域 dev 环境也需要携带
  withCredentials: true,
});

api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = window.localStorage.getItem("lr_token");
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    // 后端 get_actor 通过 X-User-Id / X-User-Role 头解析 actor（feedback / user_feedback 等端点用）
    const userRaw = window.localStorage.getItem("lr_user");
    if (userRaw) {
      try {
        const u = JSON.parse(userRaw) as { id?: string; role?: string };
        if (u.id) config.headers["X-User-Id"] = u.id;
        if (u.role) config.headers["X-User-Role"] = u.role;
      } catch {
        // ignore malformed
      }
    }
  }
  return config;
});

// ===== 401 静默续期（单飞）：HttpOnly Cookie 自动携带 → 轮换 → 重试原请求 =====
let refreshPromise: Promise<string | null> | null = null;

function isAuthEndpoint(url?: string): boolean {
  if (!url) return false;
  return (
    url.includes("/auth/refresh") ||
    url.includes("/auth/login") ||
    url.includes("/auth/register") ||
    url.includes("/auth/password") ||
    url.includes("/auth/logout")
  );
}

async function silentRefresh(): Promise<string | null> {
  if (!refreshPromise) {
    refreshPromise = axios
      .post<TokenResponse>(
        `${API_BASE_URL}/api/v1/auth/refresh`,
        {},
        { withCredentials: true, timeout: 15_000 },
      )
      .then(({ data }) => {
        if (data.access_token) {
          window.localStorage.setItem("lr_token", data.access_token);
          return data.access_token;
        }
        return null;
      })
      .catch(() => null)
      .finally(() => {
        refreshPromise = null;
      });
  }
  return refreshPromise;
}

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    if (typeof window !== "undefined") {
      const url = (error.config?.baseURL ?? "") + (error.config?.url ?? "");
      const status = error.response?.status;
      const isRetry = Boolean(
        (error.config as { _retry?: boolean } | undefined)?._retry,
      );

      // 401 且非认证端点本身 → 静默续期一次后重试；仍失败才登出
      if (status === 401 && !isRetry && !isAuthEndpoint(error.config?.url)) {
        const newToken = await silentRefresh();
        if (newToken && error.config) {
          const cfg = error.config as AxiosRequestConfig & { _retry?: boolean };
          cfg._retry = true;
          cfg.headers = { ...cfg.headers, Authorization: `Bearer ${newToken}` };
          return api.request(cfg);
        }
        // 续期失败 → 清态回登录页（携带 redirect 还原）
        window.localStorage.removeItem("lr_token");
        window.localStorage.removeItem("lr_user");
        document.cookie = "lr_hint=; path=/; max-age=0";
        if (!window.location.pathname.startsWith("/login")) {
          const redirect = encodeURIComponent(
            window.location.pathname + window.location.search,
          );
          window.location.href = `/login?redirect=${redirect}`;
        }
      }
      if (process.env.NODE_ENV === "development") {
        console.error("[api]", {
          url,
          method: error.config?.method,
          code: error.code,
          message: error.message,
          status,
          data: error.response?.data,
        });
      }
    }
    return Promise.reject(error);
  },
);

function errorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as
      | { detail?: string; message?: string; error?: { message?: string } }
      | undefined;
    // 后端统一 envelope：{error:{code,message,trace_id}}；FastAPI 校验错误走 detail
    return (
      data?.error?.message ?? data?.detail ?? data?.message ?? err.message ?? fallback
    );
  }
  return fallback;
}

// ===== Auth =====

async function fetchMeWithToken(token: string): Promise<User> {
  const { data } = await api.get<User>("/api/v1/auth/me", {
    headers: { Authorization: `Bearer ${token}` },
  });
  return data;
}

/** 后端 /auth/login 与 /auth/register 只返回 TokenResponse，没有 user 字段。 */
async function loginAndFetchUser(tokens: TokenResponse): Promise<AuthResponse> {
  const user = await fetchMeWithToken(tokens.access_token);
  return { ...tokens, user };
}

export async function login(email: string, password: string): Promise<AuthResponse> {
  try {
    const { data } = await api.post<TokenResponse>("/api/v1/auth/login", {
      email,
      password,
    });
    return await loginAndFetchUser(data);
  } catch (err) {
    throw new Error(errorMessage(err, "登录失败，请检查邮箱与密码"));
  }
}

export async function register(
  email: string,
  password: string,
  company?: string,
  realName?: string,
): Promise<AuthResponse> {
  try {
    const { data } = await api.post<TokenResponse>("/api/v1/auth/register", {
      email,
      password,
      company: company || null,
      real_name: realName || null,
    });
    return await loginAndFetchUser(data);
  } catch (err) {
    throw new Error(errorMessage(err, "注册失败，请稍后重试"));
  }
}

export async function fetchMe(): Promise<User> {
  try {
    const { data } = await api.get<User>("/api/v1/auth/me");
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取用户信息失败"));
  }
}

export async function refreshToken(refreshTokenValue: string): Promise<TokenResponse> {
  try {
    const { data } = await api.post<TokenResponse>("/api/v1/auth/refresh", {
      refresh_token: refreshTokenValue,
    });
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "刷新登录态失败"));
  }
}

export async function logout(): Promise<void> {
  try {
    await api.post("/api/v1/auth/logout");
  } catch {
    // 登出失败也由前端清 token 兜底
  }
}

// ===== Auth（统一账号升级 P0）：新认证 API =====

export interface VerificationLoginResult {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  is_new_user: boolean;
  user: User;
}

export interface LoginMethodsResult {
  methods: { key: string; enabled: boolean; label: string }[];
}

export interface SessionInfo {
  id: string;
  issued_at: string;
  expires_at: string;
  user_agent: string | null;
  ip_address: string | null;
  device_id: string | null;
}

export interface AccountProfile {
  id: string;
  username: string;
  real_name: string | null;
  email: string | null;
  email_verified: boolean;
  phone: string | null;
  phone_verified: boolean;
  company: string | null;
  role: string;
  plan_tier: string;
  locale: string;
  timezone: string;
  created_at: string | null;
  last_login_at: string | null;
  has_password: boolean;
}

/** 本地注册（邮箱 + 密码）。返回直接含 user（无需再调 /me）。 */
export async function registerPassword(body: {
  email: string;
  password: string;
  real_name?: string;
  company?: string;
  agreed_terms: boolean;
}): Promise<VerificationLoginResult> {
  try {
    const { data } = await api.post<VerificationLoginResult>(
      "/api/v1/auth/register/password",
      body,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "注册失败，请稍后重试"));
  }
}

/** 统一身份密码登录（邮箱 / 手机号自动识别；后端本地优先 + Core 回退）。 */
export async function loginPassword(
  identifier: string,
  password: string,
): Promise<VerificationLoginResult> {
  try {
    const { data } = await api.post<VerificationLoginResult>(
      "/api/v1/auth/login/password",
      { identifier, password },
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "登录失败，请检查账号与密码"));
  }
}

/** 登录方式开关（未开通渠道 enabled=false）。 */
export async function fetchLoginMethods(): Promise<LoginMethodsResult> {
  try {
    const { data } = await api.get<LoginMethodsResult>("/api/v1/auth/login-methods");
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取登录方式失败"));
  }
}

export type SendCodeChannel = "sms" | "email";

/** 发送验证码（purpose 见后端白名单；成功返回 expires_in）。 */
export async function sendVerificationCode(body: {
  channel: SendCodeChannel;
  target: string;
  purpose: string;
}): Promise<{ success: boolean; expires_in: number }> {
  try {
    const path = body.channel === "sms" ? "/api/v1/auth/sms/send" : "/api/v1/auth/email/send";
    const { data } = await api.post<{ success: boolean; expires_in: number }>(path, {
      [body.channel === "sms" ? "phone" : "email"]: body.target,
      purpose: body.purpose,
    });
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "验证码发送失败，请稍后重试"));
  }
}

/** 验证码统一登录/注册（已有身份登录原账号，新身份创建账号）。 */
export async function loginVerification(body: {
  channel: SendCodeChannel;
  target: string;
  code: string;
}): Promise<VerificationLoginResult> {
  try {
    const { data } = await api.post<VerificationLoginResult>(
      "/api/v1/auth/login/verification",
      body,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "验证码登录失败"));
  }
}

/** 忘记密码（防枚举：恒成功）。 */
export async function forgotPassword(email: string): Promise<void> {
  try {
    await api.post("/api/v1/auth/password/forgot", { email });
  } catch (err) {
    throw new Error(errorMessage(err, "发送重置邮件失败"));
  }
}

/** 重置密码（验证码 + 新密码；成功后所有设备需重新登录）。 */
export async function resetPassword(body: {
  email: string;
  code: string;
  new_password: string;
}): Promise<void> {
  try {
    await api.post("/api/v1/auth/password/reset", body);
  } catch (err) {
    throw new Error(errorMessage(err, "密码重置失败"));
  }
}

/** 修改密码（需登录；其他设备会被登出，当前设备保留）。 */
export async function changePassword(body: {
  current_password: string;
  new_password: string;
}): Promise<{ revoked_other_sessions: number }> {
  try {
    const { data } = await api.post<{ success: boolean; revoked_other_sessions: number }>(
      "/api/v1/auth/password/change",
      body,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "密码修改失败"));
  }
}

/** 绑定/换绑手机号或邮箱（需登录）。 */
export async function bindAccount(body: {
  channel: SendCodeChannel;
  target: string;
  code: string;
  purpose: string;
}): Promise<{ channel: string; target: string }> {
  try {
    const { data } = await api.post<{ success: boolean; channel: string; target: string }>(
      "/api/v1/auth/account/bind",
      body,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "绑定失败"));
  }
}

/** 用户中心资料。 */
export async function fetchAccountProfile(): Promise<AccountProfile> {
  try {
    const { data } = await api.get<AccountProfile>("/api/v1/auth/account");
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取账户信息失败"));
  }
}

/** 更新基本资料。 */
export async function updateAccountProfile(body: {
  real_name?: string;
  company?: string;
}): Promise<AccountProfile> {
  try {
    const { data } = await api.patch<AccountProfile>("/api/v1/auth/account", body);
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "更新资料失败"));
  }
}

/** 活跃会话列表（设备管理）。 */
export async function fetchSessions(): Promise<SessionInfo[]> {
  try {
    const { data } = await api.get<{ sessions: SessionInfo[] }>("/api/v1/auth/sessions");
    return data.sessions;
  } catch (err) {
    throw new Error(errorMessage(err, "获取会话列表失败"));
  }
}

/** 撤销指定会话。 */
export async function revokeSession(id: string): Promise<void> {
  try {
    await api.delete(`/api/v1/auth/sessions/${id}`);
  } catch (err) {
    throw new Error(errorMessage(err, "撤销会话失败"));
  }
}

/** 退出所有设备。 */
export async function logoutAllDevices(): Promise<number> {
  try {
    const { data } = await api.post<{ success: boolean; revoked: number }>(
      "/api/v1/auth/logout-all",
    );
    return data.revoked;
  } catch (err) {
    throw new Error(errorMessage(err, "退出所有设备失败"));
  }
}

// ===== Quota =====
export async function fetchQuota(): Promise<Quota> {
  try {
    const { data } = await api.get<Quota>("/api/v1/auth/quota");
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取配额失败"));
  }
}

// ===== Review / Task =====

/** 上传文件并创建任务。文件通过 multipart/form-data 提交，标题走 X-Task-Title header。 */
export async function createReview(
  file: File,
  opts: { title?: string; priority?: "low" | "normal" | "high" | "urgent" } = {},
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  try {
    const { data } = await api.post<DocumentUploadResponse>(
      "/api/v1/documents/upload",
      form,
      {
        headers: {
          "Content-Type": "multipart/form-data",
          "X-Task-Title": opts.title ?? file.name,
          "X-Priority": opts.priority ?? "normal",
        },
      },
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "提交审查失败"));
  }
}

/** 拉取当前用户的任务列表（分页）。 */
export async function fetchReviews(
  params: { page?: number; page_size?: number; status?: ReviewStatus } = {},
): Promise<TaskListResponse> {
  try {
    const { data } = await api.get<TaskListResponse>("/api/v1/tasks", { params });
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取任务列表失败"));
  }
}

export async function fetchReviewDetail(id: string): Promise<TaskSummary> {
  try {
    const { data } = await api.get<TaskSummary>(`/api/v1/tasks/${id}`);
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取任务详情失败"));
  }
}

export async function fetchTaskStatus(id: string): Promise<TaskStatusResponse> {
  try {
    const { data } = await api.get<TaskStatusResponse>(`/api/v1/tasks/${id}/status`);
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取任务状态失败"));
  }
}

export async function fetchTaskDocuments(taskId: string): Promise<DocumentRead[]> {
  try {
    const { data } = await api.get<DocumentRead[]>(`/api/v1/tasks/${taskId}/documents`);
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取任务文件失败"));
  }
}

export async function fetchTaskDocument(
  taskId: string,
  documentId: string,
): Promise<DocumentRead> {
  try {
    const { data } = await api.get<DocumentRead>(
      `/api/v1/tasks/${taskId}/documents/${documentId}`,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取文件失败"));
  }
}

export async function fetchReport(taskId: string): Promise<TaskReport> {
  try {
    const { data } = await api.get<TaskReport>(`/api/v1/tasks/${taskId}/report`);
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取报告失败"));
  }
}

// ===== Admin (Sprint 6.6 才会真正实现，先以 fetch 形式占位) =====
export async function fetchAdminStats(): Promise<AdminStats> {
  const { data } = await api.get<AdminStats>("/api/v1/admin/stats");
  return data;
}

export async function fetchAdminUsers(): Promise<AdminUser[]> {
  const { data } = await api.get<AdminUser[]>("/api/v1/admin/users");
  return data;
}

// ===== Notification (UI-M8 通知中心) =====
export async function fetchNotifications(
  params: { page?: number; page_size?: number; only_unread?: boolean } = {},
): Promise<NotificationListResponse> {
  try {
    const { data } = await api.get<NotificationListResponse>("/api/v1/notifications", {
      params,
    });
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取通知列表失败"));
  }
}

export async function fetchUnreadCount(): Promise<NotificationUnreadCount> {
  try {
    const { data } = await api.get<NotificationUnreadCount>(
      "/api/v1/notifications/unread-count",
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取未读通知数失败"));
  }
}

export async function markNotificationRead(id: string): Promise<Notification> {
  try {
    const { data } = await api.post<Notification>(
      `/api/v1/notifications/${id}/read`,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "标记已读失败"));
  }
}

export async function markAllNotificationsRead(): Promise<NotificationUnreadCount> {
  try {
    const { data } = await api.post<NotificationUnreadCount>(
      "/api/v1/notifications/read-all",
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "全部已读失败"));
  }
}

// ===== UserFeedback (UI-M11 用户反馈中心) =====

export async function submitUserFeedback(
  payload: UserFeedbackCreate,
): Promise<UserFeedback> {
  try {
    const { data } = await api.post<UserFeedback>("/api/v1/user-feedback", payload);
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "提交反馈失败"));
  }
}

export async function fetchMyFeedback(params: {
  status?: string;
  target_kind?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<UserFeedbackListResponse> {
  try {
    const { data } = await api.get<UserFeedbackListResponse>(
      "/api/v1/user-feedback",
      { params },
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取反馈列表失败"));
  }
}

export async function fetchMyFeedbackSummary(): Promise<UserFeedbackSummary> {
  try {
    const { data } = await api.get<UserFeedbackSummary>(
      "/api/v1/user-feedback/summary",
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取反馈概览失败"));
  }
}

export async function fetchMyFeedbackDetail(id: string): Promise<UserFeedback> {
  try {
    const { data } = await api.get<UserFeedback>(`/api/v1/user-feedback/${id}`);
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取反馈详情失败"));
  }
}

export async function closeMyFeedback(id: string): Promise<UserFeedback> {
  try {
    const { data } = await api.patch<UserFeedback>(
      `/api/v1/user-feedback/${id}`,
      { closed: true } satisfies UserFeedbackUpdate,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "关闭反馈失败"));
  }
}

// admin 端
export async function adminListFeedback(params: {
  status?: string;
  target_kind?: string;
  page?: number;
  page_size?: number;
} = {}): Promise<UserFeedbackListResponse> {
  try {
    const { data } = await api.get<UserFeedbackListResponse>(
      "/api/v1/admin/user-feedback",
      { params },
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取反馈列表失败"));
  }
}

export async function adminFeedbackSummary(): Promise<UserFeedbackSummary> {
  try {
    const { data } = await api.get<UserFeedbackSummary>(
      "/api/v1/admin/user-feedback/summary",
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取反馈概览失败"));
  }
}

export async function adminUpdateFeedback(
  id: string,
  patch: { status?: string; admin_reply?: string },
): Promise<UserFeedback> {
  try {
    const { data } = await api.patch<UserFeedback>(
      `/api/v1/admin/user-feedback/${id}`,
      patch,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "更新反馈失败"));
  }
}

// ===== GlobalSearch (UI-M12 ⌘K) =====
export async function fetchGlobalSearch(
  q: string,
  limit = 8,
): Promise<SearchResponse> {
  try {
    const { data } = await api.get<SearchResponse>("/api/v1/search", {
      params: { q, limit },
    });
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "搜索失败"));
  }
}

export { API_BASE_URL };

// ===== Billing / Payment =====
import type {
  CreateOrderRequest,
  CreateOrderResponse,
  OrderListItem,
  OrderStatusResponse,
  PricingItem,
} from "@/types/api";

export async function fetchPricing(): Promise<PricingItem[]> {
  try {
    const { data } = await api.get<PricingItem[]>("/api/v1/billing/pricing");
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取定价失败"));
  }
}

export async function createOrder(
  req: CreateOrderRequest,
): Promise<CreateOrderResponse> {
  try {
    const { data } = await api.post<CreateOrderResponse>(
      "/api/v1/billing/orders",
      req,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "创建订单失败"));
  }
}

export async function fetchOrderStatus(orderId: string): Promise<OrderStatusResponse> {
  try {
    const { data } = await api.get<OrderStatusResponse>(
      `/api/v1/billing/orders/${orderId}`,
    );
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "查询订单状态失败"));
  }
}

export async function fetchMyOrders(limit = 20): Promise<OrderListItem[]> {
  try {
    const { data } = await api.get<OrderListItem[]>("/api/v1/billing/orders", {
      params: { limit },
    });
    return data;
  } catch (err) {
    throw new Error(errorMessage(err, "获取订单列表失败"));
  }
}

/** 获取微信 JSAPI 静默授权跳转地址（微信内置浏览器内跳转后回带 openid）。 */
export async function fetchWechatOauthUrl(state = "/pricing"): Promise<string> {
  try {
    const { data } = await api.get<{ url: string }>("/api/v1/billing/wechat/oauth/url", {
      params: { state },
    });
    return data.url;
  } catch (err) {
    throw new Error(errorMessage(err, "获取微信授权地址失败"));
  }
}
