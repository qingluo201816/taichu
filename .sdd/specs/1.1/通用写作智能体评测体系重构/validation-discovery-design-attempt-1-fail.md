# 独立设计发现

规格：`1.1/通用写作智能体评测体系重构`  
模式：`design`  
发现时间：`2026-07-27T05:50:00Z`  
发现阶段允许输入：`spec.json`、已独立 PASS 且哈希有效的 `requirements.md` 与需求校验报告、`gap-analysis.md`、项目规则、当前源码/测试/配置/依赖/启动脚本、仓库内 `pico-v3` 参考实现。  
阶段隔离声明：本文件落盘前未读取、搜索、摘要或引用 `design.md`、`research.md`、`design-review-report.md` 的任何内容，也未读取由其生成的任务或实现说明。Graphify 按根 `AGENTS.md` 当前禁用规则未调用，现有图谱产物未用作事实源。

## 1. 前置对象与基线

- 需求对象：`.sdd/specs/1.1/通用写作智能体评测体系重构/requirements.md`
- 需求 SHA-256：`b5b65cf351b58c6ff72bfc6f76f1d9c3b10470ebc01875670571957fe14a1cf2`
- 需求独立报告 SHA-256：`5a963c09cf5266874e77b70c274ba7a07890960f7bbb379410d17120d3a5212f`
- 需求 discovery SHA-256：`1fec9a39dc15199b242ae095ce157c24ff60f5e397431ac377a529148f6bca82`
- `spec.json.validations.requirements` 登记值与以上三个当前文件哈希一致，报告最后一行精确为 `结论：PASS`。
- Git 基线：`HEAD 82bab37a5514f8a6f4d632872010293a910c2bec`。工作树非干净，存在大量与本校验并行的用户改动和未跟踪文件；本轮只允许写本 discovery 与后续独立设计校验报告，不回滚、不覆盖、不纳入其他改动。
- 需求规模：15 个数字需求组、325 条验收标准；本发现按需求组建立设计约束，而不是用旧五维实现反推目标。

## 2. 核心架构结论

### 2.1 必须采用“新评测核心 + 现有事实源窄适配”

旧实现是“已有 Runtime 运行 → 五维加权评分 → 单条可删除 JSON”的后验评分器，不具备固定套件执行、隔离夹具、合成/真实分轨、案例工作区、六类硬门禁、证据包、实验、缺陷闭环或多模型准入：

- 旧模型根是 `GeneralAgentEvaluationDataset`、`GeneralAgentEvaluationCase`、`GeneralAgentEvaluationDimension`、`GeneralAgentEvaluationRecord`，五维字段和 `overall_score` 位于 `src/taichu/application/evaluations/general_agent/models.py:95-163`。
- 旧服务只接收 `dataset_id/case_id/run_id`，读取既有 run 和 trace 后评分，位于 `src/taichu/application/evaluations/general_agent/service.py:53-128`；最终通过条件仍是 `overall >= 80 and not critical_failed`，位于同文件 `:354-395`。
- 旧仓储把结果保存到 `derived/agent_evaluations/general_agent/general_eval_*.json`，支持列表、读取和物理删除，位于 `src/taichu/infrastructure/evaluations/general_agent_repository.py:59-130`。
- 旧 HTTP 路径为 `/api/agent-evaluations/general-agent`，只有数据集、创建后验评估、列表、详情和删除，位于 `src/taichu/api/routes/general_agent_evaluations.py:20-137`。

因此，设计不能扩展或兼容旧根模型。应新增一个拥有套件合同、运行状态、案例工作区、门禁、证据包、迭代和比较结论的评测核心；现有 Runtime、能力目录、Inbox、LLM 审计、Markdown/Mongo 事实源继续拥有各自数据，只通过 Protocol/只读查询或受控命令适配。

### 2.2 责任与数据所有权

