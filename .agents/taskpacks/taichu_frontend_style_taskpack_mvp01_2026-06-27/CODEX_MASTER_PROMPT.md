# Codex 总提示词：太初 MVP0.1 后前端视觉系统统一改造

你现在是 `qingluo201816/taichu` 仓库的 Frontend Coding Agent。请执行“太初 MVP0.1 后前端视觉系统统一改造”任务。

本任务发生在 MVP0.1 功能闭环完成之后。你的目标不是新增核心业务功能，而是基于 `TAICHU_DESIGN.md`，把太初前端统一成三层设计系统：入口虚空、深色写作工作台、纸质稿件内容层。

太初产品定位：太初是面向单个作者、单本玄幻长篇小说的个人 AI 创作 IDE。主体验是沉浸式编辑器，核心价值是让作者连续推进当前章节正文，同时把 AI 卡片、灵感、待确认设定、最小知识库、检索证据压缩到一个稳定写作环境中。

## 你必须先读取

请先读取并遵守：

- `TAICHU_DESIGN.md`
- `docs/rule.md`
- 本任务包 `README.md`
- `00_CONTEXT/product_context.md`
- `00_CONTEXT/design_system_summary.md`
- `01_DESIGN_SYSTEM/taichu_design_contract.md`
- `01_DESIGN_SYSTEM/token_contract.md`
- `01_DESIGN_SYSTEM/layer_mapping.md`
- `01_DESIGN_SYSTEM/component_style_contract.md`
- `01_DESIGN_SYSTEM/motion_contract.md`
- `01_DESIGN_SYSTEM/anti_goals.md`
- `03_EXECUTION/codex_rules.md`
- `03_EXECUTION/stop_conditions.md`
- `03_EXECUTION/evidence_return_template.md`

## Phase 0 必须先执行

不要一上来改代码。先执行 Phase 0：

1. 扫描 `web/src/app`、`web/src/components`、`web/src/lib`、`web/src/types`、`web/src/app/globals.css`。
2. 找出当前 MVP0.1 前端页面：工作台、编辑器、收件箱、知识库、对话页、设置页、入口页。
3. 读取 `TAICHU_DESIGN.md`，提取：颜色 token、字体、布局、组件、动效、边界、实现说明、Anti-goals。
4. 生成 `STYLE_AUDIT.md`，列出当前样式和设计系统的差距。
5. 生成 `STYLE_LOCK.md`，明确本次要改哪些页面、哪些 token、哪些组件、哪些不改。
6. 把 `STYLE_LOCK.md` 交给用户确认。

用户没有明确批准 `STYLE_LOCK.md` 之前，不得进入 Phase 1，不得开始样式改造。

## 总目标

把前端统一成：

- 外层入口虚空：玄幻、浩瀚、静谧、克制，不污染主工作台效率。
- 中层深色写作工作台：暗色、低饱和、边界克制、长时间使用不刺眼，承载导航、AI 面板、卡片、知识库、收件箱。
- 内层纸质稿件内容层：正文稿纸有可读性、纸感、段落呼吸感，适合长篇中文创作。

## 硬约束

1. 不得修改后端。
2. 不得修改 `project_assets`。
3. 不得改变业务数据结构和 API 语义。
4. 不得把样式任务扩展成新功能任务。
5. 不得把主工作台做成炫酷入口页。
6. 不得把正文编辑器做成纯黑代码编辑器。
7. 不得牺牲中文长文可读性。
8. 不得隐藏 MVP0.1 关键操作：AI 卡片操作、插入正文、保存灵感、确认设定、来源证据。
9. 不得直接使用未确认的设计猜测覆盖 `TAICHU_DESIGN.md`。
10. `docs/` 下新增中文文档必须符合 `docs/rule.md`：除 `rule.md` 外用中文命名，并包含更新日期。

## 推荐执行阶段

按照 `02_PHASES/` 下的文件逐阶段执行：

- Phase 0：Design Intake / Frontend Audit / Style Lock
- Phase 1：Design Token Foundation
- Phase 2：Dark Workspace Shell
- Phase 3：Paper Manuscript Content Layer
- Phase 4：Cards / Inbox / Knowledge / AI Surfaces
- Phase 5：Responsive / Accessibility / Motion
- Phase 6：Visual QA / Freeze

每个 Phase 完成后必须停止并返回证据。不要跨 Phase 实现。

## 完成后必须返回

使用 `03_EXECUTION/evidence_return_template.md`。至少包括：

- 修改文件列表
- 设计 token 变更
- 页面/组件覆盖范围
- 未修改范围
- lint/build/test 结果
- 手动验收步骤
- 截图建议或视觉检查清单
- 与 `TAICHU_DESIGN.md` 的符合性说明
- 没有修改后端和事实源契约的证明
