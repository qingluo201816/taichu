# project_assets 目录说明

> 更新日期：2026-08-15

`project_assets/` 是太初单本小说的本地资产根目录，用于保存正文 Markdown、工作区中间态、AI/Agent 运行记录、评测审计和临时生成文件。MongoDB `taichu.knowledge_cards` 是唯一结构事实源，`project_assets/` 下的 JSON/JSONL 不承担兼容事实源职责。

## 本机实际部署位置

- 本说明文件：`C:\Users\wyh\Desktop\Taichu\project_assets\readme.md`。
- 项目资产根目录：`C:\Users\wyh\Desktop\Taichu\project_assets`，由 `PROJECT_ASSETS_DIR` 指定，仍保留在项目目录中。
- MongoDB 数据目录：`E:\Taichu\MongoDB\data\db`，由 `MONGODB_DATA_DIR` 指定。
- MongoDB 日志目录：`E:\Taichu\MongoDB\log`，由 `MONGODB_LOG_DIR` 指定。
- Milvus Vector Graph RAG 索引：Docker 命名卷 `taichu_milvus_data`、`taichu_milvus_etcd`、`taichu_milvus_minio`，服务地址为 `http://127.0.0.1:19530`；它是可删除、可重建的外部派生索引，不属于 `project_assets/`。
- Qwen Embedding 模型：`E:\Taichu\Models\Qwen3-Embedding-4B\Qwen3-Embedding-4B-Q4_K_M.gguf`，仅用于生成向量，不是小说事实源。
- llama.cpp 运行时：`E:\Taichu\Runtime\llama.cpp\b10066`；Embedding 日志位于 `E:\Taichu\Embedding\log`。
- 原小说导入资料：`E:\Taichu\导入资料\太初原小说`，只作为外部导入材料，不属于 `project_assets/`。
- 旧知识 JSON 迁移备份：`E:\Taichu\迁移备份\知识库-20260711-151915`，包含全部 88 张旧卡和 `migration-manifest.json`，不属于运行时数据目录。
- MongoDB、Milvus、模型、推理运行时和日志都不属于 `project_assets/` 目录树；当前开发机把外部数据与大文件放到 E 盘或 Docker 命名卷，避免占用项目所在磁盘。更换开发机时，应同步更新项目根目录 `.env`，不得仅修改本说明。

旧知识迁移已完成 `apply` 和 `finalize`：58 张有效卡作为 `lifecycle=confirmed` 写入 MongoDB，30 张已弃用重复卡仅保留在 E 盘备份，`source/knowledge/` 已完成对账并删除。存储骨架和业务代码不得重新创建该目录。

## 维护规则

- 修改 `project_assets/` 下的目录结构时，必须同步热更新本文件。
- 新增、删除、移动或改变任一目录职责时，必须在同一次变更里更新“目录结构”和“目录职责说明”。
- 文本事实源优先放在 `source/`；结构事实源归属 MongoDB；仓库内可再生成的运行产物放在 `derived/`，缓存、日志和导出物放在 `generated/`；外部 Milvus 图索引单独记录并保持可重建。
- 不要把可再生成的缓存或日志当作正式源数据依赖。
- 不创建或保留 `.gitkeep`；目录由存储实现按需创建。
- 评测基准和测试夹具放在 `tests/fixtures/evaluations/`，不得作为 `project_assets/` 的额外顶层目录。

## 数据宪法

