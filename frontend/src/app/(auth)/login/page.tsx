import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
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
        <h1 className="text-2xl font-semibold tracking-tight text-neutral-900">欢迎回来</h1>
        <p className="mt-1.5 text-sm text-neutral-500">登录以继续智能合法性审查</p>
      </div>
      <LoginForm />
    </div>
  );
}