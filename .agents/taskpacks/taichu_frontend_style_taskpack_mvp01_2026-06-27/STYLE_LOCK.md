# 太初 MVP0.1 前端视觉改造 Style Lock

> 更新日期：2026-06-27
> 状态：已确认；用户 2026-06-27 当前指令要求继续执行 Phase 1 至 Phase 6
> 适用范围：入口粒子页任务完成后，作为 Phase 1 至 Phase 6 的样式改造边界

## 设计来源

- `TAICHU_DESIGN.md` 更新时间：2026-06-27
- `docs/rule.md` 更新时间：2026-06-24
- 任务包 README 更新时间：2026-06-27
- 本次 Style Lock 确认人：用户

## 三层设计系统

## 前置入口任务

用户已明确：在执行本视觉系统 Phase 1 之前，先执行独立任务包 `C:\Users\wyh\Desktop\Taichu\.agents\taskpacks\taichu_entry_codex_task`，实现“太初首次进入页”。

路由基线暂锁定为：

- `/`：太初首次进入粒子页，按 `taichu_entry_codex_task` 实现点云地景、远景宫阙、`TAICHU` 入口按钮和进入转场。
- `/home`：进入后的功能入口页，承载当前“选择对话入口、编辑工作台入口、收件箱、知识库、设置”等模块入口。
- `/editor`：编辑工作台，归属深色写作工作台层。

如后续用户确认改用 `/entry` 承载首次进入页，则再同步调整本锁定文档和导航。

### 入口虚空层

定义：进入太初前的黑暗观测站，纯黑画布、暖白粒子、远景宫阙、极简 `TAICHU` 白框入口、少量中文状态读数。

本轮处理范围：

- 当前仓库还没有独立首次进入页，但该页面由前置入口任务包先实现。
- 首次进入粒子页不强行套用本 Style Lock 的普通入口层排版细节，以 `taichu_entry_codex_task` 为具体视觉与技术规格。
- 功能入口页作为进入后的主应用入口，参考入口虚空层的克制、暗色、仪式感，但不再承担粒子穿越大场景。
- 入口层视觉不得进入 `/editor`、`/inbox`、`/knowledge`、`/chat`、`/settings` 等主工作台页面。

### 深色写作工作台层

定义：主应用外壳，深灰画布、低对比边界、紧凑信息密度、长时间写作不刺眼。

本轮处理范围：

- `/editor` 的章节树、顶部工具栏、右侧 AI 面板、状态区域。
- `/inbox`、`/knowledge`、`/chat`、`/settings`、`/dashboard` 的页面外壳、表单、列表、状态、按钮。
- shadcn 基础 `Button`、`Card` 的默认视觉映射到工作台层。

### 纸质稿件内容层

定义：从深色工作台中浮出的暖米纸内容层，服务正文、长文本阅读、AI 沉淀内容和知识详情。

本轮处理范围：

- `/editor` 中间正文编辑区域。
- AI 正文候选内容、章节摘要、知识详情、来源证据中需要长时间阅读的内容块。
- 不把整个主应用铺成米纸色。

## 本轮纳入页面

| 路由 | 页面用途 | 所属层 | 本轮动作 |
|---|---|---|---|
| `/` | 太初首次进入粒子页 | 独立入口粒子页 | 由 `taichu_entry_codex_task` 前置实现，完成后再进入本视觉系统 Phase 1 |
| `/home` | 进入后的功能入口 / 模块导航 | 入口虚空层延伸 | 承接当前 `/` 的模块入口，后续改为暗色克制入口，不做普通 SaaS 卡片首页 |
| `/editor` | 章节写作、Selection AI、AI 卡片 | 深色工作台层 + 纸质稿件内容层 | 改造三栏 shell、工具栏、正文稿件层、AI 面板和状态 |
| `/inbox` | 创作收件箱 | 深色工作台层，局部纸面内容 | 改成轻量工作台看板，保留灵感、待确认设定、AI 收藏、问题分区 |
| `/knowledge` | 作者确认知识 | 深色工作台层 + 纸质详情层 | 列表工作台化，知识详情 / 长摘要可纸面化 |
| `/chat` | Agent 对话与来源证据 | 深色工作台层，输出可内容卡片化 | 改造双栏表单、回复区、来源证据展示 |
| `/settings` | 导出与 generated 重建 | 深色工作台层 | 改成低频设置面板，保留导出、重建、清理动作 |
| `/dashboard` | 模型看板占位 | 深色工作台层 | 改成太初风格空态，占位即可 |
| `/entry` | 不存在 | 可选入口路由 | 默认不新增；仅在用户要求改用 `/entry` 时启用 |

