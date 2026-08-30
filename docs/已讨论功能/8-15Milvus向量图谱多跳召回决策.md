# Milvus 向量图谱多跳召回决策

> 讨论日期：2026-08-15  
> 更新日期：2026-08-24
> 状态：已实现 Passage-first 混合召回、受控 Graph Expansion、单次 BGE、查询感知上下文装配、双来源建模与来源级增量更新；30 条小说专项全量回归门禁已通过

## 用户决策

原 Qdrant 向量基础设施退出项目，客户端依赖、配置、启动逻辑、索引实现、维护脚本、测试、生成清单和当前文档说明同步删除。新的向量与多跳推理基础设施统一使用 Milvus，不引入 Neo4j 或其他图数据库。

系统采用 Milvus 团队开源的 Vector Graph RAG 数据模型：把实体、关系和来源 passage 分别保存在 Milvus collections 中，并通过稳定 ID 相互引用。生产查询不再以 LLM 抽取的实体为入口，也不从高频人物直接展开全部关系；它先检索 Passage，再从相关 Passage 已携带的图元数据取得种子并受控扩展。太初只使用其中的召回阶段，最终回答仍由高层编排 Agent 统一生成。

最终检索栈固定为：Passage Collection 内中文 BM25 Top 30 与 HNSW Dense Top 30 → Milvus 原生 `RRFRanker(k=60)` 融合为 Passage Top 30 → 从命中 Passage 的 `entity_ids/relation_ids` 选择图种子 → 查询感知且有界的单跳 Graph Expansion → 由关系 `passage_ids` 回取最多 20 条 Graph Passage → 与 RRF Passage 合并去重 → `BAAI/bge-reranker-v2-m3` 对全部候选只重排一次。Top 10 是检索指标和追踪边界；最终上下文从统一排序中选择最多 3 份互补证据。Milvus 是可重建派生索引，不改变事实源边界。

Milvus HNSW 参数固定为：`M=24`、`efConstruction=300`、`efSearch=150`；BM25 TopK 与 Dense TopK 均固定为 30，RRF 平滑参数固定为 60。图扩展查询级硬预算为：种子实体最多 5 个、种子关系最多 32 条、`max_hop=1`、每跳实体最多 20 个、普通实体最多取 10 条关系、度数达到 100 的 Hub 实体最多取 5 条关系、候选池倍率 4、Beam 宽度 24、全局关系最多 56 条、Graph Passage 最多 20 条。实体、关系、passage 三类向量集合使用相同 HNSW 建索引参数，每次向量查询显式传入 `ef=150`。BM25 使用 Passage Collection 的 `lexical_text` 与 `SPARSE_INVERTED_INDEX`，中文分析器采用 `jieba`；标题在词法文本中写入两次，以保持标题高于正文的召回权重。

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

## 查询感知上下文装配决策

> 状态：已实现

正文仍以约 1000 字符的子块参与 BM25、Milvus ANN 和图关系抽取，不额外建立父块向量。RRF Passage 与 Graph Passage 合并去重后，由 BGE 对全部候选统一评分一次；上下文选择器最多保留 3 份互补证据，再按查询意图决定投影粒度：

- 命中中间子块 `i` 时读取 `[i-1, i, i+1]`。
- 命中章节首块或尾块时只读取实际存在的两个子块。
- 不允许跨章节补邻块。
- 直接属性、归属、人物、物品等单事实题优先从权威原文中提取覆盖主体、谓词和客体的最小连续句窗，最多保留 3 句，避免整段背景稀释上下文相关性。
- 原因、过程、方式、共同经历和确需跨句推理的问题保留更宽的父级邻域，不把多跳问题错误压缩成孤立关系句。
- 邻域和原文投影都发生在统一 BGE 评分之后，不参与 BM25、Dense、RRF、图扩展或 BGE，避免上下文重建反向污染相关性排序。
- 三个子块已有 overlap，组装模型上下文时按正文字符区间合并，重叠原文只保留一次。以 1000 字符子块和 200 字符 overlap 估算，完整三块邻域的唯一正文约为 2600 字符，而不是简单拼接成 3000 字符。
- 多个命中子块的邻域相交时先合并为连续区间，再受本轮工作记忆字符预算约束，禁止重复发送相同正文或扩展成整章；知识卡按查询相关字段和关系投影压缩。
- 命中子块仍是相关性证据和精确来源引用；前后邻块只标记为补充上下文，不得伪装成同等相关的命中证据。
- 知识卡保持一张卡一个完整 passage，不应用正文邻块规则。

实现中，Milvus Passage Collection 为每个正文子块保存章节 ID、子块序号和原文字符区间。统一 BGE 排序后，装配器按 `source_id + chunk_index` 读取必要邻块并生成查询感知投影；应用服务再回读 Markdown 或 MongoDB，只有能从权威内容连续重建的投影才被保留，否则回退到完整权威内容。Tool 契约同时返回命中内容、补充上下文和来源引用，让上层 Agent 能区分直接证据与场景材料。

## 当前实现入口

