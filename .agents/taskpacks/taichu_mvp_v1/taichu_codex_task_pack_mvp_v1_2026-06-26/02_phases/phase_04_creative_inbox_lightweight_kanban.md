# Phase 4：Creative Inbox / Lightweight Kanban

## 1. 阶段目标

给灵感、待确认设定、AI 收藏、章节问题一个轻量归宿，避免 AI 输出散落在临时面板。

## 2. 本阶段要实现

- 新增 /inbox 页面。
- 四类列表：ideas、pending_facts、saved_ai_cards、chapter_issues。
- 从 SuggestionCard 保存到 IdeaCard。
- 从 AI 卡片转 PendingFact。
- PendingFact 可忽略。
- 卡片可关联章节并跳回来源。
- workspace 内容明确标记非事实。

## 3. 本阶段不要实现

- 不要做拖拽复杂看板。
- 不要做任务截止日期、多人评论、甘特图。
- 不要做自动事实化。
- 不要做复杂标签系统。

## 4. 涉及模块

- `application/services/inbox_service.py`
- `api/routes/inbox.py`
- `web/src/app/inbox`
- `web/src/components/inbox`

## 5. 涉及数据对象

- IdeaCard
- PendingFact
- AIResultCard
- ChapterIssue
- SourceRef

## 6. AI 工作流

不新增生成能力，只消费 Phase 3 的卡片产物。

## 7. 验收标准

- AI 建议可保存为灵感。
- PendingFact 可在收件箱看到。
- 忽略后不进入待处理。
- 灵感和 PendingFact 不进入 fact_scope。
- 来源跳转可用。

## 8. 测试要求

- 保存重复卡测试
- 忽略 PendingFact 测试
- 来源跳转测试
- workspace_scope/fact_scope 隔离测试

## 9. 主要风险

- 看板膨胀成项目管理。
- workspace/source 命名让 Code Agent 误认为都是事实。

## 10. 给 Codex 的任务拆解建议

- 实现 JSONL workspace repositories。
- 实现 inbox service。
- 实现 inbox API。
- 实现前端四类列表。
- 补防污染测试。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
