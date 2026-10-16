"use client";

import * as React from "react";
import { useRouter } from "next/navigation";
import {
  fetchAccountProfile,
  fetchSessions,
  logoutAllDevices,
  revokeSession,
  changePassword,
  updateAccountProfile,
  type AccountProfile,
  type SessionInfo,
} from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import type { User } from "@/types/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { cn } from "@/lib/utils";

type TabKey = "profile" | "security" | "preferences" | "billing";

const TABS: { key: TabKey; label: string; hint: string }[] = [
  { key: "profile", label: "基本资料", hint: "姓名、单位、联系方式" },
  { key: "security", label: "登录与安全", hint: "密码、登录设备" },
  { key: "preferences", label: "偏好设置", hint: "语言、时区" },
  { key: "billing", label: "套餐与账单", hint: "当前套餐、升级" },
];

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return iso;
  }
}

function shortDevice(ua: string | null): string {
  if (!ua) return "未知设备";
  if (/iPhone/i.test(ua)) return "iPhone";
  if (/iPad/i.test(ua)) return "iPad";
  if (/Android/i.test(ua)) return "Android 设备";
  if (/Macintosh/i.test(ua)) return "Mac 浏览器";
  if (/Windows/i.test(ua)) return "Windows 浏览器";
  if (/Linux/i.test(ua)) return "Linux 浏览器";
  return "其他设备";
}

function VerifiedMark({ verified }: { verified: boolean }) {
  return verified ? (
    <Badge variant="outline" className="text-success-700">
      已验证
    </Badge>
  ) : (
    <Badge variant="outline" className="text-neutral-400">
      未验证
    </Badge>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-1 border-b border-neutral-100 py-3 last:border-0 dark:border-neutral-800 sm:flex-row sm:items-center sm:justify-between">
      <span className="text-sm text-neutral-500 dark:text-neutral-400">{label}</span>
      <div className="flex items-center gap-2 text-sm text-neutral-900 dark:text-neutral-100">
        {children}
      </div>
    </div>
  );
}

/**
 * 用户中心（认证升级阶段 7）：Profile / Security / Preferences / Billing 四区。
 * 数据全部来自后端 /auth/account 与 /auth/sessions；此处不做任何本地鉴权判断。
 */
export function AccountCenter() {
  const router = useRouter();
  const setUser = useAuthStore((s) => s.setUser);
  const logout = useAuthStore((s) => s.logout);

  const [tab, setTab] = React.useState<TabKey>("profile");
  const [profile, setProfile] = React.useState<AccountProfile | null>(null);
  const [sessions, setSessions] = React.useState<SessionInfo[]>([]);
  const [loadError, setLoadError] = React.useState<string | null>(null);

  const reloadProfile = React.useCallback(async () => {
    try {
      const p = await fetchAccountProfile();
      setProfile(p);
      // 同步 TopBar 显示的资料；保留 store 中已有的配额字段
      const prev = useAuthStore.getState().user;
      setUser({
        ...(prev ?? { quota_daily: 0, used_today: 0 }),
        id: p.id,
        email: p.email ?? prev?.email ?? "",
        username: p.username,
        real_name: p.real_name ?? "",
        company: p.company,
        role: p.role,
        plan_tier: p.plan_tier,
        last_login_at: p.last_login_at,
      } as User);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "加载失败");
    }
  }, [setUser]);

  const reloadSessions = React.useCallback(async () => {
    try {
      setSessions(await fetchSessions());
    } catch {
      /* 列表加载失败不阻塞其他区块 */
    }
  }, []);

  React.useEffect(() => {
    void reloadProfile();
    void reloadSessions();
  }, [reloadProfile, reloadSessions]);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-6 px-4 py-8 sm:px-6">
      <header>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-neutral-900 dark:text-neutral-50">
          账户设置
        </h1>
        <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">
          管理您的资料、登录方式与安全选项
        </p>
      </header>

      <div className="flex flex-col gap-6 lg:flex-row">
        {/* 侧栏 Tab：移动端横向、桌面端纵向 */}
        <nav
          aria-label="账户设置分区"
          className="flex shrink-0 gap-1 overflow-x-auto lg:w-56 lg:flex-col"
        >
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              aria-current={tab === t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "flex flex-col items-start rounded-lg px-3 py-2 text-left transition-colors",
                tab === t.key
                  ? "bg-brand-50 text-brand-800 dark:bg-brand-500/10 dark:text-brand-300"
                  : "text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-900",
              )}
            >
              <span className="whitespace-nowrap text-sm font-medium">{t.label}</span>
              <span className="hidden text-xs text-neutral-400 lg:block">{t.hint}</span>
            </button>
          ))}
        </nav>

        <div className="min-w-0 flex-1">
          {loadError && !profile && (
            <Card>
              <CardContent className="p-6 text-sm text-danger-700">{loadError}</CardContent>
            </Card>
          )}

          {profile && tab === "profile" && (
            <ProfileSection profile={profile} onSaved={reloadProfile} />
          )}
          {profile && tab === "security" && (
            <SecuritySection
              profile={profile}
              sessions={sessions}
              onSessionsChanged={reloadSessions}
              onForceLogout={() => {
                logout();
                router.replace("/login");
              }}
            />
          )}
          {profile && tab === "preferences" && <PreferencesSection profile={profile} />}
          {profile && tab === "billing" && <BillingSection profile={profile} />}
        </div>
      </div>
    </div>
  );
}

