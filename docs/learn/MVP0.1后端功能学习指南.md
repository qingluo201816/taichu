# MVP0.1 后端功能学习指南

> 更新日期：2026-06-28

## 0. 阅读原则

这是一份学习快照文档，放在 `docs/learn/` 下，目的是帮助你回看 MVP0.1 后端当时实现了什么、代码如何组织、后续怎么微调或删除功能。

重要原则：

- `docs/learn/` 下的文档不作为后续判断当前功能的事实依据。
- `docs/learn/` 下的文档不会持续更新，未来可能过时。
- 后续做需求分析、代码分析、功能判断、方案设计时，必须以 `src/taichu/`、`tests/`、`README.md`、项目规则文件和实际运行结果为准。
- 本文生成时没有参考 `docs/learn/` 下已有旧文档，只参考了当前代码、测试、`README.md` 和 `docs/rule.md`。

## 1. MVP0.1 最后实现了什么

MVP0.1 后端已经形成一个完整的个人写作闭环：

```text
章节写作
-> 选区 AI
-> AIResultCard
-> Inbox
-> PendingFact
-> 作者确认 Knowledge
-> generated rebuild
-> Agent Chat 基于 fact_scope 对话
-> Export source bundle
```

已实现的后端能力：

- 章节列表、章节读取、章节 Markdown 保存。
- 编辑器选区 AI：提问建议、补设定、续写正文候选。
- AIResultCard 统一保存、查询和状态流转。
- 创作收件箱 Inbox：灵感、待确认设定、已保存 AI 卡片、章节问题四条 lane。
- PendingFact 确认、编辑后确认、拒绝或忽略。
- Knowledge 知识库读取和作者确认写入。
- 章节总结工作流，包含关键事件、人物变化、新设定候选、伏笔候选、下一章钩子。
- generated 派生数据清空和重建。
- SQLite FTS 检索投影。
- Agent Chat 基于当前章节、已确认 Knowledge、检索证据回答，并把回答保存为 AIResultCard。
- source bundle 可读导出。
- Agent 插件发现、注册和 manifest 查询。
- Tool 插件注册基础设施，但当前没有形成用户可见工具调用入口。

仅预留但没有形成完整 MVP0.1 用户入口的能力：

- `AIWorkflow.POLISH`、`AIWorkflow.RETRIEVE`：枚举存在，但没有对应 API 工作流。
- `AIResultCardType.EVIDENCE`、`AIResultCardType.INSPIRATION`：类型存在，但主要链路没有生成或消费它们。
- `CharacterCard`：领域模型存在，但没有专门 API。
- `ImportService.import_text`：服务和测试存在，能导入文本并切章，但没有挂成公开 API。
- `RetrievalService`：薄包装存在，当前实际使用的是 `SqliteFTSRetrievalBackend`。
- `ToolRegistry` 和工具插件协议：基础设施存在，但没有产品级工具入口。
- `application/agents/chat/graph.py` 的 LangGraph 图：插件 manifest 会注册，但当前产品 API `/api/agents/chat` 走 `ChatAgentService`，不是直接暴露旧 `/api/chat`。

明确未实现或已移除的能力：

- 不支持多小说、多租户、项目切换、`project_id`。
- 不支持旧 `/api/chat`。当前 Agent 对话入口是 `/api/agents/chat`。
- 不支持流式 Agent Chat。manifest 里 `supports_streaming=false`。
- 不支持直接通过 API 创建或删除章节。
- 不支持直接手写 Knowledge CRUD。Knowledge 只能读取，写入来自 PendingFact 确认链路。
- 不支持向量检索；当前是 SQLite FTS 与精确项混合检索。
- 不支持把 AI 输出自动提升为事实。
- 不支持把 generated 目录里的 SQLite 行、数据库文件或缓存当作证据来源。

## 2. 安装、配置与启动

项目固定使用 `uv`，不要用 `pip`、`poetry`、`pipenv`。

安装依赖：

```powershell
uv sync
```

本次执行结果：

```text
Resolved 60 packages in 2ms
Checked 59 packages in 11ms
```

环境变量来自 `.env`，示例在 `.env.example`：

```text
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your-key
DEEPSEEK_API_BASE=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-pro
HOST=127.0.0.1
PORT=8000
PROJECT_ASSETS_DIR=project_assets
```

配置模型在 `src/taichu/config.py`：

- `llm_provider` 默认 `deepseek`。
- `deepseek_api_key` 默认空字符串。
- `deepseek_api_base` 默认 `https://api.deepseek.com/v1`。
- `deepseek_model` 默认 `deepseek-chat`。
- `host` 默认 `127.0.0.1`。
- `port` 默认 `8000`。
- `project_assets_dir` 默认 `project_assets`。

启动后端：

```powershell
uv run taichu
```

等价于执行 `taichu.main:main`，底层启动：

```text
uvicorn.run("taichu.main:app", host=settings.host, port=settings.port, reload=False)
```

一键启动仍以根目录 `start.bat` 为项目约定入口。本文只分析后端代码，不修改启动脚本。

## 3. 总装入口：后端应用如何被组起来

总装函数是 `src/taichu/main.py` 里的 `create_app()`。

它做了这些事：

1. 创建源资产和工作区存储：
   - `JsonStorageBackend(app_settings.project_assets_dir / "source")`
   - `ProjectAssetStorageBackend(app_settings.project_assets_dir)`
2. 创建章节服务：
   - `ChapterService(project_storage)`
3. 创建 LLM：
   - 如果测试注入 `llm`，就使用测试模型。
   - 否则通过 `create_llm(app_settings)` 创建 DeepSeek 模型。
4. 包装 LLM 协议：
   - `LangChainLLMAdapter(chat_model)`
5. 创建应用服务：
   - `AICardService`
   - `InboxService`
   - `KnowledgeService`
   - `PendingFactConfirmationService`
   - `SelectionAIService`
   - `IndexService`
   - `ExportService`
   - `ChatAgentService`
   - `ChapterSummaryService`
6. 创建检索和索引组件：
   - `SqliteFTSRetrievalBackend`
   - `SqliteProjectionRebuilder`
7. 创建能力上下文：
   - `llm`
   - `retrieval`
   - `storage`
8. 发现并注册 Agent：
   - `discover_agents("taichu.application.agents")`
   - `AgentRegistry.register_all(...)`
9. 发现并注册 Tool：
   - `discover_tools("taichu.application.tools")`
   - `ToolRegistry.register_all(...)`
10. 创建 FastAPI 应用，把服务挂到 `application.state`。
11. 添加 CORS。
12. 调用 `register_routes(application)` 挂载 API。

当前 `src/taichu/api/router.py` 只注册这 6 组路由：

```text
agents
ai_cards
chapters
export
inbox
knowledge
```

这就是为什么旧 `/api/chat` 不存在。旧入口没有被 include，测试也明确要求它返回 404。

## 4. 数据地图：source、workspace、generated

MVP0.1 最重要的数据原则是：正文和作者确认内容是事实源，索引和缓存可重建。

### 4.1 source：源资产

根目录默认是 `project_assets/source/`。

章节事实源：

```text
project_assets/source/manuscripts/manifest.json
project_assets/source/manuscripts/chapters/<chapter_id>.md
```

已确认 Knowledge 事实源：

```text
project_assets/source/knowledge/characters/
project_assets/source/knowledge/worldbuilding/
project_assets/source/knowledge/techniques/
project_assets/source/knowledge/locations/
project_assets/source/knowledge/factions/
project_assets/source/knowledge/items/
project_assets/source/knowledge/events/
project_assets/source/knowledge/foreshadows/
```

### 4.2 workspace：工作区资产