| 责任 | 所有者 | 设计必须保证 |
|---|---|---|
| 套件、案例、脚本、阈值、能力覆盖和内容身份 | 新评测核心 | 固定合同规范化后内容寻址；运行开始后不可漂移；合同错误在任何案例执行前一次列全 |
| 案例工作区、密封夹具副本和隔离生命周期 | 新评测运行器/夹具管理边界 | 每案例独立 Markdown、confirmed 知识、初始对话、初始运行记忆和派生目录；不得访问活动工作区 |
| 通用 Agent 的规划、执行、授权、记忆、检查点和运行状态 | 现有 `GeneralAgentRuntimeService` 及其依赖 | 评测调用真实 Runtime，不复制固定 DAG、不伪造能力；评测自己的生命周期不能塞入 Runtime 状态枚举 |
| Tool/Subagent 能力事实 | 生产插件发现与注册 | 快照来自当次 `discover_tools`/`discover_subagents` 和 manifest 稳定字段，不维护第二份手写生产能力清单 |
| Runtime 原始 run/call/snapshot/replay/checkpoint/effect/usage | 各现有仓储 | 只读消费稳定 ID；不改字段、生命周期或写入流程，不用 mtime 或“最新文件”关联 |
| 工作记忆四态与生产者有效性 | `AgentMemoryService`/`ContextAssembler`/Runtime | 生产修复与评测专项分开；评测不能提供作者手动操纵记忆入口 |
| 系统问题记录 | 现有 `/api/inbox/issues` 唯一入口 | 新闭环协调器只能经该入口创建/PATCH/读回；评测工件保存反向链接，但不能创建平行问题文档 |
| 请求与实际模型执行证据 | 现有 LLM gateway、usage、replay | 比较门禁读取实际 provider/model、probe、fallback、replay、Token、费用、错误；请求 model ID 本身不充分 |
| 新套件运行/案例/证据包/实验/迭代/比较工件 | 新不可变/状态化评测仓储 | 属于 `project_assets/derived/agent_evaluations/` 派生审计资料，不是小说事实；正文和 Prompt 只保留最小引用 |
| 页面状态与中文显示 | 服务端资源模型 + 前端显示适配 | 前端不重算哈希、门禁、可比性或排名准入；内部枚举集中映射为中文 |

## 3. 可复用的真实扩展点

### 3.1 生产能力目录

- `discover_tools()` 和 `discover_subagents()` 分别扫描、导入并校验插件，位于 `src/taichu/infrastructure/plugin_discovery.py:67-154`。
- 应用组合根把发现结果注册到 `ToolRegistry`/`SubagentRegistry`，位于 `src/taichu/main.py:388-428`。
- `ToolRegistry.list_manifests()` 与 `SubagentRegistry.list_manifests()` 均按名称稳定排序，位于 `src/taichu/application/tools/registry.py:72-84`、`src/taichu/application/subagents/registry.py:64-74`。
- 当前测试锁定 17 个 Tool 与 12 个 Subagent，证据为 `tests/unit/infrastructure/test_plugin_discovery.py:32-92`；`CapabilityEvaluationProfile` 对当前发现集合的一致性测试位于 `tests/unit/application/evaluations/test_capability_profiles.py:13-25`。
- `capability_profiles.py` 当前是每能力独立指标口径，不是案例覆盖事实；其 `all_capability_evaluation_profiles()` 只返回静态 profile（`src/taichu/application/evaluations/capability_profiles.py:32-53`）。设计必须明确它可作为机制指标资料但不能代替逐能力合格案例反向覆盖。

快照算法至少要规范化：能力类型、name、description、input/output schema、side effect、authorization、required capabilities、allowed tools、limits/exposures 等影响执行的稳定 manifest 字段；排序后计算内容哈希。任何能力漏覆盖、未知/重复/不可反向定位映射或运行前目录身份漂移都应使套件预检原子失败。

### 3.2 Runtime 可组合边界

- `GeneralAgentRuntimeService` 构造函数已经依赖 Protocol/服务注入，拥有 `create_run/run/start/resume/cancel/get/list`，位于 `src/taichu/application/general_agent/service.py:91-340`。
- `GeneralAgentRunLimits` 当前原生提供节点、重规划、并发、总 Tool 调用和总时长限制，位于 `src/taichu/application/general_agent/models.py:66-71`；模型调用次数与 Token 预算仍需由评测证据门禁统计，不能假称 Runtime 已直接强制全部六预算。
- Runtime 当前业务状态是 `init/clarifying/planning/executing/waiting_human/verifying/replanning/completed/failed/cancelled/timeout`，位于 `src/taichu/application/general_agent/models.py:20-33`。新评测 run 的 `queued/running/completed/failed/invalid/unfinished/cancelled/blocked` 应是独立状态机，不修改 Runtime 枚举。
- 测试 `_runtime()` 已证明可以用隔离根目录、隔离 run/memory/checkpoint/effect/snapshot 仓储和注入 LLM gateway 重新组合真实 Runtime，位于 `tests/unit/application/general_agent/test_runtime.py:1141-1182`。
- 生产 `CapabilityContext` 注入 chapter、outline、knowledge、retrieval、policy、trace、artifact、LLM 等真实能力，位于 `src/taichu/main.py:388-422`；Tool handler 在调用时从该 context 取服务（`src/taichu/application/tools/registry.py:36-141`），Subagent 同样从其 context 使用 Tool/LLM/产物仓储（`src/taichu/application/subagents/registry.py:33-135`）。

这意味着隔离运行不能只换 `GeneralAgentRunRepository`。必须用案例专属 `CapabilityContext` 重新注册同一批真实插件，把 chapter/outline/storage/knowledge/retrieval/policy/trace/artifact/memory/checkpoint/effect/snapshot/replay/usage 全部指向案例工作区或只读密封数据。若复用生产 `tool_registry` 或生产 capability context，写 Tool 仍可触及作者活动 Markdown/Mongo，是 critical 事实安全风险。

