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

// UI-M7：与后端 Pydantic RiskItem / Evidence 真实形状对齐（app/agent/state.py）
export type RiskSeverity = "low" | "medium" | "high" | "critical" | "info";
export type RiskDimension = "authority" | "procedure" | "content" | "prohibition" | "interest";

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

// 后端 Evidence：单条法规条目（Pydantic RiskItem.evidence 字段）
export interface Evidence {
  law_name: string;
  article: string;
  original_text: string;
  explanation: string;
}

export interface RiskItem {
  dimension: RiskDimension;
  risk_type: string;
  severity: RiskSeverity;
  // UI-M7：文档正文段落锚点（与 body_paragraphs[].id / .anchor 对齐）
  paragraph_id?: string | null;
  paragraph_anchor?: string | null;
  evidence: Evidence;
  confidence: number;
  suggestion: string;
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
  parsed_json?: DocumentJson | null;
  created_at: string;
}

// UI-M7：与后端 Pydantic ParagraphItem / DocumentJson 形状对齐（app/schemas/document.py）
export interface ParagraphItem {
  id: string;
  text: string;
  anchor: string;
}

export interface AttachmentItem {
  name: string;
  path: string;
  size?: number | null;
}

export interface DocumentJson {
  title?: string | null;
  issuing_authority?: string | null;
  publish_date?: string | null;
  effective_date?: string | null;
  doc_number?: string | null;
  body_paragraphs?: ParagraphItem[];
  attachments?: AttachmentItem[];
  keywords?: string[];
  policy_domain?: string | null;
  parser_version?: string;
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

// ===== Notification (UI-M8 通知中心) =====
// 与后端 Pydantic NotificationRead 对齐（app/schemas/notification.py）
export type NotificationKind =
  | "node_running"
  | "node_done"
  | "node_failed"
  | "review_done"
  | "risk_found"
  | "system";

export interface Notification {
  id: string;
  kind: NotificationKind;
  title: string;
  body?: string | null;
  task_id?: string | null;
  link?: string | null;
  payload: Record<string, unknown>;
  read_at?: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  items: Notification[];
  total: number;
  unread_count: number;
  page: number;
  page_size: number;
}

export interface NotificationUnreadCount {
  unread_count: number;
}

// ===== UserFeedback (UI-M11 用户反馈中心) =====
export type FeedbackTargetKind = "report" | "review" | "risk" | "assistant";
export type FeedbackVote = "up" | "down" | "neutral";
export type FeedbackStatus = "open" | "triaged" | "resolved" | "wontfix";

export interface UserFeedback {
  id: string;
  user_id: string;
  target_kind: FeedbackTargetKind;
  target_id: string;
  target_label: string;
  vote: FeedbackVote;
  comment?: string | null;
  status: FeedbackStatus;
  admin_reply?: string | null;
  context: Record<string, unknown>;
  closed_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface UserFeedbackCreate {
  target_kind: FeedbackTargetKind;
  target_id: string;
  target_label: string;
  vote: FeedbackVote;
  comment?: string | null;
  context?: Record<string, unknown>;
}

export interface UserFeedbackListResponse {
  items: UserFeedback[];
  total: number;
  page: number;
  page_size: number;
}

export interface UserFeedbackUpdate {
  closed?: boolean;
}

export interface UserFeedbackSummary {
  total: number;
  by_status: Record<FeedbackStatus, number>;
}

// ===== GlobalSearch (UI-M12 ⌘K 全局搜索) =====
export interface SearchTaskHit {
  id: string;
  title: string;
  status: string;
  priority: string;
  submitted_at: string;
  completed_at?: string | null;
}

export interface SearchDocumentHit {
  id: string;
  task_id: string;
  original_name: string;
  file_type: string;
  file_size: number;
  parse_status: string;
  created_at: string;
}

export interface SearchReportHit {
  task_id: string;
  title: string;
  status: string;
  completed_at?: string | null;
  has_report: boolean;
}

export interface SearchResponse {
  q: string;
  tasks: SearchTaskHit[];
  documents: SearchDocumentHit[];
  reports: SearchReportHit[];
}