工作区资产也在 `source` 下，因为它们需要可读、可导出、可迁移，但默认不进入事实检索范围：

```text
project_assets/source/workspace/ai_cards.jsonl
project_assets/source/workspace/ideas.jsonl
project_assets/source/workspace/pending_facts.jsonl
project_assets/source/workspace/chapter_issues.jsonl
project_assets/source/workspace/chapter_summaries.jsonl
project_assets/source/workspace/editor_state.json
```

这些资产不是默认事实：

- AIResultCard 不是事实。
- IdeaCard 不是事实。
- PendingFact 在确认前不是事实。
- ChapterSummary 不是事实。
- ChapterIssue 不是事实。

### 4.3 generated：派生数据

派生数据在 `project_assets/generated/`：

```text
project_assets/generated/sqlite/
project_assets/generated/search_index/
project_assets/generated/vector_store/
project_assets/generated/embedding_cache/
project_assets/generated/exports/
project_assets/generated/temp/
```

当前实际可用的是：

```text
project_assets/generated/sqlite/taichu.db
```

它由 `SqliteProjectionRebuilder` 从 source 重建。可以删除，不应该人工编辑，不可以当作证据来源。

### 4.4 fact_scope：默认事实范围

`src/taichu/domain/rules/fact_scope.py` 定义：

- `fact_scope` 只允许章节正文和 `status=confirmed` 的 Knowledge。
- `workspace_scope` 包含 PendingFact、Idea、AIResultCard、ChapterSummary。
- `debug_scope` 对应 generated。

判断函数：

- `resolve_retrieval_scope()`：把 scope 名称解析成来源集合，默认是 `fact_scope`。
- `is_allowed_in_fact_scope()`：判断某个领域对象是否允许进入默认事实范围。
- `assert_allowed_in_fact_scope()`：不允许时抛出 `FactScopeViolationError`。

这条规则是 MVP0.1 防止 AI 污染事实源的核心。

## 5. 分层结构

后端采用清晰分层：

```text
api
-> application
-> domain
-> infrastructure
```

### 5.1 api 层

位置：

```text
src/taichu/api/
```

职责：

- 定义 HTTP 路由。
- 定义请求响应 Schema。
- 从 `request.app.state` 取应用服务。
- 把领域异常转换成 HTTP 状态码。
- 不直接写文件，不直接调 LLM，不写业务规则。

### 5.2 application 层

位置：

```text
src/taichu/application/
```

职责：

- 编排用例。
- 调用 LLM、存储、检索等契约。
- 维护 AI 卡片、章节总结、PendingFact 确认、导出等业务流程。
- 定义跨层 Protocol 契约。

### 5.3 domain 层

位置：

```text
src/taichu/domain/
```

职责：

- 定义领域模型。
- 定义状态机和事实范围规则。
- 不依赖 FastAPI、LLM、LangGraph、SQLite、文件系统。

### 5.4 infrastructure 层

位置：

```text
src/taichu/infrastructure/
```

职责：

- 文件系统存储实现。
- SQLite FTS 检索实现。
- generated 投影重建。
- LLM provider 创建。
- 插件发现。

## 6. API 功能入口总览

| 功能入口 | 方法与路径 | 请求模型 | 响应模型 | 主要服务 | 写入位置 | 是否进入事实源 |
|---|---|---|---|---|---|---|
| 章节列表 | `GET /api/chapters` | 无 | `ChapterListResponse` | `ChapterService.list_chapters` | 不写入 | 读取章节事实源 |
| 章节读取 | `GET /api/chapters/{chapter_id}` | path | `ChapterReadResponse` | `ChapterService.read_chapter` | 不写入 | 读取章节事实源 |
| 章节保存 | `PUT /api/chapters/{chapter_id}` | `ChapterSaveRequest` | `ChapterReadResponse` | `ChapterService.save_chapter` | `manuscripts` | 是，修改正文事实源 |
| 选区 AI | `POST /api/ai-cards/selection` | `SelectionAIRequest` | `AICardResponse` | `SelectionAIService.run_selection` | `workspace/ai_cards.jsonl` | 否 |
| AI 卡片列表 | `GET /api/ai-cards` | query | `AICardListResponse` | `AICardService.list_cards` | 不写入 | 否 |
| AI 卡片动作 | `POST /api/ai-cards/{card_id}/actions` | `AICardActionRequest` | `AICardResponse` | `AICardService` | `workspace/ai_cards.jsonl` 或 `ideas.jsonl` | 否 |
| Inbox 读取 | `GET /api/inbox` | 无 | `InboxResponse` | `InboxService.list_inbox` | 不写入 | 否 |
| 保存灵感 | `POST /api/inbox/cards/{card_id}/save-idea` | path | `SaveIdeaResponse` | `InboxService.save_card_as_idea` | `ideas.jsonl`、`ai_cards.jsonl` | 否 |
| 卡片转待确认设定 | `POST /api/inbox/cards/{card_id}/convert-pending-fact` | path | `ConvertPendingFactResponse` | `InboxService.convert_card_to_pending_fact` | `pending_facts.jsonl`、`ai_cards.jsonl` | 否 |
| 忽略待确认设定 | `POST /api/inbox/pending-facts/{pending_fact_id}/ignore` | path | `PendingFactActionResponse` | `InboxService.ignore_pending_fact` | `pending_facts.jsonl` | 否 |
| Knowledge 列表 | `GET /api/knowledge` | 无 | `KnowledgeListResponse` | `KnowledgeService.list_cards` | 不写入 | 读取 Knowledge 事实源 |
| 确认 PendingFact | `POST /api/pending-facts/{pending_fact_id}/confirm` | path | `PendingFactConfirmationResponse` | `PendingFactConfirmationService.confirm_pending_fact` | `knowledge`、`pending_facts.jsonl` | 是 |
| 编辑后确认 PendingFact | `POST /api/pending-facts/{pending_fact_id}/confirm-edited` | `ConfirmEditedPendingFactRequest` | `PendingFactConfirmationResponse` | `PendingFactConfirmationService.confirm_pending_fact_with_edits` | `knowledge`、`pending_facts.jsonl` | 是 |
| 拒绝 PendingFact | `POST /api/pending-facts/{pending_fact_id}/reject` | path | `PendingFactRejectionResponse` | `PendingFactConfirmationService.reject_pending_fact` | `pending_facts.jsonl` | 否 |
| 章节总结生成 | `POST /api/chapters/{chapter_id}/summary` | path | `ChapterSummaryRunResponse` | `ChapterSummaryService.summarize_chapter` | `chapter_summaries.jsonl`、`ai_cards.jsonl` | 否 |
| 章节总结列表 | `GET /api/chapters/{chapter_id}/summaries` | path | `ChapterSummaryListResponse` | `ChapterSummaryService.list_summaries` | 不写入 | 否 |
| 总结确认或忽略 | `POST /api/chapter-summaries/{summary_id}/actions` | `ChapterSummaryActionRequest` | `ChapterSummaryResponse` | `ChapterSummaryService.confirm_summary` 或 `ignore_summary` | `chapter_summaries.jsonl` | 否 |
| 总结候选转 PendingFact | `POST /api/chapter-summaries/{summary_id}/pending-facts/{pending_fact_id}` | path | `PendingFactResponse` | `ChapterSummaryService.convert_candidate_to_pending_fact` | `pending_facts.jsonl` | 否 |
| Agent 列表 | `GET /api/agents` | 无 | `AgentListResponse` | `AgentRegistry.list_manifests` | 不写入 | 否 |
| Agent Chat | `POST /api/agents/chat` | `AgentChatRequest` | `AgentChatResponse` | `ChatAgentService.run` | `ai_cards.jsonl` | 否 |
| 导出 source bundle | `GET /api/export/bundle` | 无 | `ExportBundleResponse` | `ExportService.build_bundle` | 不写入 | 导出 source，不导出 generated |
| 重建 generated | `POST /api/generated/rebuild` | 无 | `IndexBuildJobResponse` | `IndexService.rebuild_generated_projection` | `generated/sqlite/taichu.db` | 不改 source |
| 清空 generated | `POST /api/generated/clear` | 无 | `IndexBuildJobResponse` | `IndexService.clear_generated` | `generated/` | 不改 source |

