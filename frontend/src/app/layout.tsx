import type { Metadata } from "next";
import { Geist, Geist_Mono, Noto_Serif_SC } from "next/font/google";
import "./globals.css";
import { Providers } from "@/components/providers";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// 衬线展示字体：中文衬线标题营造法律文书的正式感（仅用于大标题 / 区块标题，正文仍为无衬线）
const notoSerifSC = Noto_Serif_SC({
  weight: ["600", "700"],
  subsets: ["latin"],
  variable: "--font-noto-serif-sc",
  display: "swap",
});

// 强制全站动态渲染（SSR）：CSP nonce 方案要求每次请求随机 nonce，
// 静态预渲染的页面无法携带 per-request nonce，会与 script-src 的 nonce 白名单冲突。
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "智审 · 行政规范性文件智能合法性审查",
  description:
    "基于 11 节点 LangGraph + DeepSeek V4 + BGE-M3 本地检索 + 河南省法规库的智能合法性审查 SaaS 平台。",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html
      lang="zh-CN"
      className={`${geistSans.variable} ${geistMono.variable} ${notoSerifSC.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-gray-50 text-gray-900">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
