# LegalAI UI / Product Audit

> 范围：UI-M0 审计（不改代码）。本文件先盘点、再决策；具体修改在 UI-M0 / UI-M1 实施阶段。
> 原则：先复用，再改善，再新增。不为追求"新设计"破坏已经满意的 Demo。
> 参考产品（仅借鉴信息架构、交互范式与产品逻辑，不复制品牌 / 颜色 / Logo / 文案 / 具体 UI）：Harvey、Glean、Hebbia、Sierra、Decagon、Perplexity Enterprise、OpenAI / ChatGPT、Claude Workspace、Notion AI。

---

## 0. 技术栈与现状速览

- 框架：Next.js 16.3.2（App Router）+ React 19.2.8 + TypeScript 5
- 样式：Tailwind CSS v4（`@theme` token）+ Radix UI 原语 + lucide-react
- 状态：zustand（auth）+ TanStack Query 5（server state）
- 字体：Geist + Geist_Mono（next/font/google）
- 品牌主色：brand-600 `#7c3aed`（已在 globals.css 中以 50–950 全阶定义）
- 入口路由：
  - 公开：`/`（Landing）、`/login`、`/register`
  - 受保护（`(app)`）：`/dashboard`、`/upload`、`/review/[id]`、`/report/[id]`
  - 管理员：`(admin)/admin`
- UI 原语组件（7 个）：`button` / `card` / `badge` / `input` / `label` / `separator` / `progress`
- 业务组件：`TopBar` / `SideNav` / `UsageCard` / `HistoryTable` / `EvidenceCard` / `NodeFlowChart` / `ReportViewer` / `RiskList` / `LoginForm` / `RegisterForm` / `AuthGuard`
- 设计 token：现有 `globals.css` 已定义 `brand-50~950` + `background / foreground / muted / card / border / ring`；缺：success / warning / danger / info 语义色、风险等级色、间距体系、字体层级体系

---

## 1. A. 保留（已经达到较好水平，不需要重做）

| 区域 | 原因 |
| --- | --- |
| 品牌色 `brand-50~950`（紫色 #7c3aed） | 已通过 Tailwind v4 `@theme` 完整建立，全站一致 |
| 公开首页 `/` Hero + Features + Pricing + Footer | 信息层级清晰、CTA 完整、品牌调性符合"专业、克制、可信" |
| Login / Register 页面布局 | 居中卡片 + 品牌渐变 + 双入口切换，结构合理 |
| `TopBar` 现有 `User` Dropdown | Radix DropdownMenu 模式稳定，结构可复用 |
| `NodeFlowChart` 11 节点标准审查流程 | 已经是 LegalAI 的"垂直 AI 标识"，具有 Harvey 风格的 Process Status 雏形 |
| `EvidenceCard` 引用样式（brand-50 背景） | 视觉一致性强，证据模块核心组件已就位 |
| `utils.ts` 中 `cn` / `formatDateTime` / `formatBytes` | 公共格式化已就位 |
| `lib/auth.ts` zustand + localStorage + cookie sync | 鉴权状态与 proxy.ts 守卫机制稳定 |
| 7 个 UI 原语组件（button / card / badge / input / label / separator / progress） | variants / sizes 命名规范，可作为 Design System 基础 |
| 审查流程后端 SSE（`subscribeReviewStream`） | 实时流式推进节点的体验已具备，是 Vertical AI 关键 |

## 2. B. 优化（结构正确，只需改善体验）