## 7. 功能入口详解

### 7.1 章节管理

代码位置：

- API：`src/taichu/api/routes/chapters.py`
- Schema：`src/taichu/api/schemas/chapters.py`
- Service：`src/taichu/application/services/chapter_service.py`
- Model：`src/taichu/domain/models/chapter.py`
- Storage：`src/taichu/infrastructure/storage/markdown_backend.py`

API 函数：

- `api_list_chapters()`：返回 manifest 中的章节列表。
- `api_read_chapter(chapter_id)`：读取单章 Markdown。
- `api_save_chapter(chapter_id, request)`：保存已存在章节的 Markdown。

服务函数：

- `ChapterService.ensure_project_skeleton()`：保证目录骨架存在。
- `ChapterService.get_manifest()`：读取 `manuscripts/manifest.json` 并校验成 `ChapterManifest`。
- `ChapterService.list_chapters()`：按 `order` 排序返回章节。
- `ChapterService.read_chapter()`：先找章节元数据，再读 Markdown。
- `ChapterService.save_chapter()`：写 Markdown，重新计算非空白字符数，更新 `current_chapter_id`、`updated_at` 和 manifest。
- `ChapterService.clear_generated_projection_stub()`：旧式清空 generated 的 stub，当前主要由 `IndexService` 承担。
- `ChapterService._find_chapter()`：按 id 查 manifest，找不到抛 `ChapterNotFoundError`。

写入行为：

- `PUT /api/chapters/{chapter_id}` 会修改事实源。
- 写入章节 Markdown：`project_assets/source/manuscripts/chapters/<chapter_id>.md`。
- 写入 manifest：`project_assets/source/manuscripts/manifest.json`。

关键边界：

- 只能保存 manifest 已存在章节。
- 当前没有公开 API 创建章节、删除章节或调整章节顺序。
- AI 续写不会自动写正文，必须由前端拿到正文候选后再调用章节保存。

微调建议：

- 想增加创建章节，应优先扩展 `ChapterService`，同时更新 manifest 写入逻辑和集成测试。
- 想修改字数统计，改 `_count_non_space()`，并补充章节保存测试。
- 不要绕过 `ProjectAssetStorageBackend._resolve_safe_chapter_path()` 直接拼路径写文件。

### 7.2 选区 AI

代码位置：

- API：`src/taichu/api/routes/ai_cards.py`
- Schema：`src/taichu/api/schemas/ai_cards.py`
- Service：`src/taichu/application/services/selection_ai_service.py`
- Workflow Schema：`src/taichu/application/workflows/selection/schemas.py`

API 函数：

- `api_create_selection_ai_card()`：接收编辑器选区上下文，调用 `SelectionAIService.run_selection()`。

请求核心字段：

- `mode`：`ask`、`enrich_setting`、`continue_text`。
- `selection_context.chapter_id`：当前章节。
- `selection_context.selected_text`：选中文本。
- `selection_context.surrounding_text`：周边上下文。
- `selection_context.selection_range`：编辑器坐标。
- `selection_context.source_ref`：选区证据来源。
- `user_prompt`：作者提示。
- `target_words`：续写目标字数。
- `parent_card_id`：重试时的父卡片。

服务函数：

- `SelectionAIService.run_selection()`：构造 `SelectionWorkflowInput`，可选地把父卡片标记为 `retried`，调用 LLM，构造并保存 AIResultCard。
- `SelectionAIService._build_card()`：解析模型输出，决定卡片类型和内容。
- `build_selection_prompt()`：生成要求模型只返回 JSON object 的 prompt。
- `_workflow_for_mode()`：把模式映射为 `ask_selection`、`enrich_setting`、`continue_text`。
- `_parse_json_object()`：解析 LLM 原始输出。
- `_card_type_for_response()`：读取模型返回的 `card_type`。
- `_default_card_type()`：模型输出不合规时选择默认类型。
- `_card_type_allowed_for_mode()`：限制不同模式允许的卡片类型。
- `_content_for_card_type()`：把模型 JSON 转成卡片 content。
- `_text_candidate_content()`：提取可插入正文。
- `_pending_fact_content()`：把模型输出包装成 `PendingFact` 结构，但只放进 AI 卡片内容。
- `_pending_fact_type()`、`_text_field()`、`_now_iso()`：辅助转换。

三种模式：

| 模式 | 目标 | 允许返回卡片 | 默认卡片 | 是否改正文 | 是否进事实源 |
|---|---|---|---|---|---|
| `ask` | 对选区提问或建议 | `suggestion` | `suggestion` | 否 | 否 |
| `enrich_setting` | 补设定 | `suggestion` 或 `pending_fact` | `suggestion` | 否 | 否 |
| `continue_text` | 续写正文候选 | `text_candidate` | `text_candidate` | 否 | 否 |

写入行为：

- 只写 `project_assets/source/workspace/ai_cards.jsonl`。
- 不改章节 Markdown。
- 不写 Knowledge。

失败降级：

- 如果 LLM 没有返回可解析 JSON，系统会生成 `suggestion` 卡片，内容说明“智能助手输出解析失败”，并保留 `raw_text`。

微调建议：

- 想改变选区 AI 输出格式，改 `build_selection_prompt()` 和 `_content_for_card_type()`。
- 想增加新模式，需要同时改 API 枚举、Service 枚举、工作流映射、测试。
- 想让某类输出进入事实源，不能在这里直接写 Knowledge，必须走 PendingFact 确认链路。

### 7.3 AIResultCard 生命周期

代码位置：

- Service：`src/taichu/application/services/ai_card_service.py`
- Model：`src/taichu/domain/models/ai_card.py`
- 状态机：`src/taichu/domain/rules/card_state.py`

API 函数：

- `api_list_ai_cards()`：列出全部或某章的卡片。
- `api_apply_ai_card_action()`：对卡片执行 `inserted`、`save_to_idea`、`discard`。

领域类型：

- `text_candidate`：正文候选。
- `suggestion`：建议。
- `pending_fact`：待确认设定卡。
- `chapter_summary`：章节总结卡。
- `evidence`：预留。
- `inspiration`：预留。

领域状态：

- `generated`：刚生成。
- `inserted`：正文候选已被插入。
- `saved_to_inbox`：建议已保存到 Inbox。
- `converted_to_pending_fact`：待确认设定卡已转入 PendingFact。
- `discarded`：丢弃。
- `retried`：被重试生成了子卡。

状态机：

```text
generated
-> inserted
-> saved_to_inbox
-> converted_to_pending_fact
-> discarded
-> retried
```

其他状态都是终态。

服务函数：

- `AICardService.create_card()`：追加写入 `ai_cards.jsonl`。
- `AICardService.list_cards()`：读取并可按章节过滤。
- `AICardService.get_card()`：按 id 查卡片。
- `AICardService.mark_inserted()`：只有 `text_candidate` 能标记为已插入。
- `AICardService.discard_card()`：标记丢弃。
- `AICardService.mark_retried()`：标记重试。
- `AICardService.save_suggestion_as_idea()`：只有 `suggestion` 能保存成 IdeaCard。
- `AICardService.convert_card_to_pending_fact()`：只有 `pending_fact` 能转 PendingFact。
- `AICardService._transition_card()`：校验状态迁移并重写卡片。
- `AICardService._replace_card()`：重写 `ai_cards.jsonl`。
- `AICardService._find_idea_by_source_card()`：查找是否已保存灵感，保证幂等。
- `AICardService._find_pending_fact()`：查找是否已转换 PendingFact，保证幂等。
- `_idea_content()`：从建议卡 content 中提取文本。