- Markdown 是唯一文本事实源，正文与需要保留作者原始表达的长文本必须以 Markdown 为准。
- MongoDB 是唯一结构事实源，作者确认后的角色、地点、势力、物品、事件、规则等结构化事实只以 MongoDB 中 `lifecycle=confirmed` 的记录为准。
- 当前 Milvus Vector Graph RAG、BM25 稀疏索引以及未来可能增加的缓存都只能是可重建派生层。
- SQLite/FTS 已废弃，不属于当前数据目录或后续架构决策。
- AI 不得直接写入 MongoDB，必须先生成 JSON 中间态并通过 schema、来源、冲突和生命周期校验。
- 需要作者审核、业务确认或评测状态管理的非事实候选必须显式标记 `lifecycle`，取值只能是 `draft`、`confirmed`、`rejected`。通用 Agent 自动运行记忆和 LangGraph 节点检查点是纯运行状态，不经过作者确认，分别用请求序号、自动过期、`deleted_at` 和线程检查点管理有效性。

## 数据分层

- `source/`：作者和系统长期维护的本地文本源与工作区状态。正文 Markdown 是文本事实；workspace JSONL 是非事实中间态。
- MongoDB：唯一结构事实源。它不属于 `project_assets/` 目录树，角色、地点、势力、物品、事件、规则等确认事实只存于 `knowledge_cards`。
- Milvus：统一向量图谱派生层。它不属于 `project_assets/` 目录树，保存从正文 Markdown 片段和 MongoDB confirmed 卡生成的实体、关系与 passage；命中必须携带原始正文区间或知识卡引用。
- `derived/`：AI、Agent 和评测产生的 JSON 中间态、运行快照与审计记录，不等同于正式知识库。
- `generated/`：按需产生的运行日志、导出临时物和可重建缓存，不得承载唯一事实。

## 目录结构

```text
project_assets/
├── source/                                      # 单本小说的正式源数据根目录
│   ├── metadata.yaml                            # 小说级元数据
│   ├── manuscripts/                             # 正文章节、目录清单和大纲源数据
│   │   ├── manifest.json                        # 章节树和卷章元信息
│   │   ├── outline.json                         # 大纲结构数据
│   │   ├── chapters/                            # 当前有效正文稿目录
│   │   │   ├── volume_001_第一卷/               # 第一卷章节正文
│   │   │   ├── volume_002_第二卷/               # 第二卷章节正文
│   │   │   ├── volume_003_第三卷/               # 第三卷章节正文
│   │   │   └── volume_004_第四卷/               # 第四卷章节正文
│   │   └── deleted_chapters/                    # 被删除章节的归档区
│   │       └── volume_004_第四卷/               # 第四卷删除章节归档
│   └── workspace/                               # 工作区状态、收件箱、待处理事实和写作 AI 运行记录
├── derived/                                     # 派生数据和 Agent 运行记录
│   ├── agent_runs/                              # Agent 运行快照根目录
│   │   └── knowledge_extraction/                # 正文知识沉淀 Agent 的运行记录和候选审核项
│   ├── llm_usage/                               # 跨任务模型调用遥测，按需创建 calls.jsonl
│   ├── llm_call_replays/                        # 通用 Agent 逐次模型调用脱敏回放资产
│   ├── embedding_usage/                         # 旧独立向量链路的历史 Embedding 遥测
│   ├── retrieval/                               # 统一知识召回技术观测，按需创建 calls.jsonl
│   ├── capability_invocations/                  # Tool、专业子 Agent 与 LLM 的脱敏技术调用记录
│   ├── capability_artifacts/                    # 专业子 Agent 的有类型 JSON 中间产物
│   ├── general_agent_runs/                      # 通用写作助手 Runtime 的独立业务检查点
│   ├── general_agent_capability_results/        # 无副作用能力的可恢复 completed record 与权威索引
│   ├── general_agent_context_snapshots/         # 规划、重规划、校验阶段的五层上下文快照历史
│   ├── general_agent_graph_checkpoints/         # LangGraph 节点级持久检查点
│   ├── general_agent_recovery_benchmarks/        # 通用写作助手恢复机制的可重建基准报告
│   ├── general_agent_memory/                    # 通用写作助手运行记忆记录，不是小说事实
│   ├── agent_evaluations/                       # 专项 Agent 效果评估输入快照、结果与审计记录
│   │   ├── knowledge_extraction/                # 知识沉淀评估报告及裁判校准报告
│   │   └── retrieval/                           # 统一知识召回离线评测结果
│   └── general_agent_benchmarks/                # 通用写作智能体固定基准运行、实验、迭代与比较资产
│       └── interactive-runtime/                 # 网页发起评测的运行状态与终态证据持久化
└── generated/                                   # 按需创建的临时生成物根目录
    ├── pytest-workspaces/                       # pytest 临时隔离工作区，不属于项目运行数据
    ├── milvus_vector_graph/                     # 当前多跳图索引的 active 构建摘要
    ├── agent_memory_indexes/                    # 从运行记忆记录重建的词法索引
    └── temp/                                    # 前后端运行日志等临时输出
```

