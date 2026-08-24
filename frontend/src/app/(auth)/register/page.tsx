import { RegisterForm } from "@/components/auth/RegisterForm";

export default function RegisterPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-gradient-to-b from-brand-50 to-white px-4 py-12">
      <div className="mb-8 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-brand-600 text-xl font-bold text-white">
          法
        </div>
        <h1 className="text-2xl font-bold text-brand-700">创建账户</h1>
        <p className="mt-1 text-sm text-gray-500">
          注册即享体验版，3 分钟开启首次审查
        </p>
      </div>
      <RegisterForm />
    </div>
  );
}
