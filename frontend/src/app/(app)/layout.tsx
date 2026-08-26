import { AppShell } from "@/components/dashboard/AppShell";

/**
 * 受保护布局：路由层 proxy.ts + 客户端 AuthGuard 双重守卫，
 * 统一渲染 AppShell（TopBar + SideNav + 主区 + 移动端 Drawer）。
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return <AppShell>{children}</AppShell>;
}
