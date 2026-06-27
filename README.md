**产品定位**:太初是一款面向个人作者的单本玄幻长篇 AI 创作工作台。它以沉浸式编辑器为核心，把章节正文、小说设定、角色状态、世界观资料和 AI 工作流组织在同一个创作上下文中，让作者可以在不频繁切换工具、不重复解释设定的情况下，完成正文写作、续写辅助、设定查询、冲突检查、剧情推演和创作管理等功能。
 
**主体验**：沉浸式编辑器。

**主对象**：单本玄幻长篇。

**主用户**：个人作者。

**主价值**：减少上下文切换，维护设定一致性，辅助正文推进。

**主 AI 形态**：编辑器内轻量工作流 + 独立 Agent 深度对话。

**主数据原则**：正文和作者确认内容是事实源，索引与缓存可重建。

**主边界**：不做多小说平台，不做协作 SaaS，不做发布平台，不做纯自动写书工具。

太初是服务于玄幻长篇小说创作的个人 AI IDE  

太初所有功能都应该回答一个问题：它是否能帮助作者更舒服、更连续、更准确地推进这一本小说的正文创作？ 

## MVP-0.1 Release Candidate

> 更新日期：2026-06-27

MVP-0.1 RC 的闭环是：章节写作 → Selection AI → AIResultCard → Inbox → PendingFact → 作者确认 Knowledge → generated rebuild → Agent Chat 基于 fact_scope 对话 → Export source bundle。

### 数据边界

- 正式事实源：`project_assets/source/manuscripts/` 下的章节 Markdown，以及 `project_assets/source/knowledge/` 下 `status=confirmed` 的 Knowledge JSON。
- workspace 资产：AIResultCard、IdeaCard、PendingFact、ChapterSummary 等保存在 `project_assets/source/workspace/`，可导出，但默认不是 fact_scope。
- generated 投影：SQLite/FTS 等只保存在 `project_assets/generated/`，可删除并从 source 重建。

### RC 导出格式

当前导出格式是 readable JSON bundle，包含 `path`、`media_type`、`content` 三元组；它是 MVP 备份/迁移格式，不是发布包，也不会把 workspace 内容提升为事实。

### RC 验证命令

```bash
uv run python -m unittest discover tests
uv run ruff check .
uv run mypy
cd web && npm run test:editor
cd web && npm run lint
cd web && npm run build
```