写入行为：

- 所有卡片主记录在 `workspace/ai_cards.jsonl`。
- 保存灵感会追加 `workspace/ideas.jsonl`。
- 转 PendingFact 会追加 `workspace/pending_facts.jsonl`。

关键边界：

- 标记 `inserted` 只是卡片状态变化，不会写章节正文。
- `save_to_idea` 只适用于建议卡。
- `convert-pending-fact` 只适用于待确认设定卡。
- 状态机不允许终态再变更。

### 7.4 创作收件箱 Inbox

代码位置：

- API：`src/taichu/api/routes/inbox.py`
- Schema：`src/taichu/api/schemas/inbox.py`
- Service：`src/taichu/application/services/inbox_service.py`
- Model：`src/taichu/domain/models/inbox.py`

Inbox 四条 lane：

- `ideas`：灵感。
- `pending_facts`：待确认设定，只显示 `status=pending`。
- `saved_ai_cards`：已保存到收件箱的 AI 卡片。
- `chapter_issues`：章节问题，只显示 `status=open`。

API 函数：

- `api_read_inbox()`：读取四条 lane。
- `api_save_card_as_idea()`：把建议卡保存为灵感。
- `api_convert_card_to_pending_fact()`：把待确认设定卡转成 PendingFact。
- `api_ignore_pending_fact()`：忽略 PendingFact。
- `_idea_info()`、`_pending_fact_info()`、`_saved_ai_card_info()`、`_chapter_issue_info()`：组装响应。
- `_chapter_id_from_pending_fact()`：从 SourceRef 里推导章节。
- `_editor_href()`：生成前端跳转地址。

服务函数：

- `InboxService.list_inbox()`：读取四条 JSONL lane 并过滤状态。
- `InboxService.save_card_as_idea()`：委托给 `AICardService`。
- `InboxService.convert_card_to_pending_fact()`：委托给 `AICardService`。
- `InboxService.ignore_pending_fact()`：把 PendingFact 状态改为 `ignored`。

写入行为：

- 读取 Inbox 不写入。
- 保存灵感写 `ideas.jsonl`，并改 `ai_cards.jsonl` 的卡片状态。
- 转 PendingFact 写 `pending_facts.jsonl`，并改 `ai_cards.jsonl` 的卡片状态。
- 忽略 PendingFact 只改 `pending_facts.jsonl`。

关键边界：

- Inbox 是工作区，不是事实源。
- PendingFact 即使在 Inbox 中出现，也不进入 `fact_scope`。
- 忽略和拒绝都是让 PendingFact 离开事实链路，不写 Knowledge。

### 7.5 PendingFact 确认、编辑后确认、拒绝

代码位置：

- API：`src/taichu/api/routes/knowledge.py`
- Schema：`src/taichu/api/schemas/knowledge.py`
- Service：`src/taichu/application/services/pending_fact_confirmation_service.py`
- Knowledge Service：`src/taichu/application/services/knowledge_service.py`
- Model：`src/taichu/domain/models/pending_fact.py`

API 函数：

- `api_confirm_pending_fact()`：无编辑确认。
- `api_confirm_pending_fact_with_edits()`：作者编辑后确认。
- `api_reject_pending_fact()`：拒绝，不写 Knowledge。
- `_pending_fact_info()`：输出 PendingFact。
- `_knowledge_info()`：输出 KnowledgeCard。

服务函数：

- `confirm_pending_fact()`：把 pending -> confirmed。
- `confirm_pending_fact_with_edits()`：把 pending -> edited_confirmed。
- `reject_pending_fact()`：把 pending -> ignored。
- `_confirm()`：确认主流程。
- `_confirmed_knowledge_for()`：幂等处理，已确认的 PendingFact 取已有 Knowledge。
- `_list_pending_fact_records()`：读取 `pending_facts.jsonl`。
- `_replace_pending_fact()`：重写 `pending_facts.jsonl`。
- `_find_pending_fact()`：找待确认设定。
- `_knowledge_card_from_pending_fact()`：把 PendingFact 转为 KnowledgeCard。
- `_knowledge_type_for_pending_fact()`：类型映射。
- `_knowledge_id_for_pending_fact()`：生成稳定 Knowledge id。
- `_fields_from_content()`：从 PendingFact 内容生成 fields。
- `_summary_from_content()`：提取 summary。

PendingFact 类型到 Knowledge 类型的映射：

| PendingFact | Knowledge |
|---|---|
| `character` | `character` |
| `realm` | `realm` |
| `technique` | `technique` |
| `location` | `location` |
| `faction` | `faction` |
| `item` | `item` |
| `rule` | `rule` |
| `event` | `event` |
| `foreshadow` | `foreshadow` |
| `other` | `rule` |

写入行为：

- 确认会写 Knowledge JSON 到 `project_assets/source/knowledge/<category>/<id>.json`。
- 同时更新 `workspace/pending_facts.jsonl`：状态、`target_knowledge_id`、`confirmed_at`。
- 拒绝只更新 `workspace/pending_facts.jsonl`。

错误与状态码：

- 找不到 PendingFact：404。
- 身份冲突：409。
- 状态迁移非法：409。
- 写入校验失败或类型不支持：422。

关键边界：

- 这是 AI 候选进入事实源的唯一后端通路。
- 确认时必须带证据来源 `source_refs`。
- 确认后才会成为 `fact_scope` 可读取的 Knowledge。

### 7.6 Knowledge 知识库

代码位置：

- API：`src/taichu/api/routes/knowledge.py`
- Service：`src/taichu/application/services/knowledge_service.py`
- Model：`src/taichu/domain/models/knowledge.py`

API 函数：

- `api_list_knowledge()`：列出所有已确认 Knowledge。

服务函数：

- `KnowledgeService.list_cards()`：只返回 `status=confirmed` 的 Knowledge。
- `KnowledgeService.list_all_cards()`：返回所有 Knowledge 记录。
- `KnowledgeService.get_card()`：按 id 查已确认 Knowledge。
- `KnowledgeService.write_confirmed_card()`：写入 confirmed Knowledge，或复用同 id 已存在记录。
- `KnowledgeService._assert_no_identity_conflict()`：校验名称和别名冲突。
- `knowledge_category_for_type()`：把 Knowledge 类型映射到目录。
- `_validate_knowledge_source_refs()`：必须有 SourceRef，并通过本地证据形状校验。
- `_identity_terms()`、`_normalize_identity()`：身份冲突判断。

Knowledge 分类目录：

| 类型 | 目录 |
|---|---|
| `character` | `characters` |
| `realm` | `worldbuilding` |
| `technique` | `techniques` |
| `location` | `locations` |
| `faction` | `factions` |
| `item` | `items` |
| `rule` | `worldbuilding` |
| `event` | `events` |
| `foreshadow` | `foreshadows` |

关键边界：

- 没有公开 API 直接创建或编辑 Knowledge。
- Knowledge 写入要求 `status=confirmed`。
- Knowledge 写入要求 SourceRef，不允许无证据入库。
- 同名或别名冲突会阻止写入。

### 7.7 章节总结

代码位置：

