# 核心数据契约

> Phase 0 必须先落这些契约。字段可根据现有代码类型系统微调，但语义不可改。

## 1. Chapter

```text
id: string
volume_id?: string
title: string
order: int
markdown_path: string
status: draft | active | archived
word_count: int
created_at: string
updated_at: string
```

说明：章节正文事实保存在 Markdown 文件，Chapter 只保存元数据和路径。

## 2. ChapterManifest

```text
schema_version: string
current_chapter_id?: string
volumes: Volume[]
chapters: Chapter[]
updated_at: string
```

说明：卷/章顺序和当前章节定位来源。

## 3. SourceRef

详见 `source_ref_contract.md`。

## 4. AIResultCard

```text
id: string
type: text_candidate | suggestion | pending_fact | evidence | chapter_summary | inspiration
workflow: ask_selection | enrich_setting | continue_text | polish | retrieve | summarize | chat
status: generated | inserted | saved_to_inbox | converted_to_pending_fact | discarded | retried
chapter_id?: string
input_context: object
content: object | string
source_refs: SourceRef[]
parent_card_id?: string
created_at: string
updated_at: string
```

规则：AI 对前端的产品输出必须是 AIResultCard，不返回裸字符串。卡片主记录写入 `source/workspace/ai_cards.jsonl`。

## 5. PendingFact

```text
id: string
fact_type: character | realm | technique | location | faction | item | rule | event | foreshadow | other
title: string
content: object | string
proposed_by: ai | author
source_refs: SourceRef[]
status: pending | confirmed | edited_confirmed | ignored
target_knowledge_id?: string
created_at: string
confirmed_at?: string
```

规则：PendingFact 未确认前不是事实；确认后写入 Knowledge JSON。

## 6. KnowledgeCard

```text
id: string
type: character | realm | technique | location | faction | item | rule | event | foreshadow
name: string
aliases: string[]
summary: string
fields: object
source_refs: SourceRef[]
status: confirmed | archived
created_at: string
updated_at: string
```

规则：KnowledgeCard 是作者确认事实。重要设定必须有 SourceRef，作者手工设定可用 source_type=author_manual。

## 7. CharacterCard

CharacterCard 是 KnowledgeCard 的一种最小专用视图，MVP 不做复杂状态历史。

建议字段：

```text
knowledge_base: KnowledgeCard
current_realm?: string
current_location?: string
faction?: string
known_secrets?: string[]
relationship_summary?: string
importance: core | major | minor | cameo
```

## 8. IdeaCard

```text
id: string
content: string
source: author | ai
linked_chapter_id?: string
status: open | converted | archived
source_card_id?: string
tags: string[]
created_at: string
updated_at: string
```

规则：IdeaCard 是用户创作资产，但不是小说事实。

## 9. ChapterSummary

```text
id: string
chapter_id: string
status: draft | confirmed | ignored
summary: string
key_events: string[]
character_changes: object[]
new_setting_candidates: PendingFact[]
foreshadow_candidates: object[]
next_chapter_hooks: string[]
source_refs: SourceRef[]
created_at: string
updated_at: string
```

规则：summary 即使 confirmed，也不是高于章节正文的事实源，必须回指章节。

## 10. RetrievalHit

```text
source_type: chapter | knowledge | summary
source_id: string
excerpt: string
score: float
reason: exact | fts | vector | hybrid
source_ref: SourceRef
```

规则：返回给 AI 或 UI 的检索结果必须带 SourceRef。

## 11. EmbeddingChunk

```text
id: string
source_type: chapter | knowledge | summary
source_id: string
text: string
source_ref: SourceRef
embedding: number[] | external_ref
updated_at: string
```

规则：EmbeddingChunk 是 generated 投影，不是事实来源。外部只认 SourceRef。
