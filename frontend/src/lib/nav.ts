import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Bell,
  CreditCard,
  FileSearch,
  FileSignature,
  FolderKanban,
  History as HistoryIcon,
  LayoutDashboard,
  Library,
  MessageSquareQuote,
  PenLine,
  Scale,
  Settings as SettingsIcon,
  Shield,
  ShieldCheck,
  Sparkles,
  User as UserIcon,
  Workflow,
} from "lucide-react";
import type { Role } from "@/types/api";

/**
 * 统一工作台导航配置（单一事实源）。
 *
 * 一级导航固定为 11 个模块（对标 AI-Native Legal Workspace）。
 * 硬约束：没有真正实现的模块 `comingSoon: true`，禁止点击、显示「即将」角标，
 * 不得展示假入口（见 SideNav 既有约定）。
 *
 * 角色显隐：`roles` 为可访问该模块的角色白名单；缺省 = 全部角色可见。
 */
export interface NavModule {
  key: string;
  href: string;
  /** 中文主标题 */
  label: string;
  /** 英文副标题 */
  labelEn: string;
  icon: LucideIcon;
  comingSoon?: boolean;
  roles?: Role[];
  /** 额外归属本模块的路由前缀（用于高亮，如 规范性文件审核 覆盖 /review、/report）。 */
  matchPaths?: string[];
}

/** 11 个一级模块（顺序固定，按业务优先级排列）。 */
export const PRIMARY_MODULES: NavModule[] = [
  {
    key: "workspace",
    href: "/dashboard",
    label: "工作台",
    labelEn: "Workspace",
    icon: LayoutDashboard,
  },
  {
    key: "research",
    href: "/research",
    label: "法律研究",
    labelEn: "Legal Research",
    icon: Scale,
    comingSoon: true,
  },
  {
    key: "assistant",
    href: "/assistant",
    label: "AI 助手",
    labelEn: "Legal Assistant",
    icon: Sparkles,
  },
  {
    key: "contract",
    href: "/contract",
    label: "合同审查",
    labelEn: "Contract Review",
    icon: FileSignature,
    comingSoon: true,
    // 律所律师 / 企业法务 / 主管 / 管理员
    roles: ["reviewer", "supervisor", "admin"],
  },
  {
    key: "documents",
    href: "/documents",
    label: "文件分析",
    labelEn: "Document Analysis",
    icon: FileSearch,
  },
  {
    key: "government",
    href: "/upload",
    label: "规范性文件审核",
    labelEn: "Government Review",
    icon: ShieldCheck,
    matchPaths: ["/upload", "/review", "/report"],
  },
  {
    key: "editor",
    href: "/editor",
    label: "法律文书",
    labelEn: "Legal Editor",
    icon: PenLine,
    comingSoon: true,
    roles: ["reviewer", "supervisor", "admin"],
  },
  {
    key: "workflows",
    href: "/tasks",
    label: "AI 工作流",
    labelEn: "Workflows",
    icon: Workflow,
  },
  {
    key: "knowledge",
    href: "/knowledge",
    label: "法律知识库",
    labelEn: "Knowledge Base",
    icon: Library,
    comingSoon: true,
  },
  {
    key: "projects",
    href: "/projects",
    label: "项目与团队",
    labelEn: "Projects",
    icon: FolderKanban,
    comingSoon: true,
    roles: ["reviewer", "supervisor", "admin"],
  },
  {
    key: "settings",
    href: "/account",
    label: "管理与设置",
    labelEn: "Settings",
    icon: SettingsIcon,
  },
];

/** 次级快捷入口（不属于 11 个一级模块，但为常用真实页面）。 */
export const SECONDARY_ITEMS: NavModule[] = [
  {
    key: "notifications",
    href: "/notifications",
    label: "通知",
    labelEn: "Notifications",
    icon: Bell,
  },
  {
    key: "reports",
    href: "/reports",
    label: "报告",
    labelEn: "Reports",
    icon: BarChart3,
  },
  {
    key: "feedback",
    href: "/dashboard/feedback",
    label: "反馈",
    labelEn: "Feedback",
    icon: MessageSquareQuote,
  },
  {
    key: "history",
    href: "/history",
    label: "历史",
    labelEn: "History",
    icon: HistoryIcon,
    comingSoon: true,
  },
];

/** 管理员专属入口。 */
export const ADMIN_ITEMS: NavModule[] = [
  { key: "admin", href: "/admin", label: "管理后台", labelEn: "Admin", icon: Shield },
  {
    key: "admin-feedback",
    href: "/admin/feedback",
    label: "用户反馈",
    labelEn: "Feedback",
    icon: MessageSquareQuote,
  },
];

/** 底部入口（账户 / 计费）。 */
export const BOTTOM_ITEMS: NavModule[] = [
  { key: "billing", href: "/pricing", label: "套餐与计费", labelEn: "Billing", icon: CreditCard },
  { key: "account", href: "/account", label: "账户设置", labelEn: "Account", icon: UserIcon },
];

/** 当前角色是否可见该模块（缺省 roles = 全部可见）。 */
export function canSeeModule(module: NavModule, role: Role | null | undefined): boolean {
  if (!module.roles || module.roles.length === 0) return true;
  if (!role) return false;
  return module.roles.includes(role);
}

/** 按角色过滤模块列表。 */
export function filterByRole(
  modules: NavModule[],
  role: Role | null | undefined,
): NavModule[] {
  return modules.filter((m) => canSeeModule(m, role));
}

/** 用于 nav 的 testid 片段（英文小写、去空格）。 */
export function navTestId(module: NavModule): string {
  return module.labelEn.toLowerCase().replace(/\s+/g, "-");
}
