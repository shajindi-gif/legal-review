import axios, { AxiosError, type AxiosInstance } from "axios";
import type {
  AdminStats,
  AdminUser,
  AuthResponse,
  DocumentRead,
  DocumentUploadResponse,
  Quota,
  ReviewStatus,
  TaskListResponse,
  TaskReport,
  TaskStatusResponse,
  TaskSummary,
  TokenResponse,
  User,
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

export { API_BASE_URL };
