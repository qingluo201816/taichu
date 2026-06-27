# Phase 3：Paper Manuscript Content Layer

> 更新日期：2026-06-27

## 阶段目标

把正文编辑和长文本阅读区域统一成“纸质稿件内容层”，提升中文长文写作可读性。

## 要实现什么

1. 改造 editor 中心正文区域。
2. 建立稿纸背景、正文墨色、行宽、段距、字号、标题层级。
3. 优化 Tiptap/ProseMirror 内容区样式。
4. 优化选区、光标、引用、标题、分割线、空段落等 Markdown 基础格式样式。
5. 根据 `STYLE_LOCK.md`，将正文候选卡或知识详情的大段文本也接入纸质层。

## 不要实现什么

- 不改 Tiptap 编辑逻辑。
- 不改 Markdown 序列化。
- 不改保存逻辑。
- 不新增复杂排版功能。
- 不加入图片、表格、评论、协作。

## 涉及模块

- `web/src/app/editor/**`
- `web/src/components/editor/**`
- `web/src/app/globals.css`
- Tiptap content class / ProseMirror 样式

## 验收标准

- 正文区域明显像暗色工作台上的纸质稿件。
- 中文长段落可读，不刺眼。
- 光标和选区清晰。
- 标题、段落、引用、分割线样式克制。
- 编辑器不会因为样式改动影响输入。

## 测试要求

- 输入中文长段落。
- 输入标题、引用、粗体、斜体、分割线。
- 选中文本触发原有选区交互。
- 保存/自动保存不受影响。
- 检查滚动和长章节。

## 主要风险

- 纸色过亮破坏暗色工作台。
- 行宽过宽导致阅读疲劳。
- ProseMirror 样式覆盖不完整。
- 选区颜色与纸色冲突。

## 给 Codex 的任务拆解

1. 找到 editor content wrapper。
2. 用 token 定义 paper、ink、selection。
3. 改正文样式，不改 editor state。
4. 加入长文本测试样例或手动验收说明。
5. 运行 `npm run test:editor`，若存在。
