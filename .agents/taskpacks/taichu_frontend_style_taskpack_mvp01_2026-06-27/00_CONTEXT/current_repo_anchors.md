# 当前仓库锚点

> 更新日期：2026-06-27

Codex 执行时必须以本地仓库实际文件为准。以下只是当前已知锚点，不能替代本地扫描。

## 已知产品定位

仓库 README 当前定位：太初是面向个人作者的单本玄幻长篇 AI 创作工作台，以沉浸式编辑器为核心，主 AI 形态是编辑器内轻量工作流 + 独立 Agent 深度对话，主数据原则是正文和作者确认内容是事实源，索引与缓存可重建。

## 已知前端技术

`web/package.json` 当前可见：

- Next.js
- React
- TypeScript
- Tailwind CSS v4
- shadcn / class-variance-authority / clsx / tailwind-merge
- Tiptap
- lucide-react

可用脚本以本地 `web/package.json` 为准，当前已知包括：

- `npm run dev`
- `npm run build`
- `npm run lint`
- `npm run test:editor`

## 已知前端目录

当前仓库已出现：

- `web/src/app/editor`
- `web/src/app/chat`
- `web/src/app/dashboard`
- `web/src/app/knowledge`
- `web/src/app/globals.css`
- `web/src/components/editor`
- `web/src/components/ui`

Codex 必须动态扫描最新目录，不能只依据本文件。
