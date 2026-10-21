import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight, Check, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageViewTracker } from "@/components/analytics/PageViewTracker";
import { siteInfo } from "@/lib/site";

export const metadata: Metadata = {
  title: "司法局规范性文件合法性审核方案 | 智审 · LegalReview",
  description:
    "面向司法局与政府法制机构的行政规范性文件合法性审核方案：主体、内容、程序三查，全国/上海市/徐汇区分层规则包，输出标准结论与 Word 归档意见书。",
  keywords: [
    "规范性文件合法性审核",
    "司法局合法性审查",
    "行政规范性文件",
    "法制审核",
    "合法性审查意见书",
  ],
  alternates: { canonical: `https://${siteInfo.domain}/solutions/sifaju` },
  openGraph: {
    title: "司法局规范性文件合法性审核方案 | 智审 · LegalReview",
    description:
      "11 节点审查流水线 + 地域分层规则包，输出可归档的合法性审查意见书。",
    url: `https://${siteInfo.domain}/solutions/sifaju`,
    siteName: siteInfo.name,
    type: "website",
  },
};

const painPoints = [
  {
    title: "审核维度多，容易漏项",
    desc: "主体权限、内容合规、制定程序三类审查横跨多部上位法，人工逐条比对易遗漏关键依据。",
  },
  {
    title: "时限紧，往返沟通成本高",
    desc: "送审稿质量参差，退回补正反复拉长周期，审查人力被大量基础核对占用。",
  },
  {
    title: "过程留痕与归档压力",
    desc: "每份意见都需要条款级依据与可追溯记录，纸质流转难以支撑复核与备查。",
  },
];

const capabilities = [
  {
    title: "三查闭环",
    desc: "主体审查 → 内容审查 → 程序审查，覆盖越权设定、许可处罚、公平竞争等常见风险点。",
  },
  {
    title: "地域分层规则包",
    desc: "全国 / 上海市 / 徐汇区三级规则分层叠加，按送审稿适用地域命中对应审核要点。",
  },
  {
    title: "标准结论结构",
    desc: "输出 10 段标准结论与四类判定；程序材料缺失仅标注「材料不足」，不直接认定为程序违法。",
  },
  {
    title: "条款级依据可追溯",
    desc: "每条风险均附法规名称、条款编号与引用原文，证据核验节点逐条比对。",
  },
  {
    title: "可归档交付物",
    desc: "在线查看结构化风险清单，一键导出 Word 意见书，便于内部复核与卷宗归档。",
  },
  {
    title: "数据不外传",
    desc: "本地向量检索与私有化部署选项，送审材料不用于审查之外的用途。",
  },
];

const flow = [
  { no: "01", title: "上传送审稿", desc: "支持 PDF / Word / TXT / Markdown，自动解析正文与结构。" },
  { no: "02", title: "自动审查", desc: "11 节点流水线完成解析、分类、检索、三查、风险评估与证据核验。" },
  { no: "03", title: "人工复核", desc: "审查人员在风险清单上确认或修改，反馈回流用于规则与 Prompt 迭代。" },
  { no: "04", title: "出具意见书", desc: "生成标准结论并导出 Word，归档留存全流程 trace。" },
];

const faqs = [
  {
    q: "程序材料缺失时会直接认定程序违法吗？",
    a: "不会。对缺少起草说明、征求意见、合法性审核等材料的送审稿，系统仅标注「材料不足」，由审查人员补充材料后再判断，避免误判。",
  },
  {
    q: "规则包覆盖哪些地域？",
    a: "当前按全国、上海市、徐汇区三层规则组织，按送审稿适用地域叠加命中；其他地区规则需另行配置。",
  },
  {
    q: "审查结果可以直接作为最终意见吗？",
    a: "系统输出的是审查辅助结论，须经审查人员复核确认。AI 不替代法定审查责任。",
  },
];

