# Fact Scope 与防 AI 污染规则

## 1. 三类数据

### 1.1 小说事实源

允许进入默认 `fact_scope`：

- `source/manuscripts/` 下的章节 Markdown。
- `source/knowledge/` 下 status=confirmed 的 Knowledge JSON。

### 1.2 用户创作资产但非小说事实

不进入默认 `fact_scope`，但可进入 workspace 搜索：

- AIResultCard
- IdeaCard
- PendingFact
- ChapterSummary draft/confirmed
- 收件箱状态
- AI 生成记录
- 未采纳正文候选

### 1.3 技术派生投影

可删除、可重建：

- SQLite projection
- FTS index
- EmbeddingChunk
- Vector cache
- Search cache
- Word count projection
- Recent edit projection

## 2. RetrievalScope

```text
fact_scope:
  include: chapters, confirmed_knowledge
  exclude: pending_facts, ideas, ai_cards, discarded_cards, uninserted_text_candidates, workspace_notes

workspace_scope:
  include: ideas, pending_facts, ai_cards, summaries
  label: 非事实

debug_scope:
  include: generated projection and index diagnostics
  label: 开发诊断
```

## 3. 写入规则

- AI 续写只有被作者插入正文并保存 Markdown 后，才通过章节正文成为事实。
- AI 设定补充只能生成 PendingFact。
- PendingFact 只有 confirmed/edited_confirmed 后才能写入 Knowledge JSON。
- IdeaCard 永远不能自动变事实。
- ChapterSummary 即使 confirmed，也必须回指章节正文，不高于正文。

## 4. 多层防护

Domain：定义状态机、scope 规则、非法流转异常。

Application：所有写入 Knowledge、检索 fact_scope、卡片 action 必须调用 domain rules。

Infrastructure：indexer 默认只索引 fact_scope；workspace index 必须单独命名。

API：请求 scope 默认 fact_scope；workspace_scope 必须显式传入。

UI：workspace 内容必须标记“非事实”。

## 5. 测试必须覆盖

- PendingFact 未确认时不能被 fact_scope 检索。
- IdeaCard 不能被 fact_scope 检索。
- discarded AIResultCard 不能被 fact_scope 或默认 workspace 推荐使用。
- inserted TextCandidateCard 只有保存进 Markdown 后才可被章节索引重建。
- 删除 generated 后不丢用户资产。
