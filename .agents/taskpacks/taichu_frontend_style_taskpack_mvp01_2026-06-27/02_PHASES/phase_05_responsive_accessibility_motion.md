# Phase 5：Responsive / Accessibility / Motion

> 更新日期：2026-06-27

## 阶段目标

完成响应式、可访问性和动效收敛，保证新视觉系统可长期使用。

## 要实现什么

1. 检查桌面、窄屏、移动端布局。
2. 确保 focus-visible 清晰。
3. 确保按钮、输入框、卡片操作有可访问 label 或文本。
4. 支持 `prefers-reduced-motion`。
5. 统一 hover/active/disabled/loading 状态。
6. 检查对比度和中文长文可读性。

## 不要实现什么

- 不做完整移动端重构。
- 不做复杂主题切换。
- 不做可访问性面板。
- 不新增动画库，除非本地已存在且 `STYLE_LOCK.md` 允许。

## 涉及模块

- 全部已纳入样式改造的 web 页面和组件
- `globals.css`
- 组件状态样式

## 验收标准

- 键盘可以看到焦点。
- reduced motion 下无大幅动画。
- 窄屏不出现主要操作被遮挡。
- disabled/loading/error 状态统一。
- 文本对比度足够。

## 测试要求

- 手动 Tab 导航。
- 浏览器模拟 reduced motion。
- 桌面常见宽度：1440、1280、1024。
- 窄屏：768、390。
- 检查 editor 三栏在窄屏下是否可用或有合理降级。

## 主要风险

- 响应式强行压缩导致编辑器不可用。
- focus 样式被暗色背景吞掉。
- 动效破坏输入体验。

## 给 Codex 的任务拆解

1. 建立响应式检查清单。
2. 逐页修正明显布局问题。
3. 加 reduced motion CSS。
4. 加 focus-visible token。
5. 运行 lint/build。