- API：`src/taichu/api/routes/chapters.py`
- Schema：`src/taichu/api/schemas/chapters.py`
- Service：`src/taichu/application/services/chapter_summary_service.py`
- Prompt：`src/taichu/application/workflows/summary/prompts.py`
- Output Schema：`src/taichu/application/workflows/summary/schemas.py`
- Model：`src/taichu/domain/models/summary.py`

API 函数：

- `api_summarize_chapter()`：生成章节总结和一张章节总结 AI 卡片。
- `api_list_chapter_summaries()`：列出某章总结。
- `api_apply_summary_action()`：确认或忽略总结。
- `api_convert_summary_candidate()`：把总结里的新设定候选转成 PendingFact。
- `_summary_info()`、`_summary_edit()`：响应转换和编辑字段转换。

服务函数：

- `summarize_chapter()`：读取章节，构造 SourceRef，切分段落，结合已确认 Knowledge 和检索结果生成总结。
- `list_summaries()`：读取 `chapter_summaries.jsonl`。
- `confirm_summary()`：把总结状态改为 confirmed，可应用作者编辑，但不写 Knowledge。
- `ignore_summary()`：把总结状态改为 ignored。
- `convert_candidate_to_pending_fact()`：把总结候选追加到 `pending_facts.jsonl`。
- `_append_pending_fact_once()`：保证候选不是 fact_scope 对象，且避免重复追加。
- `_get_summary()`、`_replace_summary()`：查找和重写总结记录。
- `_parse_summary_output()`：解析 LLM JSON 输出。
- `_fallback_summary()`：模型输出不可用时从正文摘录兜底。
- `_candidate_pending_facts()`：把模型候选转成 PendingFact。
- `_candidate_key()`：候选去重 key。
- `_chapter_segments()`：按字符上限切分章节段落。
- `_chapter_source_ref()`：生成整章 SourceRef。
- `_is_empty_chapter()`：识别空章节。
- `_plain_excerpt()`、`_retrieval_query_text()`：生成摘要和检索文本。

写入行为：

- 生成总结写 `workspace/chapter_summaries.jsonl`。
- 同时写一张 `chapter_summary` 类型的 AIResultCard 到 `workspace/ai_cards.jsonl`。
- 确认或忽略总结只改 `chapter_summaries.jsonl`。
- 总结候选转 PendingFact 写 `workspace/pending_facts.jsonl`。
- 章节总结本身不写 Knowledge。

关键边界：

- “确认章节总结”不等于“确认设定入库”。
- 总结里的新设定候选仍必须转 PendingFact，再由作者确认成 Knowledge。
- 章节总结可作为工作区资产导出，但默认不进入 fact_scope。

### 7.8 generated 重建与 SQLite FTS 检索

代码位置：

- API：`src/taichu/api/routes/export.py`
- Service：`src/taichu/application/services/index_service.py`
- Indexer：`src/taichu/infrastructure/indexing/projection_rebuilder.py`
- Retrieval：`src/taichu/infrastructure/retrieval/sqlite_fts.py`

API 函数：

- `api_rebuild_generated()`：清空 generated 并重建 SQLite 投影。
- `api_clear_generated()`：只清空 generated。
- `_job_info()`：把 `IndexBuildJob` 转响应。

服务函数：

- `IndexService.clear_generated()`：调用存储清空 generated，返回 job。
- `IndexService.rebuild_generated_projection()`：先清空 generated，再调用 indexer 重建。
- `_job()`：构造 `IndexBuildJob`。

重建函数：

- `SqliteProjectionRebuilder.rebuild()`：异步转线程执行重建。
- `_rebuild_sync()`：重建 `generated/sqlite/taichu.db`。
- `_chapter_documents()`：把章节按段落转成检索文档。
- `_knowledge_documents()`：读取所有 confirmed Knowledge。
- `_knowledge_card_documents()`：把 Knowledge 的 name、summary、fields 展开成检索文档。
- `_knowledge_document()`：构造单条 Knowledge 检索文档和 SourceRef。
- `_resolve_source_path()`：确保索引来源只在 source 内。
- `_create_schema()`：创建 `retrieval_documents` 和 FTS5 虚表。
- `_flatten_fields()`：展开嵌套 fields。
- `_source_ref_path()`：生成 `project_assets/source/...` 证据路径。

检索函数：

- `SqliteFTSRetrievalBackend.search()`：异步转线程查询。
- `_search_sync()`：空 query、非 fact_scope、db 不存在都返回空。
- `_exact_rows()`：按 identity exact_terms 精确匹配。
- `_fts_rows()`：先 FTS5，失败或无结果则 LIKE 兜底。
- `_allows_fact_scope()`：只允许 fact_scope 查询。
- `_merge_rows()`：合并 exact 与 FTS 结果。
- `_row_to_hit()`：把 SQLite 行转成 `RetrievalHit`。
- `_fts_phrase()`、`_normalize()`：查询辅助。

写入行为：

- `POST /api/generated/rebuild` 会删除并重建 `project_assets/generated/`。
- 不修改 `project_assets/source/`。
- 生成的 SourceRef 指向 source，不指向 SQLite 行或数据库文件。

关键边界：

- generated 是派生数据，不能当事实源。
- 检索只服务 fact_scope，不读取 workspace_scope。
- 如果没有重建过索引，Agent Chat 仍可以使用当前章节和已确认 Knowledge，但检索命中为空。

### 7.9 Agent Chat

代码位置：

- API：`src/taichu/api/routes/agents.py`
- Schema：`src/taichu/api/schemas/agents.py`
- Service：`src/taichu/application/agents/chat/service.py`
- Prompt：`src/taichu/application/agents/chat/prompts.py`
- Registry：`src/taichu/application/agents/registry.py`
- Plugin Discovery：`src/taichu/infrastructure/plugin_discovery.py`

API 函数：

- `api_list_agents()`：列出已注册 Agent manifest。
- `api_run_agent_chat()`：运行当前 Basic Agent Chat。
- `_conversation_info()`：响应 conversation。
- `_card_info()`：响应 AIResultCard。

请求字段：

- `message`：作者问题。
- `chapter_id`：可选，指定当前章节。
- `include_current_chapter`：是否带当前章节，默认 true。
- `include_confirmed_facts`：是否带已确认 Knowledge 和检索证据，默认 true。

服务函数：

- `ChatAgentService.run()`：组装上下文，调用 LLM，把回答保存成 AIResultCard。
- `ChatAgentService._selected_chapter()`：选择指定章节、manifest 当前章节或第一章。
- `_confirmed_fact_line()`：把 Knowledge 转 prompt 行。
- `_retrieval_line()`：把检索命中转 prompt 行。
- `_chapter_source_ref()`：为当前章节生成 SourceRef。
- `_knowledge_source_ref()`：为 Knowledge summary 生成 SourceRef。
- `_dedupe_sources()`：按证据位置去重。
- `_citation()`：生成 S1、S2 形式引用。
- `_paragraphs()`、`_compact_excerpt()`、`_sha256()`、`_now_iso()`：辅助函数。

上下文来源：

1. 当前章节摘录，最多 1600 字符。
2. 已确认 Knowledge，最多 8 张。
3. SQLite 检索命中，最多 6 条。

写入行为：

- Agent Chat 会写一张 `suggestion` 类型、`workflow=chat` 的 AIResultCard。
- 写入位置是 `workspace/ai_cards.jsonl`。
- 不写 Knowledge。
- 不写章节正文。

回答内容：

```json
{
  "answer": "模型回答",
  "source_status": "source_backed 或 speculative",
  "citations": [
    {
      "label": "S1",
      "source_type": "chapter 或 knowledge",
      "source_id": "...",
      "path": "...",
      "excerpt": "..."
    }
  ]
}
```

关键边界：