| 区域 | 现状 | 优化方向 |
| --- | --- | --- |
| `SideNav` | 只有 2 项主导航（控制台、上传审查）+ 管理员额外一项；宽 w-56 固定 | 升级为 8 项主导航 + 底部 3 项；宽度按内容 220–260px 区间；激活态清晰；移动端折叠为 Drawer |
| `TopBar` | h-16 sticky + Logo + User Dropdown | 增加 ⌘K 全局搜索按钮、⌘N New 入口；保留 User Dropdown |
| AppShell `(app)/layout.tsx` | 简单 flex 列布局 | 抽出 `<AppShell>` 容器；预留右侧 Context Panel / Evidence Panel 折叠位；移动端汉堡菜单 |
| `/dashboard`（控制台） | 配额卡 + 总量 + 套餐 + 最近审查 | 后续 UI-M2 升级为"Home"：突出主输入框 + 推荐任务 + Recent Work（对话/文件/任务/报告） |
| `/upload` | 现有上传 + 知识库选择 | 后续 UI-M4 拆分为"Documents"列表页（与"Upload"动作解耦），通过 ⌘N / 顶部 +New 触发 |
| `/review/[id]` | 流式节点 + 证据 + 风险 | 后续 UI-M5 改造成"Agent Task"专业工作页：阶段化 Progress、Evidence 右侧栏 |
| `/report/[id]` | 报告渲染 | 后续 UI-M6 改造为独立 Report 模板（执行摘要 / 发现 / 证据 / 风险 / 建议 / 来源 + 导出） |
| `globals.css` token | 已有 brand + 基础中性色 | 补齐语义色（success / warning / danger / info）、风险等级（high / medium / low）、字体层级、间距 4/8/12/16/24/32 |
| `utils.ts` | `cn` + `formatDateTime` + `formatBytes` | 补 `formatRelativeTime`（用于 Recent Work / History）、`truncateMiddle`（用于长文件名 / 长 ID） |
| `RiskList` / `EvidenceCard` | 已可用 | 后续增加"风险等级"色标统一（high / medium / low），与全局 token 对齐 |
| 字体使用 | Geist 已加载 | 补 font-display swap；建立 5 级字号体系（Page / Section / Card / Body / Meta） |
| 错误 / 加载 | 多数是 `加载中…` 文本 | 引入 `Skeleton` / `EmptyState` / `ErrorState` 组件（即使 UI-M0 只先建立基础版本） |

## 3. C. 缺失（顶级 Vertical AI 应有，但当前没有）

> 本节是 UI-M0 / UI-M1 必须新增或预埋；后续 UI-M2 ~ UI-M7 才是真正承载页面。

| 模块 | 缺失说明 | 落地里程碑 |
| --- | --- | --- |
| Design System 文档 | 没有统一的 variant / size / state 表 | UI-M0 输出 `DESIGN_TOKENS.md`（或合并进本文件后半部） |
| Semantic Color 体系 | success / warning / danger / info 未定义 | UI-M0 写进 globals.css |
| 风险等级色 | high / medium / low 未在 token 中统一 | UI-M0 写进 globals.css |
| 字体层级 token | 缺 Page / Section / Card / Body / Meta | UI-M0 写进 globals.css |
| 间距体系 | 缺 4/8/12/16/24/32 标准 | UI-M0 写进 globals.css |
| `<EmptyState>` | 任何空页面目前都是 `No data` 或空 div | UI-M0 新增组件；UI-M2 以后页面使用 |
| `<Skeleton>` | 缺；目前是 `加载中…` | UI-M0 新增组件；UI-M1 TopBar 搜索结果先使用 |
| `<ErrorState>` | 错误直接抛 `500` | UI-M0 新增组件；UI-M2 起统一使用 |
| `Global Search (⌘K)` | 没有 | UI-M1 在 TopBar 放置入口；UI-M6 实现搜索逻辑 |
| `+ New` 全局入口 | 没有 | UI-M1 放置在 TopBar；UI-M4 / UI-M5 弹出菜单 |
| `Context Panel`（右侧） | 缺；为 Evidence / Document Viewer 预留 | UI-M1 在 AppShell 预留折叠位；UI-M3 实现 |
| `Citation` 组件 | `[1] 法规名` + 点击展开证据 | UI-M3 实现 |
| `EvidencePanel` | 右侧证据抽屉 | UI-M3 实现 |
| `AgentTaskCard` / `AgentProgress` | 没有任务卡与阶段进度条组件 | UI-M5 |
| `ReportPreview` | 没有报告预览模板 | UI-M6 |
| `UsageMeter` | UsageCard 存在但不是进度条风格 | UI-M7 之前定稿 |
| 移动端响应式 | 完全没有媒体查询 | UI-M7 重点 |
| 键盘快捷键 | 没有 | UI-M1 加 `⌘K` / `⌘N` 提示，UI-M3 / M6 补全 |
| 反馈（👍 / 👎） | 没有 | UI-M3 / M5 接入 |
| Trust Layer 标识 | 没有 `AI 生成内容` / `引用来源` 角标 | UI-M3 |
| Onboarding | 第一次进入没有"你主要需要 LegalAI 做什么？" | UI-M2 之后 |

