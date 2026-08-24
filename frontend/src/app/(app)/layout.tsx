import { AuthGuard } from "@/components/auth/AuthGuard";
import { TopBar } from "@/components/dashboard/TopBar";
import { SideNav } from "@/components/dashboard/SideNav";

/**
 * 受保护布局：路由层 proxy.ts + 客户端 AuthGuard 双重守卫，
 * 统一渲染顶栏 + 侧栏 + 内容区。
 */
export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <div className="flex h-screen flex-col">
        <TopBar />
        <div className="flex flex-1 overflow-hidden">
          <SideNav />
          <main className="flex-1 overflow-y-auto bg-gray-50 p-6">
            {children}
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}
