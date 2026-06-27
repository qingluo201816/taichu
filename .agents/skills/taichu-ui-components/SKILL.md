---
name: taichu-ui-components
description: 太初前端 UI 组件准入与复用规则。Use when Codex is implementing, modifying, reviewing, or automatically executing any frontend work under `web/`, including task-package execution, page/layout changes, React components, Tailwind styles, shadcn/ui components, visual effects, animations, command palettes, modals, cards, editor UI, entry page UI, paper-card UI, or user-visible frontend copy; trigger even when the user did not explicitly ask for a component library.
---

# 太初 UI 组件准入

## 核心原则

任何太初前端开发任务都默认进入本 Skill，不限于用户显式提出“使用组件库”的场景。自动任务包、代码修复、页面改版、样式微调、组件重构、动效实现和前端 review，只要涉及 `web/` 下用户可见 UI，都必须执行本准入流程。

本 Skill 不替代 `TAICHU_DESIGN.md`。它只规定组件库和花哨组件如何被选择、引入、改造和验证。

## 必读顺序

1. 先读取根目录 `TAICHU_DESIGN.md`，确认当前任务属于入口层、工作台层、纸面内容层或 AI 状态层。
2. 再检查 `web/components.json`、`web/package.json` 和 `web/src/components/ui/`，确认现有 shadcn/ui、Base UI、Tailwind、lucide 和本地基础组件能力。
3. 如果任务来自自动任务包，也按同样顺序执行；不要等待用户再次要求使用 UI 组件规则。

## 组件来源优先级

按以下顺序选组件：

1. 项目内已有组件：优先复用 `web/src/components/ui/` 和业务组件。
2. shadcn/ui 或 Base UI：需要基础交互组件时优先使用，落成本地源码后再适配太初 token。
3. Motion Primitives 类动效基础组件：只用于 Selection AI、纸卡浮现、状态切换等克制动效。
4. Magic UI 类视觉素材：只允许提取粒子、光线、扫描线、细微动效等局部效果，并必须改造成太初三层设计语言。
5. Aceternity UI 类视觉素材：只允许作为局部参考或源码素材，不得直接套用营销区块、霓虹背景、炫光卡片或完整 landing 页面。

不得因为外部组件“好看”而绕过太初三层设计系统。

## 分层准入

### 入口层

允许：

- 粒子场。
- 点云地景。
- 极弱仪表读数。
- 白框入口按钮。
- 低透明远景线稿。

禁止：

- 随机星空组件。
- 赛博霓虹背景。
- 大面积渐变 hero。
- 普通 SaaS landing 区块。
- 游戏 HUD。

### 工作台层

允许：

- 命令面板。
- 弹出层、抽屉、Tooltip、Popover。
- 深色面板、工具栏、状态栏。
- 极弱 aurora 线条。
- 紧凑列表、分隔线、检索状态。

禁止：

- 彩色主按钮体系。
- 大面积发光背景。
- 浮夸 hover 卡片。
- 杂志式大标题压过编辑器。
- 在工作台背景使用米纸色。

### 纸面内容层

允许：

- 暖米纸卡片。
- 黑色墨线边框。
- 小面积荧光标签。
- 来源徽标。
- 稿件预览和导出纸张。

禁止：

- 把纸面风格扩散到主工作台外壳。
- 使用极光渐变铺满卡片。
- 使用营销卡片模板替代稿件结构。

### AI 状态层

允许：

- 小圆点。
- 1px 扫描线。
- 短进度线。
- 极弱 aurora 动效。
- 等宽读数配中文说明。

禁止：

- 大型彩色 AI 按钮。
- 全屏 loading 特效。
- 高饱和状态色块。

## 引入外部组件的规则

外部组件只能作为源码素材或 registry 输入，不能成为太初的全局视觉规则。

执行前检查：

- 是否能用已有组件完成。
- 是否符合 `TAICHU_DESIGN.md` 的层级边界。
- 是否需要新增依赖；如果需要，必须确认 `web/package.json`、`package-lock.json` 和启动脚本风险。
- 是否会引入大面积装饰、霓虹、游戏化或普通 SaaS landing 语言。

落地时要求：

- 组件源码放进项目组件目录后，必须改成太初 token。
- 所有用户可见文案必须中文。
- 图标优先使用 `lucide-react`。
- 动效必须尊重 `prefers-reduced-motion`。
- 不要把外部组件原始英文文案、品牌色、示例数据留在界面里。

## 自动任务检查清单

每次处理前端任务时，确认：

- 已读取 `TAICHU_DESIGN.md`。
- 已判断当前 UI 属于哪个视觉层。
- 已优先检查本地组件能否复用。
- 若使用花哨组件，已缩小到局部效果并完成太初化改造。
- 没有新增无边界混搭、游戏 UI、赛博霓虹、大面积米纸主应用或高饱和按钮。
- 变更后至少运行适合范围的校验，例如 `npm run lint`、`npm run test:editor` 或 `npm run build`；无法运行时说明原因。

## 输出要求

交付前说明：

- 使用了哪些本地组件或外部组件素材。
- 它们分别服务于入口层、工作台层、纸面内容层或 AI 状态层中的哪一层。
- 是否新增依赖。
- 做了哪些验证。
