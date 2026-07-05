# 统一 API 契约

更新日期：2026-07-05

## 创建运行

`POST /api/writing-ai/runs`

请求体：

```json
{
  "button_type": "continue",
  "chapter_id": "chapter-001",
  "reference_scope": "chapter",
  "user_input": "续写500字，保持压迫感",
  "selected_text": "",
  "selection_range": {
    "paragraph_start": 12,
    "paragraph_end": 14,
    "char_start": 0,
    "char_end": 120
  },
  "target_words": 500
}
```

响应体：

```json
{
  "run_id": "writing-ai-run-20260705-0001",
  "status": "completed",
  "button_type": "continue",
  "button_label": "续写",
  "model": "deepseek-chat",
  "chapter_id": "chapter-001",
  "reference_scope": "chapter",
  "prompt_snapshot": {
    "prompt_id": "continue_prompt_v1",
    "prompt_version": "1.0.0",
    "system_prompt": "...",
    "user_prompt": "...",
    "rendered_at": "2026-07-05T10:00:00+08:00"
  },
  "retrieval_context": {
    "used": true,
    "empty_reason": null,
    "items": []
  },
  "raw_llm_output": "...",
  "structured_output": {
    "output_type": "text_candidate",
    "content": {
      "text": "..."
    }
  },
  "error": null
}
```

## 查询详情

`GET /api/writing-ai/runs/{run_id}`

## 列表

`GET /api/writing-ai/runs?page=1&page_size=20&chapter_id=&button_type=&status=`

## 回放

`POST /api/writing-ai/runs/{run_id}/replay`

第一版 replay 不重新调用 LLM，只返回已保存 trace。
