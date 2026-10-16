"use client";

import * as React from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { registerPassword } from "@/lib/api";
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

function passwordIssues(pw: string): string[] {
  const issues: string[] = [];
  if (pw.length < 8) issues.push("至少 8 位");
  if (pw.length > 128) issues.push("不超过 128 位");
  if (!/[a-zA-Z]/.test(pw)) issues.push("需包含字母");
  if (!/\d/.test(pw)) issues.push("需包含数字");
  return issues;
}

/**
 * 注册表单（认证升级 P0，本地密码注册）：
 * - 渐进注册：邮箱 + 密码必填，姓名 / 单位选填（降低摩擦，后续在 /account 补全）
 * - 个保法合规：agreed_terms 明示勾选，时间戳落库
 * - 埋点：signup_start（首次输入）/ signup_success
 */
export function RegisterForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = React.useMemo(
    () => sanitizeRedirect(searchParams.get("redirect")),
    [searchParams],
  );
  const setAuth = useAuthStore((s) => s.setAuth);

  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [realName, setRealName] = React.useState("");
  const [company, setCompany] = React.useState("");
  const [agreed, setAgreed] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const startedRef = React.useRef(false);

  const issues = passwordIssues(password);
  const passwordValid = password.length > 0 && issues.length === 0;

  // 低摩擦埋点：用户开始填写即记 signup_start（每次页面加载只记一次）
  function markStarted() {
    if (startedRef.current) return;
    startedRef.current = true;
    track("signup_start");
  }

  // 页面曝光（注册漏斗第一步）
  React.useEffect(() => {
    track("auth_page_view", { page: "register" });
  }, []);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (issues.length > 0) {
      setError(`密码要求：${issues.join("、")}`);
      return;
    }
    if (!agreed) {
      setError("请先阅读并同意《服务条款》与《隐私政策》");
      return;
    }
    setLoading(true);
    try {
      const res = await registerPassword({
        email: email.trim(),
        password,
        real_name: realName.trim() || undefined,
        company: company.trim() || undefined,
        agreed_terms: true,
      });
      setAuth(res.access_token, res.user);
      track("signup_success", { has_company: Boolean(company.trim()) });
      router.replace(redirect);
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败，请稍后重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-2">
        <Label htmlFor="r-email">工作邮箱</Label>
        <Input
          id="r-email"
          type="email"
          required
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          placeholder="you@company.com"
          aria-invalid={Boolean(error)}
          value={email}
          onFocus={markStarted}
          onChange={(e) => setEmail(e.target.value)}
        />
      </div>

      <div className="flex flex-col gap-2">
        <Label htmlFor="r-password">设置密码</Label>
        <Input
          id="r-password"
          type="password"
          required
          autoComplete="new-password"
          placeholder="至少 8 位，含字母和数字"
          aria-invalid={Boolean(error)}
          aria-describedby="r-password-hint"
          value={password}
          onFocus={markStarted}
          onChange={(e) => setPassword(e.target.value)}
        />
        {password.length > 0 && !passwordValid && (
          <p id="r-password-hint" className="text-xs text-warning-700 dark:text-warning-500">
            {issues.join("、")}
          </p>
        )}
      </div>

      {/* 选填字段：渐进注册，降低首屏摩擦 */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label htmlFor="r-realname">
            姓名 <span className="font-normal text-neutral-400">（选填）</span>
          </Label>
          <Input
            id="r-realname"
            type="text"
            autoComplete="name"
            placeholder="您的姓名"
            value={realName}
            onFocus={markStarted}
            onChange={(e) => setRealName(e.target.value)}
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label htmlFor="r-company">
            单位 <span className="font-normal text-neutral-400">（选填）</span>
          </Label>
          <Input
            id="r-company"
            type="text"
            autoComplete="organization"
            placeholder="如：XX县司法局"
            value={company}
            onFocus={markStarted}
            onChange={(e) => setCompany(e.target.value)}
          />
        </div>
      </div>

      {/* 个保法合规：注册前必须明示同意用户协议与隐私政策 */}
      <label className="flex items-start gap-2 text-sm leading-relaxed text-neutral-600 dark:text-neutral-400">
        <input
          type="checkbox"
          required
          checked={agreed}
          onChange={(e) => setAgreed(e.target.checked)}
          className="mt-0.5 h-4 w-4 flex-shrink-0 accent-brand-600"
        />
        <span>
          我已阅读并同意
          <Link
            href="/terms"
            target="_blank"
            className="mx-0.5 font-medium text-brand-700 hover:underline dark:text-brand-400"
          >
            《服务条款》
          </Link>
          与
          <Link
            href="/privacy"
            target="_blank"
            className="mx-0.5 font-medium text-brand-700 hover:underline dark:text-brand-400"
          >
            《隐私政策》
          </Link>
        </span>
      </label>

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

      <Button type="submit" disabled={loading || !agreed} className="w-full">
        {loading ? "注册中…" : "注册并开始"}
      </Button>

      <p className="text-center text-sm text-neutral-500 dark:text-neutral-400">
        已有账号？{" "}
        <Link
          href={`/login${redirect !== "/dashboard" ? `?redirect=${encodeURIComponent(redirect)}` : ""}`}
          className="font-medium text-brand-700 hover:underline dark:text-brand-400"
        >
          去登录
        </Link>
      </p>
    </form>
  );
}
