import Link from "next/link";
import {
  ShieldCheck,
  GitGraph,
  Brain,
  Database,
  FileSearch,
  ArrowRight,
  Check,
  Upload,
  FileText,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { siteInfo } from "@/lib/site";

const steps = [
  {
    no: "01",
    icon: Upload,
    title: "上传文件",
    desc: "支持 PDF / Word / TXT / Markdown，自动解析文本与结构。",
  },
  {
    no: "02",
    icon: GitGraph,
    title: "智能审查",
    desc: "11 节点流水线完成主体、内容、程序三查，附风险评估与证据核验。",
  },
  {
    no: "03",
    icon: FileText,
    title: "出具意见书",
    desc: "输出结构化风险清单、法规依据与修改建议，可导出归档。",
  },
];

const features = [
  {
    icon: GitGraph,
    title: "11 节点 LangGraph 流水线",
    desc: "文档解析 → 分类 → 检索 → 主体/内容/程序审查 → 风险评估 → 证据核验 → 报告生成 → 人工复核，全流程可追溯。",
  },
  {
    icon: Brain,
    title: "DeepSeek V4 推理引擎",
    desc: "深度推理模型驱动多 Agent 协同审查，输出结构化风险清单与修改建议。",
  },
  {
    icon: Database,
    title: "BGE-M3 本地向量检索",
    desc: "私有化部署嵌入模型，法规库检索不外传数据，满足政务合规要求。",
  },
  {
    icon: FileSearch,
    title: "河南省法规库",
    desc: "覆盖省、市、县三级地方性法规与规范性文件，审查依据精确到条款。",
  },
];

// 次数 / 能力与定价页（/pricing）保持一致，避免前后矛盾。
const plans = [
  {
    name: "体验版",
    price: "免费",
    unit: "",
    desc: "适合个人体验与少量审查",
    features: ["每日 3 次审查", "基础法规库（国家法律 + 行政法规）", "标准审查报告", "社区支持"],
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

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col bg-white">
      {/* 顶栏 */}
      <header className="sticky top-0 z-30 border-b border-neutral-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
              法
            </div>
            <span className="text-base font-semibold tracking-tight text-neutral-900">
              智审 <span className="font-normal text-neutral-500">·</span> LegaReview
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

      {/* Hero */}
      <section className="relative">
        <div className="mx-auto max-w-6xl px-6 pb-20 pt-20 text-center sm:pt-24">
          <Badge variant="secondary" className="mb-6">
            <ShieldCheck className="mr-1.5 h-3.5 w-3.5" />
            行政规范性文件 · 智能合法性审查
          </Badge>
          <h1 className="mx-auto max-w-3xl text-4xl font-semibold leading-tight tracking-tight text-neutral-900 sm:text-5xl sm:leading-tight">
            行政规范性文件
            <br className="hidden sm:block" />
            <span className="text-brand-600">智能合法性审查</span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-neutral-600">
            基于 11 节点 LangGraph 工作流与 DeepSeek V4 推理引擎，结合 BGE-M3 本地检索与河南省法规库，秒级出具带法规依据的审查意见书，结论可追溯。
          </p>
          <div className="mt-9 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/register">
              <Button size="lg" className="w-full sm:w-auto">
                免费开始审查 <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="outline" className="w-full sm:w-auto">
                登录控制台
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* 三步流程 */}
      <section className="border-t border-neutral-100 bg-neutral-50/60">
        <div className="mx-auto max-w-6xl px-6 py-16">
          <p className="text-center text-sm font-medium uppercase tracking-widest text-neutral-400">
            从文件到意见书
          </p>
          <h2 className="mt-2 text-center text-2xl font-semibold tracking-tight text-neutral-900">
            三步完成审查
          </h2>
          <div className="mt-10 grid grid-cols-1 gap-6 md:grid-cols-3">
            {steps.map((s) => {
              const Icon = s.icon;
              return (
                <div key={s.no} className="relative rounded-xl border border-neutral-200 bg-white p-6">
                  <span className="absolute right-5 top-5 text-3xl font-semibold tracking-tight text-neutral-100">
                    {s.no}
                  </span>
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                    <Icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-4 text-base font-semibold text-neutral-900">{s.title}</h3>
                  <p className="mt-2 text-sm leading-relaxed text-neutral-600">{s.desc}</p>
                </div>
              );
            })}
          </div>
        </div>
      </section>

      {/* 核心能力 */}
      <section id="features" className="mx-auto max-w-6xl scroll-mt-20 px-6 py-20">
        <h2 className="text-center text-2xl font-semibold tracking-tight text-neutral-900">
          核心能力
        </h2>
        <p className="mt-2 text-center text-sm text-neutral-500">
          面向合法性审查场景的专业技术底座
        </p>
        <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => {
            const Icon = f.icon;
            return (
              <Card key={f.title} className="h-full border-neutral-200 shadow-none">
                <CardHeader>
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-50 text-brand-700">
                    <Icon className="h-5 w-5" />
                  </div>
                  <CardTitle className="mt-3 text-base text-neutral-900">{f.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm leading-relaxed text-neutral-600">{f.desc}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* 套餐 */}
      <section id="pricing" className="border-t border-neutral-100 bg-neutral-50/60 scroll-mt-20">
        <div className="mx-auto max-w-6xl px-6 py-20">
          <h2 className="text-center text-2xl font-semibold tracking-tight text-neutral-900">
            选择适合您的套餐
          </h2>
          <p className="mt-2 text-center text-sm text-neutral-500">
            按月订阅，随时升级或降级
          </p>
          <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-3">
            {plans.map((p) => (
              <Card
                key={p.name}
                className={
                  p.highlight
                    ? "border-brand-300 ring-1 ring-brand-200 shadow-sm"
                    : "border-neutral-200 shadow-none"
                }
              >
                <CardHeader>
                  <div className="flex items-center justify-between">
                    <CardTitle className="text-neutral-900">{p.name}</CardTitle>
                    {p.highlight && <Badge variant="default">推荐</Badge>}
                  </div>
                  <p className="text-sm text-neutral-500">{p.desc}</p>
                  <div className="mt-2 flex items-baseline gap-1">
                    <span className="text-3xl font-semibold text-neutral-900">
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
                        <span className="text-neutral-700">{feat}</span>
                      </li>
                    ))}
                  </ul>
                  <Link href={p.href}>
                    <Button className="w-full" variant={p.highlight ? "default" : "outline"}>
                      {p.cta}
                    </Button>
                  </Link>
                </CardContent>
              </Card>
            ))}
          </div>
          <p className="mx-auto mt-8 max-w-xl text-center text-xs leading-relaxed text-neutral-400">
            线上支付与开票服务正在接入中，正式购买请联系我们获取报价与人工开票安排。
          </p>
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-neutral-200 bg-white py-10">
        <div className="mx-auto max-w-6xl px-6">
          <div className="flex flex-col items-center gap-6 border-b border-neutral-100 pb-6 text-center sm:flex-row sm:justify-between sm:text-left">
            <div>
              <p className="text-sm font-medium text-neutral-700">{siteInfo.name}</p>
              <p className="mt-1 text-xs text-neutral-500">
                行政规范性文件智能合法性审查 SaaS
              </p>
            </div>
            <nav className="flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-neutral-600">
              <Link href="/privacy" className="hover:text-brand-700">
                隐私政策
              </Link>
              <Link href="/terms" className="hover:text-brand-700">
                服务条款
              </Link>
              <Link href="/cookies" className="hover:text-brand-700">
                Cookie 政策
              </Link>
              {siteInfo.contactEmail && (
                <a
                  href={`mailto:${siteInfo.contactEmail}`}
                  className="hover:text-brand-700"
                >
                  联系我们
                </a>
              )}
            </nav>
          </div>

          <div className="mt-6 space-y-1 text-center text-xs text-neutral-500">
            <p>
              © {new Date().getFullYear()} {siteInfo.name} · AI
              不替代最终法律责任
            </p>
            {siteInfo.legalEntityName ? (
              <p>{siteInfo.legalEntityName}</p>
            ) : (
              <p className="text-amber-600">经营主体信息待补充</p>
            )}
            {siteInfo.icpRecord ? (
              <p>
                <a
                  href="https://beian.miit.gov.cn/"
                  target="_blank"
                  rel="noreferrer"
                  className="hover:text-brand-700"
                >
                  {siteInfo.icpRecord}
                </a>
              </p>
            ) : (
              <p className="text-amber-600">ICP 备案号待补充</p>
            )}
            {siteInfo.icpSecurityRecord && <p>{siteInfo.icpSecurityRecord}</p>}
          </div>
        </div>
      </footer>
    </div>
  );
}