### 3.3 密封事实与隔离存储

- 活动 Markdown 事实由 `ProjectAssetStorageBackend`/`ChapterService` 从 `project_assets/source` 使用；生产组合见 `src/taichu/main.py:150-154`。
- 结构事实由 `MongoKnowledgeRepository` 持有，默认数据库是 `taichu`、集合是 `knowledge_cards`；构造函数允许显式 `database_name` 和 `collection_name`，位于 `src/taichu/infrastructure/knowledge/mongo_repository.py:35-65`。
- `StructuredKnowledgeRepository.list_confirmed_cards()` 是技术无关读取契约，位于 `src/taichu/application/contracts/knowledge_repository.py:75-88`。
- 数据宪法要求 Markdown 与 Mongo confirmed 分别为事实源，评测 JSON 只作派生审计资料；`project_assets/readme.md:94-122,132-146` 说明现有运行和评测目录职责。

计划新增的密封夹具应有一个规范化 manifest，分别记录 Markdown 文件路径/哈希、confirmed 知识规范化快照/哈希、初始对话/记忆、快照总身份。每案例先在精确 suite/run/case 命名空间创建干净副本；Mongo 使用专用测试数据库或专用临时集合且绝不能回退到 `taichu.knowledge_cards`，文件侧使用工作区专属根。运行前后分别计算活动 Markdown、活动 confirmed 知识、密封源和其他案例副本不变量；失败即 `fixture_isolation_failed/invalid`。取消/崩溃需要保留最小失败证据并提供孤儿工作区清理规则。

### 3.4 严格合成脚本边界

- 当前 `_ScriptedGateway` 只是测试私有对象，按 `task_name` 从多个列表 `pop(0)`，未知任务直接字典索引，位于 `tests/unit/application/general_agent/test_runtime.py:111-151`。
- 它能证明 `LLMGatewayContract` 注入缝有效，但不能证明全局顺序、交互类型、内容 matcher、意外交互、跨类型乱序、脚本提前耗尽、Runtime 停止后剩余步骤或规范化重复结果。
- `LLMRequest` 已携带 `model_id/messages/task_type/task_name/run_id/context_snapshot_id/tools/temperature/max_output_tokens`，位于 `src/taichu/application/contracts/llm.py:65-82`；可作为严格 step matcher 的真实输入形状。

计划新增 driver 应使用单一全序 step stream。每步至少含稳定 step ID、交互类型、任务/能力目标、允许匹配字段、规范化请求条件、固定响应或固定异常。调用时必须逐步匹配；未声明、乱序、内容不符和提前耗尽分别形成稳定失败。Runtime 结束无论成功/失败/取消都必须调用 finalize，列出全部剩余 step。消费轨迹、脚本身份、Runtime 配置身份和规范化结果哈希进入案例工件。合成 driver 是评测基础设施，不得注册为生产 Tool/Subagent。

### 3.5 Runtime 证据读取

现有最小 Protocol：

- run：`GeneralAgentRunRepository.get/list_runs`，`src/taichu/application/contracts/general_agent_run.py:8-25`；
- invocation：`InvocationTraceReader.list_for_run`，`src/taichu/application/contracts/invocation_trace.py:17-25`；
- context snapshot：`GeneralAgentContextSnapshotRepository.list_for_run`，`src/taichu/application/contracts/general_agent_context_snapshot.py:8-13`；
- replay：`LLMCallReplayRepository.get/list_for_run`，`src/taichu/application/contracts/llm_replay.py:8-15`；
- usage：`LLMUsageRepository.get/list_calls/summarize`，`src/taichu/application/contracts/llm_usage.py:14-35`；
- effects：`GeneralAgentEffectRepository.latest/list_effects`，`src/taichu/application/contracts/general_agent_effects.py:9-16`。

`GeneralAgentRun` 包含 `run_id/conversation_id/request_index/plan_revision/node_runs/context_snapshot_id/checkpoint_revision/lifecycle_events/errors`（`src/taichu/application/general_agent/models.py:404-446`）；调用记录保存 `call_id/parent_call_id` 及 run，context/replay/effect 各有稳定关联。设计需新增窄的只读 `EvaluationEvidenceReader` 聚合 adapter，显式返回每类证据的 `available/missing/corrupt/not_applicable/conflict`，并验证：

`conversation_id → run_id/thread_id → node_id/plan_revision → attempt_id/effect_id`，再以 `call_id/parent_call_id/context_snapshot_id` 补充。

不能按 mtime、目录最新项或文本近似关联。案例证据包只保存摘要、稳定引用、availability 和规范化 `bundle_hash`，不能复制 replay 全消息、context 全正文或巨型 trace。

