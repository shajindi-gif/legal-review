import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";
import { AuthLayout } from "@/components/auth/AuthLayout";

export const metadata = { title: "忘记密码 · 智审 LegalReview" };

export default function ForgotPasswordPage() {
  return (
    <AuthLayout title="找回密码" subtitle="输入注册邮箱，我们将发送重置验证码">
      <div className="rounded-xl border border-neutral-200 bg-white p-6 shadow-[0_1px_2px_rgba(15,23,42,0.04)] dark:border-neutral-800 dark:bg-neutral-900 sm:p-8">
        <ForgotPasswordForm />
      </div>
    </AuthLayout>
  );
}