## 4. D. 删除 / 隐藏（对用户价值低、重复或开发痕迹明显）

| 区域 | 处理 |
| --- | --- |
| `ReportViewer` 中 `dangerouslySetInnerHTML` + 手写 Markdown 渲染 | 风险与样式双失；先标记删除，UI-M3 / M6 用成熟方案替代（`react-markdown` + `rehype-sanitize`） |
| 简单 `加载中…` 文本（出现多处） | 用 `<Skeleton>` 替换 |
| `未识别到法律风险` 这类无引导空状态 | 替换为 `<EmptyState actionLabel="上传第一个文件" />` |
| 旧的"控制台"作为唯一首页的命名 | 改名 `Home`；旧的 `/dashboard` 路由保留作 alias（重定向到 `/`） |
| Dashboard 中与"工作台"无关的"套餐"硬销 | 弱化为底部"Account"区域中的"Plan"项 |

---

## 5. 决策摘要（落到 UI-M0 + UI-M1）

- **保留**（不在本轮动）：品牌色、首页 Hero、Login/Register、NodeFlowChart、EvidenceCard、UI 原语、auth 体系、SSE 流。
- **优化**（本轮动）：`globals.css` token、`utils.ts` 工具、`AppShell`、`SideNav`、`TopBar`，并补 `EmptyState` / `Skeleton` 基础组件。
- **新增**（本轮动）：`AppShell` 容器、8 项主导航、底部 3 项、全局搜索入口、+New 入口、Skeleton / EmptyState 基础版、字体 / 间距 / 语义色 / 风险色 token。
- **删除 / 隐藏**（本轮动）：无（报告渲染的 `dangerouslySetInnerHTML` 与空状态文案统一推迟到 UI-M3 之前）。
- **兼容策略**：本轮**不删除任何旧路由**——`/dashboard` 仍跳到 dashboard 页面，但 Sidebar 把"Home"也指到 `/dashboard`；`/upload`、`/review`、`/report` 路径全部保留；新增"Agents / Documents / Knowledge / Tasks / Reports / History"暂以 Sidebar 入口 + 占位 page 形式出现（**不展示假功能**，占位页只显示"即将在 UI-Mx 上线 + 推荐开始方式"——这是 Section 2 "没有真正实现的模块不要展示假入口" 的折中：在 Sidebar 暴露但不展示可点的子功能）。

> 注：用户要求"不要一次加入大量没有实际功能的菜单"。**UI-M1 的 Sidebar 只暴露真实可用的入口 + 升级后的旧入口**，新模块（Agents / Documents / Knowledge / Tasks / Reports / History）**只显示"Home"和已经可以用的页面**；其余模块在 UI-M2 之后随页面落地再上 Sidebar。这一选择优先于 Section 30 的"理想一级导航"，以免破坏"没有真正实现的模块不要展示假入口"原则。

---

## 6. UI-M0 + UI-M1 落地清单（与 Section 45 完全对齐）

1. ✅ 审计现有界面（本文）
2. ✅ 明确保留页面（本文件 §1）
3. ▶ 整理 Design Tokens（`globals.css`）
4. ▶ 整理公共 Component（`utils.ts` 扩展 + `EmptyState` + `Skeleton`）
5. ▶ 优化 App Shell（`(app)/layout.tsx` 抽出 `AppShell`）
6. ▶ 优化 Sidebar（`SideNav.tsx` 升级为 8 项 + 底部 3 项，但只暴露可用页面）
7. ▶ 优化 Header（`TopBar.tsx` 增加 ⌘K、⌘N）
8. ▶ 保证所有旧业务仍然可用（regression 路径：`/dashboard` / `/upload` / `/review/[id]` / `/report/[id]` / `/admin`）

完成 UI-M1 后停止；输出 `UI-M1 STATUS: PASS / BLOCKED` 与报告。
