# SourceRef v1 契约

## 1. 目标

SourceRef 用于回答“这条 AI 回答、知识、候选设定、检索证据来自哪里”。它不是复杂版本控制系统。

## 2. SourceRef v1 字段

```text
source_type: chapter | knowledge | summary | workspace | ai_card | author_manual
source_id: string
path: string
chapter_id?: string

anchor_type: document | heading | paragraph | paragraph_range | knowledge_field | card
heading_path?: string[]

paragraph_start?: int
paragraph_end?: int

field_path?: string
char_start?: int
char_end?: int

excerpt: string
excerpt_hash: string
source_hash: string
created_at: string
stale?: bool
```

## 3. 语义

- `paragraph_start/end`：Markdown 段落序号，从 0 或 1 开始必须全项目统一。
- `char_start/end`：仅相对于 `paragraph_start` 对应段落，不是全文 offset。
- `field_path`：Knowledge JSON 字段路径，例如 `fields.cultivation.current_realm`。
- `excerpt_hash`：摘录文本 hash，用于判断摘录是否还能匹配。
- `source_hash`：创建引用时源文件或源对象 hash，用于判断来源是否已变化。

## 4. 精度约束

MVP v1：

- 章节证据定位到 paragraph 或 paragraph_range。
- 编辑器选区额外记录段内 char_start/char_end。
- 知识库证据定位到 card + field_path。
- 检索结果返回 SourceRef，不返回 SQLite row id 作为证据。

不做：

- 全文稳定字符 offset。
- token offset。
- CRDT anchor。
- Markdown 隐藏 UUID 注释。
- Git commit 级定位。
- 复杂 re-anchor 算法。

## 5. 失效检测

`SourceRefResolver.validate(ref)` 最小行为：

1. 读取 ref 指向的 source。
2. 比较 source_hash。
3. 若不匹配，在同 source 内用 excerpt_hash 或 excerpt 做一次简单查找。
4. 若找到，返回 relocated ref 或提示可更新。
5. 若找不到，标记 `stale=true`，UI 显示“来源可能已变化”。

## 6. 禁止事项

- SourceRef 不指向 generated SQLite 行。
- EmbeddingChunk id 不能作为事实证据 id。
- AI 不得伪造 SourceRef。
- 没有来源的回答必须标记为推测。
