import { Suspense } from "react";
import { LoginForm } from "@/components/auth/LoginForm";
import { AuthLayout } from "@/components/auth/AuthLayout";

export default function LoginPage() {
  return (
    <AuthLayout title="欢迎回来" subtitle="登录以继续智能合法性审查">
      <div className="rounded-xl border border-neutral-200 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-neutral-800 dark:bg-neutral-900 sm:p-8">
        {/* useSearchParams 需要 Suspense 边界 */}
        <Suspense fallback={null}>
          <LoginForm />
        </Suspense>
      </div>
    </AuthLayout>
  );
}
