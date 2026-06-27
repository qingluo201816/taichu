# Phase 1：Design Token Foundation

> 更新日期：2026-06-27

## 阶段目标

把 `TAICHU_DESIGN.md` 中的视觉规则落成可复用 token，形成后续页面和组件统一改造基础。

## 前置条件

- Phase 0 完成。
- 用户已批准 `STYLE_LOCK.md`。

## 要实现什么

1. 在合适位置建立或整理全局 token。
2. 将三层设计系统映射成 CSS 变量或 Tailwind 可消费的语义变量。
3. 建立基础页面背景、文字、边界、阴影、半径、动效变量。
4. 更新 `globals.css`，减少硬编码。
5. 如有必要新增 `web/src/styles/` 或 `web/src/lib/design-tokens.ts`。
6. 不改变页面布局和业务交互。

## 不要实现什么

- 不大改 editor 页面。
- 不大改 AI 卡片。
- 不新增组件功能。
- 不引入重型 UI 库。
- 不把所有现有 class 一次性重写。

## 涉及模块

- `web/src/app/globals.css`
- `web/src/styles/**`，若新增
- `web/src/lib/design-tokens.ts`，若新增
- 少量基础 layout 引用

## 验收标准

- 设计 token 能表达入口虚空、深色工作台、纸质稿件三层。
- `npm run lint` 通过或列出与本任务无关的既有失败。
- `npm run build` 通过或列出与本任务无关的既有失败。
- 不影响 MVP0.1 功能。

## 测试要求

- 浏览主要页面无白底闪烁。
- 浏览器暗色主题下正常。
- 基础文字对比度可读。
- focus-visible 仍可见。

## 主要风险

- token 命名过细，导致后续维护困难。
- 颜色过暗，正文可读性下降。
- Tailwind v4 与 CSS 变量使用方式冲突。

## 给 Codex 的任务拆解

1. 读取 `STYLE_LOCK.md` 中确认的 token。
2. 梳理现有 `globals.css`。
3. 新增语义 token。
4. 小范围替换全局背景和文字。
5. 运行检查并返回证据。
