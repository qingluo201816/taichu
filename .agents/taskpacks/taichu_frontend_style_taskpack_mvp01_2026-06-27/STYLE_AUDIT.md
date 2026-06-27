# 太初 MVP0.1 前端视觉审计

> 更新日期：2026-06-27
> 阶段：Phase 0：Design Intake / Frontend Audit / Style Lock
> 审计依据：`TAICHU_DESIGN.md`、任务包设计契约、当前 `web/` 实现

## 审计结论

当前 MVP0.1 前端功能闭环已经成型，但视觉系统仍处于“功能可用样式”阶段，尚未落到 `TAICHU_DESIGN.md` 定义的三层设计系统。

主要差距：

- 缺少 `--tc-void-*`、`--tc-workspace-*`、`--tc-aurora-*`、`--tc-paper-*` 等太初语义 token。
- 多数页面使用白底、黑色粗边框、`zinc/gray` 默认色和硬编码色，整体更接近纸质线框或默认后台，而不是深色写作工作台。
- `/` 是模块入口卡片页，不是“太初虚空”入口；当前不存在 `/entry` 路由。
- `/editor` 虽然已有三栏功能结构，但外壳和编辑区都是浅色纸面，未形成“深色工作台承载稿件层”的关系。
- AI 卡片、收件箱、知识库、对话页、设置页的视觉边界未按“工作台层 / 纸面内容层”拆分。
- 动效只有基础 `transition` 和加载图标，未建立 AI 状态、纸面浮现、reduced motion 等规则。

## 扫描范围

已扫描：

- `web/src/app`
- `web/src/components`
- `web/src/lib`
- `web/src/lib/types`
- `web/src/app/globals.css`

说明：

- `web/src/types` 目录当前不存在。
- 类型文件实际位于 `web/src/lib/types/`。
- 未发现 `/entry` 路由。
- 未修改任何样式、组件、业务逻辑、后端或 `project_assets`。

## 页面审计

| 路由 | 当前文件 | 页面用途 | 当前视觉层级 | 应映射设计层 | 主要差距 | 建议纳入 |
|---|---|---|---|---|---|---|
| `/` | `web/src/app/page.tsx` | 当前入口 / 模块导航 | 默认 shadcn 卡片网格，偏 SaaS 首页 | 入口虚空层，或入口到工作台的极简过渡 | 无粒子观测站、无 `TAICHU` 白框入口、模块卡片像普通产品入口 | 是 |
| `/dashboard` | `web/src/app/dashboard/page.tsx` | 模型看板占位 | 默认居中占位 | 深色写作工作台层 | 未使用工作台 shell，占位页没有太初风格空态 | 是，低优先级 |
| `/editor` | `web/src/app/editor/page.tsx` + `web/src/components/editor/editor-shell.tsx` | 章节编辑、保存、Selection AI、AI 卡片 | 浅色三栏，粗黑边框 | 深色工作台层 + 纸质稿件内容层 | 外壳不是深色工作台；编辑区不是暗色工作台中的稿件层；右侧 AI 面板缺少仪表化状态与极光细线 | 是 |
| `/inbox` | `web/src/app/inbox/page.tsx` + `web/src/components/inbox/inbox-board.tsx` | 灵感、待确认设定、已保存 AI 卡片、章节问题 | 白底看板，彩色栏头，粗黑边框 | 深色工作台层，局部内容可用纸面卡片 | 容易靠近项目管理看板；色块未走 token；PendingFact 状态需更清晰但克制 | 是 |
| `/knowledge` | `web/src/app/knowledge/page.tsx` + `web/src/components/knowledge/knowledge-list.tsx` | 已确认知识列表 | 白底卡片，粗黑边框 | 深色工作台层 + 纸质详情层 | 列表和详情未区分，正式事实卡可转为纸面内容，但列表外壳应为深色工作台 | 是 |
| `/chat` | `web/src/app/chat/page.tsx` | Agent 对话与来源证据 | 白底双栏，粗黑边框 | 深色工作台层，输出可卡片化 | 像普通表单页；来源证据仍是线框块，缺少工作台读数感 | 是 |
| `/settings` | `web/src/app/settings/page.tsx` | 导出、重建、清理派生数据 | 米白背景，粗黑边框 | 深色工作台层 | 低频设置页不应主导纸面风格；危险/清理动作需克制但明确 | 是 |

## 组件审计

