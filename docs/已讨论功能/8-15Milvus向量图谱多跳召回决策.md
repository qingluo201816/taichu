# Milvus 向量图谱多跳召回决策

> 讨论日期：2026-08-15  
> 更新日期：2026-08-18  
> 状态：已实现 Milvus BM25＋HNSW/Vector Graph＋原生 RRF、BGE 二阶段重排、双来源建模、统一 LLM 契约适配、生产 Tool 与来源级增量更新代码路径；待完成真实增量更新实机门禁和小说专项评测

## 用户决策

原 Qdrant 向量基础设施退出项目，客户端依赖、配置、启动逻辑、索引实现、维护脚本、测试、生成清单和当前文档说明同步删除。新的向量与多跳推理基础设施统一使用 Milvus，不引入 Neo4j 或其他图数据库。

系统采用 Milvus 团队开源的 Vector Graph RAG：把实体、关系和来源 passage 分别保存在 Milvus collections 中，并通过稳定 ID 相互引用。查询先检索实体和关系种子，再沿 ID 扩展局部子图，使用一次模型重排选择关系链，最后回读来源 passage。太初只使用其中的召回阶段，最终回答仍由高层编排 Agent 统一生成。

最终检索栈固定为 Milvus 单库混合检索：Passage Collection 内的中文 BM25 召回 30 条；Vector Graph 先抽取查询实体、扩展局部关系图并重排关系，再用关系文本增强 Dense 查询，HNSW 召回 30 条；两路由 Milvus 原生 `RRFRanker(k=60)` 融合为 30 条候选，再交给 `BAAI/bge-reranker-v2-m3`，最终保留 Top 10。Milvus 是可重建派生索引，不改变事实源边界。

Milvus HNSW 参数固定为：`M=24`、`efConstruction=300`、`efSearch=150`；BM25 TopK 与 Dense TopK 均固定为 30，RRF 平滑参数固定为 60。实体、关系、passage 三类向量集合使用相同 HNSW 建索引参数，每次向量查询显式传入 `ef=150`。BM25 使用 Passage Collection 的 `lexical_text` 与 `SPARSE_INVERTED_INDEX`，中文分析器采用 `jieba`；标题在词法文本中写入两次，以保持标题高于正文的召回权重。

## 双来源建模

### 正文 Markdown

- `project_assets/source/manuscripts/chapters/` 仍是正文唯一事实源。
- 切片结束位置优先沿 Markdown 标题和段落边界确定，默认目标长度 1000 字符、目标重叠 200 字符。下一片起点在目标位置附近优先对齐段落，其次对齐句号、问号或感叹号后的完整句首；允许实际 overlap 在目标值的 70%～130% 范围浮动，找不到语义边界时才回退到固定字符位置。
- 每个片段保存章节 ID、章节名、切片序号、原文字符区间、更新时间、内容哈希和稳定来源引用。
- passage 中的文本只来自 Markdown；Milvus 中的副本可以随时删除重建。

### 已确认知识卡

- MongoDB `taichu.knowledge_cards` 中 `lifecycle=confirmed` 的记录仍是结构事实源。
- 每张知识卡形成一个完整 passage，包括名称、别名、摘要、类型专属字段和来源说明。
- 不再把一张卡拆成身份、摘要、类型字段三个独立向量，避免关系抽取时割裂同一事实对象。
- 草稿、已拒绝和软删除知识不得进入 Milvus。

两类 passage 在同一图索引中共同抽取实体与关系，从而允许正文片段和知识卡通过共享实体形成跨来源多跳路径。

## 运行边界

- `retrieve_story_context` 是唯一生产相关性检索 Tool，统一覆盖正文、已确认知识卡、混合来源和多跳关系问题。
- `retrieve_knowledge`、`search_manuscript` 和独立暴露的 `retrieve_story_graph` 已退出生产能力目录；明确章节读取仍使用 `read_manuscript`，名称和别名确定性解析直接查询 MongoDB。
- 统一 Tool 返回关系候选、扩展后关系、重排关系和可追溯证据，不直接决定最终答案；证据进入模型上下文前回到 Markdown 或 MongoDB 读取权威内容。
- Milvus 只承担派生检索与图结构，不获得事实写入权，也不成为 Markdown 或 MongoDB 的兼容回退源。
- 日常维护入口为 `uv run python scripts/update_vector_graph_index.py`；`--dry-run` 只计算来源数量与当前语料快照，不调用模型或写入 Milvus。
- BM25 稀疏字段与 Dense 向量共用 Passage Collection Schema，因此不存在独立词法索引维护入口；语料变化由同一来源级增量路径同时更新两类索引，只有不兼容 Schema 变化才进入一次性迁移。

