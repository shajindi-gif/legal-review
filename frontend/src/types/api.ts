// 后端 API 响应的 TypeScript 类型定义（Sprint 8.1.1 对齐后端契约）
// 对应后端: app/schemas/auth.py + app/schemas/task.py + app/schemas/document.py

// ===== Plan / Role =====
export type PlanTier = "free" | "pro" | "enterprise";
export type Role =
  | "submitter"
  | "reviewer"
  | "supervisor"
  | "admin"
  | "librarian";

// ===== User / Auth =====
export interface User {
  id: string;
  email: string;
  username: string;
  real_name: string;
  company?: string | null;
  role: Role;
  plan_tier: PlanTier;
  quota_daily: number;
  used_today: number;
  last_login_at?: string | null;
}

export interface AuthResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

// 后端 /auth/login 与 /auth/register 直接返回 TokenResponse（不带 user 字段）
// 前端拿到 token 后需要再调一次 /auth/me 补全 user
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface Quota {
  tier: PlanTier;
  quota_daily: number;
  used_today: number;
  remaining: number;
  unlimited: boolean;
  reset_date?: string | null;
}

// ===== Review / Task =====
export type ReviewStatus =
  | "pending"
  | "parsing"
  | "running"
  | "completed"
  | "failed"
  | "done";

export type RiskSeverity = "high" | "medium" | "low" | "info";

export interface TaskSummary {
  id: string;
  trace_id: string;
  title: string;
  status: ReviewStatus;
  current_node?: string | null;
  iteration: number;
  max_iteration: number;
  priority: string;
  submitted_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  due_at?: string | null;
  created_at: string;
}

export interface TaskListResponse {
  total: number;
  page: number;
  page_size: number;
  items: TaskSummary[];
}

export interface TaskStatusResponse {
  task_id: string;
  trace_id: string;
  status: ReviewStatus;
  current_node?: string | null;
  progress: number;
  iteration: number;
  max_iteration: number;
  estimated_remaining_sec?: number | null;
}

export interface TaskReport {
  task_id: string;
  status: ReviewStatus;
  report_markdown: string;
  risks: RiskItem[];
  evidences: Evidence[];
}

export interface Evidence {
  title: string;
  source?: string;
  article?: string;
  content: string;
  url?: string;
}

export interface RiskItem {
  id: string;
  severity: RiskSeverity;
  category: string;
  description: string;
  suggestion?: string;
  evidence?: Evidence[];
}

export type NodeStatus = "pending" | "running" | "done" | "skipped";

export interface ReviewNode {
  id: string;
  name: string;
  label: string;
  status: NodeStatus;
  started_at?: string;
  finished_at?: string;
  detail?: string;
}

// ===== Document =====
export interface DocumentUploadResponse {
  task_id: string;
  trace_id: string;
  document_id: string;
  original_name: string;
  file_type: string;
  file_size: number;
  file_hash: string;
  storage_path: string;
  parse_status: string;
  status: string;
}

export interface DocumentRead {
  id: string;
  task_id: string;
  original_name: string;
  file_type: string;
  file_size: number;
  file_hash: string;
  parse_status: string;
  parsed_json?: Record<string, unknown> | null;
  created_at: string;
}

// ===== SSE =====
export type SSEEvent =
  | { type: "node_start"; node_id: string; node_name: string; ts?: string }
  | { type: "node_finish"; node_id: string; node_name: string; ts?: string; detail?: string }
  | { type: "risk_found"; risk: RiskItem }
  | { type: "evidence"; evidence: Evidence }
  | { type: "suggestion"; suggestion: string }
  | { type: "complete"; review_id: string }
  | { type: "error"; message: string };

// ===== Admin (Sprint 6.6 才会真正实现，先保留形状避免 8.2 admin 页面编译失败) =====
export interface AdminStats {
  total_users: number;
  total_reviews: number;
  today_reviews: number;
  active_users?: number;
}

export interface AdminUser {
  id: string;
  email: string;
  company?: string;
  plan: PlanTier;
  role: Role;
  created_at: string;
  review_count?: number;
}