export default function SifajuSolutionPage() {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      <PageViewTracker page="solutions/sifaju" />

      <header className="sticky top-0 z-30 border-b border-neutral-200/60 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
              法
            </div>
            <span className="text-base font-semibold tracking-tight text-neutral-900">
              智审 <span className="font-normal text-neutral-500">·</span> LegalReview
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/pricing" className="text-sm text-neutral-600 hover:text-neutral-900">
              定价
            </Link>
            <Link href="/register">
              <Button size="sm">免费体验</Button>
            </Link>
          </div>
        </div>
      </header>

      <main className="flex-1">
        {/* Hero */}
        <section className="border-b border-neutral-200/60 bg-[#fafaf9]">
          <div className="mx-auto max-w-6xl px-6 py-16 sm:py-20">
            <span className="inline-flex items-center gap-2 rounded-full border border-neutral-200/70 bg-white px-3.5 py-1.5 text-xs font-medium text-neutral-600">
              <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
              面向司法局 / 政府法制机构
            </span>
            <h1 className="mt-6 max-w-3xl font-display text-4xl font-semibold leading-tight tracking-tight text-neutral-900 sm:text-5xl">
              行政规范性文件
              <br className="hidden sm:block" />
              合法性审核方案
            </h1>
            <p className="mt-5 max-w-2xl text-base leading-relaxed text-neutral-600 sm:text-lg">
              把主体、内容、程序三查交给 11 节点审查流水线，输出条款级依据与标准结论，
              审查人员只需在风险清单上做确认与复核。
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-4">
              <Link href="/register">
                <Button size="lg">
                  免费体验 2 次完整审查
                  <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </Link>
              <Link href="/pricing">
                <Button size="lg" variant="outline">
                  查看方案与定价
                </Button>
              </Link>
            </div>
          </div>
        </section>

        {/* 痛点 */}
        <section className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="font-display text-2xl font-semibold tracking-tight text-neutral-900">
            传统审核方式的三个瓶颈
          </h2>
          <div className="mt-8 grid gap-6 md:grid-cols-3">
            {painPoints.map((p) => (
              <div key={p.title} className="border-t border-neutral-200/70 pt-5">
                <h3 className="text-base font-medium text-neutral-900">{p.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-neutral-600">{p.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* 能力 */}
        <section className="border-t border-neutral-200/60 bg-[#fafaf9]">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="font-display text-2xl font-semibold tracking-tight text-neutral-900">
              方案能力
            </h2>
            <div className="mt-8 grid gap-6 md:grid-cols-2 lg:grid-cols-3">
              {capabilities.map((c) => (
                <Card key={c.title} className="border-neutral-200/70 shadow-none">
                  <CardHeader className="pb-2">
                    <CardTitle className="flex items-center gap-2 text-base">
                      <Check className="h-4 w-4 text-brand-600" />
                      {c.title}
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <p className="text-sm leading-relaxed text-neutral-600">{c.desc}</p>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </section>

        {/* 流程 */}
        <section className="mx-auto max-w-6xl px-6 py-16">
          <h2 className="font-display text-2xl font-semibold tracking-tight text-neutral-900">
            审核流程
          </h2>
          <div className="mt-8 grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
            {flow.map((f) => (
              <div key={f.no}>
                <span className="font-display text-sm font-semibold tabular-nums text-neutral-300">
                  {f.no}
                </span>
                <h3 className="mt-2 text-base font-medium text-neutral-900">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-neutral-600">{f.desc}</p>
              </div>
            ))}
          </div>
        </section>

        {/* FAQ */}
        <section className="border-t border-neutral-200/60 bg-[#fafaf9]">
          <div className="mx-auto max-w-6xl px-6 py-16">
            <h2 className="font-display text-2xl font-semibold tracking-tight text-neutral-900">
              常见问题
            </h2>
            <div className="mt-8 max-w-3xl divide-y divide-neutral-200/60 border-t border-neutral-200/60">
              {faqs.map((f, i) => (
                <div key={f.q} className="flex gap-5 py-6">
                  <span className="shrink-0 pt-0.5 font-display text-sm font-semibold tabular-nums text-neutral-300">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <h3 className="text-base font-medium text-neutral-900">{f.q}</h3>
                    <p className="mt-2 text-sm leading-relaxed text-neutral-600">{f.a}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="mx-auto max-w-6xl px-6 py-16 text-center">
          <h2 className="font-display text-2xl font-semibold tracking-tight text-neutral-900">
            先用一份真实的送审稿试一次
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-neutral-600">
            注册即可获得 2 次完整审查体验，无需信用卡。
          </p>
          <div className="mt-6 flex justify-center">
            <Link href="/register">
              <Button size="lg">
                免费开始
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            </Link>
          </div>
        </section>
      </main>

      <footer className="bg-neutral-950 py-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-4 px-6 text-center sm:flex-row sm:justify-between sm:text-left">
          <p className="text-xs text-neutral-500">
            © {new Date().getFullYear()} {siteInfo.name}
            {siteInfo.legalEntityName ? ` · ${siteInfo.legalEntityName}` : ""}
          </p>
          <nav className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-neutral-400">
            <Link href="/" className="hover:text-neutral-100">
              首页
            </Link>
            <Link href="/pricing" className="hover:text-neutral-100">
              定价
            </Link>
            <Link href="/privacy" className="hover:text-neutral-100">
              隐私政策
            </Link>
            <Link href="/terms" className="hover:text-neutral-100">
              服务条款
            </Link>
            {siteInfo.icpRecord && <span>{siteInfo.icpRecord}</span>}
          </nav>
        </div>
      </footer>
    </div>
  );
}
