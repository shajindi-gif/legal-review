"use client";

import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { Users, FileCheck, Activity, ShieldAlert } from "lucide-react";
import { fetchAdminStats, fetchAdminUsers } from "@/lib/api";
import { useAuthStore } from "@/lib/auth";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDateTime } from "@/lib/utils";

export default function AdminPage() {
  const token = useAuthStore((s) => s.token);
  const user = useAuthStore((s) => s.user);

  const { data: stats } = useQuery({
    queryKey: ["admin-stats"],
    queryFn: fetchAdminStats,
    enabled: !!token,
  });
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: fetchAdminUsers,
    enabled: !!token,
  });

  if (user && user.role !== "admin") {
    return (
      <div className="mx-auto flex max-w-3xl flex-col items-center gap-3 py-20 text-center">
        <ShieldAlert className="h-10 w-10 text-red-500" />
        <h1 className="text-xl font-bold text-gray-900">无访问权限</h1>
        <p className="text-sm text-gray-500">该页面仅对管理员开放。</p>
      </div>
    );
  }

  const statCards = [
    {
      icon: Users,
      label: "总用户数",
      value: stats?.total_users ?? "—",
    },
    {
      icon: FileCheck,
      label: "总审查数",
      value: stats?.total_reviews ?? "—",
    },
    {
      icon: Activity,
      label: "今日审查",
      value: stats?.today_reviews ?? "—",
    },
  ];

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">管理后台</h1>
        <p className="mt-1 text-sm text-gray-500">平台用户与审查统计概览</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {statCards.map((s) => {
          const Icon = s.icon;
          return (
            <Card key={s.label}>
              <CardHeader className="flex-row items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
                  <Icon className="h-5 w-5" />
                </div>
                <CardTitle className="text-sm font-medium text-gray-500">
                  {s.label}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <span className="text-2xl font-bold text-brand-700">
                  {s.value}
                </span>
              </CardContent>
            </Card>
          );
        })}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>用户列表</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex h-32 items-center justify-center text-sm text-gray-400">
              加载中…
            </div>
          ) : users && users.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-gray-200 text-left text-xs text-gray-500">
                    <th className="px-3 py-2 font-medium">邮箱</th>
                    <th className="px-3 py-2 font-medium">单位</th>
                    <th className="px-3 py-2 font-medium">套餐</th>
                    <th className="px-3 py-2 font-medium">角色</th>
                    <th className="px-3 py-2 font-medium">注册时间</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr
                      key={u.id}
                      className="border-b border-gray-100 last:border-0"
                    >
                      <td className="px-3 py-2 font-medium text-gray-800">
                        {u.email}
                      </td>
                      <td className="px-3 py-2 text-gray-600">
                        {u.company || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <Badge variant="secondary">{u.plan}</Badge>
                      </td>
                      <td className="px-3 py-2">
                        {u.role === "admin" ? (
                          <Badge variant="default">管理员</Badge>
                        ) : (
                          <Badge variant="outline">用户</Badge>
                        )}
                      </td>
                      <td className="px-3 py-2 text-gray-500">
                        {formatDateTime(u.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex h-32 items-center justify-center text-sm text-gray-400">
              暂无用户数据
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