## 关键目录职责

### source

`source/` 是本地文本源数据和工作区资产层。正文 Markdown 是唯一文本事实源；结构化事实只存于 MongoDB。

- 正文源文件位于 `source/manuscripts/chapters/`。
- 章节清单位于 `source/manuscripts/manifest.json`。
- 大纲数据位于 `source/manuscripts/outline.json`。
- 收件箱、偏好设置、工作区状态、待处理事实和写作 AI 运行记录位于 `source/workspace/`。
- 写作页 9 个 AI 按钮的真实模型调用轨迹保存在 `source/workspace/writing_ai_runs.jsonl`，用于历史查看、提示词审计和回放，不直接写入正式知识库。
- `source/knowledge/` 已退出运行时结构并在迁移 `finalize` 时删除；`ensure_skeleton()` 不会重建它。

### 旧知识 JSON 迁移结果

旧知识卡不再保存在 `project_assets/` 中作为运行数据。迁移备份固定在：

`E:\Taichu\迁移备份\知识库-20260711-151915`

- 全部 88 张旧 JSON 均已复制并通过迁移清单记录 SHA-256。
- 58 张原 `active` 卡已转换并导入为 MongoDB `lifecycle=confirmed`。
- 30 张原 `deprecated` 重复卡未导入，只存在于备份和迁移清单。
- `finalize` 对账已通过，`project_assets/source/knowledge/` 已删除；后端无 JSON 双写、读取回退或目录重建逻辑。

MongoDB 知识卡统一使用 `lifecycle=draft|confirmed|rejected`；默认列表、事实查询和 AI 有效上下文只读取 `confirmed`。

### derived

`derived/` 是派生数据层。这里保存 Agent 运行快照、LLM 调用记录、评测 JSON 中间态和候选审核项，用于审计与回放；`source/workspace/` 中的 Inbox 与 AI JSONL 也只属于工作区中间态。

跨任务模型调用遥测追加保存在 `derived/llm_usage/calls.jsonl`。每行只包含模型快照、任务来源、Token、费用、耗时、状态、上游请求 ID 和脱敏错误，不保存密钥、鉴权头、完整 Prompt 或模型原文；该目录属于可重建运行遥测，不是正文或结构化知识事实源。

通用 Agent 逐次模型调用回放保存在 `derived/llm_call_replays/`。生产统一网关按调用保存脱敏后的角色消息、规范化模型正文、模型与 Token 元数据以及请求和响应 SHA-256，用于质量评测和问题回放；它不保存 HTTP 鉴权头、API Key 或供应商原始响应包。该目录与只保存技术遥测的 `llm_usage/`、`capability_invocations/` 分工独立，也不是正文或结构事实源。

`derived/embedding_usage/calls.jsonl` 是被 Milvus Vector Graph RAG 替换前的独立向量链路历史遥测。当前上游库直接调用本地 OpenAI 兼容 Embedding 接口，不再向该文件追加；历史记录仍不是知识事实或向量备份。