- 当前入口是 `POST /api/agents/chat`。
- 旧 `/api/chat` 已移除。
- Agent Chat 回答是建议卡，不是事实。
- 引用路径必须指向 source，不允许指向 generated。

### 7.10 source bundle 导出

代码位置：

- API：`src/taichu/api/routes/export.py`
- Schema：`src/taichu/api/schemas/export.py`
- Service：`src/taichu/application/services/export_service.py`
- Model：`src/taichu/domain/models/export.py`

API 函数：

- `api_export_bundle()`：生成可读导出包。
- `_bundle_response()`：转换响应。

服务函数：

- `ExportService.build_bundle()`：从 source 构造 readable JSON bundle。
- `_json_text()`：格式化 JSON。
- `_jsonl_text()`：格式化 JSONL。
- `_format_simple_yaml()`：格式化 metadata。
- `_format_scalar()`：格式化 YAML 标量。

导出内容：

- `source/metadata.yaml`
- `source/manuscripts/manifest.json`
- `source/manuscripts/chapters/*.md`
- `source/knowledge/<category>/<knowledge_id>.json`
- `source/workspace/ai_cards.jsonl`
- `source/workspace/ideas.jsonl`
- `source/workspace/pending_facts.jsonl`
- `source/workspace/chapter_issues.jsonl`
- `source/workspace/chapter_summaries.jsonl`

不导出：

- `project_assets/generated/`
- SQLite 数据库
- 向量缓存
- 临时文件

关键边界：

- 导出格式是 MVP 备份/迁移格式，不是发布包。
- 导出 workspace 不代表 workspace 成为事实。

## 8. 完整链路学习

### 8.1 链路一：选区续写到保存正文

目标：让 AI 生成一段正文候选，并由作者决定是否写入章节。

调用顺序：

1. 前端选中一段正文，构造 `SourceRef`。
2. 调用：

```http
POST /api/ai-cards/selection
```

请求核心：

```json
{
  "mode": "continue_text",
  "selection_context": {
    "chapter_id": "chapter_001",
    "selected_text": "太初古卷",
    "surrounding_text": "秦浩轩携太初古卷入山。",
    "selection_range": {"from": 1, "to": 5},
    "source_ref": {}
  },
  "user_prompt": "续写一句",
  "target_words": 30
}
```

3. `SelectionAIService.run_selection()` 生成 `text_candidate` 卡。
4. `AICardService.create_card()` 写入 `workspace/ai_cards.jsonl`。
5. 前端把 `card.content` 插入编辑器本地正文。
6. 前端调用：

```http
POST /api/ai-cards/{card_id}/actions
{"action": "inserted"}
```

7. `AICardService.mark_inserted()` 把卡片标记为 `inserted`。
8. 前端调用：

```http
PUT /api/chapters/chapter_001
{"markdown": "...插入后的完整章节 Markdown..."}
```

9. `ChapterService.save_chapter()` 写章节 Markdown 和 manifest。

关键理解：

- AI 只给候选，不自动改正文。
- 真正改正文的是 `PUT /api/chapters/{chapter_id}`。
- 卡片状态 `inserted` 是记录作者采纳过，不是正文内容本身。

### 8.2 链路二：AI 建议保存为灵感

目标：把一次选区问答保存为后续可回看的灵感。

调用顺序：

1. 调用 `POST /api/ai-cards/selection`，`mode=ask`。
2. 生成 `suggestion` 卡片，写入 `ai_cards.jsonl`。
3. 调用：

```http
POST /api/inbox/cards/{card_id}/save-idea
```

4. `InboxService.save_card_as_idea()` 委托 `AICardService.save_suggestion_as_idea()`。
5. 系统写入：
   - `workspace/ideas.jsonl`
   - 更新 `workspace/ai_cards.jsonl` 中卡片状态为 `saved_to_inbox`

关键理解：

- 灵感不是事实。
- 灵感不会进入默认检索。
- 同一张卡重复保存时，服务会复用已有 IdeaCard，避免重复。

### 8.3 链路三：候选设定进入 PendingFact，再确认成 Knowledge

目标：AI 提出一个设定候选，作者确认后才进入知识库。

调用顺序：

1. 调用 `POST /api/ai-cards/selection`，`mode=enrich_setting`。
2. 如果模型返回 `card_type=pending_fact`，系统生成 `pending_fact` 类型 AIResultCard。
3. 调用：

```http
POST /api/inbox/cards/{card_id}/convert-pending-fact
```

4. `AICardService.convert_card_to_pending_fact()` 把卡片 content 校验为 `PendingFact`。
5. 系统写入 `workspace/pending_facts.jsonl`，并把卡片状态改为 `converted_to_pending_fact`。
6. 作者确认：

```http
POST /api/pending-facts/{pending_fact_id}/confirm
```

或编辑后确认：

```http
POST /api/pending-facts/{pending_fact_id}/confirm-edited
```

7. `PendingFactConfirmationService._confirm()` 把 PendingFact 转成 KnowledgeCard。
8. `KnowledgeService.write_confirmed_card()` 校验证据和身份冲突。
9. 系统写入：
   - `project_assets/source/knowledge/<category>/<knowledge_id>.json`
   - 更新 `workspace/pending_facts.jsonl` 状态和 `target_knowledge_id`

关键理解：

- PendingFact 是候选，不是事实。
- Knowledge 是作者确认后的事实。
- 证据来源必须有效。
- 如果同名或别名冲突，Knowledge 写入会失败。

### 8.4 链路四：Knowledge 重建索引后被 Agent Chat 使用

目标：让确认后的知识能被后续对话检索引用。

调用顺序：

1. 先通过链路三写入 Knowledge。
2. 调用：

```http
POST /api/generated/rebuild
```

3. `IndexService.rebuild_generated_projection()` 清空 generated。
4. `SqliteProjectionRebuilder.rebuild()` 从章节和 confirmed Knowledge 重建 SQLite。
5. 调用：

```http
POST /api/agents/chat
```

请求：

```json
{
  "message": "下一幕怎么推进？",
  "chapter_id": "chapter_001",
  "include_current_chapter": true,
  "include_confirmed_facts": true
}
```

6. `ChatAgentService.run()` 读取当前章节、已确认 Knowledge，并查询 SQLite 检索结果。
7. LLM 回答被保存为 `workflow=chat` 的建议卡。

关键理解：

- 重建索引只改 generated，不改 source。
- Agent Chat 引用的 SourceRef 指向 source。
- generated 只加速检索，不是证据。

### 8.5 链路五：source bundle 导出

目标：把当前源资产和工作区资产导出成可读 bundle。

调用：

```http
GET /api/export/bundle
```

内部流程：

1. `ExportService.build_bundle()` 确保 skeleton 存在。
2. 读取 metadata。
3. 读取 manifest。
4. 读取章节 Markdown。
5. 读取 Knowledge JSON。
6. 读取 workspace JSONL。
7. 返回 `ExportBundleResponse`。

关键理解：

- 导出包含 workspace，是为了备份和迁移。
- 导出不包含 generated。
- workspace 出现在导出里，不代表它进入 fact_scope。

## 9. 函数地图

这一节列出当前后端主要功能函数，方便以后微调、删除或新增功能时定位。

### 9.1 组装、配置、依赖注入