## 来源级增量更新决策

> 决策日期：2026-08-16  
> 状态：已确认并实现代码路径，真实语料实机门禁待执行

正常正文和知识卡维护不得删除并重建全部 Milvus collections。系统以 `source_type:source_id` 组成稳定 `source_key`，按来源维护内容哈希与索引状态：

- 一个正文章节是一个同步来源，章节内所有子块共同参与同一来源哈希；一张已确认知识卡是一个同步来源。
- 来源首次出现或规范化内容哈希变化时，删除该来源旧 passage 和引用，再以当前完整来源执行整源 Upsert。章节切片数量或边界变化不会留下旧子块。
- 来源从 Markdown 或 MongoDB confirmed 集合中消失时，同步删除该来源 passage，并清理由它独占的无引用实体与关系；仍被其他来源引用的共享图数据继续保留。
- 删除来源只有在 Milvus 明确确认按来源删除成功后才能移除来源清单。若来源清单仍记录该来源、但实际 passage 已异常为 0，系统无法证明关联实体与关系已经完成级联清理，必须在改写来源清单和完成基线前阻断并要求恢复一致性；不得凭通用失败状态推断删除已经完成。
- 内容未变化的来源直接跳过。文件时间戳或知识卡更新时间本身不作为内容变化依据，避免无语义改动触发模型调用。
- passage ID 由稳定来源键与来源内子块序号确定，重复执行同一来源得到同一组 ID；网络中断后重试不会追加重复 passage。
- 每个来源成功后立即推进来源清单中的状态，整批任务失败时不推进失败来源。再次执行只处理失败、缺失或后来发生变化的来源。

来源内更新采用可恢复的收敛语义：先清理该来源旧索引，再写入新索引；如果单个来源中途失败，该来源可能暂时缺失，但来源清单不会将其误记为成功，后续重试会完整重做该来源。系统不把部分写入视为正式完成。

已有集合升级到来源清单时，只有 `active_manifest.json` 同时保存了可验证的索引配置指纹，且该指纹、语料快照、集合 Schema、总记录数量以及每个来源的 passage 数量都和当前计划一致，才允许直接接管为来源清单而不重复调用模型。旧格式清单没有配置指纹，无法证明当时使用的抽取提示词、模型和嵌入配置，必须进行一次逐来源重放；不得把未知配置生成的旧索引伪装成当前索引。快照不一致或来源分布不一致时同样按逐来源差异执行增量更新。

只有集合 Schema、嵌入维度、索引协议等不兼容变化才允许通过专用迁移执行一次性集合重建；这类迁移不是日常维护入口。普通正文新增、编辑、删除以及知识卡确认、更新、软删除都必须走来源级增量替换和删除同步，正常流程不得 `drop` collections。

## 三子块邻域上下文决策

> 状态：已实现

正文仍以约 1000 字符的子块参与 BM25、Milvus ANN、图关系抽取与 BGE 重排，不额外建立父块向量。需要给最终回答模型补充更大范围上下文时，以重排后的命中子块为中心，按章节内顺序读取“前一子块、命中子块、后一子块”：

- 命中中间子块 `i` 时读取 `[i-1, i, i+1]`。
- 命中章节首块或尾块时只读取实际存在的两个子块。
- 不允许跨章节补邻块。
- 邻域扩展必须发生在 BGE Top 10 之后，邻块不参与该次召回和重排，避免无关上下文稀释检索精度。
- 三个子块已有 overlap，组装模型上下文时按正文字符区间合并，重叠原文只保留一次。以 1000 字符子块和 200 字符 overlap 估算，完整三块邻域的唯一正文约为 2600 字符，而不是简单拼接成 3000 字符。
- 多个命中子块的邻域相交时先合并为连续区间，再受本轮工作记忆字符预算约束，禁止重复发送相同正文或扩展成整章。
- 命中子块仍是相关性证据和精确来源引用；前后邻块只标记为补充上下文，不得伪装成同等相关的命中证据。
- 知识卡保持一张卡一个完整 passage，不应用正文邻块规则。

实现中，Milvus Passage Collection 为每个正文子块保存章节 ID、子块序号和原文字符区间。原生 RRF 候选先由 BGE 选出 Top 10，再按 `source_id + chunk_index` 从同一 Collection 读取邻块；因此父级上下文不会进入第一阶段索引内容、向量、图关系抽取或重排输入。Tool 契约同时返回命中子块的 `content/source_ref` 和补充上下文的 `context_content/context_source_ref/context_chunk_indexes`，让上层 Agent 能区分直接证据与邻域材料。

## 当前实现入口