| 组件 | 路径 | 业务用途 | 当前样式来源 | 问题 | 风险等级 |
|---|---|---|---|---|---|
| `RootLayout` | `web/src/app/layout.tsx` | 全局字体和 body | `bg-white dark:bg-black`、Geist 字体 | 未声明太初字体 token；body 默认背景不符合工作台层 | 中 |
| `globals.css` | `web/src/app/globals.css` | Tailwind v4、shadcn 变量、编辑器样式 | 默认 shadcn `oklch` token + `.taichu-editor` | 无 `--tc-*` token；编辑器引用、分割线硬编码黑色 | 高 |
| `Button` | `web/src/components/ui/button.tsx` | 全局按钮基础组件 | shadcn/cva 默认变量 | 默认按钮未映射工作台按钮、入口按钮、纸面按钮三类 | 中 |
| `Card` | `web/src/components/ui/card.tsx` | 首页卡片基础组件 | shadcn 默认 `bg-card`、`rounded-xl` | 圆角偏大，未区分工作台卡片和纸面卡片 | 中 |
| `BackButton` | `web/src/components/back-button.tsx` | 返回入口 | fixed 文本按钮、`zinc` 默认色 | 与各页 header 返回样式不统一；未使用工作台 token | 中 |
| `EditorShell` | `web/src/components/editor/editor-shell.tsx` | 章节树、编辑器、工具栏、AI 侧栏 | 大量硬编码浅色、粗黑边框、固定三栏 | 样式改造核心；Tiptap 与三栏响应式风险高 | 高 |
| `AICardList` | `web/src/components/ai-card/ai-card-list.tsx` | Selection AI、AIResultCard 操作 | 白底卡片、黑边按钮、灰底内容区 | 需要保留操作可见性，同时转为工作台 AI 面板和纸面候选内容 | 高 |
| `InboxBoard` | `web/src/components/inbox/inbox-board.tsx` | Inbox 四栏、PendingFact 确认 | 白底看板、彩色栏头、粗黑边 | 需要避免变成项目管理工具；编辑确认表单不能被样式改造破坏 | 高 |
| `KnowledgeList` | `web/src/components/knowledge/knowledge-list.tsx` | Knowledge 列表 | 白底知识卡、粗黑边 | 列表态应工作台化，知识详情可纸面化 | 中 |
| `ChatPage` | `web/src/app/chat/page.tsx` | Agent 对话和来源 | 页面内硬编码样式 | 需保留来源证据和 fact_scope 语义，不改 API | 中 |
| `SettingsPage` | `web/src/app/settings/page.tsx` | 导出与 generated 重建 | 页面内硬编码样式 | 需保持导出、重建、清理动作清楚，不改业务调用 | 中 |

## Token 审计

当前全局 token：

- `globals.css` 只有 shadcn 默认变量：`--background`、`--foreground`、`--card`、`--primary`、`--border`、`--ring` 等。
- 暗色模式使用 `.dark` 变量，但当前页面多数直接写浅色类，未真正依赖暗色主题。
- 无太初设计系统 token：缺少 `--tc-void-*`、`--tc-workspace-*`、`--tc-aurora-*`、`--tc-paper-*`、`--tc-font-*`。

硬编码样式集中点：

- 背景：`bg-[#fffefc]`、`bg-[#fbfaf7]`、`bg-white`、`bg-gray-50`。
- 边框：大量 `border-2 border-black`、`border-[3px] border-black`。
- 文本：`text-black`、`text-zinc-*`、`text-gray-*`、`text-red-700`。
- 色块：`#cce7df`、`#f6e7a8`、`#d9ddff`、`#f4c7b8`。
- 形状：大量 `rounded-lg`、`rounded-full`，未区分工作台按钮、纸面标签和入口按钮。

与设计系统冲突：

- 主应用大面积使用米白 / 白色背景，冲突于“工作台层深色灰阶画布”。
- 编辑器和 AI 侧栏同为浅色，未体现“深色工作台中浮出稿件”的层级。
- 强黑边和饱和彩色栏头不符合工作台的 hairline border 与低对比灰阶。
- 首页模块卡片像普通 SaaS 功能入口，不符合入口虚空层。

## TAICHU_DESIGN.md 提取要点

### 色彩 token

- 入口虚空：`--tc-void-black`、`--tc-void-near`、`--tc-void-carbon`、`--tc-void-particle`、`--tc-void-frame`、`--tc-void-label`、`--tc-void-seed`。
- 主工作台：`--tc-workspace-bg`、`--tc-workspace-shell`、`--tc-workspace-panel`、`--tc-workspace-panel-soft`、`--tc-workspace-editor`、`--tc-workspace-border`、`--tc-workspace-border-weak`、`--tc-workspace-text`、`--tc-workspace-text-secondary`、`--tc-workspace-text-muted`。
- AI 极光：`--tc-aurora-peach`、`--tc-aurora-rose`、`--tc-aurora-violet`、`--tc-aurora-mint`、`--tc-aurora-sky`、`--tc-aurora-line`、`--tc-aurora-soft`、`--tc-aurora-glow`、`--tc-aurora-gradient`。
- 纸质稿件：`--tc-paper-bg`、`--tc-paper-bg-soft`、`--tc-paper-ink`、`--tc-paper-ink-muted`、`--tc-paper-border`、`--tc-paper-border-soft`、`--tc-paper-shadow`、`--tc-paper-lime`、`--tc-paper-spring`、`--tc-paper-cornflower`。