统一知识召回技术观测追加保存在 `derived/retrieval/calls.jsonl`。每行保存召回关联 ID、调用方、模式、策略档案、请求与实际策略、回退原因、分支候选数与命中数、后端与过滤耗时、索引快照和脱敏错误；查询与辅助上下文只保存长度和 SHA-256，不重复保存正文或用户完整输入。该记录用于跨消费者排查召回链路，但不替代写作区、知识沉淀 Workflow 或通用 Agent Runtime 各自的业务日志、状态机与评测记录。旧记录不要求补写新增字段，读取时使用兼容默认值。

通用写作助手能力层的 Tool、专业子 Agent 和内部 LLM 技术调用记录追加保存在 `derived/capability_invocations/calls.jsonl`。记录只保存调用树引用、能力名称、状态、输入哈希、字符数、模型角色、耗时、授权引用和脱敏错误，不保存密钥、鉴权头、完整 Prompt、完整模型原文或外部页面全文；通用 Agent 节点监控按运行标识读取这些记录并折叠到所属节点，但它不替代三类执行体系各自的业务日志。

专业子 Agent 的结构化输出保存在 `derived/capability_artifacts/`。每个 JSON 文件显式标记 `lifecycle=draft`，记录产物类型、生产者、输入与内容哈希、来源引用和创建时间，可供后续专业子 Agent 按稳定引用接力消费；这些文件是可审计中间态，不是 Markdown 正文或 MongoDB 结构事实。

通用写作助手 Runtime 的业务检查点保存在 `derived/general_agent_runs/`。每次运行独立保存目标、范围、计划修订、动态节点状态、人工中断、来源与中间产物引用、校验结果和最终回答，用于任务列表、恢复和后续节点监控。它不复用知识沉淀 Workflow 的 `agent_runs/knowledge_extraction/`，也不成为正文或结构事实源。

无副作用 Tool 与专业子 Agent 的已完成结果保存在 `derived/general_agent_capability_results/`。目录按 `conversation_id/run_id` 双层 owner 分区，每个结果分别保存 create-once completed record 和同 ID 权威索引；Runtime 只在完整 record 与索引均落盘后推进节点成功，并在同一运行恢复时按完整能力身份定向复用。写入型 Tool 不进入该目录，仍只通过 Effect 与真实资源对账恢复。结果随父运行保留和清理，不提供单条手工新增、修改或删除接口；这些 JSON 只用于运行恢复、审计和回放，不是 Markdown 文本事实源、MongoDB 结构事实源或其兼容回退。

通用写作助手五层上下文历史保存在 `derived/general_agent_context_snapshots/`。规划、每次重规划和校验阶段组装完成后各追加一份不可变快照，供前端按请求和阶段查看、供后续评测复盘；`general_agent_runs/` 与 LangGraph 检查点中只保留最新快照用于当前业务投影和恢复，不把整段快照历史重复写入每个检查点。

LangGraph 节点级检查点保存在 `derived/general_agent_graph_checkpoints/`。每个 `run_id（运行标识）` 对应一个线程目录，内部使用原子写入、哈希链修订和最新修订指针保存 LangGraph 通道状态、中间写入及父检查点关系；服务重启后以同一个 `thread_id（线程标识）` 和计划命名空间恢复未完成节点，已经成功的能力节点不会重复执行。写能力的副作用日志也追加保存在该线程目录中，用于在“外部写入成功、检查点尚未落盘”的窗口内先核对真实资源，再决定复用、继续或转人工处理。它与 `general_agent_runs/` 的业务投影互补，不替代任务列表、最终回答或能力节点审计。

通用写作助手恢复基准保存在 `derived/general_agent_recovery_benchmarks/`。报告由 `scripts/benchmark_general_agent_recovery.py` 使用真实能力注册表和动态 LangGraph 执行器生成，记录不同节点数、并发度和进程中断场景的完成率、恢复率、重复执行保护、修订数量、存储体积与耗时。该目录是可重建的工程验证产物，不保存完整 Prompt、正文或密钥，也不构成业务状态或小说事实。

