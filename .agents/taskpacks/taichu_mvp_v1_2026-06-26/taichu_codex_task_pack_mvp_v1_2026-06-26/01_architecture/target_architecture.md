# 推荐目标架构

## 1. 后端目录

```text
src/taichu/
  main.py
  config.py

  api/
    deps.py
    router.py
    schemas/
      common.py
      chapters.py
      ai_cards.py
      inbox.py
      knowledge.py
      retrieval.py
      agents.py
      export.py
    routes/
      chapters.py
      ai_cards.py
      inbox.py
      knowledge.py
      retrieval.py
      agents.py
      export.py
      health.py

  application/
    capabilities.py
    contracts/
      storage.py
      retrieval.py
      llm.py
      indexer.py
    services/
      chapter_service.py
      selection_ai_service.py
      ai_card_service.py
      inbox_service.py
      knowledge_service.py
      retrieval_service.py
      index_service.py
      export_service.py
    workflows/
      selection/
        prompts.py
        schemas.py
        policy.py
    agents/
      contract.py
      registry.py
      chat/
    tools/
      contract.py
      registry.py
      retrieval_tool.py
      source_ref_tool.py
      word_count_tool.py
      entity_alias_tool.py

  domain/
    models/
      chapter.py
      source_ref.py
      ai_card.py
      inbox.py
      knowledge.py
      pending_fact.py
      retrieval.py
      summary.py
    rules/
      fact_scope.py
      card_state.py
      source_ref.py
      identity.py
    exceptions.py

  infrastructure/
    plugin_discovery.py
    storage/
      markdown_backend.py
      json_backend.py
      jsonl_backend.py
      sqlite_projection.py
    retrieval/
      exact.py
      fts.py
      vector_lite.py
      hybrid.py
    indexing/
      chunker.py
      fts_indexer.py
      embedding_indexer.py
      projection_rebuilder.py
    llm/
      factory.py
      providers/
    mcp/
```

## 2. 前端目录

```text
web/src/app/
  editor/
  inbox/
  knowledge/
  chat/
  settings/

web/src/components/
  editor/
  ai-card/
  inbox/
  knowledge/
  layout/
  ui/

web/src/lib/
  api-client.ts
  api/
    chapters.ts
    ai-cards.ts
    inbox.ts
    knowledge.ts
    retrieval.ts
    agents.ts
    export.ts
  types/
```

## 3. 数据目录

```text
project_assets/
  source/
    metadata.yaml
    manuscripts/
      manifest.json
      chapters/
    knowledge/
      characters/
      worldbuilding/
      techniques/
      locations/
      factions/
      items/
      events/
      foreshadows/
    workspace/
      ai_cards.jsonl
      ideas.jsonl
      pending_facts.jsonl
      chapter_summaries.jsonl
      editor_state.json
  generated/
    sqlite/
      taichu.db
    search_index/
    vector_store/
    embedding_cache/
    exports/
    temp/
```

## 4. 依赖方向

```text
api -> application -> domain
application -> contracts
infrastructure -> contracts implementation
main.py -> 组装 infrastructure 并注入 application
web -> API only
```

禁止：

- domain 依赖 FastAPI、LangGraph、LLM、SQLite、文件系统。
- application import 具体 infrastructure 实现。
- infrastructure 编写小说业务规则。
- API route 直接操作 project_assets。
- 前端直接访问 project_assets、SQLite、LLM、向量库。

## 5. Service / Workflow / Tool / Agent 边界

Service：产品用例，例如章节保存、Selection AI、卡片状态变化、PendingFact 确认、知识库编辑。

Workflow：一个 Service 内部的多步骤 AI 流程，例如 selection ask/enrich/continue 的 prompt、上下文构建、结构化解析、失败降级。

Tool：可复用原子能力，例如检索、字数统计、SourceRef 解析、实体别名匹配。

Agent：独立深度对话或复杂编排能力，例如 chat、review、long_context_planning。Agent 可以调用 Tool，不直接写文件或绕过 Service 状态机。

Domain：技术无关规则，例如卡片状态是否合法、PendingFact 是否可确认、SourceRef 是否有效、fact_scope 是否允许读取。

Infrastructure：具体 Markdown/JSON/JSONL/SQLite/FTS/Embedding/LLM 实现。