## 本轮纳入组件

| 组件 | 路径 | 所属层 | 本轮动作 |
|---|---|---|---|
| 全局样式 | `web/src/app/globals.css` | token 基础 | 新增 `--tc-*` token，映射 shadcn 默认变量到工作台层，保留局部纸面变量 |
| 根布局 | `web/src/app/layout.tsx` | 全局壳 | 使用太初 UI 字体变量和默认工作台背景，不改变 metadata 语义 |
| 首次进入页 | `web/src/app/page.tsx` | 独立入口粒子页 | 前置入口任务包实现点云地景和进入转场 |
| 功能入口页 | `web/src/app/home/page.tsx` | 入口虚空层延伸 | 从当前模块卡片页迁移而来，后续视觉系统 Phase 中继续收敛 |
| 编辑器壳 | `web/src/components/editor/editor-shell.tsx` | 工作台 + 纸面 | 改造三栏、工具栏、正文容器、状态，不改保存和 AI 调用 |
| AI 卡片列表 | `web/src/components/ai-card/ai-card-list.tsx` | AI 状态 + 工作台 + 纸面 | 临时结果深色面板化，正文候选 / 摘要可使用纸面内容块 |
| 收件箱 | `web/src/components/inbox/inbox-board.tsx` | 工作台 | 统一四类分区样式，保留 PendingFact 操作和编辑确认表单 |
| 知识库 | `web/src/components/knowledge/knowledge-list.tsx` | 工作台 + 纸面 | 列表工作台化，知识卡阅读区纸面化 |
| 对话页 | `web/src/app/chat/page.tsx` | 工作台 | 改造表单、回复、来源证据，不改 Agent API |
| 设置页 | `web/src/app/settings/page.tsx` | 工作台 | 改造操作面板和导出结果，不改下载、重建、清理调用 |
| 看板占位 | `web/src/app/dashboard/page.tsx` | 工作台 | 改造空态 |
| 返回按钮 | `web/src/components/back-button.tsx` | 工作台导航 | 统一为工作台返回控件 |
| 基础按钮 | `web/src/components/ui/button.tsx` | 组件基础 | token 化工作台按钮，不做入口按钮或纸面按钮的唯一实现 |
| 基础卡片 | `web/src/components/ui/card.tsx` | 组件基础 | 降低圆角和默认阴影，避免普通 SaaS 卡片感 |

## Token 决策

### 色彩

用户确认后在 `web/src/app/globals.css` 中建立以下语义 token。优先不新增 `web/src/styles/` 目录，除非后续文件体积明显失控。

入口虚空：

- `--tc-void-black: #000000`
- `--tc-void-near: #050505`
- `--tc-void-carbon: #0a0a0a`
- `--tc-void-particle: #f7f3ea`
- `--tc-void-particle-muted: #b8b2a8`
- `--tc-void-frame: #ffffff`
- `--tc-void-frame-warm: #f4efe5`
- `--tc-void-label: #9d9d9d`
- `--tc-void-label-dim: #6f6f6f`
- `--tc-void-seed: #ebfb10`
- `--tc-void-seed-soft: rgba(235, 251, 16, 0.16)`
- `--tc-void-palace-line: rgba(244, 239, 229, 0.28)`

主工作台：

