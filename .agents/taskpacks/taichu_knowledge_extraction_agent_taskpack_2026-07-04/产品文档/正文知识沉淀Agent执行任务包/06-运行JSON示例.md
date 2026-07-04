# 运行 JSON 示例

> 更新日期：2026-07-04

## 1. 顶层结构

```json
{
  "run_id": "extract_run_20260704_153022_a1b2c3",
  "agent_name": "knowledge_extraction",
  "agent_version": "v0.1",
  "schema_version": "knowledge_fields_v2",
  "prompt_version": "knowledge_extraction_prompt_v1",
  "model_name": "gpt-xxx",
  "status": "completed",
  "scope": {
    "scope_type": "chapter",
    "chapter_id": "chapter_0012",
    "chapter_title": "第12章 xxx",
    "content_hash": "sha256..."
  },
  "started_at": "2026-07-04T15:30:22+09:00",
  "finished_at": "2026-07-04T15:30:58+09:00",
  "nodes": [],
  "llm_calls": [],
  "raw_candidates": [],
  "typed_candidates": [],
  "review_items": [],
  "metrics": {},
  "errors": []
}
```

## 2. run status

```text
pending
running
completed
failed
```

第一版运行接口同步执行，不做 streaming，不做后台队列。

## 3. node 结构

```json
{
  "node_name": "GeneralExtractionNode",
  "status": "success",
  "started_at": "2026-07-04T15:30:25+09:00",
  "finished_at": "2026-07-04T15:30:34+09:00",
  "duration_ms": 9000,
  "input_summary": "第12章正文，约4200字",
  "output_summary": "抽出人物3个、地点1个、物品2个",
  "error": null
}
```

node status：

```text
pending
running
success
failed
skipped
```

## 4. llm_calls 结构

```json
{
  "call_id": "llm_call_001",
  "node_name": "GeneralExtractionNode",
  "model_name": "gpt-xxx",
  "prompt_version": "general_extraction_v1",
  "input_prompt": "完整 prompt 文本",
  "raw_response": "完整 response 文本",
  "parsed_output": {},
  "started_at": "2026-07-04T15:30:25+09:00",
  "finished_at": "2026-07-04T15:30:34+09:00",
  "duration_ms": 9000,
  "error": null
}
```

## 5. review_items 结构

```json
{
  "review_item_id": "review_item_001",
  "run_id": "extract_run_20260704_153022_a1b2c3",
  "candidate_action": "create_card",
  "knowledge_type": "character",
  "candidate_status": "pending",
  "display_title": "秦浩轩",
  "suggested_card": {},
  "target_card_id": null,
  "matched_card_name": null,
  "match_reason": "",
  "source_excerpt": "原文摘录，不超过300字",
  "schema_validation": {
    "passed": true,
    "errors": []
  },
  "internal_conflicts": [],
  "external_conflicts": [],
  "suggested_action_label": "建议创建新角色卡",
  "author_action": null,
  "created_knowledge_card_id": null,
  "updated_knowledge_card_id": null,
  "created_at": "2026-07-04T15:30:58+09:00",
  "updated_at": "2026-07-04T15:30:58+09:00"
}
```

candidate_action：

```text
create_card
update_card
conflict
ignore
```

candidate_status：

```text
pending
confirmed
rejected
deferred
```

knowledge_type 第一版：

```text
character
location
faction
item
```

## 6. metrics 示例

```json
{
  "candidate_total": 8,
  "character_candidate_count": 3,
  "location_candidate_count": 1,
  "faction_candidate_count": 1,
  "item_candidate_count": 3,
  "create_card_count": 5,
  "update_card_count": 2,
  "conflict_count": 1,
  "schema_passed_count": 7,
  "schema_failed_count": 1,
  "confirmed_count": 0,
  "rejected_count": 0,
  "pending_count": 8,
  "total_duration_ms": 36000,
  "llm_call_count": 3
}
```
