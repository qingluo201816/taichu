# 输出 Schema 契约

更新日期：2026-07-05

## 统一包装

所有按钮最后都包装为 `WritingAIResult`：

```json
{
  "run_id": "string",
  "button_type": "continue",
  "button_label": "续写",
  "status": "completed",
  "output_type": "text_candidate",
  "content": {},
  "evidence_items": [],
  "prompt_snapshot": {},
  "retrieval_context": {},
  "raw_llm_output": "string",
  "error": null
}
```

## output_type 对照

| 按钮 | output_type |
|---|---|
| 纯对话 | chat_answer |
| 续写 | text_candidate |
| 润色 | polished_text |
| 设定 | setting_suggestion |
| 建议 | writing_suggestion |
| 证据 | evidence_answer |
| 章节摘要 | chapter_summary |
| 灵感 | inspiration |
| 事实 | pending_fact_candidates |

## 注意

1. `evidence_items` 是 AI 运行记录的证据项，不是知识卡字段。
2. 不得把 `evidence_items` 写回知识卡 `source_refs`。
3. 最新知识库字段若废弃 `source_refs`，必须遵守。
4. 事实按钮输出的是 Inbox 待确认事实候选，不是知识卡。
5. 章节摘要按钮输出的是章节摘要结果，不进入正式知识库。