- `--tc-workspace-bg: #151516`
- `--tc-workspace-shell: #0f0f10`
- `--tc-workspace-panel: #1c1c1e`
- `--tc-workspace-panel-soft: #202023`
- `--tc-workspace-recess: #101012`
- `--tc-workspace-editor: #181819`
- `--tc-workspace-border: #3a3a3f`
- `--tc-workspace-border-weak: #29292d`
- `--tc-workspace-grid: rgba(255, 255, 255, 0.035)`
- `--tc-workspace-text: #f4f1ea`
- `--tc-workspace-text-secondary: #b7b3aa`
- `--tc-workspace-text-muted: #85858b`
- `--tc-workspace-text-dim: #5f5f66`
- `--tc-workspace-focus: #fafafa`

AI 极光：

- `--tc-aurora-peach: #f6d1ac`
- `--tc-aurora-rose: #f3b5d2`
- `--tc-aurora-violet: #c7b8f5`
- `--tc-aurora-mint: #a7eadc`
- `--tc-aurora-sky: #afcdf6`
- `--tc-aurora-line: rgba(199, 184, 245, 0.48)`
- `--tc-aurora-soft: rgba(167, 234, 220, 0.08)`
- `--tc-aurora-glow: rgba(167, 234, 220, 0.16)`
- `--tc-aurora-gradient: linear-gradient(90deg, #f6d1ac 0%, #f3b5d2 24%, #c7b8f5 48%, #a7eadc 72%, #afcdf6 100%)`

纸质稿件：

- `--tc-paper-bg: #f8f3e6`
- `--tc-paper-bg-soft: #fbf7ee`
- `--tc-paper-ink: #11100d`
- `--tc-paper-ink-muted: #6f675c`
- `--tc-paper-border: #11100d`
- `--tc-paper-border-soft: #d8cdbb`
- `--tc-paper-shadow: rgba(0, 0, 0, 0.18)`
- `--tc-paper-lime: #edfe5e`
- `--tc-paper-spring: #31e992`
- `--tc-paper-cornflower: #bed4fb`
- `--tc-paper-mark-soft: rgba(237, 254, 94, 0.36)`

### 字体

- `--tc-font-ui`: `"Geist", "Inter", "PingFang SC", "Microsoft YaHei", "Noto Sans SC", sans-serif`
- `--tc-font-mono`: `"Geist Mono", "JetBrains Mono", "SFMono-Regular", Consolas, monospace`
- `--tc-font-editor`: `"Noto Serif SC", "Source Han Serif SC", "Songti SC", "SimSun", serif`
- `--tc-font-paper-title`: `"Noto Serif SC", "Source Han Serif SC", "Songti SC", serif`
- `--tc-font-paper-body`: `"Noto Serif SC", "Source Han Serif SC", "Songti SC", serif`

实现边界：

- UI、导航、工具栏、按钮、表单使用 UI 字体。
- 编辑器正文和纸面长文本使用 serif。
- 等宽字体只用于编号、来源、状态读数、路径等短文本，并配中文说明。

### 间距 / 半径 / 阴影

新增或统一：

- `--tc-shell-sidebar-width: 280px`
- `--tc-shell-inspector-width: 360px`
- `--tc-editor-max-width: 46rem`
- `--tc-card-radius: 8px`
- `--tc-panel-radius: 6px`
- `--tc-shadow-paper: 0 18px 40px rgba(0, 0, 0, 0.18)`
- `--tc-shadow-panel: none`

规则：

- 工作台面板圆角 0-8px。
- 卡片不得层层套卡片。
- 纸面卡片可有轻阴影，但不做普通 SaaS 悬浮卡。

### 动效

新增或统一：

- `--tc-duration-fast: 120ms`
- `--tc-duration-normal: 200ms`
- `--tc-duration-slow: 320ms`
- `--tc-ease-standard: cubic-bezier(0.2, 0, 0, 1)`
- `--tc-ease-enter: cubic-bezier(0.16, 1, 0.3, 1)`

