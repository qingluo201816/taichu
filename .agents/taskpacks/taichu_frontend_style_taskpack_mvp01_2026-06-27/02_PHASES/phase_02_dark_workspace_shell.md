# Phase 2：Dark Workspace Shell

> 更新日期：2026-06-27

## 阶段目标

把主应用框架统一成“深色写作工作台层”，让太初看起来像一个稳定的玄幻长篇创作 IDE，而不是普通后台或临时 Demo。

## 要实现什么

1. 改造主工作台/首页。
2. 改造 editor 外层壳：左侧章节区、中间编辑区外框、右侧 AI 面板外框。
3. 改造 dashboard / chat / knowledge / settings 等页面的基础 shell，具体以 `STYLE_LOCK.md` 为准。
4. 建立统一导航、面板、状态条、分割线、背景层级。
5. 保证当前工作台标题“太初玄幻小说 AI 写作助手”不被破坏。

## 不要实现什么

- 不改正文稿纸细节，留给 Phase 3。
- 不改卡片细节，留给 Phase 4。
- 不改业务逻辑。
- 不加入入口点云特效。

## 涉及模块

- `web/src/app/page.tsx`
- `web/src/app/dashboard/**`
- `web/src/app/editor/**`
- `web/src/app/chat/**`
- `web/src/app/knowledge/**`
- `web/src/components/**` 中的 layout / navigation / shell 组件

## 验收标准

- 主应用整体呈现深色工作台层。
- 页面之间视觉一致。
- 所有主要操作仍可见。
- 不出现大片默认白底。
- 不出现高饱和霓虹或赛博朋克 HUD。

## 测试要求

- 手动打开所有纳入改造的页面。
- 检查窄屏和常见桌面宽度。
- 检查 hover/focus/active 状态。
- 检查当前章节、保存状态、AI 入口是否仍可识别。

## 主要风险

- 暗色层级不足，所有面板糊成一片。
- 视觉过重，影响长时间写作。
- 改 shell 时破坏 editor 布局。

## 给 Codex 的任务拆解

1. 识别 shell 组件或重复布局代码。
2. 应用 workspace token。
3. 保留现有交互与路由。
4. 每改一个页面立即检查视觉和布局。
5. 返回截图建议与验收路径。
