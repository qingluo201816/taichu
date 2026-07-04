# LangGraph 节点契约

> 更新日期：2026-07-04

## 1. 主图

```text
Start
  ↓
LoadChapterNode
  ↓
SegmentChapterNode
  ↓
GeneralExtractionNode
  ↓
MergeChapterCandidatesNode
  ↓
TypeDispatchNode
  ↓
CharacterExpertNode
  ↓
EntityExpertNode
  ↓
NormalizeAndValidateNode
  ↓
RunInternalConflictCheckNode
  ↓
MatchExistingKnowledgeNode
  ↓
BuildReviewItemsNode
  ↓
WriteIntermediateJsonNode
  ↓
End
```

第一版 HumanReview 不放进 LangGraph interrupt/resume。LangGraph 结束后写 JSON 中间态，前端读取候选，作者通过普通 API 审核。

## 2. 节点职责

### LoadChapterNode

输入：

```text
chapter_id
```

输出：

```text
chapter_id
display_title
markdown_text
content_hash
word_count
```

失败：

```text
章节不存在
Markdown 文件不可读
正文为空
```

### SegmentChapterNode

规则：

```text
短章节：整章作为 LLM 输入。
长章节：按场景片段或段落窗口切分。
片段抽取后再章内合并候选。
```

第一版不要做多章节批次。

### GeneralExtractionNode

```text
调用真实 LLM。
使用 general_extraction_v1。
只抽 character、location、faction、item。
输出 raw_candidates。
记录 llm_call。
```

### MergeChapterCandidatesNode

```text
同一 run 内先按 name + aliases 规范化比较。
同名同类型合并。
同名但类型不同进入本轮冲突。
别名互相包含标记疑似重复。
```

### TypeDispatchNode

```text
角色候选进入 CharacterExpertNode。
location/faction/item 进入 EntityExpertNode。
event/rule/realm/technique/foreshadow 全部忽略。
```

### CharacterExpertNode

```text
调用真实 LLM。
使用 character_expert_v1。
输出角色卡草稿或更新建议。
禁止输出 personality、motivation、appearance。
```

### EntityExpertNode

```text
调用真实 LLM。
使用 entity_expert_v1。
只处理 location、faction、item。
不能编造知识卡 ID。
```

### NormalizeAndValidateNode

校验：

```text
字段白名单
枚举值
空值
chapter_id
source_origin
source_note
evidence_excerpt 长度
不含 fields/source_refs/body/tags/confidence
```

### RunInternalConflictCheckNode

检查：

```text
同一 run 内重复
同名不同类型
别名互相包含
字段冲突
```

### MatchExistingKnowledgeNode

规则：

```text
只匹配 active 知识卡。
不匹配 draft。
不匹配 deprecated。
```

### BuildReviewItemsNode

生成：

```text
create_card
update_card
conflict
ignore
```

### WriteIntermediateJsonNode

写入：

```text
project_assets/derived/agent_runs/knowledge_extraction/extract_run_<时间>_<短ID>.json
```

必须保存：

```text
nodes
llm_calls
raw_candidates
typed_candidates
review_items
metrics
errors
```

## 3. 节点状态

```text
pending
running
success
failed
skipped
```

失败节点必须写入 error，不得静默跳过。