## 4. 关键生产缺口必须在设计中形成可达调用链

### 4.1 工作记忆防复活

真实现状：

- 四态 `ACTIVE/STALE/REJECTED/SUPERSEDED` 与 `BASIS/REVIEW_TARGET/REPAIR_SOURCE` 已存在，位于 `src/taichu/application/agent_memory/models.py:37-65`。
- `AgentMemoryEntry` 记录 producer、result type、evidence anchors、dependencies、前后状态原因和哈希，位于同文件 `:78-167`。
- `list_active()` 严格使用 `entry.is_active()`，但 `list_invalidated()` 默认只选择 `REJECTED/STALE`，漏 `SUPERSEDED`，位于 `src/taichu/application/services/agent_memory_service.py:236-301`。
- `ContextAssembler` 将有效与失效记忆分区、根据 producer validity 排除非 ACTIVE 节点摘要，位于 `src/taichu/application/general_agent/context.py:180-257`；当前失效区仍因默认参数看不到 `SUPERSEDED`。
- 当前代码已经新增只读 `producer_validities()`（`src/taichu/application/services/agent_memory_service.py:387-402`），但 Orchestrator 和 Executor 的复用校验仍只检查旧节点 `SUCCESS`、节点 ID 和能力契约，位于 `src/taichu/application/general_agent/orchestrator.py:259-293`、`src/taichu/application/general_agent/executor.py:190-227`。
- 现有测试覆盖 rejected 隔离、revision 替代、部分依赖传播和节点摘要排除（`tests/unit/application/general_agent/test_memory_context.py:159-340`），但未形成 `SUPERSEDED` 修复投影、复用来源 ACTIVE 门禁、所有 digest/snapshot/reuse 投影及并行候选的完整专项。

设计必须同时规划生产修复与评测专项：

1. 失效修复区显式包含三种非 ACTIVE 状态，并标记“仅供修复、不作为当前事实”；
2. Orchestrator 计划校验和 Executor 实际复用必须共同调用同一生产者有效性查询；缺失、非 ACTIVE、冲突都拒绝复用，不能只看 `SUCCESS`；
3. 节点摘要、digest、context snapshot、resume/reuse 都使用统一有效性过滤，不各自复制规则；
4. 评测专项分别验证来源指纹、BASIS/REVIEW_TARGET 传播、REPAIR_SOURCE 不传染、审查目标、替代、并行候选和四个投影入口；任一旧三态成为当前事实即专项整体失败；
5. 评测只读取/驱动 Runtime，不新增作者手动记忆 API。

若设计只增加测试、只修 `list_invalidated()` 或只修 Executor 其中一处，均不足以满足需求 14。

### 4.2 Inbox 缺陷闭环

真实现状：

- 唯一公开入口是 `GET/POST/PATCH /api/inbox/issues`，位于 `src/taichu/api/routes/inbox.py:203-251`。
- `create_issue()` 接受调用方给的 ID 或随机 ID，然后直接 append；没有唯一性检查，位于 `src/taichu/application/services/mvp_inbox_service.py:146-165`。
- `patch_issue()` 先 list、内存修改、再整文件 rewrite，位于同文件 `:215-227,308-335`。
- 八字段固定顺序、全角冒号、非空和日期格式校验已存在，位于同文件 `:377-412`。
- `ProjectAssetStorageBackend` 的 append/rewrite 有进程内文件锁和原子替换，但 PATCH 的“读 → 改 → 写”没有跨服务 CAS/lease，位于 `src/taichu/infrastructure/storage/markdown_backend.py:266-310`。
- `MVPInboxIssue` 目前只有 id/title/content/source_chapter_id/priority/status/timestamps，位于 `src/taichu/domain/models/mvp_inbox.py:68-79`，没有结构化评测反向引用字段。

设计必须明确稳定 issue ID 的计算、唯一查询/创建语义、同一闭环协调器租约或等价串行所有权、超时后先查再重试、确定失败/格式拒绝/未持久化阻断、关闭前 PATCH 和写后读回。双向关联不能只写“已关联”：

- 评测 iteration/failure artifact 必须保存 `issue_id`；
- Inbox 侧必须能反向定位 suite/run/iteration/failure evidence。若扩展 `MVPInboxIssue` 顶层结构化字段，必须同步 domain/schema/API/service/storage/前端与旧记录读取默认值；若使用八字段正文中的“相关代码”承载，则设计必须给出稳定、可机械解析且仍符合高层工程正文规则的格式与读回校验；
- 任何单向、不可读回或身份不一致都保持未闭环。

评测缺陷、provider 行为和环境受阻禁止写 Inbox。只有分类为真实系统缺陷且证据充分时调用协调器。

### 4.3 实际模型身份和多模型准入

