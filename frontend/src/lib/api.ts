import axios, { AxiosError, type AxiosInstance } from "axios";
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

api.interceptors.response.use(
  (res) => res,
  (error: AxiosError) => {
    // 临时诊断日志：把 Network Error 的真实原因打到浏览器控制台
    if (typeof window !== "undefined") {
      const url = (error.config?.baseURL ?? "") + (error.config?.url ?? "");
      console.error("[api]", {
        url,
        method: error.config?.method,
        code: error.code,
        message: error.message,
        status: error.response?.status,
        data: error.response?.data,
        cause: (error as { cause?: unknown }).cause,
      });
    }
    if (error.response?.status === 401 && typeof window !== "undefined") {
      window.localStorage.removeItem("lr_token");
      window.localStorage.removeItem("lr_user");
      if (!window.location.pathname.startsWith("/login")) {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  },
);

function errorMessage(err: unknown, fallback: string): string {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as { detail?: string; message?: string } | undefined;
    return data?.detail ?? data?.message ?? err.message ?? fallback;
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
