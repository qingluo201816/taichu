# Phase 3：Selection AI / AI Result Card

## 1. 阶段目标

实现三类选区 AI，并把输出统一变成 AIResultCard，完成插入/保存/丢弃/重试的最小闭环。

## 2. 本阶段要实现

- 新增 SelectionAIService。
- 新增 POST /api/ai-cards/selection。
- 实现 mode=ask/enrich_setting/continue_text。
- 实现 AIResultCard JSONL 主记录。
- 实现右侧 AI 卡片列表。
- TextCandidateCard 支持插入光标、替换选区、追加段落后、复制、重试、丢弃。
- SuggestionCard 支持保存为灵感。
- enrich_setting 可生成 PendingFactCard，但不确认入库。
- LLM 返回非结构化时做失败降级卡。

## 3. 本阶段不要实现

- 不要注册为 Agent。
- 不要做 Agent Chat。
- 不要写 Knowledge。
- 不要做复杂检索，只可用当前章节/选区上下文和后续 Phase 的 retrieval stub。
- 不要让卡片只存在前端内存。

## 4. 涉及模块

- `application/services/selection_ai_service.py`
- `application/workflows/selection`
- `application/services/ai_card_service.py`
- `api/routes/ai_cards.py`
- `web/src/components/ai-card`
- `web/src/lib/api/ai-cards.ts`

## 5. 涉及数据对象

- AIResultCard
- PendingFact
- IdeaCard
- SourceRef
- SelectionContext

## 6. AI 工作流

输入 chapter_id、selection_range、selected_text、surrounding_text、mode、user_prompt、target_words；输出 AIResultCard。作者 action 改变 card status。

## 7. 验收标准

- 选区问答返回 SuggestionCard。
- 设定补充返回 SuggestionCard 或 PendingFactCard。
- 续写返回 TextCandidateCard，默认只含正文。
- 插入正文后 Markdown 可保存。
- 保存建议后生成 IdeaCard。
- 丢弃卡片不进入事实源。
- Selection AI 未进入 AgentRegistry。

## 8. 测试要求

- Mock LLM 结构化输出测试
- LLM 非 JSON 降级测试
- 卡片状态机测试
- 插入/替换/追加测试
- 丢弃防污染测试
- target_words 基础测试

## 9. 主要风险

- LLM 输出不稳定。
- 卡片 action 与编辑器 selection 不同步。
- AI 续写夹带解释。

## 10. 给 Codex 的任务拆解建议

- 新增 SelectionAIService。
- 新增 AI card repository JSONL。
- 新增 API schema/routes。
- 新增前端卡片组件。
- 实现 editor card actions。
- 补 mock LLM tests。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
