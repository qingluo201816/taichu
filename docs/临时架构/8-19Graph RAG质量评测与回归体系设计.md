# Graph RAG 质量评测与回归体系设计

> 首次形成日期：2026-08-19  
> 更新日期：2026-08-19  
> 状态：第一版已实现，Golden 与阈值待真实基线校准；本文件仍是临时架构说明，代码 Schema 以实现为准

## 一、目标与边界

本方案为太初重新设计长期 RAG 质量评估与回归体系，重点证明两件事：

1. Graph RAG 相比关闭图扩展的混合检索，是否在真正需要关系推理的小说问题上产生稳定、可量化的收益。
2. RAG 代码、语料、索引、Embedding、重排器或生成模型变化后，评测体系是否能发现质量回退，并通过 CI 自动执行回归。

第一版只覆盖必要基础指标、30 条人工维护 Golden、Graph RAG 专项消融和自动 CI 回归。不建设新评测网页，不建设模型排行榜、时间线专项基础设施或大规模线上实验平台。

技术主线是生产级 RAG Evaluation，CI 只是稳定执行评测与回归的载体：

```text
                 RAG Evaluation
                       │
         ┌─────────────┼─────────────┐
         ↓             ↓             ↓
     Retriever      Generator      Graph
         │             │             │
    Recall@10      Faithfulness   Relation Recall@K
    MRR@10         Relevancy      Complete Path Recall
         │             │             │
         └─────────────┼─────────────┘
                       ↓
                30 Golden Cases
                       │
                Graph ON / OFF
                    Ablation
                       │
                   Regression
                       │
                      CI
                       │
                失败/灰区人工诊断
```

旧 RAG 评测实现、页面、测试、60 条旧夹具、装配和当前文档入口已经退出工作树。新体系不得复用旧 `RetrievalService`，也不得建立与生产检索并行的评测检索器。

## 二、当前生产事实与评测接缝

当前统一故事上下文入口是 [`retrieve_story_context.py`](../../src/taichu/application/tools/retrieve_story_context.py)。该工具调用 `VectorGraphRAGService`，生产链包含：

- 正文片段和已确认知识卡联合建模；
- Milvus BM25 与稠密向量候选；
- 实体、关系种子检索和图关系扩展；
- 倒数排名融合与 BGE 重排；
- 正文邻近片段扩展；
- 返回模型上下文前的权威回源。

检索结果已包含 `source_type`、`source_id`、`source_ref`、`content_sha256`、排名、正文字符范围、`authority_verified`，以及三阶段关系列表。现有模型见 [`models.py`](../../src/taichu/application/vector_graph/models.py)，权威回源见 [`service.py`](../../src/taichu/application/vector_graph/service.py)。

正文命中必须重新读取 Markdown 对应范围并核对内容摘要；知识卡命中必须重新读取 MongoDB 当前 `lifecycle=confirmed` 的记录。Milvus 只是可重建索引，不能成为评测 Ground Truth。

因此，新评测的被测接缝固定为生产 `retrieve_story_context → VectorGraphRAGService`。评测代码只能调用真实链路，不能复制简化算法后声称代表生产效果,用户实际用什么链路，评测就测什么链路。

## 三、统一评测样例

### 3.1 运行时数据

每次样例运行统一形成：

- `input`：Golden 原始问题和必要的查询参数。
- `retrieval_context`：权威回源后真正进入模型上下文的正文和知识卡内容。
- `actual_output`：模型基于本次上下文生成的最终回答。
- `retrieval_trace`：候选、关系检索、图扩展、融合、重排、回源和耗时信息。

第一版只评测通用 Agent 实际使用的生产检索入口，暂不为写作区单独设计评测适配器。

### 3.2 Golden 最小字段

```text
case_id
query
category
graph_required
expected_source_ids
expected_relation_ids
expected_path
expected_claims
reference_answer
```

- `expected_source_ids` 使用稳定知识卡 ID 或章节 ID，不使用易随编辑漂移的 `chunk_index`。
- 正文字符范围只作为某次语料快照证据，不作为 Golden 长期身份。
- `expected_claims` 是回答必须覆盖的原子事实。
- 放入 Golden 集的样例默认已经由维护者确认，不额外设计草稿、确认和拒绝工作流。