- 默认模型是 `deepseek-v4-pro`，见 `.env.example:6`、`src/taichu/config.py:24`。
- `RightCodeLLMGateway.probe_model()` 产生 `available/unavailable` 内存状态，位于 `src/taichu/infrastructure/llm/rightcode.py:113-153`。
- 网关可从 RightCode fallback 到 DeepSeek 官方，并在记录成功/失败时保留 `fallback_from_provider`，位于同文件 `:158-235`。
- `LLMCallRecord` 保存逻辑 `model_id`、实际 `provider/upstream_model/fallback_from_provider`、状态、Token、费用和错误，位于 `src/taichu/application/models/llm_usage.py:15-46`。
- `LLMCallReplayRecord` 保存同样的实际执行身份、request/response hash、脱敏 messages、Token 和错误，位于 `src/taichu/application/models/llm_replay.py:36-77`。
- 应用层 `LLMGatewayContract` 只声明 complete/stream/list_models，不声明 probe，位于 `src/taichu/application/contracts/llm.py:208-219`；因此设计不能声称任意 LLM adapter 都已有可持久 probe 接口。

应新增窄的 provider evaluation adapter/Protocol，明确 live 轨道如何：

1. 在运行前探测请求模型并把探测时间、结果和证据身份固化到 comparison run；
2. 从 usage/replay 对账请求模型、实际 provider、实际 upstream model、fallback、Token、费用、错误；
3. probe 失败/不可验证、fallback 污染、身份不符、replay 或必需审计缺失均判 `uncomparable`，与 Agent 能力失败分开；
4. synthetic 与 live 工件、分母、通过率和结论完全分轨；
5. 只有合成套件全绿、DeepSeek 完整真实套件闭环、所有核心硬门禁满足且代码/suite/fixture/cases/逐案预算/能力/授权/解码/环境 identity 相同，才允许多模型排名。

## 5. 计划新增合同与状态约束

以下是需求必需的边界候选；名称可以在正式设计中调整，但必须明确标为“新增”，不得声称当前存在：

| 新增边界候选 | 最小职责/关键字段 |
|---|---|
| `EvaluationSuite/CaseContract` | suite/case 稳定 ID、category/tags、用户请求原文、fixture hash、required/allowed/forbidden、授权、六预算、typed expected artifacts、verifier IDs、script、gate、failure priority、thresholds |
| `CapabilityCatalogSnapshot` | 规范化生产 manifests、catalog hash、逐能力合格覆盖反向表、preflight issues |
| `SealedFixtureManifest/CaseWorkspace` | Markdown/confirmed 知识/对话/记忆身份，案例副本位置，创建/校验/销毁/孤儿恢复状态 |
| `StrictScriptStep/Trace` | 单一全序 step、matcher、response/error、消费状态、位置、剩余步骤、script/runtime-config hash |
| `ExpectedArtifact` 封闭联合 | final answer、source reference、capability artifact、write candidate、HITL；required/forbidden/N/A 和稳定身份 |
| `VerifierRegistry` | 稳定 ID → 接受产物类型 → 只读 verifier；禁止 Shell、任意命令、动态 import 和副作用 |
| `GateResult/BudgetObservation` | 六预算及预算/校验器/产物/停止/权限/证据六类门禁的上限、实际、适用性、证据、状态 |
| `FailureFacts` | `failure_category` + 完整 `failure_categories`，固定全序，未知归因保留原条件 |
| `EvaluationRun/CaseRun` | 独立运行 ID、幂等提交身份、queued/running/终态、进度、取消、中断、恢复、终态保护 |
| `CaseEvidenceBundle/SuiteArtifact` | 稳定关联、availability、最小摘要、bundle hash、复现元数据、完整案例行、不可变引用 |
| `MechanismExperiment/Aggregator` | synthetic/live 分轨、真实开关资格、可比条件、重复样本、绝对门禁、统计解释 |
| `DeepSeekIteration/IssueLink` | 首轮冻结、四类失败/未知、定向+全套+无回归关闭、suite hash、issue 双向链接和协调租约 |
| `ModelComparison` | 固定条件 identity、逐模型实际身份/probe/fallback/replay、可比性、排除原因、排名准入 |

规范化哈希必须采用固定字段、稳定排序和 UTF-8 规范序列化，并写测试证明相同内容稳定、任一实质字段变化改变身份。代码提交/分支/工作树、locale、timezone 等取不到时记录明确 unavailable，不能静默省略。

## 6. 生命周期、并发与恢复约束