规则：

- Selection AI 与 AI 生成状态只使用小面积极光线或状态点。
- 纸面内容浮现位移 6-12px，时长 180-260ms。
- 必须补充 `prefers-reduced-motion` 降级。

## 不改范围

用户确认本 Style Lock 后，后续样式 Phase 仍不得修改：

- `src/taichu/**`
- `project_assets/**`
- `web/src/lib/api/**`
- `web/src/lib/types/**`
- `web/src/lib/editor/**` 的业务逻辑
- `AIResultCard`、`PendingFact`、`Knowledge`、`Retrieval`、`SQLite`、`SourceRef`、`SelectionAIService`、`AgentRegistry` 的业务契约
- API 路径、请求参数、响应结构、状态机
- `web/package.json`、`web/package-lock.json`，除非用户单独批准依赖变化
- `web/next.config.ts`

## 本轮不做

- 不新增后端能力。
- 不新增多小说、多租户、项目切换、发布平台、团队协作入口。
- 不把入口粒子、宫阙、世界种子读数带入主工作台。
- 不把正文编辑器做成纯黑代码编辑器。
- 不把整个主应用做成大面积米纸背景。
- 不把 AI 状态做成大型彩色组件。
- 不隐藏 AI 卡片、PendingFact、Knowledge、来源证据的关键操作。
- 不新增重型 UI 或动画库。

## 风险

- `/editor` 的 Tiptap 样式改造风险最高，必须保留中文输入、选区、撤销、保存、长章节滚动。
- `AICardList` 的操作按钮不能因视觉收敛变得不可见或只在 hover 显示。
- `InboxBoard` 的 PendingFact 编辑确认表单不能改变 JSON 校验和提交语义。
- 响应式折叠必须保证章节、正文、AI 操作仍可达。
- 全局 token 映射不能破坏 shadcn / Base UI / Tiptap 的 focus 与 disabled 状态。

## 验收方式

自动检查：

```text
cd web
npm run lint
npm run build
npm run test:editor
```

手动检查路径：

1. 打开 `/`，确认首次进入页为点云地景粒子空间，点击 `TAICHU` 后进入功能入口。
2. 打开 `/home`，确认功能入口能进入编辑器、对话、收件箱、知识库和设置。
3. 打开 `/editor`，检查章节树、正文输入、选区 AI、保存、AI 卡片操作。
4. 打开 `/inbox`，检查灵感、待确认设定、已保存卡片、章节问题四类分区。
5. 打开 `/knowledge`，检查正式事实状态、来源数量、长摘要可读性。
6. 打开 `/chat`，检查章节选择、事实范围开关、回复和来源证据。
7. 打开 `/settings`，检查导出、重建、清理动作仍清楚。
8. 检查窄屏、键盘 focus、reduced motion。

## 需要用户确认的问题

请用户确认以下锁定项后，才能进入 Phase 1：

1. 同意先执行 `taichu_entry_codex_task`，在 Phase 1 前实现首次进入粒子页。
2. 同意默认路由为 `/` 首次进入页、`/home` 功能入口页、`/editor` 编辑工作台。
3. 同意本视觉系统后续覆盖 `/home`、`/editor`、`/inbox`、`/knowledge`、`/chat`、`/settings`、`/dashboard`。
4. 同意纸质稿件层覆盖编辑器正文、正文候选、章节摘要、知识详情和来源证据中的长文本，不铺满主应用。
5. 同意 Phase 1 优先在 `web/src/app/globals.css` 中新增 token，不新增 `web/src/styles/` 目录。
6. 同意后续 Phase 6 再决定是否新增 `docs/太初前端视觉冻结说明.md`；如新增，必须遵守 `docs/rule.md`。

## 用户确认

用户是否批准进入 Phase 1：是，用户已在 2026-06-27 当前指令中确认 Phase 0 完成并要求继续执行 Phase 1 至 Phase 6。