- Docker 编排：`infra/milvus/docker-compose.yml`
- BGE 编排：`infra/reranker/docker-compose.yml`
- 应用模型与联合语料投影：`src/taichu/application/vector_graph/`
- 官方库适配：`src/taichu/infrastructure/vector_graph/backend.py`
- Milvus HNSW、BM25、RRF 与邻块读取：`src/taichu/infrastructure/vector_graph/milvus_store.py`
- Passage-first 受控图扩展：`src/taichu/infrastructure/vector_graph/controlled_retriever.py`
- Passage 合并、单次 BGE 与上下文装配：`src/taichu/infrastructure/vector_graph/backend.py`、`hybrid_backend.py`、`reranker.py`
- 生产 Tool：`src/taichu/application/tools/retrieve_story_context.py`
- 增量更新命令：`scripts/update_vector_graph_index.py`
- 来源状态清单：`project_assets/generated/milvus_vector_graph/source_manifest.json`
- 运行摘要：`project_assets/generated/milvus_vector_graph/active_manifest.json`

## 2026-08-15 实机验证

- `start.bat` 已在固定端口成功启动并复用 MongoDB、Milvus、本地 Qwen Embedding、FastAPI 与 Next.js；Milvus、etcd、MinIO 三个容器均为健康状态。
- PyMilvus 已连接 `127.0.0.1:19530`；使用临时前缀创建并删除了实体、关系、passage 三个集合，验证官方库的 Milvus Schema 可用且未留下测试集合。
- 本地嵌入端点实测返回 2560 维向量，与 Milvus Schema 配置一致。
- Milvus 实机临时建表验证实体、关系、passage 三个集合均为 HNSW，返回参数为 `M=24`、`efConstruction=300`；插入测试向量后使用 `ef=150`、TopK 30 查询成功，测试集合随后删除。
- Milvus Passage Collection 的正式 Schema 已包含中文 BM25 稀疏字段与 HNSW 稠密字段；BM25 Top 30 和 Dense Top 30 使用原生 RRF 先融合，查询结果继续携带正文字符区间、知识卡引用和图种子元数据。
- `BAAI/bge-reranker-v2-m3` 初次验证时通过本地 TEI CPU 服务运行；截至 2026-08-24 已迁移到 TEI 1.9 CUDA 服务。客户端按 64 条分批，所有合并候选汇总全局分数且整条生产查询只执行一次 BGE 重排。
- 真实语料最新 dry-run 结果为：100 个正文文件、1753 个正文片段、257 张已确认知识卡，共 2010 个 passage、543175 个建模字符；当前快照为 `1a7a59fdecf31c910d5f130be989ab57aafe94502bdaeac15be2417a2f1acc3c`。
- 第一章中间子块在 2026-08-15 的父级区间验证中，命中区间为 `1502-2430`，相邻子块 `[1,2,3]` 可合并为 `741-3231`、唯一正文 2490 字符且两处 overlap 只保留一次。该结果只证明父级重建算法；当前生产链不会机械扩展 BGE Top 10，而是最多选择 3 份证据并按问题类型决定句窗或父级邻域。
- 后端单元与架构测试 818 项及 16 个子测试通过，集成测试 132 项及 7 个子测试通过；Ruff 与目标范围 mypy 通过。
- 旧词法引擎的容器、数据卷、镜像、Compose 网络、Python 包及其传递依赖均已删除；BGE 容器已迁移到 `infra/reranker/` 编排。
- 旧 Qdrant 容器、数据卷、镜像和当前代码、依赖、配置、脚本、测试引用均已清除。

## 2026-08-24 受控扩展与评测验证

- 查询时已经删除 LLM 实体抽取、全量 Hub 邻接展开和关系 LLM 重排；索引构建仍通过统一 `LLMGatewayContract` 使用 `deepseek-v4-pro` 抽取实体与关系。
- 生产链从 Passage 相关性出发，主角等高频实体只有同时出现在高排名 Passage 图元数据中才可能成为种子，并受每实体、每跳、Beam 和全局关系预算共同约束；原先约 30 条候选扩展到 2994 条关系、导致约 5.4 万字符 Prompt 的路径已被结构上移除。
- 30 条 Golden 全量运行全部完成且自动门禁通过：`Recall@10=0.8365`、`MRR@10=0.7042`、权威回源通过率 `1.0000`、`Relation Recall@10=0.8929`、完整路径通过率 `1.0000`。
- 30 条 DeepEval 语义评测无执行失败：上下文相关性均分 `0.8530`、忠实度均分 `0.9933`、回答相关性均分 `0.9526`。个别低分用例保留为后续查询感知装配调优尾项，不影响本次冻结门禁。
- 当前门禁与完整报告见 `docs/学习资料/8-19Graph RAG质量评测与回归体系设计.md` 和 `project_assets/derived/rag_evaluations/20260823T191756Z-full.json`。生产链只有一个受控 Graph 路径，不再保留 Graph ON/OFF 双实现或消融入口。

## 依据

- [Vector Graph RAG 官方仓库](https://github.com/zilliztech/vector-graph-rag)
- [Milvus 官方 Graph RAG 文档](https://milvus.io/docs/graph_rag_with_milvus.md)
- [Milvus 官方 Windows Docker 部署文档](https://milvus.io/docs/install_standalone-windows.md)