当前报告已经记录逐案来源、关系、确定性指标、消融结果、语义评分和门禁原因。语料快照、索引清单、Embedding、重排器、Prompt、延迟、Token 与成本身份尚未完整进入报告，属于冻结首个可信基线前必须补齐的审计增强，不能把这一部分描述成已经完成。

### 3.3 稳定关系标识

生产索引内部关系 ID 会随重建变化，评测层不使用该随机身份。当前实现把关系文本做 Unicode NFKC、大小写和空白归一化，再对规范化三元组文本生成稳定 `relation_id`：

```text
subject + predicate + object
```

该标识解决索引重建漂移，但谓词同义表达仍可能产生不同 ID。当前 Golden 必须使用生产抽取口径；以后只有在真实失败证明同义谓词是高频噪声时，才增加受控谓词归一，第一版不建设关系本体系统。

## 四、30 条 Golden

| 类别 | 数量 | 主要目标 |
|---|---:|---|
| 单事实检索 | 6 | 基本命中、排序和权威回源 |
| 正文与知识卡交叉验证 | 6 | 双来源一致性与来源优先级 |
| Graph 多跳推理 | 14 | 完整关系链、跨实体推理和图扩展收益 |
| 困难负例与不可回答 | 4 | 同名干扰、噪声、已拒绝知识和正确拒答 |

设计要求：

- 多跳题不能依靠一个孤立片段直接回答。
- 同时覆盖正文来源、知识卡来源和跨来源组合。
- 负例包含高连接度实体、同名对象、语义相似噪声和已失效事实。
- 每个预期结论都能追溯到 Markdown 或 MongoDB confirmed 卡，不能从现有索引结果反推答案。

30 条 Golden 是第一版回归地基，不代表已经覆盖全部小说和问法。后续可以增加轮换集，防止围绕固定题目过拟合。

## 五、基础指标

第一版不设置一个可相互抵消问题的综合总分，各层分别给出结论。

| 层级 | 指标 |
|---|---|
| 检索 | Recall@10、MRR@10 |
| 上下文 | DeepEval 上下文相关性 |
| 数据完整性 | 权威回源通过率 |
| 生成 | DeepEval 忠实度、回答相关性 |

建议初始候选门槛：

- `Recall@10 >= 0.90`；
- `MRR@10 >= 0.80`；
- 忠实度不低于 `0.85`；
- 回答相关性不低于 `0.80`；
- 权威回源通过率为 `100%`，关键事实错误和关键引用错误次数为 `0`。

最终阈值必须在 Golden 完成人工复核并跑出首个可信基线后冻结。初始数值不能直接当作已经验证的生产标准。

## 六、Graph RAG 专项

### 6.1 完整链召回

多跳题按完整证据链评分。只召回一个节点或一条关系不能算成功。

- `Complete Path Recall`：预期完整路径是否被召回。
- `Relation Recall@K`：必需关系进入前 K 的比例。
- `Graph Expansion Noise Rate`：图扩展带入但不支持问题的证据比例；只作为失败诊断信息，不作为第一版核心硬门禁。

所有路径节点和关系都必须有权威来源，不能因为索引中存在一条边就认为它是可信证据。

### 6.2 成对消融

所有 `graph_required=true` 样例运行两组：

```text
A：BM25 + Dense + RRF + BGE
B：BM25 + Dense + Graph Expansion + RRF + BGE
```

两组必须使用同一语料快照、Embedding、候选规模、融合参数、重排器、生成模型和 Prompt，只允许图扩展开关不同。

候选晋级门槛：

- Graph 组多跳完整链召回率至少提升 10 个百分点。
- 单事实题 `Recall@10` 下降不超过 2 个百分点。
- P95 延迟和成本不超过冻结预算。

未满足成对消融门槛时，只能说明 Graph 能力已经接入，不能宣称 Graph RAG 带来质量收益。

## 七、三层评测体系

### 7.1 第一层：无参考自动语义评测

第一层使用 DeepEval 对真实查询、实际检索上下文和实际回答进行无参考自动语义评测，不依赖 `reference_answer` 或人工逐次确认。它回答的是：当前上下文是否围绕问题、回答是否忠于上下文、回答是否真正回应问题。

第一版只使用三个无参考指标：

- `ContextualRelevancyMetric`：检索上下文是否包含过多无关内容。
- `FaithfulnessMetric`：回答中的事实是否能够从实际上下文得到支持。
- `AnswerRelevancyMetric`：回答是否直接回应问题。