- Docker 编排：`infra/milvus/docker-compose.yml`
- BGE 编排：`infra/reranker/docker-compose.yml`
- 应用模型与联合语料投影：`src/taichu/application/vector_graph/`
- 官方库适配：`src/taichu/infrastructure/vector_graph/backend.py`
- Milvus HNSW、BM25、RRF 与邻块读取：`src/taichu/infrastructure/vector_graph/milvus_store.py`
- Vector Graph 查询增强与 BGE 重排：`src/taichu/infrastructure/vector_graph/backend.py`、`hybrid_backend.py`、`reranker.py`
- 生产 Tool：`src/taichu/application/tools/retrieve_story_context.py`
- 增量更新命令：`scripts/update_vector_graph_index.py`
- 来源状态清单：`project_assets/generated/milvus_vector_graph/source_manifest.json`
- 运行摘要：`project_assets/generated/milvus_vector_graph/active_manifest.json`

## 2026-08-15 实机验证

- `start.bat` 已在固定端口成功启动并复用 MongoDB、Milvus、本地 Qwen Embedding、FastAPI 与 Next.js；Milvus、etcd、MinIO 三个容器均为健康状态。
- PyMilvus 已连接 `127.0.0.1:19530`；使用临时前缀创建并删除了实体、关系、passage 三个集合，验证官方库的 Milvus Schema 可用且未留下测试集合。
- 本地嵌入端点实测返回 2560 维向量，与 Milvus Schema 配置一致。
- Milvus 实机临时建表验证实体、关系、passage 三个集合均为 HNSW，返回参数为 `M=24`、`efConstruction=300`；插入测试向量后使用 `ef=150`、TopK 30 查询成功，测试集合随后删除。
- Milvus Passage Collection 的正式 Schema 已包含中文 BM25 稀疏字段与 HNSW 稠密字段；BM25 Top 30 和图增强 Dense Top 30 使用原生 RRF 融合，查询结果继续携带正文字符区间或知识卡引用。
- `BAAI/bge-reranker-v2-m3` 已下载到 `E:\Taichu\Models\bge-reranker-v2-m3` 并通过本地 TEI CPU 服务运行；中文武器问题实测将对应证据排在首位。候选超过 TEI 单批 32 条时由客户端安全分批，汇总全局分数后统一取 Top 10。
- 真实语料最新 dry-run 结果为：100 个正文文件、1753 个正文片段、257 张已确认知识卡，共 2010 个 passage、543175 个建模字符；当前快照为 `1a7a59fdecf31c910d5f130be989ab57aafe94502bdaeac15be2417a2f1acc3c`。
- 第一章中间子块实测命中区间为 `1502-2430`，Top 10 后扩展为子块 `[1,2,3]`，合并上下文区间 `741-3231`、唯一正文 2490 字符；两处 overlap 均只保留一次。
- 后端单元与架构测试 818 项及 16 个子测试通过，集成测试 132 项及 7 个子测试通过；Ruff 与目标范围 mypy 通过。
- 旧词法引擎的容器、数据卷、镜像、Compose 网络、Python 包及其传递依赖均已删除；BGE 容器已迁移到 `infra/reranker/` 编排。
- 旧 Qdrant 容器、数据卷、镜像和当前代码、依赖、配置、脚本、测试引用均已清除。

## 待完成门禁

实体/关系抽取、查询实体识别和关系重排已经通过太初统一 `LLMGatewayContract` 复用现有 RightCode 网关，当前模型为 `deepseek-v4-pro`，不再要求 OpenAI Chat Completions 专用密钥或地址。正式发布前仍须执行：

1. 用真实语料完成现有索引来源清单接管或首次逐来源建模，核对章节数、正文片段数、知识卡数、实体数、关系数和 passage 数。
2. 至少覆盖正文内多跳、知识卡内多跳、正文到知识卡跨来源多跳、无答案和冲突证据五类小说专项用例。
3. 验证返回的每条 passage 都能解析为正文字符区间或知识卡 ID，禁止无来源证据进入 Agent 上下文。
4. 分别验证正文和知识卡的新增、内容变化、删除与未变化跳过，确认只处理目标来源，旧子块与旧事实不会继续出现在新索引。
5. 在单个来源写入中断后重试，确认已成功来源不重复调用模型、失败来源能够完整收敛，且来源清单不会提前记录失败来源。
6. 通过一次不兼容测试 Schema 的隔离迁移验证集合级重建边界，确认日常更新入口没有集合删除能力。

## 依据

- [Vector Graph RAG 官方仓库](https://github.com/zilliztech/vector-graph-rag)
- [Milvus 官方 Graph RAG 文档](https://milvus.io/docs/graph_rag_with_milvus.md)
- [Milvus 官方 Windows Docker 部署文档](https://milvus.io/docs/install_standalone-windows.md)
