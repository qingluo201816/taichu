# 不可变架构决策

## 1. 单本小说边界

产品运行态只有当前唯一小说上下文。

禁止：

- API / Service / Agent / Tool 接收 `project_id`、`novel_id`。
- 产品 UI 提供小说列表、创建多本小说、跨小说检索。
- 测试语料与原创小说 source 混用。

允许：开发态通过环境变量或启动配置切换 active data root。

## 2. 事实源

正式小说事实源只有两类：

1. 章节正文 Markdown。
2. 作者确认过的 Knowledge JSON。

AIResultCard、IdeaCard、PendingFact、ChapterSummary 草稿、未采纳续写、被丢弃卡片、索引、向量缓存都不是正式事实。

## 3. SQLite

SQLite v1 只能是 `project_assets/generated/sqlite/taichu.db` 下的可重建投影。

规则：

- 任何写入 SQLite 的数据，都必须能说明从哪个 `project_assets/source/` 文件重建。
- 任何只存在 SQLite、删库后无法重建的数据，都是架构错误。
- AI 卡片、灵感、PendingFact、章节摘要等用户资产的主记录必须是 source 下的 JSON/JSONL。
- SQLite 可用于 FTS、索引、查询投影、分页、统计、embedding chunk 投影。

## 4. Selection AI

Selection AI v1 是编辑器应用工作流，不是 Agent。

规则：

- 主逻辑放 `application/services/selection_ai_service.py` 或等价 service/workflow。
- 不进入 AgentRegistry。
- 不新增 `application/agents/selection_assistant/` 作为主逻辑。
- 未来 Agent Chat 若要复用，只能通过 AgentAdapter 调用同一 Service。
- Selection AI 必须返回 AIResultCard，不能返回裸字符串。

## 5. SourceRef

SourceRef v1 做段落级/字段级证据定位。

规则：

- 章节证据定位到 paragraph 或 paragraph_range。
- 选区额外保存段内 `char_start/char_end`。
- Knowledge 证据定位到 card + field_path。
- 所有引用带 excerpt_hash 和 source_hash。
- SourceRef 不指向 generated SQLite 行。
- EmbeddingChunk 不是事实来源；它内部必须带 SourceRef。

不做：全文稳定锚点、token 级坐标、CRDT anchor、Git commit 级版本定位、Markdown 隐藏 UUID 注释、复杂 re-anchor。

## 6. API 和层边界

- 前端只通过统一 API client 调后端。
- 前端不得直接访问 LLM、SQLite、向量库、`project_assets/`。
- API route 只做协议转换、校验、响应格式化。
- 业务逻辑在 application services。
- 领域规则在 domain。
- infrastructure 实现 storage/retrieval/LLM，不写小说业务规则。
- application 通过 contracts 依赖 infrastructure，不直接 import 具体实现。
