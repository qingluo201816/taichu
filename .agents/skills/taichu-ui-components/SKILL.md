---
name: taichu-ui-components
description: 太初前端 UI 组件准入与复用规则。Use when Codex is implementing, modifying, reviewing, or automatically executing any frontend work under `web/`, including task-package execution, page/layout changes, React components, Tailwind styles, shadcn/ui components, visual effects, animations, command palettes, modals, cards, editor UI, entry page UI, paper-card UI, or user-visible frontend copy; trigger even when the user did not explicitly ask for a component library.
---

# 太初 UI 组件准入

## 核心原则

任何太初前端开发任务都默认进入本 Skill，不限于用户显式提出“使用组件库”的场景。自动任务包、代码修复、页面改版、样式微调、组件重构、动效实现和前端 review，只要涉及 `web/` 下用户可见 UI，都必须执行本准入流程。

本 Skill 不定义视觉风格，也不替代根目录 `DESIGN.md`。页面模式、入口页例外、颜色、排版、动效和禁止项只以 `DESIGN.md` 为准；本 Skill 只规定组件如何选择、引入、改造和验证。

## 必读顺序

1. 先读取根目录 `DESIGN.md`，确认当前页面模式和适用边界。
2. 再检查 `web/components.json`、`web/package.json` 和 `web/src/components/ui/`，确认现有 shadcn/ui、Base UI、Tailwind、lucide 和本地基础组件能力。
3. 如果任务来自自动任务包，也按同样顺序执行；不要等待用户再次要求使用 UI 组件规则。

## 组件来源优先级

按以下顺序选组件：

1. 项目内已有组件：优先复用 `web/src/components/ui/` 和业务组件。
2. shadcn/ui 或 Base UI：需要基础交互组件时优先使用，落成本地源码后再适配太初 token。
3. Motion Primitives 类动效基础组件：只用于状态切换和 `DESIGN.md` 允许的克制动效。
4. Magic UI 类视觉素材：只允许提取粒子、光线、扫描线、细微动效等局部效果，并必须改造成太初设计语言。
5. Aceternity UI 类视觉素材：只允许作为局部参考或源码素材，不得直接套用营销区块、霓虹背景、炫光卡片或完整 landing 页面。

不得因为外部组件“好看”而绕过 `DESIGN.md`。

## 引入外部组件的规则

外部组件只能作为源码素材或 registry 输入，不能成为太初的全局视觉规则。

执行前检查：

- 是否能用已有组件完成。
- 是否符合 `DESIGN.md` 的页面模式与视觉边界。
- 是否需要新增依赖；如果需要，必须确认 `web/package.json`、`web/package-lock.json` 和启动脚本风险。
- 是否会引入大面积装饰、霓虹、游戏化或普通 SaaS landing 语言。

落地时要求：

- 组件源码放进项目组件目录后，必须改成太初 token。
- 所有用户可见文案必须中文。
- 图标优先使用 `lucide-react`。
- 动效必须尊重 `prefers-reduced-motion`。
- 不要把外部组件原始英文文案、品牌色、示例数据留在界面里。

## 自动任务检查清单

每次处理前端任务时，确认：

- 已读取 `DESIGN.md`。
- 已判断当前 UI 使用的页面模式及例外边界。
- 已优先检查本地组件能否复用。
- 若使用花哨组件，已缩小到局部效果并完成太初化改造。
- 没有新增无边界混搭、游戏 UI、赛博霓虹、大面积米纸主应用或高饱和按钮。
- 变更后至少运行适合范围的校验，例如 `npm run lint`、`npm run test:editor` 或 `npm run build`；无法运行时说明原因。

## 输出要求

交付前说明：

- 使用了哪些本地组件或外部组件素材。
- 它们分别服务于哪个页面模式或交互场景。
- 是否新增依赖。
- 做了哪些验证。
