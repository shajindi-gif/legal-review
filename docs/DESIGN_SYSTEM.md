# LegalAI Design System

> 单一事实来源（Single Source of Truth）：所有 UI 颜色、间距、字体、组件变体的唯一来源。
> 落地于 [`frontend/src/app/globals.css`](../frontend/src/app/globals.css) 与 [`frontend/src/components/ui/`](../frontend/src/components/ui/)。
> 任何新页面 / 新组件必须从这里取值，**禁止在业务组件里写死 hex / Tailwind 默认色板**。

---

## 0. 目录

1. [Token：颜色](#1-token颜色)
2. [Token：间距](#2-token间距)
3. [Token：字体层级](#3-token字体层级)
4. [UI 原语：Button / Badge / Card / Input / Label / Progress / Separator](#4-ui-原语)
5. [状态组件：Skeleton / EmptyState / ErrorState / FeedbackBar](#5-状态组件)
6. [业务组件：TrustBadge / StatusBadge / MarkdownContent](#6-业务组件)
7. [审查业务组件：RiskList / Citation / EvidencePanel / ReportViewer / NodeFlowChart / DocumentBody / NewReviewForm](#7-审查业务组件)
8. [App Shell：AppShell / TopBar / SideNav / OnboardingDialog](#8-app-shell)
9. [utils 工具函数](#9-utils)
10. [不推荐用法（Do / Don't）](#10-不推荐用法)
11. [扩展点（如何新增组件 / variant）](#11-扩展点)

---

## 1. Token：颜色

### 1.1 品牌色 `brand-*`（紫色 #7c3aed，LegalAI 主调）

| Token | 值 | 用途 |
|---|---|---|
| `brand-50` `#f5f3ff` | 极浅 | AI 角标底色、提示背景 |
| `brand-100` `#ede9fe` | 浅 | secondary 按钮、二级标签 |
| `brand-300` `#c4b5fd` | 中浅 | outline 按钮边框 |
| `brand-500` `#8b5cf6` | 中 | focus ring |
| `brand-600` `#7c3aed` | **主** | default 按钮、主 CTA |
| `brand-700` `#6d28d9` | 深 | hover 态 |
| `brand-800 / 900 / 950` | 深至极深 | 文字、强对比 |

### 1.2 中性色 `neutral-*`

| Token | 值 | 用途 |
|---|---|---|
| `neutral-0` `#ffffff` | 纯白 | 卡片底 |
| `neutral-50` `#f9fafb` | 近白 | 页面背景 |
| `neutral-100` `#f3f4f6` | 浅 | 滚动条、hover 背景 |
| `neutral-200` `#e5e7eb` | 边框 |
| `neutral-300` `#d1d5db` | 较深边框 |
| `neutral-400` `#9ca3af` | placeholder |
| `neutral-500` `#6b7280` | meta 文字 |
| `neutral-600` `#4b5563` | 次级文字 |
| `neutral-700` `#374151` | 主文字 |
| `neutral-900` `#111827` | 标题 |

> 业务组件**禁止使用 Tailwind 默认 `gray-*`** —— 已 M10.1 统一替换为 `neutral-*`。

### 1.3 语义色 `success / warning / danger / info`

| Token | 50 | 100 | 500 | 600 | 700 |
|---|---|---|---|---|---|
| success | `#ecfdf5` | `#d1fae5` | `#10b981` | `#059669` | `#047857` |
| warning | `#fffbeb` | `#fef3c7` | `#f59e0b` | `#d97706` | `#b45309` |
| danger | `#fef2f2` | `#fee2e2` | `#ef4444` | `#dc2626` | `#b91c1c` |
| info | `#eff6ff` | `#dbeafe` | `#3b82f6` | `#2563eb` | `#1d4ed8` |

使用规则：
- **success** —— 成功、已通过、已完成
- **warning** —— 进行中、提示、需注意
- **danger** —— 失败、错误、严重风险
- **info** —— 中性提示、引用来源角标

### 1.4 业务风险色 `risk-*`（LegalAI 业务专用）

| Token | 值 | 用途 |
|---|---|---|
| `risk-high` | `#dc2626` | 严重 / 高风险 文字 |
| `risk-high-bg` | `#fef2f2` | 高风险背景 |
| `risk-medium` | `#d97706` | 中风险 |
| `risk-medium-bg` | `#fffbeb` | 中风险背景 |
| `risk-low` | `#059669` | 低风险 |
| `risk-low-bg` | `#ecfdf5` | 低风险背景 |

业务侧**统一通过 `riskClasses(level)` 取值**（见 [utils](#9-utils)），不要手写 hex。

### 1.5 基础语义

`background` / `foreground` / `muted` / `muted-foreground` / `card` / `card-foreground` / `border` / `ring` —— 全局 default，由 `@layer base` 接管。

---

## 2. Token：间距

| Token | 值 | 用途 |
|---|---|---|
| `--spacing-tight` | `8px` | 行内、按钮内 |
| `--spacing-snug` | `12px` | 紧凑块内 |
| `--spacing-cozy` | `16px` | 默认卡片间距 |
| `--spacing-roomy` | `24px` | 区块间距 |
| `--spacing-loose` | `32px` | 页面区块 |
| `--spacing-grand` | `48px` | Hero / 大间隔 |
| `--spacing-page-x` | `24px` | 页面水平内边距 |
| `--spacing-section-y` | `24px` | 区块垂直内边距 |
| `--spacing-card-p` | `20px` | 卡片内边距 |

实用层 class（`text-display` 等）和 utility class（`p-cozy` 等）尚未一一映射，目前靠业务侧直接用 Tailwind 数值。建议在 24 区间内用 `p-2 / p-3 / p-4 / p-6 / p-8`，与上表对应。

---

## 3. Token：字体层级

| Class | 等价 Tailwind | 用途 |
|---|---|---|
| `text-display` | `text-3xl font-semibold tracking-tight text-neutral-900` | 公开页 Hero |
| `text-page-title` | `text-2xl font-semibold tracking-tight text-neutral-900` | 受保护页主标题（`/review/[id]` 等） |
| `text-section-title` | `text-lg font-semibold text-neutral-900` | 区块大标题 |
| `text-card-title` | `text-base font-semibold text-neutral-900` | 卡片标题 |
| `text-body` | `text-sm text-neutral-700` | 正文 |
| `text-meta` | `text-xs text-neutral-500` | 元信息（时间、计数） |
| `text-secondary` | `text-sm text-neutral-500` | 次级正文 |

> 业务侧**禁止再写 `text-2xl font-semibold ...` 这种长串**，统一调用上述 class。

字体族：
- `font-sans` = Geist + system fallback
- `font-mono` = Geist Mono

---

## 4. UI 原语

### 4.1 Button

[`src/components/ui/button.tsx`](../frontend/src/components/ui/button.tsx)

| prop | 可选值 |
|---|---|
| `variant` | `default` / `secondary` / `outline` / `ghost` / `destructive` / `link` |
| `size` | `default` (h-10) / `sm` (h-8) / `lg` (h-12) / `icon` (h-10 w-10) |
| `asChild` | 布尔；为 true 时渲染 Radix `<Slot>`（用于嵌套 `<Link>`） |

```tsx
<Button>提交审查</Button>
<Button variant="secondary" size="sm">次要操作</Button>
<Button variant="outline">取消</Button>
<Button variant="destructive">删除</Button>
<Button asChild><Link href="/review/123">查看报告</Link></Button>
```

### 4.2 Badge

[`src/components/ui/badge.tsx`](../frontend/src/components/ui/badge.tsx)

| `variant` | 颜色 | 用途 |
|---|---|---|
| `default` | brand 紫底白字 | 强调 |
| `secondary` | brand-100 底 brand-800 字 | 次级 |
| `outline` | 白底 brand 边框 | 轮廓 |
| `success` | success-100/700 | 成功 |
| `warning` | warning-100/700 | 警告 |
| `danger` | danger-100/700 | 危险 |

### 4.3 Card

[`src/components/ui/card.tsx`](../frontend/src/components/ui/card.tsx)

复合组件：`Card` / `CardHeader` / `CardTitle` / `CardDescription` / `CardContent` / `CardFooter`。**注意 CardTitle 是 `<h3>`**，标题层级固定，不可改造为 `<div>`。

### 4.4 Input

[`src/components/ui/input.tsx`](../frontend/src/components/ui/input.tsx)

原生 `<input>` 包装，h-10、border-neutral-300、focus brand-500 ring。**支持所有标准 `type`**，包括 `type="file"`。

### 4.5 Label

[`src/components/ui/label.tsx`](../frontend/src/components/ui/label.tsx)

Radix `<Label>` 原语包装。配 `<Input>` 用，支持 `peer-disabled`。

### 4.6 Progress

[`src/components/ui/progress.tsx`](../frontend/src/components/ui/progress.tsx)

Radix `<Progress>` 原语包装，brand-100 底 + brand-600 条。接 `value={0..100}`。

### 4.7 Separator

[`src/components/ui/separator.tsx`](../frontend/src/components/ui/separator.tsx)

Radix `<Separator>`，默认 `decorative=true`。`orientation="vertical"` 渲染竖线。

---

## 5. 状态组件

| 组件 | 文件 | 用途 |
|---|---|---|
| `Skeleton` | [`skeleton.tsx`](../frontend/src/components/ui/skeleton.tsx) | 通用占位条 |
| `SkeletonText` | 同上 | 单行文字占位 |
| `SkeletonCard` | 同上 | 卡片占位骨架 |
| `EmptyState` | [`empty-state.tsx`](../frontend/src/components/ui/empty-state.tsx) | 空态，必带 `title` + 可选 `description` / `icon` / `action` |
| `ErrorState` | [`error-state.tsx`](../frontend/src/components/ui/error-state.tsx) | 错误态，role="alert"，danger 配色 |
| `FeedbackBar` | [`feedback-bar.tsx`](../frontend/src/components/ui/feedback-bar.tsx) | AI 输出 👍/👎，localStorage 持久化 |

### 5.1 三态一致原则

任何列表 / 详情页都必须考虑三态：

| 状态 | 组件 |
|---|---|
| 加载中 | `Skeleton` 或 `SkeletonCard` |
| 空（无数据） | `EmptyState` —— **永远带"下一步"按钮**，禁止只显示"无数据" |
| 失败 | `ErrorState` —— 带"重试"动作 |
| 成功 | 真实内容 |

旧实现遗留的"加载中…"、"未识别到法律风险"等纯文本态，**禁止新增**。

---

## 6. 业务组件

### 6.1 TrustBadge

[`src/components/ui/trust-badge.tsx`](../frontend/src/components/ui/trust-badge.tsx)

| `kind` | 视觉 | 用途 |
|---|---|---|
| `"ai"` | Sparkles + brand-50 底 brand-700 字 | 标识"此文本由 AI 生成" |
| `"citation"` | Quote + info-50 底 info-700 字 | 标识"此处为引用来源" |

**强制规则（Vertical AI 底线）**：
- 审查报告标题、风险行、修改建议卡等任何**AI 输出文本**都必须挂 `TrustBadge kind="ai"`。
- 法规引用处（Citation 组件 / EvidenceCard）必须挂 `TrustBadge kind="citation"` 或在 Citation 内自带。

### 6.2 StatusBadge

[`src/components/ui/status-badge.tsx`](../frontend/src/components/ui/status-badge.tsx)

审查任务状态的单一来源。`ReviewStatus` → `{ label, variant, dot }`：

| status | label | variant | dot |
|---|---|---|---|
| `pending` | 排队中 | secondary | neutral-400 |
| `parsing` | 解析中 | warning | warning-500 |
| `running` | 审查中 | warning | warning-500 |
| `completed` / `done` | 已完成 | success | success-500 |
| `failed` | 失败 | danger | danger-500 |

支持 `withDot`（状态色点）、`withSpinner`（进行中加旋转）。同时导出 `statusMeta(s)` / `isFinished(s)` / `isInProgress(s)` 给其他逻辑使用。

### 6.3 MarkdownContent

[`src/components/ui/markdown-content.tsx`](../frontend/src/components/ui/markdown-content.tsx)

所有 AI 输出文本（报告全文、Assistant 回复、节点详细说明）**必须经此组件渲染**。

| `size` | 字号 | 用途 |
|---|---|---|
| `sm` | 13/22 | Assistant 聊天气泡 |
| `md` | 14/24 | 默认（节点说明） |
| `lg` | 16/28 | 报告全文（ReportViewer） |

特性：
- `remark-gfm` —— 表格 / 任务列表 / 删除线 / autolink
- `rehype-sanitize` —— XSS-safe
- 外链自动 `target="_blank"` + `rel="noopener noreferrer"`
- 自定义 `components` 可覆盖默认渲染
- `data-testid="markdown-content"` `data-size={size}` 便于 e2e

---

## 7. 审查业务组件

[`src/components/review/`](../frontend/src/components/review/)

| 组件 | 文件 | 职责 |
|---|---|---|
| `NodeFlowChart` | `NodeFlowChart.tsx` | 11 节点审查流程图（Vertical AI 标识） |
| `RiskList` | `RiskList.tsx` | 风险清单，支持 `onOpenEvidence` 联动 |
| `DocumentBody` | `DocumentBody.tsx` | 正文段落 + 段内批注高亮 |
| `Citation` | `Citation.tsx` | 单条法规引用（compact + detail 两态） |
| `EvidenceCard` | `EvidenceCard.tsx` | 单条证据卡（在 EvidencePanel 内部使用） |
| `EvidencePanel` | `EvidencePanel.tsx` | 右侧证据抽屉，接收 `focusedId` 滚动聚焦 |
| `NewReviewForm` | `NewReviewForm.tsx` | 提交新审查表单 |
| `ReportViewer` | `ReportViewer.tsx` | 报告全文渲染（包 MarkdownContent） |

### 7.1 RiskList 联动约定

`RiskList` 通过 `onOpenEvidence?: (risk, evidence) => void` 把 evidence 推到 EvidencePanel。
调用方（`/review/[id]/page.tsx`）维护 `focusedEvidenceKey: \`regulation#${idx}\`` 状态，EvidencePanel 收到 `focusedId` 后滚动到对应 evidence 并高亮。

### 7.2 Citation 行为

`<Citation evidence={ev} index={1} onFocus={(e) => ...} />` 渲染为：
- **compact**（默认）—— `[1] 法规名 · 第 X 条`，点击触发 `onFocus`
- **detail**（hover/聚焦）—— 展开条号、原文摘录

---

## 8. App Shell

[`src/components/dashboard/`](../frontend/src/components/dashboard/)

| 组件 | 文件 | 职责 |
|---|---|---|
| `AppShell` | `AppShell.tsx` | 受保护布局容器，处理 SideNav Drawer、Assistant store hydrate |
| `TopBar` | `TopBar.tsx` | h-16 sticky；Logo + NotificationBell + ⌘K 占位 + User Dropdown |
| `SideNav` | `SideNav.tsx` | 主导航 240px（≥lg）/ Drawer（<lg） |
| `OnboardingDialog` | `OnboardingDialog.tsx` | 首次进入选偏好（Section 33：只问 1 个问题） |
| `HistoryTable` | `HistoryTable.tsx` | 旧版历史表，Home 之外少数处仍使用 |
| `UsageCard` | `UsageCard.tsx` | 配额卡（弱化为 Account 区域） |
| `NotificationBell` | `NotificationBell.tsx` | 通知中心铃铛（30s 轮询 + 5 项下拉） |

辅助：
- [`proxy.ts`](../frontend/src/proxy.ts) —— 路由守卫（受保护路径无 `lr_token` cookie → 307 → `/login`）

---

## 9. utils

[`src/lib/utils.ts`](../frontend/src/lib/utils.ts)

| 函数 | 用途 |
|---|---|
| `cn(...inputs)` | Tailwind 类合并 + dedupe（基于 clsx + tailwind-merge） |
| `formatDateTime(iso)` | `YYYY-MM-DD HH:mm` |
| `formatBytes(n)` | `1.2 MB` |
| `formatRelativeTime(iso)` | "10 分钟前" / "3 天前" / "2 个月前" |
| `truncateMiddle(s, max=20)` | "verylo…123.pdf" |
| `riskClasses(level)` | `high` / `medium` / `low` → `{ text, bg, border }` 类对象，**风险色单一来源** |

辅助 lib：
- [`lib/auth.ts`](../frontend/src/lib/auth.ts) —— zustand + localStorage + cookie sync
- [`lib/preferences.ts`](../frontend/src/lib/preferences.ts) —— 用户偏好（onboarding 用）
- [`lib/assistant-store.ts`](../frontend/src/lib/assistant-store.ts) —— Assistant 多会话 zustand store
- [`lib/sse.ts`](../frontend/src/lib/sse.ts) —— 审查流订阅（task-level SSE）

---

## 10. 不推荐用法（Do / Don't）

### 颜色
- ❌ `<div className="text-gray-500">` —— 必须 `text-neutral-500`
- ❌ `<div className="bg-red-100 text-red-800">` —— 必须 `bg-danger-100 text-danger-700`
- ❌ 直接写 `style={{ color: '#7c3aed' }}` —— 必须 `text-brand-600`
- ❌ 自创 `bg-purple-200` —— 必须用 `brand-*` token

### 间距
- ❌ `p-[13px]` 任意值 —— 必须落到 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48 体系
- ✅ `p-4` / `gap-6` / `space-y-2` —— 落入体系即可

### 字体
- ❌ 重复写 `text-2xl font-semibold tracking-tight text-neutral-900` —— 必须 `text-page-title`
- ❌ 自创 `text-h1` / `text-h2` —— 必须用 §3 class

### 状态
- ❌ `<div>加载中…</div>` —— 必须 `<SkeletonText />` 或 `<Skeleton className="h-3 w-1/2" />`
- ❌ `<div>无数据</div>` —— 必须 `<EmptyState title="..." action={...} />`
- ❌ 错误直接 throw / 空白 —— 必须 `<ErrorState title="..." action={<Button onClick={refetch}>重试</Button>} />`

### Trust Layer
- ❌ 在风险行 / 报告标题省略 `TrustBadge kind="ai"` —— 用户不知道这是模型输出
- ❌ 引用法规但不挂 `TrustBadge kind="citation"` —— 用户无法识别"这是引用"

### 风险色
- ❌ `<span className="text-red-600">高风险</span>` —— 必须 `riskClasses('high').text`

---

## 11. 扩展点

### 11.1 新增 Button variant
1. 在 `button.tsx` 的 `Variant` 联合类型 + `variants` 对象中加项
2. class 必须从 `brand-*` / `neutral-*` / `success-*` / `warning-*` / `danger-*` / `info-*` token 取
3. 在本文 §4.1 表格里登记

### 11.2 新增 Badge variant
1. 在 `badge.tsx` 的 `BadgeVariant` + `variantStyles` 加项
2. 必须使用语义色（success/warning/danger/info）或品牌色
3. 在本文 §4.2 登记

### 11.3 新增业务组件
1. 路径：`frontend/src/components/<domain>/<Name>.tsx`（domain ∈ ui / dashboard / review / auth / assistant）
2. 复合现有原语，**禁止在业务组件里写 hex**
3. 暴露的 props 必须写在文件顶部 JSDoc，并在本文对应章节登记
4. 加 `data-testid` 便于 e2e 探测

### 11.4 新增 token
1. 在 `globals.css` 的 `@theme {}` 加 `--color-*` / `--spacing-*`
2. 在本文对应章节登记
3. 提交前跑 `pnpm tsc --noEmit && pnpm run build` 验证不破

### 11.5 新增页面
1. 路由：`frontend/src/app/(app)/<feature>/page.tsx`
2. 必须三态齐全（loading / empty / error）
3. 任何 AI 输出文本必须经 `MarkdownContent` 渲染 + 挂 `TrustBadge`
4. 受保护路径需在 `proxy.ts` 的 `PROTECTED` 数组中登记

---

## 12. 版本与变更

| 里程碑 | 主要变更 |
|---|---|
| UI-M0 | Design System 审计；token（brand/neutral/语义/风险/间距/字体）写入 `globals.css` |
| UI-M1 | AppShell + SideNav + TopBar；⌘K/⌘N 占位；UI 原语 7 件套 |
| UI-M2 | Home / Assistant / Onboarding |
| UI-M3 | Citation / EvidencePanel / FeedbackBar / MarkdownContent（M0 雏形 → M9 升级） |
| UI-M4 | Documents / NewReviewForm / ⌘N 菜单 |
| UI-M5 | Tasks/Reports 中心页 + 跨页状态 |
| UI-M6 | Assistant 多会话 + 跨页联动 |
| UI-M7 | Review 详情页批注视图 |
| UI-M8 | 通知中心（NotificationBell + 全页 + 4 端点） |
| UI-M9 | Markdown 渲染（remark-gfm）+ Citation 联动 RiskList + Trust Layer 全覆盖 |
| UI-M10 | **本文档**；统一 ui 原语到 token；新增 ErrorState |