// ============== 基本资料 ==============

function ProfileSection({
  profile,
  onSaved,
}: {
  profile: AccountProfile;
  onSaved: () => Promise<void>;
}) {
  const [realName, setRealName] = React.useState(profile.real_name ?? "");
  const [company, setCompany] = React.useState(profile.company ?? "");
  const [saving, setSaving] = React.useState(false);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    setSaving(true);
    try {
      await updateAccountProfile({ real_name: realName.trim() || undefined, company: company.trim() || undefined });
      setNotice("资料已更新");
      await onSaved();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>基本资料</CardTitle>
        <CardDescription>邮箱与手机号是登录凭证；如需变更绑定请联系客服。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-6">
        <div>
          <Row label="登录账号">
            {profile.email ?? profile.phone ?? profile.username}
            {profile.email ? <VerifiedMark verified={profile.email_verified} /> : null}
            {profile.phone ? <VerifiedMark verified={profile.phone_verified} /> : null}
          </Row>
          <Row label="用户名">{profile.username}</Row>
          <Row label="注册时间">{formatDate(profile.created_at)}</Row>
          <Row label="最近登录">{formatDate(profile.last_login_at)}</Row>
        </div>

        <form onSubmit={onSave} className="flex flex-col gap-4 border-t border-neutral-100 pt-5 dark:border-neutral-800">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="acct-name">姓名</Label>
              <Input id="acct-name" value={realName} onChange={(e) => setRealName(e.target.value)} placeholder="您的姓名" />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="acct-company">单位</Label>
              <Input id="acct-company" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="如：XX县司法局" />
            </div>
          </div>
          {notice && (
            <p role="status" className="text-sm text-success-700 dark:text-success-500">
              {notice}
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger-700 dark:text-danger-500">
              {error}
            </p>
          )}
          <div>
            <Button type="submit" disabled={saving}>
              {saving ? "保存中…" : "保存修改"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ============== 登录与安全 ==============

function SecuritySection({
  profile,
  sessions,
  onSessionsChanged,
  onForceLogout,
}: {
  profile: AccountProfile;
  sessions: SessionInfo[];
  onSessionsChanged: () => Promise<void>;
  onForceLogout: () => void;
}) {
  return (
    <div className="flex flex-col gap-6">
      <PasswordCard hasPassword={profile.has_password} onForceLogout={onForceLogout} />
      <SessionsCard sessions={sessions} onChanged={onSessionsChanged} />
    </div>
  );
}

function PasswordCard({
  hasPassword,
  onForceLogout,
}: {
  hasPassword: boolean;
  onForceLogout: () => void;
}) {
  const [current, setCurrent] = React.useState("");
  const [next, setNext] = React.useState("");
  const [confirm, setConfirm] = React.useState("");
  const [saving, setSaving] = React.useState(false);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const valid = next.length >= 8 && /[a-zA-Z]/.test(next) && /\d/.test(next) && next === confirm;

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNotice(null);
    if (!valid) {
      setError("新密码至少 8 位且包含字母和数字，两次输入需一致");
      return;
    }
    setSaving(true);
    try {
      const res = await changePassword({ current_password: current, new_password: next });
      setNotice(`密码已更新，其他 ${res.revoked_other_sessions} 台设备已退出登录`);
      setCurrent("");
      setNext("");
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "密码修改失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>登录密码</CardTitle>
        <CardDescription>
          {hasPassword
            ? "修改密码后，其他设备将自动退出登录（当前设备保留）。"
            : "您当前使用验证码登录，设置密码后可使用账号密码登录。"}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4">
          <div className="flex flex-col gap-2">
            <Label htmlFor="pw-current">当前密码</Label>
            <Input
              id="pw-current"
              type="password"
              required
              autoComplete="current-password"
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="pw-next">新密码</Label>
            <Input
              id="pw-next"
              type="password"
              required
              autoComplete="new-password"
              placeholder="至少 8 位，含字母和数字"
              value={next}
              onChange={(e) => setNext(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-2">
            <Label htmlFor="pw-confirm">确认新密码</Label>
            <Input
              id="pw-confirm"
              type="password"
              required
              autoComplete="new-password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
            />
          </div>
          {notice && (
            <p role="status" className="text-sm text-success-700 dark:text-success-500">
              {notice}
            </p>
          )}
          {error && (
            <p role="alert" className="text-sm text-danger-700 dark:text-danger-500">
              {error}
            </p>
          )}
          <div>
            <Button type="submit" disabled={saving}>
              {saving ? "提交中…" : "更新密码"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

function SessionsCard({
  sessions,
  onChanged,
}: {
  sessions: SessionInfo[];
  onChanged: () => Promise<void>;
}) {
  const [revoking, setRevoking] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  async function onRevoke(id: string) {
    setError(null);
    setRevoking(id);
    try {
      await revokeSession(id);
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "撤销失败");
    } finally {
      setRevoking(null);
    }
  }

  async function onRevokeAll() {
    setError(null);
    try {
      await logoutAllDevices();
      await onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    }
  }

  return (
    <Card>
      <CardHeader className="flex-row items-start justify-between space-y-0">
        <div className="flex flex-col gap-1.5">
          <CardTitle>登录设备</CardTitle>
          <CardDescription>已登录的会话列表；撤销后对应设备需重新登录。</CardDescription>
        </div>
        {sessions.length > 0 && (
          <Button variant="outline" onClick={onRevokeAll} className="shrink-0">
            退出所有设备
          </Button>
        )}
      </CardHeader>
      <CardContent>
        {sessions.length === 0 ? (
          <p className="text-sm text-neutral-500">暂无活跃会话记录</p>
        ) : (
          <ul className="flex flex-col divide-y divide-neutral-100 dark:divide-neutral-800">
            {sessions.map((s) => (
              <li key={s.id} className="flex items-center justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
                    {shortDevice(s.user_agent)}
                  </p>
                  <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">
                    登录于 {formatDate(s.issued_at)} · 到期 {formatDate(s.expires_at)}
                    {s.ip_address ? ` · IP ${s.ip_address}` : ""}
                  </p>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={revoking === s.id}
                  onClick={() => onRevoke(s.id)}
                  className="shrink-0"
                >
                  {revoking === s.id ? "撤销中…" : "下线"}
                </Button>
              </li>
            ))}
          </ul>
        )}
        {error && (
          <p role="alert" className="mt-3 text-sm text-danger-700 dark:text-danger-500">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ============== 偏好设置 ==============

function PreferencesSection({ profile }: { profile: AccountProfile }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>偏好设置</CardTitle>
        <CardDescription>语言与时区当前跟随账户默认值，更多选项即将开放。</CardDescription>
      </CardHeader>
      <CardContent>
        <Row label="界面语言">
          <Badge variant="outline">
            {profile.locale === "zh-CN" || !profile.locale ? "简体中文" : profile.locale}
          </Badge>
        </Row>
        <Row label="时区">
          <Badge variant="outline">{profile.timezone || "Asia/Shanghai"}</Badge>
        </Row>
      </CardContent>
    </Card>
  );
}

// ============== 套餐与账单 ==============

const PLAN_LABEL: Record<string, string> = {
  free: "体验版",
  pro: "专业版",
  enterprise: "企业版",
};

function BillingSection({ profile }: { profile: AccountProfile }) {
  const router = useRouter();
  return (
    <Card>
      <CardHeader>
        <CardTitle>套餐与账单</CardTitle>
        <CardDescription>查看当前套餐权益，或升级获得更多审查额度。</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Row label="当前套餐">
          <Badge variant="secondary">{PLAN_LABEL[profile.plan_tier] ?? profile.plan_tier}</Badge>
        </Row>
        <div className="flex items-center justify-between rounded-lg bg-neutral-50 p-4 dark:bg-neutral-900">
          <div>
            <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">
              需要更多额度？
            </p>
            <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">
              升级到专业版，解锁更高审查配额与优先队列
            </p>
          </div>
          <Button onClick={() => router.push("/pricing")}>查看套餐</Button>
        </div>
      </CardContent>
    </Card>
  );
}