### 字体

- UI 字体：`--tc-font-ui`，用于导航、按钮、面板、状态、表单。
- 等宽字体：`--tc-font-mono`，用于坐标、编号、来源、状态读数。
- 编辑器正文：`--tc-font-editor`，建议 17px-18px，行高 1.75-1.9，行宽 38-46 个中文字符。
- 纸面内容：`--tc-font-paper-title`、`--tc-font-paper-body`。

### 布局

- 入口页：全屏虚空、点云、远景宫阙、少量读数、唯一主要入口。
- 主工作台：顶部 44-52px、左侧 260-304px、中间编辑器 `minmax(560px, 1fr)`、右侧 320-400px、底部 24-32px。
- 响应式：小于 1100px 右侧 AI 面板折叠，小于 820px 左侧章节树折叠。
- Selection AI：靠近选区、280-360px、深色面板、1px 极光线，不大面积渐变。
- 内容卡片：纸面只用于内容沉淀，宽 320-520px，详情可到 720px。

### 组件

- 工作台按钮以灰阶、白色或透明边框为主，高饱和色禁用。
- 工作台面板使用深色面板、1px 边框、0-8px 圆角、无厚阴影。
- 编辑器背景使用工作台编辑器色，正文使用编辑器字体，状态放状态栏，不覆盖正文。
- AI 结果临时态留在右侧深色面板，沉淀后转纸面卡片。
- Knowledge 列表态紧凑深色行，详情态可纸面。
- SourceRef / citation badge 必须中文展示“来源”“章节”“选区”等。

### 动效

- 入口粒子 900-1400ms 建立，不做星空闪烁。
- AI 状态使用小点、1px 扫描线、极弱极光条，1200-1800ms。
- Selection AI 出现 120-160ms，消失 90-120ms，不弹跳。
- Paper Card 浮现 180-260ms，位移 6-12px。
- 必须尊重 `prefers-reduced-motion`。

### 边界与 Anti-goals

- Aaru 只影响入口页、世界种子状态灯和少量读数，不进入主工作台。
- Langbase 是主工作台外壳，不影响纸面稿件内部。
- Switch-Lit 只用于内容卡片和稿件预览，不铺满主应用。
- 禁止普通 SaaS 后台、赛博霓虹、游戏 UI、大面积米纸主应用、纯黑代码编辑器、入口页功能堆叠、AI 大型彩色组件。

## 风险审计

### Tiptap 编辑器风险

- `.taichu-editor` 当前在 `globals.css` 中控制标题、段落、引用、分割线。
- 若全局修改 `p`、`blockquote`、`hr` 或 ProseMirror 类，可能影响输入、选区、撤销、保存状态和 Markdown 转换。
- 编辑器应优先通过局部容器和 `.taichu-editor` token 化，不应改业务保存逻辑。

### AI 卡片操作风险

- `AICardList` 暴露“插入”“替换”“追加”“复制”“灵感”“待确认”“重试”“丢弃”等关键操作。
- 样式改造不能把操作隐藏到 hover，不能减小点击区域，不能弱化 disabled / loading / generated 状态。
- `AIResultCard` 类型、状态、action 语义不得改。

### PendingFact / Knowledge 风险

- `InboxBoard` 内有待确认设定的直接确认、编辑确认、驳回流程。
- 编辑确认表单包含 JSON 字段，后续样式改造不能改变校验和提交结构。
- `KnowledgeList` 展示 source_refs 数量和知识编号，后续只能改展示样式，不改数据结构。

### 响应式风险

- `/editor` 当前固定三栏 `280px / 1fr / 320px`，没有折叠逻辑。
- 收件箱在 `xl:grid-cols-4` 下为四栏，窄屏可变一栏，但卡片内容长文本和编辑表单需要复查。
- 后续 Phase 不能用纯 CSS 隐藏关键面板而导致操作不可达。

### 可访问性风险

- 多处按钮已有中文文本或 `aria-label`，但 focus-visible 目前主要依赖 shadcn 默认变量。
- 未来暗色工作台必须保证中文长文对比度、按钮 focus、键盘顺序。
- 纸面荧光标签必须配文字，不能只靠颜色表达状态。

## Phase 0 不修改范围

- 未修改 `src/taichu/**`。
- 未修改 `project_assets/**`。
- 未修改 `web/src/app/**`、`web/src/components/**`、`web/src/lib/**` 的实现代码。
- 未修改 API、数据结构、状态机、AIResultCard、PendingFact、Knowledge、Retrieval、SQLite、SourceRef、SelectionAIService、AgentRegistry。

