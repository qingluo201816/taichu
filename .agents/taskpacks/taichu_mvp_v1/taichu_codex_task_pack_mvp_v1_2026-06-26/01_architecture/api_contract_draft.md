# API 契约草案

> API 名称可随当前仓库风格微调，但语义和边界不可改。

## 1. Chapters

```text
GET    /api/chapters
GET    /api/chapters/{chapter_id}
POST   /api/chapters
PATCH  /api/chapters/{chapter_id}
POST   /api/chapters/{chapter_id}/save-markdown
POST   /api/chapters/reorder
```

规则：API 不接收 project_id / novel_id。

## 2. Selection AI

```text
POST /api/ai-cards/selection
```

请求：

```text
chapter_id
selection_range
selected_text
surrounding_text
mode: ask | enrich_setting | continue_text
user_prompt
target_words?
retrieval_policy?
```

响应：AIResultCard。

规则：不返回裸字符串；不走 AgentRegistry；不直接写 Knowledge。

## 3. AI Cards

```text
GET  /api/ai-cards
POST /api/ai-cards/{card_id}/insert
POST /api/ai-cards/{card_id}/save-to-inbox
POST /api/ai-cards/{card_id}/convert-to-pending-fact
POST /api/ai-cards/{card_id}/discard
POST /api/ai-cards/{card_id}/retry
```

## 4. Inbox

```text
GET  /api/inbox
GET  /api/inbox/ideas
POST /api/inbox/ideas
GET  /api/inbox/pending-facts
POST /api/inbox/pending-facts/{id}/ignore
```

## 5. Knowledge

```text
GET    /api/knowledge
GET    /api/knowledge/{id}
POST   /api/knowledge
PATCH  /api/knowledge/{id}
POST   /api/pending-facts/{id}/confirm
POST   /api/pending-facts/{id}/confirm-edited
```

## 6. Retrieval

```text
POST /api/retrieval/query
POST /api/retrieval/rebuild-index
```

默认 scope=fact_scope。workspace_scope 必须显式请求，响应必须标记非事实。

## 7. Export

```text
POST /api/export
GET  /api/export/{export_id}
```

导出：Markdown、Knowledge JSON、workspace JSONL、metadata。

## 8. Agent Chat

```text
GET  /api/agents
POST /api/agents/{agent_name}/invoke
```

Agent Chat 是 Phase 8。Selection AI 不通过此接口。