DeepEval 是语义指标执行适配器，不是数据事实源、结果仓储或评测编排中心。通过 `assert_test` 或 `deepeval test run` 接入 Pytest/CI。

参考资料：

- [DeepEval RAG 评测快速入门](https://deepeval.com/docs/getting-started-rag)
- [DeepEval 指标说明](https://deepeval.com/docs/metrics-introduction)

来源 ID、完整关系链、权威回源和索引新鲜度由第二层确定性回归判断，不能交给 LLM Judge。

裁判模型必须通过太初统一 LLM 网关调用并记录模型、Prompt、Token、成本和回放。固定温度；阈值附近自动重复判断；结果不一致时标记灰区并进入第三层诊断，不增加“最终人工确认后才算通过”的发布流程。

### 7.2 第二层：Golden 确定性回归

30 条 Golden 是自动回归的稳定数据基础。第一版确定性硬门禁集中检查三组契约：

- `Retrieval`：预期来源是否命中、排名是否退化、权威回源是否成功。
- `Graph`：预期实体、关系和完整路径是否被召回，Graph 开启相对关闭时是否产生真实收益。
- `Data Integrity`：所有进入模型上下文的证据是否通过权威回源与内容摘要校验。

Golden 继续保留 `expected_claims` 和 `reference_answer`，用于表达期望答案、辅助语义评测解释和人工诊断，但第一版不建设 Claims 投影、标准化、别名解析或确定性匹配引擎。生成侧质量先由第一层 DeepEval 的忠实度与回答相关性负责；Claims 自动回归只作为未来确有需要时的增强项。

第二层的任一关键案例失败都直接阻断合并，不能被平均分抵消。

### 7.3 第三层：人工兜底

人工只处理两类工作：

- 建立或修改 Golden，确保问题、预期来源、参考答案、Claims 和 Graph 路径正确。
- 诊断 CI 失败或 DeepEval 灰区，判断应该修代码、修索引、修 Golden 还是调整已校准阈值。

人工兜底不是每次发布的最后确认环节，也不承担日常逐条评分。第一版不为它建设审批工作流或页面。

## 八、自动 CI 回归策略

当前通过 `rag-smoke.yml` 和 `rag-regression.yml` 分开承载普通 PR 与 RAG 相关 PR/手动全量回归。CI 的核心不是“所有检查每次都跑”，而是在正确的变化和时点运行正确评测。

| 运行时点 | 触发范围 | 自动执行 | 结果用途 |
|---|---|---|---|
| 每个 PR | 全部代码变化 | Golden Schema、稳定 ID、5 条最快 Smoke | 防止评测资产和基本契约损坏 |
| RAG 相关 PR | Graph、检索、Embedding、重排、Prompt、语料或索引配置变化 | 30 条 Golden 确定性回归、14 条 Graph 消融、10 条 DeepEval 语义 Smoke | 确定性失败阻断合并；语义显著退化阻断，灰区自动复测后进入诊断 |
| 手动或发布前 | 主动触发或准备发布的提交 | 30 条完整评测、14 条 Graph 消融、延迟与成本 | 形成完整版本基线；未通过则阻断发布 |

### 8.1 每个 PR 的快速检查

不调用 DeepEval 裁判，检查 Golden Schema、稳定关系身份、权威回源，以及 5 条覆盖单事实、跨来源、多跳和困难负例的真实生产链 Smoke。生产 Graph 查询自身仍会调用实体抽取和关系重排模型，因此自托管 Runner 必须具备完整生产依赖，不能把它误解为纯离线单元测试。

### 8.2 RAG 相关 PR 的质量门禁

使用固定 Milvus 镜像、语料快照、Embedding 和重排模型。路径过滤至少覆盖生产 Graph RAG、检索 Tool、语料投影、索引构建、Embedding、重排、生成 Prompt、Golden 和评测代码。

确定性门禁同时比较绝对阈值和主分支冻结基线；Graph 消融必须保持变量隔离。DeepEval 先跑 10 条代表性语义 Smoke，显著低于校准下限时自动复测一次；复测仍失败则阻断，结果落在灰区时标记为待诊断，不把一次 Judge 抖动伪装成确定回归。

### 8.3 手动与发布前全量运行

个人项目当前不设置 nightly。完整 30 条评测只在手动触发或发布前运行；以后出现线上模型或索引可能每日漂移的真实需求，再根据运行证据增加定时任务。发布前不要求人工最终确认，只要求目标提交存在有效的全量自动通过记录。

当前每次运行原子保存结构化 JSON 并上传 CI Artifact，控制台输出指标摘要和具体门禁原因。JUnit、Markdown PR 摘要、基线差值、灰区自动复测、延迟和成本尚未实现，完成基线校准后再按失败诊断价值补齐。

- 失败案例和分类；
- 缺失来源、关系和证据链；
- `expected_claims` 与 `reference_answer` 的语义差异说明；
- 当前值、主分支基线和差值；
- 裁判理由与灰区状态；
- 延迟、Token 和成本变化。

裁判或供应商基础设施失败可以重试，但不能通过重试挑选最高分；质量失败必须保留首次证据。基础设施不可用必须报告为基础设施失败，不得输出质量通过。

## 九、实现入口

```text
tests/fixtures/evaluations/rag_graph_core/
src/taichu/application/evaluations/rag/
src/taichu/infrastructure/evaluations/rag/
tests/unit/application/evaluations/rag/
tests/unit/infrastructure/evaluations/rag/
scripts/evaluate_rag.py
.github/workflows/rag-smoke.yml
.github/workflows/rag-regression.yml
```

结果保存到 `project_assets/derived/rag_evaluations/`，只作为运行、审计和回放数据，不得成为正文或结构事实源；目录由报告仓储按需创建，职责已经同步到 `project_assets/readme.md`。

## 十、实施顺序

### 第一批：评测地基（已完成）

- 建立 Schema、稳定来源标识和 30 条人工维护样例。
- 实现生产链适配器与确定性基础指标。
- 固定语料、索引和模型身份。
- 完成 5 条 Smoke 的本地与 CI 运行入口。

验收：相同输入连续运行的确定性指标一致，Ground Truth 全部能回读权威事实源。

### 第二批：Graph 专项（已完成代码实现，待真实基线校准）

- 增加稳定关系 ID。
- 实现完整路径召回和关系召回两个核心指标，并把扩展噪声作为诊断指标。
- 实现严格成对的 Graph 开关消融。
- 冻结首个可信 Graph 收益基线。

验收：可以定位差异发生在关系检索、扩展、重排还是生成阶段。

### 第三批：CI 与无参考语义评测（核心链路已完成）

- 接入普通 PR、RAG 相关 PR、手动和发布前工作流。
- 接入 DeepEval 与统一 LLM 网关。
- 自动复测、灰区诊断规则和成本上限留待首个可信基线后实现。
- 当前产出控制台摘要与可下载 JSON 审计工件。

验收：人为制造来源回归、关系链回归、语义质量回归和延迟回归时，评测均能在正确时点失败，并由 CI 提供可定位证据。

## 十一、自我 Review

本方案刻意避免：

- 只看最终回答而混淆检索失败与生成失败；
- 用综合平均分掩盖关键事实错误；
- 把 LLM Judge 当作唯一裁判；
- 用不同模型或候选规模伪装 Graph 因果收益；
- 把 Milvus 索引副本当作 Ground Truth；
- 为第一版增加时间线专项、负向字段审批流或发布前人工确认。

仍需校准：

1. 30 条 Golden 的问题、来源、关系谓词、`expected_claims` 和 `reference_answer` 是否与当前权威语料逐条一致。
2. Graph 收益与 DeepEval 的最终阈值；当前代码阈值只是首跑候选值。
3. 自托管 CI Runner 的 Milvus、Embedding、BGE 重排器和模型网关可用性及固定版本。
4. 语料/索引/模型/Prompt 身份、延迟、Token 和成本进入报告后的冻结基线。

当前结论：第一版核心代码、30 条 Golden、Graph ON/OFF 消融、DeepEval 适配、命令入口和分层 CI 已落地。2026-08-19 真实 Smoke 先遇到 BGE 重排服务 `127.0.0.1:8012` 返回 502，按 `start.bat` 完整重启并通过健康检查后，实际重排又超过 120 秒读取超时；两次均被识别为基础设施失败，没有生成虚假质量分数，因此尚未形成可信质量基线。下一步是解决或扩容固定 BGE 运行环境后逐条校准 Golden 与阈值，而不是继续增加指标、审批流、评测平台或夜间任务。