通用写作助手运行记忆保存在 `derived/general_agent_memory/`。每条 JSON 记录使用原子替换写入，保存类型、短摘要、来源运行、稳定引用、创建请求序号、自动退出上下文的请求序号、内容哈希和 `deleted_at（删除时间）`。运行记忆由 Runtime 自动写入、替换和自动过期，不存在草稿、确认、拒绝生命周期，也不要求作者确认；前端只读查看，用户不能新增、修改或逐条删除底层运行记忆，只能通过正常对话或人工确认节点影响 Agent。章节或长资源只保存短摘要与引用，不复制全文。运行记忆用于延续任务，不是 MongoDB 知识卡或小说事实，事实引用在消费时仍须重新取证。

知识沉淀效果评估保存在 `derived/agent_evaluations/knowledge_extraction/`。每次评估独立冻结评测集、实际候选、正文、评分参数和模型身份，并保存确定性结果与裁判调用审计；裁判校准报告位于其 `calibration_reports/` 子目录。评估报告和校准报告都是非事实派生数据，通过 `lifecycle` 区分草稿、已确认和已废弃状态，不得反向成为正文或结构化知识事实源。

通用写作智能体固定基准的派生资产统一归属 `derived/general_agent_benchmarks/`，评测基准位于 `tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json`。该目录按需保存 synthetic 冻结基线、网页发起评测的运行状态与终态证据、真实模型逐案运行、首轮资格工件、多模型比较、问题关联、权威索引、幂等记录、关闭租约和隔离工作区，用于从固定用例、预检门禁、逐案审计、提供商实验和冻结清单回放评测。`interactive-runtime/` 以运行标识逐条原子保存网页运行及其案例、门禁和证据包，服务重启后继续作为最近评测列表的可审计来源；冻结基线仍只从权威索引恢复，不扫描未索引历史。这些资产是可审计派生数据，不成为正文或结构事实。

统一知识召回离线评测结果保存在 `derived/agent_evaluations/retrieval/`。每次结果冻结评测集校验和、已确认知识快照、请求与实际策略、策略预算、Recall/Precision/MRR/nDCG、空结果与禁止卡指标、分组指标、延迟和失败样例；评测基准位于 `tests/fixtures/evaluations/retrieval_knowledge_core/`。结果只保存样例标识、稳定知识卡 ID 和结构化指标，不复制查询正文或完整知识卡，也不得反向成为结构事实。

正文知识沉淀 Agent 的候选卡不单独落到 `source/knowledge/`，而是保存在运行 JSON 的 `review_items[*].suggested_card` 中。只有用户确认并通过 JSON 中间态校验后，才允许由应用层服务写入 MongoDB 成为结构事实。

现有运行记录中的候选处理状态通过 `candidate_status` 表达；非事实数据仍须用 `lifecycle` 表达事实生命周期：

- `pending`：待处理；保留在待处理队列中，本身就表示可以稍后再处理。
- `confirmed`：已确认。
- `rejected`：已废弃，保留在运行记录中用于审计。

### generated

`generated/` 是按需创建的临时生成物层。`generated/milvus_vector_graph/active_manifest.json` 保存最近一次正文与知识卡联合建模的快照哈希、来源数量、实体数、关系数和 passage 数；它不保存向量、正文或完整知识卡。删除 Milvus collections 和该清单后，可以从 Markdown 与 MongoDB confirmed 卡全量重建。

`generated/agent_memory_indexes/lexical_index.json` 是运行记忆的可重建词法索引，只保存记忆标识、内容哈希和词项，不保存唯一内容副本。索引缺失、过期或损坏时会从 `derived/general_agent_memory/` 自动重建；它不得与知识库向量索引混用。

该目录下的数据不得成为唯一事实来源。若生成物丢失，系统应能从 Markdown 文本事实源、MongoDB 结构事实源和必要的运行流程重新生成。
