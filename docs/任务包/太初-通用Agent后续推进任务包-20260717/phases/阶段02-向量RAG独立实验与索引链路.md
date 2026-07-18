# 阶段 02：向量 RAG 独立实验与索引链路

> 更新日期：2026-07-18
> 阶段编号：`P02`  
> 依赖：`P01=PASS`  
> 默认连续执行：是  
> 生产接入：本阶段禁止；独立向量能力必须保留

## 一、阶段目标

构建一个真实、可重建、可评测并长期保留的独立向量召回能力，但不改变任何生产消费者的召回结果。该阶段必须把向量能力本身落地；评测结论用于指导优化并决定阶段 03 是否进入融合与生产灰度，而不是决定是否删除向量能力。

## 二、核心方案修正

2026-07-18 用户已明确选择一步到位配置长期向量基础设施，但仍要求向量与词法保持独立。最终方案：

- 应用层 `EmbeddingGateway` Protocol。
- 本地 Qwen3-Embedding-4B 真实 Embedding 适配器，通过 llama.cpp OpenAI 兼容接口调用。
- 一张知识卡投影成少量可追溯片段。
- Qdrant Server 作为首个 `VectorIndexBackend`，向量存于 Docker 命名卷，索引清单与审计产物仍保持可删除、可重建。
- 所有向量条目只来自 MongoDB `lifecycle=confirmed` 知识卡，命中后回读 MongoDB 当前卡。
- 当前生产默认继续使用 `mongo_lexical`，阶段 02 不做 RRF、加权融合或消费者切换。

Qdrant 与本地模型的安装、版本、哈希、端口和实机探测记录见 `docs/临时架构/7-18向量知识召回技术设计.md`。首轮效果不理想时应定位投影、指令、模型、维度、过滤或评分问题并继续优化；只有融合与生产晋级可以被门禁阻止。

## 三、任务清单

### `VEC-001` 定义 Embedding 应用契约

建议新增：

- `src/taichu/application/contracts/embedding.py`
- `src/taichu/application/embeddings/models.py`

最小模型：

- `EmbeddingRequest`
  - 文本列表。
  - 逻辑用途：`knowledge_document` / `knowledge_query`。
  - 模型角色。
  - 输入字符预算。
  - 运行与调用关联。
- `EmbeddingResponse`
  - 模型 ID。
  - 维度。
  - 归一化方式。
  - 向量列表。
  - Token/费用/耗时。
  - 上游请求 ID。
- `EmbeddingModelProfile`
  - 模型 ID。
  - 维度。
  - 最大输入。
  - 是否适合中文/多语。
  - 传输方式。

契约拒绝额外字段，校验向量数量、维度、NaN/Infinity 和空响应。

### `VEC-002` 真实能力探测与 ADR

新增安全探测脚本，例如：

`scripts/probe_embedding_models.py`

要求：

- 密钥只从本机 `.env` 读取。
- 不打印密钥、鉴权头、完整文本或完整向量。
- 使用少量中文小说语义对进行探测。
- 记录可用端点、模型 ID、维度、最大输入、延迟和费用。
- 真实调用失败时，不用随机向量或哈希向量冒充生产实现。

生成：

`docs/临时架构/7-18向量知识召回技术设计.md`

其中写明：

- 候选方案。
- Windows 本机兼容性。
- 新依赖和模型下载体积。
- 隐私、离线可用性和成本。
- 最终选择及淘汰原因。

真实探测已于 2026-07-18 成功，Qdrant、本地 Qwen 模型、`pyproject.toml`、`.env.example`、`config.py` 和一键启动配置已经落地；后续不得用假 Embedding 替换该真实链路。

### `VEC-003` 知识卡向量文档投影

建议新增：

- `src/taichu/application/retrieval/vector_documents.py`

每张已确认知识卡生成可追溯文档片段：

1. 身份片段：类型、名称、别名。
2. 摘要片段：summary。
3. 类型字段片段：当前知识类型允许的顶层专属字段。

每个片段必须带：

- `card_id`
- `knowledge_type`
- `field_paths`
- `content_sha256`
- `card_updated_at`
- `source_lifecycle=confirmed`
- 投影策略 ID

禁止把已废弃字段、未确认卡、评测结果或运行记忆投影进知识向量索引。

第一版不做无边界固定字符切块；结构化字段本身就是更稳定的切分边界。

### `VEC-004` 向量索引格式与存储

建议新增：

- `src/taichu/application/contracts/vector_index.py`
- `src/taichu/application/retrieval/vector_index_models.py`
- `src/taichu/infrastructure/retrieval/vector_index/qdrant.py`

Qdrant 配置：

- 服务：`http://127.0.0.1:6333`
- 集合：`taichu_knowledge_vectors`
- 距离：Cosine
- 向量维度：2560，必须与配置模型一致。
- active 索引使用 Qdrant alias 指向构建完成且校验通过的物理集合。

索引清单作为可审计派生产物按需写入 `project_assets/generated/vector_indexes/knowledge_cards/`，至少包含：

- `format_version`：只用于存储兼容。
- `index_id`
- `lifecycle=confirmed`
- Mongo 知识快照哈希。
- Embedding 模型 ID 和维度。
- 文档投影策略 ID。
- 向量归一化方式。
- 卡片数和片段数。
- 构建时间。
- Qdrant 物理集合名、active alias 和清单校验和。

