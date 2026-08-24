import Link from "next/link";
import {
  ShieldCheck,
  GitGraph,
  Brain,
  Database,
  FileSearch,
  ArrowRight,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

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

const plans = [
  {
    name: "体验版",
    price: "免费",
    unit: "",
    desc: "适合个人体验与少量审查",
    features: ["每月 3 次审查", "基础风险清单", "在线报告查看", "社区支持"],
    cta: "免费开始",
    highlight: false,
  },
  {
    name: "专业版",
    price: "¥299",
    unit: "/月",
    desc: "适合县级司法局日常审查",
    features: [
      "每月 100 次审查",
      "完整 11 节点审查报告",
      "PDF 报告下载",
      "法规依据追溯",
      "优先邮件支持",
    ],
    cta: "立即升级",
    highlight: true,
  },
  {
    name: "企业版",
    price: "¥1999",
    unit: "/月",
    desc: "适合多部门协同与定制",
    features: [
      "每月 1000 次审查",
      "多账号协同工作台",
      "私有法规库接入",
      "审查结果 API 集成",
      "专属客户成功经理",
    ],
    cta: "联系销售",
    highlight: false,
  },
];

export default function HomePage() {
  return (
    <div className="flex min-h-screen flex-col">
      {/* 顶栏 */}
      <header className="sticky top-0 z-30 border-b border-gray-200 bg-white/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-6">
          <Link href="/" className="flex items-center gap-2">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-brand-600 text-sm font-bold text-white">
              法
            </div>
            <span className="text-lg font-semibold text-brand-700">
              智审 · LegaReview
            </span>
          </Link>
          <div className="flex items-center gap-3">
            <Link href="/login" className="text-sm text-gray-600 hover:text-brand-700">
              登录
            </Link>
            <Link href="/register">
              <Button size="sm">立即注册</Button>
            </Link>
          </div>
        </div>
      </header>

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-gradient-to-b from-brand-50 to-white" />
        <div className="mx-auto max-w-6xl px-6 py-20 text-center">
          <Badge variant="secondary" className="mb-4">
            <ShieldCheck className="mr-1 h-3.5 w-3.5" /> 县级司法局合法性审查部门
          </Badge>
          <h1 className="text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl">
            行政规范性文件{" "}
            <span className="text-brand-600">智能合法性审查</span>
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-lg text-gray-600">
            基于 11 节点 LangGraph 工作流、DeepSeek V4 推理引擎、BGE-M3 本地向量检索与河南省法规库，秒级出具带法规依据的审查意见书。
          </p>
          <div className="mt-8 flex items-center justify-center gap-3">
            <Link href="/register">
              <Button size="lg">
                立即注册 <ArrowRight className="h-4 w-4" />
              </Button>
            </Link>
            <Link href="/login">
              <Button size="lg" variant="outline">
                登录控制台
              </Button>
            </Link>
          </div>
        </div>
      </section>

      {/* 核心能力 */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-center text-2xl font-bold text-gray-900">
          核心能力
        </h2>
        <div className="mt-10 grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => {
            const Icon = f.icon;
            return (
              <Card key={f.title} className="h-full">
                <CardHeader>
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-brand-100 text-brand-700">
                    <Icon className="h-5 w-5" />
                  </div>
                  <CardTitle className="mt-2 text-base">{f.title}</CardTitle>
                </CardHeader>
                <CardContent>
                  <p className="text-sm text-gray-600">{f.desc}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </section>

      {/* 套餐 */}
      <section className="mx-auto max-w-6xl px-6 py-16">
        <h2 className="text-center text-2xl font-bold text-gray-900">
          选择适合您的套餐
        </h2>
        <p className="mt-2 text-center text-gray-500">
          按月订阅，随时升级或降级
        </p>
        <div className="mt-10 grid grid-cols-1 gap-6 lg:grid-cols-3">
          {plans.map((p) => (
            <Card
              key={p.name}
              className={
                p.highlight
                  ? "border-brand-300 ring-2 ring-brand-200"
                  : ""
              }
            >
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle>{p.name}</CardTitle>
                  {p.highlight && (
                    <Badge variant="default">推荐</Badge>
                  )}
                </div>
                <p className="text-sm text-gray-500">{p.desc}</p>
                <div className="mt-2 flex items-baseline gap-1">
                  <span className="text-3xl font-bold text-brand-700">
                    {p.price}
                  </span>
                  {p.unit && (
                    <span className="text-sm text-gray-500">{p.unit}</span>
                  )}
                </div>
              </CardHeader>
              <CardContent className="flex flex-col gap-4">
                <ul className="flex flex-col gap-2">
                  {p.features.map((feat) => (
                    <li key={feat} className="flex items-center gap-2 text-sm">
                      <Check className="h-4 w-4 shrink-0 text-brand-600" />
                      <span className="text-gray-700">{feat}</span>
                    </li>
                  ))}
                </ul>
                <Link href="/register" className="mt-2">
                  <Button className="w-full" variant={p.highlight ? "default" : "outline"}>
                    {p.cta}
                  </Button>
                </Link>
              </CardContent>
            </Card>
          ))}
        </div>
      </section>

      {/* Footer */}
      <footer className="border-t border-gray-200 bg-white py-8">
        <div className="mx-auto max-w-6xl px-6 text-center text-sm text-gray-500">
          © {new Date().getFullYear()} 智审 · LegaReview — 行政规范性文件智能合法性审查 SaaS
          <span className="mx-2">·</span>
          AI 不替代最终法律责任
        </div>
      </footer>
    </div>
  );
}
