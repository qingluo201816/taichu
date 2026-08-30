# 统一检索与 Agentic RAG 能力架构

> 讨论日期：2026-08-18  
> 更新日期：2026-08-24
> 状态：已实现；生产检索已收敛为 Passage-first 受控图扩展并通过 30 条全量回归门禁

## 决策结论

太初采用 Markdown、MongoDB、Milvus 三层分工：Markdown 是正文唯一事实源；MongoDB 是作者确认后结构化知识的唯一事实源；Milvus 是同时覆盖正文片段、已确认知识卡、实体和关系的可重建派生检索层。Milvus 不获得事实写入权，检索结果在进入模型上下文前必须回到 Markdown 或 MongoDB 读取当前权威内容。

相关性检索只向 Agent 暴露一个生产 Tool：`retrieve_story_context`。正文位置未知、知识卡相关性查询、正文与知识卡混合查询以及多跳关系问题都进入同一链路。BM25、Dense、Vector Graph、RRF 和 BGE 是工具内部策略，不作为多个 Tool 交给编排模型选择。

名称、别名、对象存在性和同名歧义不使用 RAG 判断。`resolve_knowledge_identity` 直接查询 MongoDB 已确认知识，返回唯一、歧义或不存在及轻量身份信息；`read_knowledge_cards`、`read_manuscript`、`list_knowledge_catalog` 和 `get_novel_structure` 只执行已经明确范围的权威读取或目录浏览。

## 数据职责

### Markdown

- 保存章节正文、段落、句子和作者原始表达。
- 正文切片、BM25 文本和 Dense 向量均由 Markdown 派生。
- Milvus 命中后按章节 ID、字符区间和内容哈希回读 Markdown；区间内容已经变化时拒绝把旧索引文本作为事实。
- 明确章节读取使用 `read_manuscript`，不经过相关性检索。

### MongoDB

- 保存知识卡结构、名称、别名、生命周期和作者确认后的最新字段。
- Workflow 与 LLM 只能先生成 JSON 候选；通过 Schema、来源、冲突和生命周期校验并经作者确认后，才能写成 `lifecycle=confirmed` 的知识卡。
- `draft`、`rejected` 和软删除记录不得进入正式 Milvus 索引。
- 名称或别名解析、目录、完整卡读取和修改前身份锁定直接访问 MongoDB，不能用 RAG 空结果证明对象不存在。

### Milvus

- Passage Collection 同时索引正文片段和已确认知识卡，承载中文 BM25 与 Dense 向量。
- Entity 与 Relation Collections 承载实体、关系、来源引用和多跳扩展。
- 正式检索链固定为 BM25 Passage Top 30 与 Dense Passage Top 30，经 `RRFRanker(k=60)` 先融合为 Passage Top 30；从这些 Passage 的 `entity_ids/relation_ids` 取得种子并执行一次受控 Graph Expansion，通过关系的 `passage_ids` 回取 Graph Passage，与原候选合并去重后只调用一次 BGE。Top 10 作为检索指标与追踪边界；上下文装配再从统一排序中选择最多 3 份互补证据，并按问题类型执行原文句窗或同章父级邻域重建。
- 知识卡命中回 MongoDB 校验仍为确认态并读取最新投影；正文命中回 Markdown 校验哈希并读取原文。

## Tool 能力边界

| Tool | 职责 | 权威来源 |
|---|---|---|
| `retrieve_story_context` | 位置未知的正文、知识卡、混合证据和多跳关系统一相关性检索 | Milvus 发现候选，Markdown/MongoDB 回源 |
| `resolve_knowledge_identity` | 按类型、名称和别名判断唯一、歧义或不存在 | MongoDB |
| `read_knowledge_cards` | 按内部稳定身份读取完整已确认知识卡 | MongoDB |
| `list_knowledge_catalog` | 按类型和分页条件浏览已确认知识目录 | MongoDB |
| `read_manuscript` | 按明确章节或范围读取正文 | Markdown |
| `get_novel_structure` | 读取卷章结构 | Markdown 结构清单 |

`retrieve_knowledge`、`search_manuscript` 和独立暴露的 `retrieve_story_graph` 已退出生产能力目录。MongoDB 手工字符切词和加权排名后端已经删除；Vector Graph 能力并入统一相关性检索工具，未知正文位置由 Milvus BM25 覆盖。

## Agent 分层

高层编排 Agent 保持全局控制，并拥有全部只读上下文 Tool。简单事实问题直接调用一次统一检索；明确章节、身份或目录问题直接调用确定性 Tool，不强制启动子 Agent。

复杂因果、多跳、跨章节、跨来源和冲突核查任务交给现有 `canon_evidence` 事实与证据子 Agent。它可以拆解问题、执行有预算上限的多轮统一检索、检查证据充分性与冲突，并向父 Agent 返回契约化证据包；内部工具轨迹不并入父 Agent 历史。

角色、世界观、情节、写作、修订和审校等专业子 Agent 默认消费父 Agent 已准备的证据包，同时保留受调用预算约束的 `retrieve_story_context` 补充检索权限。它们不能直接写 MongoDB，也不能把检索结果自动确认为知识卡。

## Agentic RAG 边界

一次 `retrieve_story_context` 调用完成单轮 Hybrid RAG：BM25 与 Dense 双路 Passage 召回、RRF、由命中 Passage 驱动的受控图扩展、Graph Passage 合并、单次 BGE、查询感知上下文装配和权威回源。查询阶段不再调用 LLM 做实体抽取或关系重排，工具内部也不得隐藏无上限自主循环。

多轮 Agentic RAG 由高层编排 Agent 或事实与证据子 Agent 显式执行：拆解问题、第一次检索、检查缺口、按需改写或补充查询、交叉验证、输出证据包。简单请求不得强制进入多轮链路，复杂请求必须受检索轮数、字符和模型调用预算约束。

## 实现入口

- 统一 Tool：`src/taichu/application/tools/retrieve_story_context.py`
- 确定性身份：`src/taichu/application/tools/resolve_knowledge_identity.py`
- MongoDB 目录：`src/taichu/application/tools/list_knowledge_catalog.py`
- 权威回源与索引用例：`src/taichu/application/vector_graph/service.py`
- Milvus 混合召回：`src/taichu/infrastructure/vector_graph/`
- 高层编排规则：`src/taichu/application/general_agent/orchestrator.py`
- 子 Agent 检索授权：`src/taichu/application/subagents/_factory.py`
