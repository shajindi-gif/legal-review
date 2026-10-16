import { Suspense } from "react";
import { RegisterForm } from "@/components/auth/RegisterForm";
import { AuthLayout } from "@/components/auth/AuthLayout";

export default function RegisterPage() {
  return (
    <AuthLayout title="创建账户" subtitle="注册即享体验版，立即开启首次审查">
      <div className="rounded-xl border border-neutral-200 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-neutral-800 dark:bg-neutral-900 sm:p-8">
        {/* useSearchParams 需要 Suspense 边界 */}
        <Suspense fallback={null}>
          <RegisterForm />
        </Suspense>
      </div>
    </AuthLayout>
  );
}