| 位置 | 函数 | 职责 |
|---|---|---|
| `main.py` | `create_app()` | 创建并组装 FastAPI 应用、服务、注册中心和路由 |
| `main.py` | `main()` | 启动 uvicorn 开发服务器 |
| `config.py` | `Settings` | 读取运行配置 |
| `api/router.py` | `register_routes()` | 挂载所有 API 路由 |
| `api/deps.py` | `provide_agent_registry()` | 从 app state 取 AgentRegistry |
| `api/deps.py` | `provide_chat_agent_service()` | 取 ChatAgentService |
| `api/deps.py` | `provide_storage()` | 取基础 storage |
| `api/deps.py` | `provide_chapter_service()` | 取 ChapterService |
| `api/deps.py` | `provide_chapter_summary_service()` | 取 ChapterSummaryService |
| `api/deps.py` | `provide_ai_card_service()` | 取 AICardService |
| `api/deps.py` | `provide_selection_ai_service()` | 取 SelectionAIService |
| `api/deps.py` | `provide_inbox_service()` | 取 InboxService |
| `api/deps.py` | `provide_export_service()` | 取 ExportService |
| `api/deps.py` | `provide_index_service()` | 取 IndexService |
| `api/deps.py` | `provide_knowledge_service()` | 取 KnowledgeService |
| `api/deps.py` | `provide_pending_fact_confirmation_service()` | 取 PendingFactConfirmationService |

### 9.2 API 路由函数

| 功能 | 函数 |
|---|---|
| Agent | `api_list_agents()`、`api_run_agent_chat()`、`_conversation_info()`、`_card_info()` |
| AI 卡片 | `api_list_ai_cards()`、`api_create_selection_ai_card()`、`api_apply_ai_card_action()`、`_card_info()` |
| 章节 | `api_list_chapters()`、`api_read_chapter()`、`api_save_chapter()`、`api_summarize_chapter()`、`api_list_chapter_summaries()`、`api_apply_summary_action()`、`api_convert_summary_candidate()` |
| 章节响应转换 | `_chapter_info()`、`_summary_info()`、`_pending_fact_info()`、`_card_info()`、`_summary_edit()` |
| Inbox | `api_read_inbox()`、`api_save_card_as_idea()`、`api_convert_card_to_pending_fact()`、`api_ignore_pending_fact()` |
| Inbox 响应转换 | `_idea_info()`、`_pending_fact_info()`、`_saved_ai_card_info()`、`_chapter_issue_info()`、`_chapter_id_from_pending_fact()`、`_editor_href()` |
| Knowledge | `api_list_knowledge()`、`api_confirm_pending_fact()`、`api_confirm_pending_fact_with_edits()`、`api_reject_pending_fact()`、`_knowledge_info()`、`_pending_fact_info()` |
| Export 和 generated | `api_export_bundle()`、`api_rebuild_generated()`、`api_clear_generated()`、`_bundle_response()`、`_job_info()` |

### 9.3 应用服务函数

| 服务 | 函数 |
|---|---|
| `ChapterService` | `ensure_project_skeleton()`、`get_manifest()`、`list_chapters()`、`read_chapter()`、`save_chapter()`、`clear_generated_projection_stub()`、`_find_chapter()`、`_count_non_space()`、`_now_iso()` |
| `SelectionAIService` | `run_selection()`、`_build_card()`、`build_selection_prompt()`、`_workflow_for_mode()`、`_parse_json_object()`、`_card_type_for_response()`、`_default_card_type()`、`_card_type_allowed_for_mode()`、`_content_for_card_type()`、`_text_candidate_content()`、`_pending_fact_content()`、`_pending_fact_type()`、`_text_field()`、`_now_iso()` |
| `AICardService` | `create_card()`、`list_cards()`、`get_card()`、`mark_inserted()`、`discard_card()`、`mark_retried()`、`save_suggestion_as_idea()`、`convert_card_to_pending_fact()`、`_transition_card()`、`_replace_card()`、`_find_idea_by_source_card()`、`_find_pending_fact()`、`_idea_content()`、`_now_iso()` |
| `InboxService` | `list_inbox()`、`save_card_as_idea()`、`convert_card_to_pending_fact()`、`ignore_pending_fact()` |
| `KnowledgeService` | `list_cards()`、`list_all_cards()`、`get_card()`、`write_confirmed_card()`、`_assert_no_identity_conflict()`、`knowledge_category_for_type()`、`_validate_knowledge_source_refs()`、`_identity_terms()`、`_normalize_identity()` |
| `PendingFactConfirmationService` | `confirm_pending_fact()`、`confirm_pending_fact_with_edits()`、`reject_pending_fact()`、`_confirm()`、`_confirmed_knowledge_for()`、`_list_pending_fact_records()`、`_replace_pending_fact()`、`_find_pending_fact()`、`_knowledge_card_from_pending_fact()`、`_knowledge_type_for_pending_fact()`、`_knowledge_id_for_pending_fact()`、`_fields_from_content()`、`_summary_from_content()`、`_now_iso()` |
| `ChapterSummaryService` | `summarize_chapter()`、`list_summaries()`、`confirm_summary()`、`ignore_summary()`、`convert_candidate_to_pending_fact()`、`_append_pending_fact_once()`、`_get_summary()`、`_replace_summary()`、`_parse_summary_output()`、`_fallback_summary()`、`_candidate_pending_facts()`、`_candidate_data()`、`_pending_fact_type()`、`_candidate_key()`、`_chapter_segments()`、`_chapter_source_ref()`、`_paragraphs()`、`_is_empty_chapter()`、`_plain_excerpt()`、`_retrieval_query_text()`、`_clean_strings()`、`_text_or_none()`、`_sha256()`、`_now_iso()` |
| `IndexService` | `clear_generated()`、`rebuild_generated_projection()`、`_job()`、`_now_iso()` |
| `ExportService` | `build_bundle()`、`_json_text()`、`_jsonl_text()`、`_format_simple_yaml()`、`_format_scalar()`、`_now_iso()` |
| `ImportService` | `import_text()`、`_split_chapters()`、`_format_chapter_markdown()`、`_next_order()`、`_next_chapter_index()`、`_count_non_space()`、`_now_iso()` |
| `RetrievalService` | `search()` |

### 9.4 Agent、插件和工具函数

| 模块 | 函数或方法 |
|---|---|
| `ChatAgentService` | `run()`、`_selected_chapter()`、`_confirmed_fact_line()`、`_retrieval_line()`、`_chapter_source_ref()`、`_knowledge_source_ref()`、`_dedupe_sources()`、`_citation()`、`_paragraphs()`、`_compact_excerpt()`、`_sha256()`、`_now_iso()` |
| `chat/prompts.py` | `build_chat_prompt()`、`_numbered_block()` |
| `chat/graph.py` | `build_graph()` |
| `chat/nodes.py` | `create_call_model_node()` |
| `AgentRegistry` | `register()`、`register_all()`、`list_manifests()`、`get_graph()` |
| `ToolRegistry` | `register()`、`register_all()`、`list_manifests()`、`get()` |
| `plugin_discovery.py` | `discover_agents()`、`discover_tools()` |
| `CapabilityContext` | `__post_init__()`、`require()` |

### 9.5 领域规则函数

| 模块 | 函数 | 职责 |
|---|---|---|
| `card_state.py` | `assert_ai_card_transition_allowed()` | 校验 AIResultCard 状态迁移 |
| `card_state.py` | `assert_pending_fact_transition_allowed()` | 校验 PendingFact 状态迁移 |
| `fact_scope.py` | `resolve_retrieval_scope()` | 解析检索范围 |
| `fact_scope.py` | `is_allowed_in_fact_scope()` | 判断对象是否能进入默认事实范围 |
| `fact_scope.py` | `assert_allowed_in_fact_scope()` | 阻止非事实对象污染 fact_scope |
| `source_ref.py` | `validate_source_ref_contract()` | 校验 SourceRef 本地契约 |
| `SourceRef` | `validate_anchor_contract()` | Pydantic 模型级证据形状校验 |
| `Chapter` | `markdown_path_must_not_be_generated()` | 阻止章节路径指向 generated |