Qdrant payload 只保存定位、过滤和过期校验所需的 `card_id`、类型、字段路径、内容哈希、卡片更新时间、投影策略和生命周期快照，不保存可反向取代 MongoDB 的完整卡片事实副本。返回时必须按 `card_id` 回读 MongoDB 当前已确认卡，并再次校验生命周期和更新时间。

### `VEC-005` 可重建与过期检测

新增显式重建命令：

```bash
uv run python scripts/rebuild_knowledge_vector_index.py
```

支持：

- 全量重建到新的临时 Qdrant 物理集合。
- 校验卡片数、片段数、维度和哈希。
- 成功后原子切换 active alias 和清单。
- 构建失败保留旧 active 集合，不切 alias。
- `--dry-run`。
- `--verify-only`。
- Mongo 卡片更新后检测索引过期。
- 删除整个 Qdrant 集合与本地清单后可从 MongoDB 重新生成。

第一版不要求复杂增量更新或 change stream。先证明全量重建稳定，再决定是否需要增量。

### `VEC-006` 独立向量后端

建议新增：

- `src/taichu/infrastructure/retrieval/vector_backend.py`

行为：

- 只实现 `RetrievalMode.RELEVANCE`。
- query/context 经过预算和标准化后生成查询 Embedding。
- 通过 `VectorIndexBackend` 调用 Qdrant 做 Cosine 检索和 payload 过滤。
- 按卡片聚合：建议使用最高片段分数加少量多片段覆盖奖励。
- 返回 `RetrievalBackendCandidate`，保留片段字段路径、原始相似度和后端排名的脱敏信号。
- 结果回读 MongoDB，并过滤未确认、已删除和更新时间不一致卡。
- 索引不存在、过期或模型不匹配时返回明确可分类错误，不自行写事实或静默生成新索引。

本阶段只通过评测服务显式调用，不注入生产 `RetrievalService`。

### `VEC-007` Embedding 与索引遥测

新增独立、脱敏记录：

- Embedding 调用 ID、模型、维度、文本数量、字符数、Token、费用、耗时、状态和错误代码。
- 索引 ID、快照哈希、构建耗时、条目数和校验结果。
- 查询不保存原文，向量不写入普通调用日志。

目录建议：

- `project_assets/derived/embedding_usage/calls.jsonl`
- `project_assets/generated/vector_indexes/...`

同步 `project_assets/readme.md`。

### `VEC-008` 运行独立评测

对阶段 01 同一数据集运行：

- `mongo_lexical`
- `knowledge_vector`

分组比较：

- 精确名称。
- 别名。
- 语义改写。
- 状态和关系。
- 多实体。
- 无答案。

增加：

- Embedding 调用失败率。
- 查询 Embedding p50/p95。
- 索引检索 p50/p95。
- 单次查询费用。
- 索引大小和构建时间。
- 重复运行排名稳定性。

向量后端本身不必在所有分组胜过词法。它的价值应主要体现在语义改写和隐含表达。

### `VEC-009` 形成融合 GO / HOLD 结论

生成：

`docs/历史/<日期>-向量知识召回实验报告.md`

结论只允许：

- `GO_TO_HYBRID_SHADOW`
- `HOLD_HYBRID_QUALITY`
- `HOLD_HYBRID_COST`
- `HOLD_HYBRID_LATENCY`
- `HOLD_HYBRID_OPERABILITY`
- `HOLD_HYBRID_PROVIDER`

若 HOLD：

- 保留独立向量实现并说明下一轮优化项。
- 不修改生产召回策略。
- 记录重新评测和进入融合的触发条件。
- 后续阶段 04—08继续执行。

## 四、测试重点

- 向量维度不一致、NaN、空结果。
- 索引清单损坏和校验和失败。
- Mongo 卡更新导致索引过期。
- 索引中存在旧卡 ID 时不能返回已删除/未确认卡。
- 全量重建失败时 active 索引不受影响。
- Qdrant 临时集合构建失败与 alias 原子切换。
- Embedding 超时、429、5xx 和权限错误。
- 查询日志不保存原文和向量。
- 删除 Qdrant 集合和 generated 清单后可重建。

## 五、晋级门禁

采用总路线图中的向量门禁。特别强调：

- 单元测试的确定性假 Embedding 只证明代码正确，不作为晋级证据。
- 必须至少一次真实 Embedding 构建完整索引并运行全量评测。
- 未达到稳定收益时不得进入阶段 03 的混合影子与生产接入，但独立向量能力继续保留和优化。
- 本阶段不得修改 `src/taichu/main.py` 中生产 `retrieval_service` 注入策略，除非只为评测显式装配且默认关闭。

## 六、自检

- [ ] 向量位于 Qdrant 派生集合，清单位于 generated；两者都不是 source/Mongo 事实。
- [ ] 所有索引条目来自 confirmed 卡。
- [ ] 返回前重新读取 Mongo 当前卡。
- [ ] 没有随机/哈希向量冒充生产。
- [ ] 真实 provider 探测不泄露密钥。
- [ ] 索引可全量重建。
- [ ] 词法生产路径完全未改变。
- [ ] 评测与阶段 01 使用同一数据集校验和。
- [ ] 已输出明确的融合 GO/HOLD 结论和向量优化项。

## 七、交付物

- Embedding 契约和真实适配器。
- 向量文档投影。
- Qdrant Cosine 索引、active alias 与清单存储。
- 重建/校验脚本。
- 独立向量后端。
- 评测结果和融合 GO/HOLD 报告。
