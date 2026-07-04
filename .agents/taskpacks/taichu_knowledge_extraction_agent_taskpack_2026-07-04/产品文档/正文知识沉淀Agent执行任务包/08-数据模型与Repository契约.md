# 数据模型与 Repository 契约

> 更新日期：2026-07-04

## 1. Repository 抽象

必须新增或复用以下抽象，不得让 Agent、API、前端直接依赖 JSON 文件路径。

```python
class StructuredKnowledgeRepository(Protocol):
    def list_active_cards(self, type: str | None = None) -> list[StructuredKnowledgeCard]: ...
    def get_card(self, card_id: str) -> StructuredKnowledgeCard | None: ...
    def create_active_card(self, card: StructuredKnowledgeCard) -> StructuredKnowledgeCard: ...
    def patch_active_card(self, card_id: str, updates: dict[str, Any]) -> StructuredKnowledgeCard: ...
    def search_active_identity(self, type: str, name: str, aliases: list[str]) -> list[StructuredKnowledgeCard]: ...
```

第一版实现：

```text
JSONKnowledgeRepository
```

后续实现：

```text
MongoKnowledgeRepository
```

## 2. active 匹配规则

```text
1. 只匹配 status=active 的卡。
2. draft 不参与匹配。
3. deprecated 不参与匹配。
4. 匹配来源是当前 JSON 知识库。
```

匹配顺序：

```text
1. 同类型 name 完全相同。
2. 同类型 aliases 命中。
3. name 命中对方 aliases。
4. aliases 之间有交集。
5. 摘要或 source_note 中出现明显同指称文本。
```

## 3. 知识卡字段 v2

### 通用字段

```text
id
type
name
aliases
summary
importance
status
source_origin
source_note
created_at
updated_at
```

不得维护：

```text
body
tags
fields
confidence
source_refs
relations
foreshadow
```

### source_origin

第一版允许：

```text
inbox_fact
agent_extract
manual
```

正文知识沉淀 Agent 生成固定为：

```text
agent_extract
```

### status

```text
draft
active
deprecated
```

确认候选写入有效知识库时必须写：

```text
active
```

## 4. 类型字段

### character

```text
role_type
identity
relationship_summary
death_chapter_id
current_realm_text
first_seen_chapter_id
last_seen_chapter_id
```

不得维护：

```text
personality
motivation
appearance
relations
current_goal
secret
known_secrets
```

### location

```text
controlling_faction_id
first_seen_chapter_id
```

### faction

```text
faction_type
leader_id
```

### item

```text
item_type
grade
current_holder_id
first_seen_chapter_id
last_seen_chapter_id
```

## 5. 章节引用规则

所有章节引用字段保存稳定 `chapter_id`，不得保存展示用章节序号。

```text
death_chapter_id
first_seen_chapter_id
last_seen_chapter_id
```

## 6. source_note 规则

```text
1. source_note 是作者可读中文来源说明。
2. 必须包含章节标题和原文摘录。
3. 原文摘录不得超过 300 字。
4. 更新已有 active 卡时，不覆盖原 source_note；采用追加方式。
```

## 7. 中间态存储

目录固定：

```text
project_assets/derived/agent_runs/knowledge_extraction/
```

文件命名：

```text
extract_run_<YYYYMMDD_HHMMSS>_<short_id>.json
```

中间态不是事实源，候选内容不能进入 `project_assets/source/knowledge/`。
