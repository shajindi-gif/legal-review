import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { RegisterForm } from "@/components/auth/RegisterForm";

export default function RegisterPage() {
  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center bg-neutral-50 px-4 py-12">
      <Link
        href="/"
        className="absolute left-6 top-6 inline-flex items-center gap-1.5 text-sm text-neutral-500 transition-colors hover:text-neutral-800"
      >
        <ArrowLeft className="h-4 w-4" /> 返回首页
      </Link>
      <div className="mb-8 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-xl font-bold text-white shadow-sm">
          法
        </div>
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">创建账户</h1>
        <p className="mt-1.5 text-sm text-neutral-500">
          注册即享体验版，立即开启首次审查
        </p>
      </div>
      <RegisterForm />
    </div>
  );
}