# 太初 MVP0.1 后前端视觉系统统一改造任务包

> 更新日期：2026-06-27
> 任务类型：Frontend Styling / Visual System Refactor / MVP0.1 后置任务
> 执行对象：Codex / Frontend Coding Agent
> 主输入文档：`TAICHU_DESIGN.md`

## 目标

本任务包用于在 MVP0.1 完成后，把太初前端从“功能可用”统一升级到“三层设计系统一致”的视觉状态：

1. **入口虚空层**：太初外层仪式感，不是本任务主开发对象，但要保证风格与工作台衔接。
2. **深色写作工作台层**：应用主框架、导航、侧栏、AI 面板、收件箱、知识库、对话页的暗色工作区。
3. **纸质稿件内容层**：编辑器正文、章节稿纸、正文候选、可阅读内容区域的纸感层。

目标不是重写业务逻辑，而是建立长期稳定的前端视觉基线：颜色 token、字体层级、布局密度、组件状态、卡片样式、编辑器稿纸、动效、边界和 Anti-goals 一次收敛。

## 必须先读

Codex 执行前必须先读取仓库中的：

- `TAICHU_DESIGN.md`
- `docs/rule.md`
- `README.md`
- `web/package.json`
- `web/src/app/globals.css`
- `web/src/app/layout.tsx`
- `web/src/app/page.tsx`
- `web/src/app/editor/**`
- `web/src/components/**`

如果 `TAICHU_DESIGN.md` 不存在，或者不在仓库根目录，必须停止并询问用户它的实际位置。不要凭空编造设计 token。

## 不要做什么

本任务不是实现 MVP0.1 功能，不是写后端，不是接 AI，不是改事实源。不得修改：

- `src/taichu/**`
- `project_assets/**`
- AIResultCard / PendingFact / Knowledge / Retrieval / SQLite / SourceRef / SelectionAIService / AgentRegistry 的业务契约
- 入口点云 Three.js 大场景，除非 `TAICHU_DESIGN.md` 明确要求做少量风格衔接

## 推荐使用方式

每次只执行一个 Phase。最安全顺序：

1. Phase 0：Design Intake / Frontend Audit / Style Lock
2. Phase 1：Design Token Foundation
3. Phase 2：Dark Workspace Shell
4. Phase 3：Paper Manuscript Content Layer
5. Phase 4：Cards / Inbox / Knowledge / AI Surfaces
6. Phase 5：Responsive / Accessibility / Motion
7. Phase 6：Visual QA / Freeze

Phase 0 生成并获得用户确认 `STYLE_LOCK.md` 之前，禁止开始样式改造。
