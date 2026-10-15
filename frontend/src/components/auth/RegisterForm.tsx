"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import { register } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { track } from "@/lib/analytics";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent } from "@/components/ui/card";

export function RegisterForm() {
  const router = useRouter();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = React.useState("");
  const [password, setPassword] = React.useState("");
  const [realName, setRealName] = React.useState("");
  const [company, setCompany] = React.useState("");
  const [agreed, setAgreed] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const res = await register(
        email.trim(),
        password,
        company.trim() || undefined,
        realName.trim() || undefined,
      );
      setAuth(res.access_token, res.user);
      // 商业化埋点：注册成功
      track("signup_submit");
      router.replace("/dashboard");
    } catch (err) {
      setError(err instanceof Error ? err.message : "注册失败");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card className="w-full max-w-md shadow-sm">
      <CardContent className="p-6 sm:p-8">
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="r-email">邮箱</Label>
            <Input
              id="r-email"
              type="email"
              required
              autoComplete="email"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="r-password">密码</Label>
            <Input
              id="r-password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              placeholder="至少 8 位"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="r-realname">姓名（选填）</Label>
            <Input
              id="r-realname"
              type="text"
              placeholder="您的真实姓名"
              value={realName}
              onChange={(e) => setRealName(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="r-company">单位名称（选填）</Label>
            <Input
              id="r-company"
              type="text"
              placeholder="如：XX县司法局"
              value={company}
              onChange={(e) => setCompany(e.target.value)}
            />
          </div>
          {error && (
            <p className="text-sm text-red-600" role="alert">
              {error}
            </p>
          )}
          {/* 个保法合规：注册前必须明示同意用户协议与隐私政策 */}
          <label className="flex items-start gap-2 text-sm leading-relaxed text-neutral-600">
            <input
              type="checkbox"
              required
              checked={agreed}
              onChange={(e) => setAgreed(e.target.checked)}
              className="mt-0.5 h-4 w-4 flex-shrink-0 accent-brand-600"
            />
            <span>
              我已阅读并同意
              <a href="/terms" target="_blank" className="mx-0.5 font-medium text-brand-700 hover:underline">
                《服务条款》
              </a>
              与
              <a href="/privacy" target="_blank" className="mx-0.5 font-medium text-brand-700 hover:underline">
                《隐私政策》
              </a>
            </span>
          </label>
          <Button type="submit" disabled={loading || !agreed} className="w-full">
            {loading ? "注册中…" : "注册并开始"}
          </Button>
          <p className="text-center text-sm text-neutral-500">
            已有账号？{" "}
            <a href="/login" className="font-medium text-brand-700 hover:underline">
              去登录
            </a>
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
