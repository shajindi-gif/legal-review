import Link from "next/link";
import { ShieldCheck, ArrowRight, Check, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { siteInfo } from "@/lib/site";

const steps = [
  {
    no: "01",
    title: "上传文件",
    desc: "支持 PDF / Word / TXT / Markdown，自动解析文本与结构。",
  },
  {
    no: "02",
    title: "智能审查",
    desc: "11 节点流水线完成主体、内容、程序三查，附风险评估与证据核验。",
  },
  {
    no: "03",
    title: "出具意见书",
    desc: "输出结构化风险清单、法规依据与修改建议，可导出归档。",
  },
];

const features = [
  {
    title: "11 节点 LangGraph 流水线",
    desc: "文档解析 → 分类 → 检索 → 主体/内容/程序审查 → 风险评估 → 证据核验 → 报告生成 → 人工复核，全流程可追溯。",
  },
  {
    title: "DeepSeek V4 推理引擎",
    desc: "深度推理模型驱动多 Agent 协同审查，输出结构化风险清单与修改建议。",
  },
  {
    title: "BGE-M3 本地向量检索",
    desc: "私有化部署嵌入模型，法规库检索不外传数据，满足政务合规要求。",
  },
  {
    title: "河南省法规库",
    desc: "覆盖省、市、县三级地方性法规与规范性文件，审查依据精确到条款。",
  },
];

// 额度文案必须与后端一致：FREE_TRIAL_LIMIT=2（累计体验 2 次，非每日重置）。
// 价格与 backend/app/core/constants.py 的 PLAN_PRICING_CENTS 保持同步（299/月、1999/月）。
const plans = [
  {
    name: "体验版",
    price: "免费",
    unit: "",
    desc: "先试后买，完整流程",
    features: ["免费体验 2 次完整审查", "基础法规库（国家法律 + 行政法规）", "标准审查报告在线查看", "无需信用卡，注册即用"],
    cta: "免费开始",
    href: "/register",
    highlight: false,
  },
  {
    name: "专业版",
    price: "¥299",
    unit: "/月",
    desc: "适合县级司法局日常审查",
    features: [
      "无限审查次数",
      "全量法规库（含地方性法规）",
      "深度审查报告 + 修改建议",
      "优先支持（工作日 8h 响应）",
    ],
    cta: "查看套餐",
    href: "/pricing",
    highlight: true,
  },
  {
    name: "企业版",
    price: "¥1999",
    unit: "/月",
    desc: "适合多部门协同与定制",
    features: [
      "无限审查次数",
      "全量法规库 + 自定义法规",
      "团队账号（最多 50 人）",
      "私有化部署支持",
    ],
    cta: "联系销售",
    href: "/pricing",
    highlight: false,
  },
];

// 意见书预览区的三条卖点：只复述既有事实（条款引用、全程留痕、人工复核、导出归档）。
const docPoints = [
  {
    title: "条款级风险定位",
    desc: "每条意见对应文件原文的具体条款，逐条可核对。",
  },
  {
    title: "法规依据引用",
    desc: "引用国家法律、行政法规与地方性法规库的具体条文，精确到条款。",
  },
  {
    title: "全程留痕 · 人工复核",
    desc: "审查过程全程留痕，意见书支持导出归档，由法制审核人员复核确认。",
  },
];

// FAQ：只承诺已实现的事实（不自动扣款来自订单一次性支付模型；退款政策未上线不承诺）。
const faqs = [
  {
    q: "AI 的审查结论可以直接作为最终意见吗？",
    a: "不可以。系统出具的是审查初稿与风险提示，最终审查意见必须由法制审核人员复核确认。系统全程留痕，每条结论附法规条款依据，支持逐条核对。",
  },
  {
    q: "审查依据的法规是哪些？",
    a: "内置国家法律、行政法规与地方性法规库，覆盖省、市、县三级规范性文件。每条审查结论附具体条款引用，可点击核对。",
  },
  {
    q: "免费体验包含什么？",
    a: "注册即享 2 次完整审查体验（含全部审查节点与报告在线查看），无需绑定任何支付方式。",
  },
  {
    q: "如何付费？",
    a: "支持支付宝在线支付，支付成功即时开通。企业版采购与开票事宜请通过页脚联系方式咨询。",
  },
  {
    q: "到期后会自动扣款吗？",
    a: "不会。套餐按订单一次性支付，到期后不自动扣费，需要时重新订购即可。",
  },
  {
    q: "我的文件数据如何处理？",
    a: "文件仅用于完成本次审查，不用于其他用途；具体数据处理方式见《隐私政策》。",
  },
];

/** 文档骨架线条：模拟意见书正文排版（纯装饰，aria-hidden）。 */
function SkeletonLines({ count }: { count: number }) {
  const widths = ["w-full", "w-11/12", "w-full", "w-10/12", "w-3/4"];
  return (
    <div aria-hidden className="space-y-2.5">
      {widths.slice(0, count).map((w, i) => (
        <div key={i} className={`h-1.5 rounded-full bg-neutral-200/70 ${w}`} />
      ))}
    </div>
  );
}

/** 审查意见书仿真文档卡：全静态示例，页眉编号与风险条目均为示例格式，非真实客户数据。 */
function DocPreview({ compact = false }: { compact?: boolean }) {
  return (
    <figure className="relative">
      {/* 右侧角标：强调条款级依据可追溯 */}
      <span className="absolute -top-2.5 right-5 z-10 rounded-full border border-neutral-200/70 bg-white px-2.5 py-0.5 text-[10px] font-medium tracking-wide text-neutral-400">
        条款级依据 · 可追溯
      </span>
      <div className="overflow-hidden rounded-lg border border-neutral-200/70 bg-white shadow-[0_16px_48px_-16px_rgba(15,23,42,0.18)]">
        {/* 模拟页眉：文书标题 + 编号（示例格式） */}
        <div className="border-b border-neutral-200/60 px-6 pb-4 pt-6 text-center">
          <p className="font-display text-base font-semibold tracking-wide text-neutral-900 sm:text-lg">
            行政规范性文件合法性审查意见书
          </p>
          <p className="mt-1.5 text-[11px] tabular-nums text-neutral-400">
            编号 沪衍策审〔2026〕第 001 号（示例格式）
          </p>
        </div>
        {/* 模拟正文：骨架线条 + 一条真实格式的风险条目示例 */}
        <div className="space-y-5 px-6 py-6">
          <SkeletonLines count={2} />
          <div className="rounded-md border border-warning-100 bg-warning-50 px-3.5 py-3">
            <p className="flex items-start gap-1.5 text-xs font-medium leading-relaxed text-warning-700">
              <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              部分条款设定行政许可，未引用上位法依据
            </p>
            <p className="mt-1.5 pl-5 text-xs leading-relaxed text-neutral-500">
              依据《行政许可法》第十七条
            </p>
          </div>
          <SkeletonLines count={2} />
          {!compact && <SkeletonLines count={2} />}
          {/* 完整版底部：三查维度 + 示例声明 */}
          {!compact && (
            <div className="flex flex-wrap items-center gap-x-5 gap-y-2 border-t border-neutral-200/60 pt-4">
              {["主体审查", "内容审查", "程序审查"].map((t) => (
                <span key={t} className="inline-flex items-center gap-1.5 text-[11px] text-neutral-500">
                  <Check className="h-3 w-3 text-success-600" />
                  {t}
                </span>
              ))}
              <span className="ml-auto text-[10px] text-neutral-300">示例文档 · 非真实数据</span>
            </div>
          )}
        </div>
      </div>
    </figure>
  );
}

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* 顶栏 */}
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
          <nav className="hidden items-center gap-7 text-sm text-neutral-600 md:flex">
            <a href="#features" className="hover:text-neutral-900">核心能力</a>
            <a href="#pricing" className="hover:text-neutral-900">定价</a>
          </nav>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-neutral-600 hover:text-neutral-900">
              登录
            </Link>
            <Link href="/register">
              <Button size="sm">免费开始</Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero：桌面端左文右「意见书预览卡」，移动端上下堆叠 */}
      <section className="relative">
        <div className="mx-auto grid max-w-6xl items-center gap-12 px-6 pb-20 pt-14 sm:pt-20 lg:grid-cols-[1.05fr_0.95fr] lg:gap-16">
          <div>
            <span className="inline-flex items-center gap-2 rounded-full border border-neutral-200/70 bg-white px-3.5 py-1.5 text-xs font-medium text-neutral-600">
              <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
              行政规范性文件 · 智能合法性审查
            </span>
            <h1 className="mt-6 font-display text-4xl font-semibold leading-[1.2] tracking-tight text-neutral-900 sm:text-5xl">
              行政规范性文件
              <br className="hidden sm:block" />
              <span className="text-brand-600">智能合法性审查</span>
            </h1>
            <p className="mt-5 max-w-xl text-base leading-relaxed text-neutral-600 sm:text-lg">
              自动完成主体、内容、程序三查，每条结论附法规条款依据；审查过程全程留痕，支持人工复核。
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Link href="/register">
                <Button
                  size="lg"
                  className="w-full rounded-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg sm:w-auto"
                >
                  免费开始审查 <ArrowRight className="h-4 w-4" />
                </Button>
              </Link>
              <Link href="/login">
                <Button
                  size="lg"
                  variant="outline"
                  className="w-full rounded-xl transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg sm:w-auto"
                >
                  登录控制台
                </Button>
              </Link>
            </div>
            {/* 信任行：国办 115 号文依据（链接与措辞保持原文） */}
            <div className="mt-8 flex">
              <p className="inline-flex flex-wrap items-center gap-x-1.5 gap-y-1 rounded-full border border-neutral-200/70 bg-white px-4 py-2 text-xs leading-relaxed text-neutral-500">
                <ShieldCheck className="h-3.5 w-3.5 shrink-0 text-brand-600" />
                <span>依据国办发〔2018〕115号</span>
                <a
                  href="https://www.gov.cn/zhengce/zhengceku/2018-12/20/content_5350427.htm"
                  target="_blank"
                  rel="noreferrer"
                  className="font-medium text-brand-700 hover:underline"
                >
                  《关于全面推行行政规范性文件合法性审核机制的指导意见》
                </a>
                <span>设计 · 结论均附法规依据 · 人工复核兜底</span>
              </p>
            </div>
          </div>
          {/* 视觉锚：意见书预览卡（缩小版示例） */}
          <div className="lg:pl-4">
            <DocPreview compact />
            <p className="mt-3 text-center text-[11px] text-neutral-400">示例文档 · 非真实客户数据</p>
          </div>
        </div>
      </section>

      {/* 三步流程：编号纵列 + 左侧细竖线的时间轴排版 */}
      <section className="border-t border-neutral-200/60 bg-[#fafaf9]">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-neutral-400">
            从文件到意见书
          </p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-neutral-900">
            三步完成审查
          </h2>
          <div className="relative mx-auto mt-14 max-w-3xl">
            <ol>
              {steps.map((s, i) => (
                <li key={s.no} className="relative flex gap-6 sm:gap-10">
                  {/* 大号衬线编号 */}
                  <span className="w-12 shrink-0 pt-1 text-right font-display text-3xl font-semibold leading-none tabular-nums tracking-tight text-neutral-300 sm:w-16">
                    {s.no}
                  </span>
                  <div
                    className={`relative flex-1 border-l border-neutral-200/60 pl-8 sm:pl-10 ${
                      i < steps.length - 1 ? "pb-14" : "pb-2"
                    }`}
                  >
                    {/* 竖线节点 */}
                    <span
                      aria-hidden
                      className="absolute -left-[5px] top-2 h-2.5 w-2.5 rounded-full bg-neutral-900"
                    />
                    <h3 className="text-lg font-semibold text-neutral-900">{s.title}</h3>
                    <p className="mt-2 max-w-xl text-sm leading-relaxed text-neutral-600">{s.desc}</p>
                  </div>
                </li>
              ))}
            </ol>
          </div>
        </div>
      </section>

      {/* 审查意见书预览：全页核心产品展示（示例内容已标注） */}
      <section className="bg-white">
        <div className="mx-auto max-w-6xl px-6 py-20 sm:py-24">
          <div className="grid items-center gap-12 lg:grid-cols-2 lg:gap-16">
            <div>
              <p className="text-xs font-medium uppercase tracking-[0.2em] text-neutral-400">
                输出示例
              </p>
              <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-neutral-900">
                审查意见书预览
              </h2>
              <p className="mt-4 max-w-lg text-base leading-relaxed text-neutral-600">
                每份文件审查完成后，系统输出结构化的合法性审查意见书：风险条目对应原文具体条款，法规依据精确到条文，可直接用于人工复核与归档。
              </p>
              <ul className="mt-8 space-y-5">
                {docPoints.map((p) => (
                  <li key={p.title} className="flex items-start gap-3">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                    <div>
                      <p className="text-sm font-medium text-neutral-900">{p.title}</p>
                      <p className="mt-1 max-w-md text-sm leading-relaxed text-neutral-600">{p.desc}</p>
                    </div>
                  </li>
                ))}
              </ul>
            </div>
            <div>
              <DocPreview />
              <p className="mt-3 text-center text-[11px] text-neutral-400">示例文档 · 非真实客户数据</p>
            </div>
          </div>
        </div>
      </section>

      {/* 核心能力：两列不对称清单（无图标，hover 划过 brand 左边框） */}
      <section id="features" className="scroll-mt-20 border-t border-neutral-200/60 bg-[#fafaf9]">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-neutral-400">
            平台能力
          </p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-neutral-900">
            核心能力
          </h2>
          <p className="mt-3 max-w-lg text-base leading-relaxed text-neutral-600">
            面向合法性审查场景的专业技术底座
          </p>
          <div className="mt-10 grid gap-x-16 md:grid-cols-2">
            <div className="flex flex-col">
              {features.slice(0, 2).map((f) => (
                <div
                  key={f.title}
                  className="group relative border-b border-neutral-200/60 py-7 pl-5 last:border-b-0"
                >
                  <span
                    aria-hidden
                    className="absolute bottom-7 left-0 top-7 w-0.5 rounded-full bg-brand-600 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
                  />
                  <h3 className="text-base font-semibold text-neutral-900">{f.title}</h3>
                  <p className="mt-2 max-w-md text-sm leading-relaxed text-neutral-600">{f.desc}</p>
                </div>
              ))}
            </div>
            <div className="flex flex-col">
              {features.slice(2).map((f) => (
                <div
                  key={f.title}
                  className="group relative border-b border-neutral-200/60 py-7 pl-5 last:border-b-0"
                >
                  <span
                    aria-hidden
                    className="absolute bottom-7 left-0 top-7 w-0.5 rounded-full bg-brand-600 opacity-0 transition-opacity duration-200 group-hover:opacity-100"
                  />
                  <h3 className="text-base font-semibold text-neutral-900">{f.title}</h3>
                  <p className="mt-2 max-w-md text-sm leading-relaxed text-neutral-600">{f.desc}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* 套餐 */}
      <section id="pricing" className="scroll-mt-20 border-t border-neutral-200/60 bg-white">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-neutral-400">
            定价方案
          </p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-neutral-900">
            选择适合您的套餐
          </h2>
          <p className="mt-3 max-w-lg text-base leading-relaxed text-neutral-600">
            先免费体验 2 次完整审查，再决定是否升级
          </p>
          <div className="mt-12 grid grid-cols-1 gap-6 lg:grid-cols-3">
            {plans.map((p) => (
              <Card
                key={p.name}
                className={
                  p.highlight
                    ? "border-brand-200 shadow-none ring-1 ring-brand-200/70"
                    : "border-neutral-200/70 shadow-none"
                }
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-base text-neutral-900">{p.name}</CardTitle>
                    {p.highlight && <Badge variant="default">推荐</Badge>}
                  </div>
                  <p className="text-sm text-neutral-500">{p.desc}</p>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="text-3xl font-semibold tabular-nums text-neutral-900">
                      {p.price}
                    </span>
                    {p.unit && <span className="text-sm text-neutral-500">{p.unit}</span>}
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-5">
                  <ul className="flex flex-col gap-2.5">
                    {p.features.map((feat) => (
                      <li key={feat} className="flex items-start gap-2.5 text-sm">
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-brand-600" />
                        <span className="text-neutral-600">{feat}</span>
                      </li>
                    ))}
                  </ul>
                  <Link href={p.href}>
                    <Button
                      className={`w-full transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg ${
                        p.highlight ? "rounded-xl" : ""
                      }`}
                      variant={p.highlight ? "default" : "outline"}
                    >
                      {p.cta}
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="mx-auto mt-8 flex items-center justify-center gap-1.5 text-center text-xs leading-relaxed text-neutral-500">
            <ShieldCheck className="h-3.5 w-3.5 text-brand-600" />
            在线支付由支付宝提供安全保障，支付成功即时开通；定价详情见
            <Link href="/pricing" className="font-medium text-brand-700 hover:underline">
              完整定价页
            </Link>
          </p>
        </div>
      </section>

      {/* 常见问题：细分隔线纵列 */}
      <section className="border-t border-neutral-200/60 bg-[#fafaf9]">
        <div className="mx-auto max-w-6xl scroll-mt-20 px-6 py-20">
          <p className="text-xs font-medium uppercase tracking-[0.2em] text-neutral-400">
            FAQ
          </p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight text-neutral-900">
            常见问题
          </h2>
          <div className="mt-10 max-w-3xl divide-y divide-neutral-200/60 border-t border-neutral-200/60">
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

      {/* Footer：深墨色权威收尾（内容与链接保持原样） */}
      <footer className="bg-neutral-950 py-12">
        <div className="mx-auto max-w-6xl px-6">
          <div className="flex flex-col items-center gap-6 border-b border-neutral-800 pb-8 text-center sm:flex-row sm:justify-between sm:text-left">
            <div>
              <p className="text-sm font-medium text-neutral-100">{siteInfo.name}</p>
              <p className="mt-1.5 text-xs text-neutral-500">
                行政规范性文件智能合法性审查 SaaS
              </p>
            </div>
            <nav className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-neutral-400">
              <Link href="/privacy" className="hover:text-neutral-100">
                隐私政策
              </Link>
              <Link href="/terms" className="hover:text-neutral-100">
                服务条款
              </Link>
              <Link href="/cookies" className="hover:text-neutral-100">
                Cookie 政策
              </Link>
              {siteInfo.contactEmail && (
                <a
                  href={`mailto:${siteInfo.contactEmail}`}
                  className="hover:text-neutral-100"
                >
                  联系我们
                </a>
              )}
            </nav>
          </div>

          <div className="mt-6 space-y-1.5 text-center text-xs text-neutral-500 sm:text-left">
            <p>
              © {new Date().getFullYear()} {siteInfo.name} · AI
              不替代最终法律责任
            </p>
            {siteInfo.legalEntityName ? (
              <p>{siteInfo.legalEntityName}</p>
            ) : (
              <p className="text-amber-400">经营主体信息待补充</p>
            )}
            <p>
              {siteInfo.icpRecord ? (
                <a
                  href="https://beian.miit.gov.cn/"
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-neutral-300"
                >
                  {siteInfo.icpRecord}
                </a>
              ) : (
                <span className="text-amber-400">ICP 备案号待补充</span>
              )}
              {siteInfo.contactEmail && (
                <>
                  {" · 客服邮箱："}
                  <a
                    href={`mailto:${siteInfo.contactEmail}`}
                    className="hover:text-neutral-300"
                  >
                    {siteInfo.contactEmail}
                  </a>
                </>
              )}
            </p>
            {siteInfo.icpSecurityRecord && <p>{siteInfo.icpSecurityRecord}</p>}
          </div>
        </div>
      </footer>
    </div>
  );
}
