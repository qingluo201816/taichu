# Phase 2：Editor Shell / Markdown Persistence

## 1. 阶段目标

让产品从聊天骨架变成章节写作产品：能打开章节、写正文、保存 Markdown、捕获选区。

## 2. 本阶段要实现

- 新增 /editor 页面或对现有 writing 页面收敛。
- 左侧卷/章导航。
- 中间 Tiptap/ProseMirror 编辑器。
- 加载/保存 Markdown。
- 自动保存、手动保存、保存状态提示。
- 基础格式：标题、段落、粗体、斜体、引用、分割线。
- 选区捕获，生成 SelectionContext。
- 右侧 AI 卡片面板占位。

## 3. 本阶段不要实现

- 不要接真实 AI。
- 不要做复杂排版、图片、表格、评论、协作。
- 不要做版本 diff。
- 不要做卡片业务。

## 4. 涉及模块

- `web/src/app/editor`
- `web/src/components/editor`
- `web/src/lib/api/chapters.ts`
- `api/routes/chapters.py`
- `application/services/chapter_service.py`

## 5. 涉及数据对象

- Chapter
- ChapterManifest
- EditorSelection
- AutosaveSnapshot
- SourceRef

## 6. AI 工作流

不调用 AI，只采集 selected_text、surrounding_text、selection_range。

## 7. 验收标准

- 打开章节可看到 Markdown 内容。
- 输入中文长段落稳定。
- 保存后 Markdown 文件更新。
- 刷新后内容不丢。
- 卷/章导航可切换当前章。
- 选中文本后前端能得到 SelectionContext。

## 8. 测试要求

- Markdown 往返测试
- 中文输入手测/自动测试
- 保存/刷新测试
- 章节切换测试
- 非法文件名测试
- 自动保存冲突测试

## 9. 主要风险

- 编辑器 Markdown 往返污染文本。
- 选区坐标和 SourceRef 坐标不一致。

## 10. 给 Codex 的任务拆解建议

- 封装前端 chapters API。
- 实现 editor layout。
- 接入 Tiptap。
- 实现 Markdown serializer/deserializer。
- 实现 autosave hook。
- 实现 selection capture。
- 补前后端测试。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
