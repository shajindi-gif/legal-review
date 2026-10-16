"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { forgotPassword, resetPassword } from "@/lib/api";
import { track } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

function passwordIssues(pw: string): string[] {
  const issues: string[] = [];
  if (pw.length < 8) issues.push("至少 8 位");
  if (pw.length > 128) issues.push("不超过 128 位");
  if (!/[a-zA-Z]/.test(pw)) issues.push("需包含字母");
  if (!/\d/.test(pw)) issues.push("需包含数字");
  return issues;
}

/**
 * 忘记密码两步流程（防枚举）：
 * 1. 输入邮箱发送重置验证码——无论邮箱是否存在恒提示已发送（不泄露账户存在性）
 * 2. 验证码 + 新密码重置——成功后所有设备强制重新登录
 */
export function ForgotPasswordForm() {
  const router = useRouter();
  const [step, setStep] = React.useState<1 | 2>(1);
  const [email, setEmail] = React.useState("");
  const [code, setCode] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [countdown, setCountdown] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [sentNotice, setSentNotice] = React.useState(false);

  const issues = passwordIssues(newPassword);
  const passwordValid = newPassword.length > 0 && issues.length === 0;

  React.useEffect(() => {
    if (countdown <= 0) return;
    const t = setInterval(() => setCountdown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [countdown]);

  async function onSend(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim())) {
      setError("请输入正确的邮箱地址");
      return;
    }
    setLoading(true);
    try {
      await forgotPassword(email.trim());
      // 防枚举：统一提示，不暴露邮箱是否已注册
      setSentNotice(true);
      setStep(2);
      setCountdown(60);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  async function onReset(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (code.trim().length < 4) {
      setError("请输入邮箱收到的验证码");
      return;
    }
    if (!passwordValid) {
      setError(`密码要求：${issues.join("、")}`);
      return;
    }
    setLoading(true);
    try {
      await resetPassword({
        email: email.trim(),
        code: code.trim(),
        new_password: newPassword,
      });
      track("password_reset_success");
      // replace：重置完成后回到登录页，避免后退回到已失效的重置表单
      router.replace("/login?reset=1");
    } catch (err) {
      setError(err instanceof Error ? err.message : "密码重置失败");
    } finally {
      setLoading(false);
    }
  }

  async function onResend() {
    if (loading || countdown > 0) return;
    setError(null);
    setLoading(true);
    try {
      await forgotPassword(email.trim());
      setCountdown(60);
    } catch (err) {
      setError(err instanceof Error ? err.message : "发送失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={step === 1 ? onSend : onReset} className="flex flex-col gap-4" noValidate>
      {step === 1 ? (
        <div className="flex flex-col gap-2">
          <Label htmlFor="fp-email">注册邮箱</Label>
          <Input
            id="fp-email"
            type="email"
            required
            autoComplete="email"
            autoCapitalize="none"
            spellCheck={false}
            placeholder="you@company.com"
            aria-invalid={Boolean(error)}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
      ) : (
        <>
          {sentNotice && (
            <p
              role="status"
              className="rounded-md bg-success-50 px-3 py-2 text-sm text-success-700 dark:bg-success-500/10 dark:text-success-500"
            >
              若该邮箱已注册，验证码已发送，请查收（含垃圾邮件箱）
            </p>
          )}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="fp-code">验证码</Label>
              <button
                type="button"
                onClick={onResend}
                disabled={countdown > 0 || loading}
                className="text-xs text-neutral-500 transition-colors hover:text-brand-700 disabled:cursor-not-allowed disabled:text-neutral-400 dark:hover:text-brand-400"
              >
                {countdown > 0 ? `${countdown}s 后重发` : "重新发送"}
              </button>
            </div>
            <Input
              id="fp-code"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              required
              maxLength={6}
              placeholder="6 位验证码"
              aria-invalid={Boolean(error)}
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="fp-new-password">新密码</Label>
            <Input
              id="fp-new-password"
              type="password"
              required
              autoComplete="new-password"
              placeholder="至少 8 位，含字母和数字"
              aria-invalid={Boolean(error)}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
            />
            {newPassword.length > 0 && !passwordValid && (
              <p className="text-xs text-warning-700 dark:text-warning-500">{issues.join("、")}</p>
            )}
          </div>
        </>
      )}

      {error && (
        <p
          role="alert"
          className={cn(
            "rounded-md bg-danger-50 px-3 py-2 text-sm text-danger-700",
            "dark:bg-danger-500/10 dark:text-danger-500",
          )}
        >
          {error}
        </p>
      )}

      <Button type="submit" disabled={loading} className="w-full">
        {loading ? "处理中…" : step === 1 ? "发送验证码" : "重置密码"}
      </Button>

      <p className="text-center text-sm text-neutral-500 dark:text-neutral-400">
        <Link
          href="/login"
          className="font-medium text-brand-700 hover:underline dark:text-brand-400"
        >
          返回登录
        </Link>
      </p>
    </form>
  );
}
