"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  fetchLoginMethods,
  loginPassword,
  loginVerification,
  sendVerificationCode,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { track } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

/** 仅允许站内路径，防开放重定向。 */
function sanitizeRedirect(raw: string | null): string {
  if (!raw || !raw.startsWith("/") || raw.startsWith("//") || raw.includes("\n")) {
    return "/dashboard";
  }
  return raw;
}

function isEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

function isPhone(value: string): boolean {
  return /^1\d{10}$/.test(value.trim());
}

/** 标识符是否合法（邮箱或手机号其一）。 */
function validIdentifier(value: string): boolean {
  return isEmail(value) || isPhone(value);
}

type LoginMode = "password" | "code";

interface MethodFlags {
  password: boolean;
  sms: boolean;
  email: boolean;
}

const DEFAULT_METHODS: MethodFlags = { password: true, sms: false, email: false };

/**
 * 统一登录表单（认证升级 P0）：
 * - 单一标识符输入（邮箱 / 手机号自动识别），低注册摩擦
 * - 密码登录 / 验证码登录分段切换（依据后端 login-methods 开关）
 * - 验证码 60s 倒计时重发；错误统一 role=alert 可访问播报
 * - 埋点：auth_page_view / login_success / login_failed / verification_*
 */
export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = React.useMemo(
    () => sanitizeRedirect(searchParams.get("redirect")),
    [searchParams],
  );
  const justReset = searchParams.get("reset") === "1";
  const setAuth = useAuthStore((s) => s.setAuth);

  const [mode, setMode] = React.useState<LoginMode>("password");
  const [methods, setMethods] = React.useState<MethodFlags>(DEFAULT_METHODS);
  const [identifier, setIdentifier] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [code, setCode] = React.useState("");
  const [countdown, setCountdown] = React.useState(0);
  const [loading, setLoading] = React.useState(false);
  const [sending, setSending] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const identifierRef = React.useRef<HTMLInputElement>(null);

  // 页面曝光 + 登录方式开关（失败时静默回落默认：仅密码）
  React.useEffect(() => {
    track("auth_page_view", { page: "login" });
    fetchLoginMethods()
      .then((res) => {
        const byKey = new Map(res.methods.map((m) => [m.key, m.enabled]));
        setMethods({
          password: byKey.get("password") ?? false,
          sms: byKey.get("phone") ?? false,
          email: byKey.get("email") ?? false,
        });
      })
      .catch(() => {
        /* 网络失败时保持默认：密码登录可用 */
      });
  }, []);

  // 验证码倒计时
  React.useEffect(() => {
    if (countdown <= 0) return;
    const t = setInterval(() => setCountdown((c) => c - 1), 1000);
    return () => clearInterval(t);
  }, [countdown]);

  // 渠道不可用时自动切回密码模式
  React.useEffect(() => {
    if (mode === "code" && !methods.sms && !methods.email) {
      setMode("password");
    }
    if (mode === "password" && !methods.password && (methods.sms || methods.email)) {
      setMode("code");
    }
  }, [mode, methods]);

  async function onSendCode() {
    if (sending || countdown > 0) return;
    setError(null);
    if (!validIdentifier(identifier)) {
      setError("请输入正确的手机号或邮箱地址");
      identifierRef.current?.focus();
      return;
    }
    const emailTarget = isEmail(identifier);
    const channel = emailTarget ? "email" : "sms";
    if (emailTarget && !methods.email) {
      setError("邮箱验证码登录暂未开通，请使用密码登录");
      return;
    }
    if (!emailTarget && !methods.sms) {
      setError("手机号验证码登录暂未开通，请使用密码登录");
      return;
    }
    setSending(true);
    try {
      await sendVerificationCode({ channel, target: identifier.trim(), purpose: "login" });
      track("verification_sent", { context: "login", channel });
      setCountdown(60);
    } catch (err) {
      setError(err instanceof Error ? err.message : "验证码发送失败，请稍后重试");
      track("verification_failed", { context: "login_send", channel });
    } finally {
      setSending(false);
    }
  }

  function onSwitchMode(next: LoginMode) {
    setMode(next);
    setError(null);
    setCode("");
    if (next === "password") setPassword("");
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!validIdentifier(identifier)) {
      setError("请输入正确的手机号或邮箱地址");
      identifierRef.current?.focus();
      return;
    }
    setLoading(true);
    try {
      let res;
      if (mode === "password") {
        if (!password) {
          setError("请输入密码");
          setLoading(false);
          return;
        }
        res = await loginPassword(identifier.trim(), password);
      } else {
        if (code.trim().length < 4) {
          setError("请输入收到的验证码");
          setLoading(false);
          return;
        }
        const channel = isEmail(identifier) ? "email" : "sms";
        res = await loginVerification({
          channel,
          target: identifier.trim(),
          code: code.trim(),
        });
        track("verification_success", { context: "login" });
      }
      setAuth(res.access_token, res.user);
      track("login_success", {
        method: mode,
        is_new_user: res.is_new_user,
      });
      // replace 而非 push：避免后退键回到登录页
      router.replace(redirect);
    } catch (err) {
      // 防枚举：文案统一，不区分「账号不存在 / 密码错误」
      setError(err instanceof Error ? err.message : "登录失败，请稍后重试");
      track("login_failed", { method: mode });
    } finally {
      setLoading(false);
    }
  }

  const codeChannelReady =
    methods.sms || methods.email ? (isEmail(identifier) ? methods.email : methods.sms) : false;

  return (
    <div className="w-full">
      {/* 登录方式切换（仅展示已开通方式；两者都可用才显示分段控件） */}
      {methods.password && (methods.sms || methods.email) && (
        <div
          role="tablist"
          aria-label="登录方式"
          className="mb-6 grid grid-cols-2 gap-1 rounded-lg bg-neutral-100 p-1 dark:bg-neutral-900"
        >
          {(
            [
              ["password", "密码登录"],
              ["code", "验证码登录"],
            ] as const
          ).map(([key, label]) => (
            <button
              key={key}
              type="button"
              role="tab"
              aria-selected={mode === key}
              onClick={() => onSwitchMode(key)}
              className={cn(
                "rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
                mode === key
                  ? "bg-white text-neutral-900 shadow-sm dark:bg-neutral-800 dark:text-neutral-100"
                  : "text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300",
              )}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
        {justReset && !error && (
          <p
            role="status"
            className="rounded-md bg-success-50 px-3 py-2 text-sm text-success-700 dark:bg-success-500/10 dark:text-success-500"
          >
            密码已重置，请使用新密码登录
          </p>
        )}
        <div className="flex flex-col gap-2">
          <Label htmlFor="login-identifier">
            {mode === "code" ? "手机号 / 邮箱" : "账号"}
          </Label>
          <Input
            id="login-identifier"
            ref={identifierRef}
            type="text"
            inputMode={mode === "code" ? "text" : undefined}
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            placeholder={mode === "code" ? "用于接收验证码" : "邮箱或手机号"}
            aria-invalid={Boolean(error)}
            value={identifier}
            onChange={(e) => setIdentifier(e.target.value)}
          />
        </div>

        {mode === "password" ? (
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="login-password">密码</Label>
              <Link
                href={`/forgot-password${redirect !== "/dashboard" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`}
                className="text-xs text-neutral-500 transition-colors hover:text-brand-700 dark:hover:text-brand-400"
              >
                忘记密码？
              </Link>
            </div>
            <Input
              id="login-password"
              type="password"
              required
              autoComplete="current-password"
              placeholder="••••••••"
              aria-invalid={Boolean(error)}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
        ) : (
          <div className="flex flex-col gap-2">
            <Label htmlFor="login-code">验证码</Label>
            <div className="flex gap-2">
              <Input
                id="login-code"
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                maxLength={6}
                placeholder="6 位验证码"
                aria-invalid={Boolean(error)}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))}
                className="flex-1"
              />
              <Button
                type="button"
                variant="outline"
                disabled={sending || countdown > 0 || !codeChannelReady}
                onClick={onSendCode}
                className="w-[112px] shrink-0"
              >
                {sending ? "发送中…" : countdown > 0 ? `${countdown}s 后重发` : "获取验证码"}
              </Button>
            </div>
            <p className="text-xs text-neutral-500 dark:text-neutral-400">
              未注册的手机号或邮箱验证通过后将自动创建账号
            </p>
          </div>
        )}

        {error && (
          <p
            role="alert"
            className="rounded-md bg-danger-50 px-3 py-2 text-sm text-danger-700 dark:bg-danger-500/10 dark:text-danger-500"
          >
            {error}
          </p>
        )}

        <Button type="submit" disabled={loading} className="w-full">
          {loading ? "登录中…" : mode === "password" ? "登录" : "验证并登录"}
        </Button>

        <p className="text-center text-sm text-neutral-500 dark:text-neutral-400">
          还没有账号？{" "}
          <Link
            href={`/register${redirect !== "/dashboard" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`}
            className="font-medium text-brand-700 hover:underline dark:text-brand-400"
          >
            立即注册
          </Link>
        </p>
      </form>
    </div>
  );
}