1. 套件提交先完整 preflight，再持久化唯一 run ID；preflight 失败不能启动任何案例或形成整体能力结论。
2. 幂等键应由提交内容身份构成并绑定 suite/fixture/track/model/config/authorization/budgets；相同未确认提交返回既有 run，不生成无法区分的重复项。
3. `queued → running` 后逐案例持久化进度。单案例行为失败且运行级隔离仍成立时继续；隔离/事实安全/suite identity 失效时立即停止后续案例并把 run 置 invalid。
4. cancel 只阻止启动新案例；已完成案例和工件保留。进程中断后没有完整结论的运行是 unfinished，不从残留汇总推导 pass。
5. 终态必须通过仓储级 compare-and-set/允许迁移表保护，后台任务不得把 cancelled/invalid/unfinished 反写成 completed。
6. case workspace、artifact 写入和 run 状态不是跨文件事务时，必须采用“先不可变内容、后原子索引/状态引用”以及恢复扫描/补偿规则。
7. DeepSeek iteration 首轮及每轮套件工件不可覆盖；suite hash 改变后必须从完整套件起点重跑，不能直接比较不同 hash。
8. 运行工件保留策略需区分不可变审计证据、可清理 case workspace 和活动旧 `general_eval_*.json`；新目录职责必须同步 `project_assets/readme.md`。

## 7. API 资源和错误契约预期

设计需要给出服务端拥有结论的分层资源，至少覆盖：

- suites：列表、详情、内容身份、能力覆盖和 preflight；
- runs：提交、列表、详情、进度、取消、恢复可用性、幂等冲突；
- cases/bundles：案例结论、六类 gate、失败解释、只读证据包；
- experiments：资格、控制/实验组、重复运行与机制汇总；
- DeepSeek iterations/issue links：冻结、分类、闭环状态、读回失败；
- comparisons：准入条件、逐模型实际身份、不可比原因、允许时的排名。

错误不能只返回自由文本。应有稳定 code + 中文 message + 可定位 details，区分 contract invalid、catalog drift、fixture isolation、security violation、infrastructure blocked、evidence incomplete、provider error/uncomparable、idempotency conflict 和 terminal transition conflict。敏感正文、Prompt、API key、鉴权头和完整 replay 不进入 HTTP 列表/总览。

## 8. 前端真实边界

### 8.1 可复用与必须替换

- 路由薄入口保留：`web/src/app/task-monitor/general-agent/evaluation/page.tsx:1-5`。
- 通用 Agent 监控导航已有 evaluation 项和中文标签，保留关系：`web/src/components/agent-task-monitor/general-agent-monitor-nav.tsx:8-56`。
- 旧 Shell 当前绑定 dataset/case/既有 run、删除结果、五维分数，见 `web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx:54-321`；必须重写内部合同。
- 旧 API prefix/操作只有 datasets/evaluations/delete，见 `web/src/lib/api/general-agent-evaluation.ts:8-48`；旧类型含五维、overall_score 和旧状态，见 `web/src/lib/types/general-agent-evaluation.ts:6-114`；旧显示适配直接输出“分”和按问题文本匹配 run，见 `web/src/lib/general-agent-evaluation-view.ts:11-72`。均不得保留兼容。
- 本地 `Button`、`CompactPagination`、`Checkbox`、lucide 足以复用；`web/components.json` 与 `web/package.json` 显示现有 shadcn/Base UI/Tailwind 能力，无需新增依赖。

### 8.2 页面信息优先级

桌面工作台首屏顺序必须是：

1. 整体能力硬门禁；
2. 工作记忆细粒度失效专项；
3. 各局部机制达标/未达标/无效/不适用；
4. DeepSeek 真实套件迭代和系统问题闭环；
5. 多模型准入条件；未准入时不生成/不展示排名。

分数、均值、差异、Token、费用只进入解释层。案例使用紧凑行、筛选、复选和分页；预期/实际/证据/全部失败类别/工件按需展开。所有状态、provider 和失败类别经单一中文适配层显示，不把英文枚举直接暴露给用户。

### 8.3 DESIGN/UI 门禁

必须遵循根 `DESIGN.md`：

- 仅桌面 1280px+，不新增移动/窄屏逻辑；
- 午夜极光控制台、高密度低干扰；不使用大卡片、营销说明或漂亮指标中心；
- 不用横线、竖线、`divide-*` 或边框边分割内容；独立交互外轮廓可以使用；
- 状态同时使用中文文字，颜色只辅助；
- 低频技术内容进入 details/drawer/二级详情；
- 使用现有 UI 组件和语义 token，不新增平行组件体系，不新增前端依赖；
- 动效克制并尊重 `prefers-reduced-motion`。

前端测试必须覆盖中文枚举、所有终态、provider blocked/error/completed/uncomparable、双失败类别、工作记忆专项、闭环/准入、提交禁用、幂等冲突、取消、错误重试、紧凑空状态、分页筛选和详情展开。真实验收固定为 `http://localhost:3000/task-monitor/general-agent/evaluation` 与 `http://127.0.0.1:8000`。

## 9. 清理、保留与启动联动