### 9.6 基础设施函数

| 模块 | 函数或方法 |
|---|---|
| `ProjectAssetStorageBackend` | `ensure_skeleton()`、`read_metadata()`、`write_metadata()`、`read_manifest()`、`write_manifest()`、`write_chapter_markdown()`、`read_chapter_markdown()`、`append_workspace_record()`、`list_workspace_records()`、`rewrite_workspace_records()`、`write_knowledge_record()`、`read_knowledge_record()`、`list_knowledge_records()`、`clear_generated()` |
| `ProjectAssetStorageBackend` 内部 | `_ensure_skeleton_sync()`、`_read_metadata_sync()`、`_write_metadata_sync()`、`_read_manifest_sync()`、`_write_manifest_sync()`、`_write_chapter_markdown_sync()`、`_read_chapter_markdown_sync()`、`_append_workspace_record_sync()`、`_list_workspace_records_sync()`、`_rewrite_workspace_records_sync()`、`_write_knowledge_record_sync()`、`_read_knowledge_record_sync()`、`_list_knowledge_records_sync()`、`_clear_generated_sync()`、`_ensure_generated_dirs()`、`_resolve_safe_chapter_path()`、`_resolve_safe_workspace_jsonl()`、`_resolve_safe_knowledge_json()`、`_resolve_safe_knowledge_category()`、`_replace_workspace_text()`、`_replace_file_text()`、`_manifest_path`、`_empty_manifest()`、`_parse_simple_yaml()`、`_format_simple_yaml()`、`_now_iso()`、`_parse_scalar()`、`_format_scalar()` |
| `SqliteProjectionRebuilder` | `rebuild()`、`_rebuild_sync()`、`_chapter_documents()`、`_knowledge_documents()`、`_knowledge_card_documents()`、`_knowledge_document()`、`_resolve_source_path()` |
| `projection_rebuilder.py` 辅助 | `_create_schema()`、`_split_paragraphs()`、`_flatten_fields()`、`_source_ref_path()`、`_identity_terms()`、`_normalize()`、`_heading_text()`、`_compact_excerpt()`、`_sha256()`、`_now_iso()` |
| `SqliteFTSRetrievalBackend` | `search()`、`_search_sync()`、`_exact_rows()`、`_fts_rows()` |
| `sqlite_fts.py` 辅助 | `_allows_fact_scope()`、`_merge_rows()`、`_row_to_hit()`、`_fts_phrase()`、`_normalize()` |
| `JsonStorageBackend` | `get()`、`list()`、`put()`、`delete()`、`_collection_dir()`、`_key_path()`、`_validate_segment()`、`_get_sync()`、`_list_sync()`、`_put_sync()`、`_delete_sync()`、`_read_object()` |
| `LLM` | `create_llm()`、`create_deepseek()`、`LangChainLLMAdapter.complete()`、`_stringify_content()` |

## 10. 后续微调、删除、新增功能指南

### 10.1 微调一个功能时看哪里

| 想改什么 | 优先看 |
|---|---|
| API 路径、状态码、请求响应 | `src/taichu/api/routes/` 和 `src/taichu/api/schemas/` |
| 业务流程 | `src/taichu/application/services/` |
| 状态流转限制 | `src/taichu/domain/rules/card_state.py` |
| 事实范围 | `src/taichu/domain/rules/fact_scope.py` |
| 证据来源 | `src/taichu/domain/models/source_ref.py` 和 `src/taichu/domain/rules/source_ref.py` |
| 文件落盘 | `src/taichu/infrastructure/storage/markdown_backend.py` |
| 检索结果 | `src/taichu/infrastructure/indexing/` 和 `src/taichu/infrastructure/retrieval/` |
| AI prompt | `src/taichu/application/workflows/` 或 `src/taichu/application/agents/chat/prompts.py` |

### 10.2 删除一个功能时的检查顺序

删除功能不要只删 API。至少检查：

1. `api/router.py` 是否还 include 对应路由模块。
2. `main.py` 是否还创建对应 Service。
3. `api/deps.py` 是否还有对应 provider。
4. `api/schemas/` 是否还有只给该功能使用的请求响应模型。
5. `application/services/` 是否还有无入口服务。
6. `domain/models/` 是否还有仅服务该功能的模型或枚举。
7. `domain/rules/` 是否有状态机或 fact_scope 依赖。
8. `infrastructure/storage/markdown_backend.py` 是否还有 workspace 文件契约。
9. `ExportService` 是否还导出对应 workspace 文件。
10. `tests/` 是否还有对应单元测试和集成测试。
11. `README.md` 是否还描述该闭环。

特别注意：

- 如果删除 PendingFact，Knowledge 确认链路会断。
- 如果删除 AIResultCard，选区 AI、Agent Chat、章节总结卡都会受影响。
- 如果删除 generated rebuild，Agent Chat 的检索证据会弱化，但当前章节和已确认 Knowledge 仍可直接注入。
- 如果删除章节总结，不应影响 PendingFact 主链路，但会少一个候选来源。

### 10.3 新增一个功能的推荐路径

推荐顺序：

1. 先定义领域模型或复用现有模型。
2. 如果涉及状态，先补领域状态机。
3. 在 `application/contracts/` 定义跨层协议。
4. 在 `application/services/` 写用例编排。
5. 在 `infrastructure/` 写具体实现。
6. 在 `api/schemas/` 定义请求响应。
7. 在 `api/routes/` 暴露 HTTP。
8. 在 `main.py` 装配服务。
9. 在 `api/deps.py` 暴露依赖。
10. 在 `api/router.py` 挂载路由。
11. 补单元测试和集成测试。

新增 AI 相关功能时的默认原则：

- AI 输出默认进入 AIResultCard 或 workspace。
- 只有作者确认才能写 Knowledge。
- SourceRef 必须指向 source，不得指向 generated。
- generated 只能重建，不应成为事实源。

## 11. 当前代码质量判断

优点：

- 分层清楚：API、应用、领域、基础设施职责边界明确。
- source/workspace/generated 数据边界清晰。
- 状态机集中在领域规则里，避免随意改状态。
- fact_scope 明确阻止 AI/workspace 污染默认检索。
- SourceRef 明确禁止 generated、SQLite、数据库文件成为证据来源。
- 服务大多通过 Protocol 或应用服务组合，替换实现成本低。
- 集成测试覆盖了 MVP 写作闭环。

需要注意的地方：

- 文档外的旧说明可能过时，尤其是旧 `/api/chat`。
- 部分枚举和模型是预留，不代表已有完整功能。
- Knowledge 没有直接编辑 API，后续如果要做知识库管理，需要新增明确的作者编辑链路。
- `chapter_issues.jsonl` 有 Inbox lane，但当前没有生成章节问题的后端入口。
- `ImportService` 能导入文本，但没有公开 API；如果前端需要导入功能，要补路由。
- Tool 插件注册基础设施存在，但当前没有产品使用链路。

## 12. 验证记录

本次生成前已执行：

```powershell
uv sync
uv run python -m unittest discover tests
uv run ruff check .
uv run mypy
```

结果：

```text
uv sync: Resolved 60 packages，Checked 59 packages
unit tests: Ran 111 tests，OK
ruff: All checks passed!
mypy: Success: no issues found in 133 source files
```

验收结论：

- 新文档位于 `docs/learn/MVP0.1后端功能学习指南.md`。
- 文档包含更新日期。
- 文档没有引用 `docs/learn/` 旧文档作为依据。
- 文档明确列出 MVP0.1 已实现功能、仅预留能力、未实现能力。
- 文档明确指出旧 `/api/chat` 已移除，当前入口是 `/api/agents/chat`。