### 9.1 必须删除/重写

- `src/taichu/application/evaluations/general_agent/`
- `src/taichu/application/contracts/general_agent_evaluation.py`
- `src/taichu/infrastructure/evaluations/general_agent_repository.py`
- `src/taichu/api/schemas/general_agent_evaluations.py`
- `src/taichu/api/routes/general_agent_evaluations.py`
- `tests/fixtures/evaluations/general_writing_assistant_core/manifest.json`
- `tests/integration/api/test_general_agent_evaluations_api.py`
- 活动 `project_assets/derived/agent_evaluations/general_agent/general_eval_*.json`
- 前端旧 Shell/API/types/view/test 的旧合同内容
- `main.py/deps.py/router.py` 与相关 `__init__.py` 中旧装配/导出
- README、当前 `docs/` 和 `project_assets/readme.md` 的旧五维口径。

当前旧资料命中包括 `project_assets/readme.md:81,144`、`docs/已讨论功能/7-13通用写作助手智能体架构与能力演进决策.md:127,288` 和 `docs/临时架构/7-20通用Agent运行链路上下文与能力调用排查地图.md:1556`。根 `README.md:131` 还使用已被 `AGENTS.md` 禁止的旧五层近义名称，当前资料更新时必须改为“稳定记忆、工作记忆、长期记忆、历史记忆、当前请求”；历史快照不改。

### 9.2 必须保留

- `docs/历史/` 原貌；
- 生产插件发现/注册和 29 capability profiles；
- `src/taichu/config.py:39-41` 共享评测目录/裁判配置；
- Runtime、调用、context、replay、checkpoint、effect、usage 原始证据；
- AgentMemory 四态/依赖模型及不属于旧评测的生产修复；
- Inbox 唯一入口与其他 Inbox 功能；
- 知识抽取/知识召回评测；
- `scripts/benchmark_general_agent_recovery.py` 独立恢复可靠性基准；
- route/card/nav/AppShell 和本地 UI primitives。

全仓防僵尸扫描必须排除 `docs/历史/`，否则会以篡改历史制造“零命中”。旧活动 JSON 的物理删除必须先解析精确绝对目录和 `general_eval_*.json` 文件模式。

### 9.3 启动联动

设计必然修改 `src/taichu/main.py`，可能修改 `src/taichu/config.py`、`.env.example` 或 `web/package.json`。按根规则：

- 若无需新配置/依赖，应明确不修改后两者，减少启动风险；
- 任何上述启动关键文件变化都必须验证根 `start.bat`；
- 后端代码修改后等待热重载并调用 `http://127.0.0.1:8000` 真实新接口；
- 固定端口不能用 3001/8001 规避。

## 10. 测试与机械门禁预期

### 10.1 后端契约/单元

1. 生产目录快照、29 项合格覆盖、漏项/重复/未知/反向映射/目录漂移 preflight。
2. suite/case/fixture/script/runtime-config/bundle/iteration/comparison 规范化 hash 稳定与实质变化。
3. strict driver 的意外、跨类型乱序、内容不符、提前耗尽、剩余步骤、重复结果漂移。
4. 六预算与六类硬门禁真值表；invalid/unfinished/cancelled/blocked/uncomparable 不计通过。
5. 五类 typed artifact、未知 verifier、类型不匹配、Shell/命令/动态执行/副作用注入。
6. 四态、来源指纹、三类依赖、否决、替代、并行候选、node summary/digest/snapshot/reuse 防污染。
7. evidence 链完整/缺失/损坏/冲突/N/A，禁止 mtime，bundle 最小化。
8. suite run 状态迁移、取消竞态、中断恢复、终态保护、幂等重复提交。
9. DeepSeek 首轮冻结、四类失败和未知、suite hash 变化、定向+全套+无回归关闭。
10. Inbox 稳定 ID、单协调器竞争、确定失败、格式拒绝、超时不确定、未持久化、读回失败和双向关联断裂。
11. provider probe/fallback/request-vs-actual/replay/usage/cost/error 缺失或冲突导致不可比且排除排名。
12. 旧标识扫描和相邻评测/Runtime/Inbox/恢复基准回归。

### 10.2 API/前端/启动

- 新 suite/run/case/bundle/experiment/iteration/comparison API 集成测试及稳定错误码；
- `npm run lint`、`npm run test:general-agent`、`npm run build`；
- Python 至少运行相关单元与集成测试，最终运行项目既定 `ruff`/`mypy` 或等价全量门禁；
- `start.bat` 固定端口启动、真实 API 和桌面浏览器验收；
- 检查 active 源码/测试/前端/当前资料中的旧 API、旧五维字段、旧状态和 `general_eval_*.json` 为零，同时显式保留历史命中。

## 11. 需求到设计约束追踪

| 需求 | 独立发现出的必要设计承诺 |
|---|---|
| 1 | 生产目录内容快照、逐能力合格案例反向覆盖、完整 preflight 和稳定 suite/case 合同 |
| 2 | 规范化内容身份、运行时冻结、完整复现元数据和 unavailable 语义 |
| 3 | 案例专属 CapabilityContext/Runtime 全栈重组、Markdown/Mongo/对话/记忆密封副本和活动事实前后不变量 |
| 4 | 单一全序 strict driver、matcher、显式错误类别、finalize 剩余检查和规范化重复身份 |
| 5 | 六预算、六 gate 合取、case/suite/mechanism 三层结论，禁止任何分数覆盖 |
| 6 | 类型化失败事实、主类别固定全序、完整类别全集、未知归因和中文解释 |
| 7 | 只读 EvidenceReader、稳定关联、availability、最小 bundle 和内容 hash |
| 8 | synthetic/live 物理与统计分轨、真实开关资格、可比性、不变量/收益/无回归和机制 aggregator |
| 9 | 独立 suite run 状态机、原子进度、取消、中断、恢复、幂等、终态保护 |
| 10 | 保留 route/nav，重写内部合同；结论优先、高密度、中文、桌面、现有组件、固定端口 |
| 11 | Runtime 审计只读、相邻评测/恢复基准隔离、事实源不写、审计缺失与能力失败分开 |
| 12 | 精确删除旧后端/前端/测试/活动结果/当前资料，保留历史和共享资产，启动联动 |
| 13 | 五类封闭产物联合、注册式 typed verifier、预检类型匹配、禁止 Shell/任意命令/副作用 |
| 14 | 生产 `SUPERSEDED` 修复投影与 reuse ACTIVE 门禁，加全投影/并行候选专项硬门禁 |
| 15 | DeepSeek 首轮冻结与迭代状态、四类失败、Inbox 稳定幂等闭环/双向关联/读回、多模型实际身份可比准入 |

## 12. 风险与未知项

### Critical 风险

1. 复用生产 `ToolRegistry/CapabilityContext` 只更换 run 仓储，会让写能力触及活动 Markdown/Mongo。
2. 把旧 `GeneralAgentEvaluationRecord` 扩展成 suite 根或保留兼容读取，会留下双重口径。
3. 只按请求 model ID 比较而忽略实际 provider/fallback/replay，会产生虚假排名。
4. Inbox 写入失败、格式拒绝、读回失败或双向关联断裂仍允许闭环，会绕过系统问题唯一入口门禁。
5. `reuse_from_node_id` 继续只看 SUCCESS 会让非 ACTIVE 产物复活。

### Major 风险

1. suite 维护平行能力清单或只检查 profile 存在，不能证明 29 项合格案例覆盖。
2. strict driver 不在所有 Runtime 停止路径 finalize，会漏报未消费步骤。
3. evidence reader 跨仓储按时间邻近补配或复制巨型 trace，会破坏追溯/隐私边界。
4. run 状态无 CAS/终态保护，取消或中断可能被后台反写为通过。
5. 前端把分数、费用或排名置于硬门禁之上，或未准入时展示空排名。

### 仍需正式设计明确但不应阻塞的选择

- 密封 Mongo 使用逐 case 数据库还是逐 case 集合，以及崩溃清理/保留证据策略；
- 新评测核心的精确模块/文件名；
- suite/case 首批数量和各 suite 的实际数值阈值（不得由设计静默发明；合同应允许固定数据声明）；
- 只读 evidence 跨多个 JSON/JSONL 仓储的一致读取切面；
- Inbox 反向链接采用结构化字段扩展还是八字段内可机械解析的稳定引用；
- provider probe 的窄 Protocol 和持久证据形状；
- 不可变 artifact、可变 run state 与索引的具体文件布局及保留策略。

这些选择必须在正式设计中给出唯一实现路径、依赖方向、错误/补偿语义和测试，不得继续留作实现者自由发挥。

## 13. 已运行命令与结果

- `Get-FileHash -Algorithm SHA256`：需求、需求报告、需求 discovery 与 `spec.json` 登记值一致。
- `git rev-parse HEAD`：`82bab37a5514f8a6f4d632872010293a910c2bec`。
- `git status --short`：工作树非干净；已记录并保持不改。
- `rg --files`：确认旧评测、Runtime、记忆、Inbox、LLM、前端和 Pico 真实文件范围。
- `rg -n` + `Get-Content -Encoding UTF8`：逐项核验本文件引用的类、Protocol、状态、路由、仓储、测试和 UI 资产。
- Graphify：未运行，符合根项目当前禁用规则。

本 discovery 已形成独立设计约束。下一阶段只有在确认本文件存在、非空并取得 SHA-256 后，才允许计算并核对 `design.md` 目标 SHA-256并读取 `research.md`/`design.md`。
