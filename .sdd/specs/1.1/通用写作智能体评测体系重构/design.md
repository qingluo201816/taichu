# 通用写作智能体评测体系重构技术设计

## 文档信息

- 规格：`1.1/通用写作智能体评测体系重构`
- 设计日期：2026-07-27
- 发现级别：完整
- 采用方案：新评测核心 + 现有共享能力的窄适配
- 上游需求 SHA-256：`b5b65cf351b58c6ff72bfc6f76f1d9c3b10470ebc01875670571957fe14a1cf2`
- 设计性质：破坏式替换；不保留旧五维合同、接口、字段、状态、结果或兼容读取

## 1. 概述

本功能为太初维护者提供固定、隔离、可复现、可解释的通用写作智能体评测。系统从同一份不可变 suite/case 合同创建 scripted synthetic 或 live provider 运行，为每个案例构造独立单本小说夹具和完整生产能力目录，聚合既有 Runtime 的只读证据，以硬门禁直接形成案例、整体能力、工作记忆专项和局部机制结论，再按强顺序执行 DeepSeek V4 Pro 首轮、Inbox 系统问题闭环与多模型比较准入。

新评测拥有 suite、生产能力快照、fixture snapshot、评测运行状态、case result、evidence bundle、suite artifact、mechanism conclusion、首轮 iteration、issue correlation、comparison admission 和机制指标；不拥有小说事实、活动 Runtime、调用审计、上下文快照、模型回放、检查点、副作用、Inbox 主数据或独立恢复 benchmark。现有页面 route、任务卡片、监控导航、应用壳和基础 UI 保留，页面内部合同和视图一次性切换到新资源。

## 2. 目标

1. 固定 suite/case/fixture/track 合同并以规范化内容哈希冻结运行输入。
2. 用每案例独立临时 assets root、独立 Mongo 数据库和独立 Runtime 验证真实已注册能力，保持活动小说事实不变。
3. 用类型化预期产物、静态 verifier、六预算和六硬门禁产生确定性且不可被平均分覆盖的结论。
4. 用精确标识链只读聚合 Runtime 证据，明确可用、缺失、损坏、不适用和冲突。
5. 严格分开 synthetic/live 工件、provider 状态、实验可比性、机制指标和重复性结论。
6. 提供幂等、可取消、可恢复且终态稳定的 suite runner 与资源化 API。
7. 在既有中文桌面入口提供高密度 suite 控制、摘要、case 行、右侧详情、实验和指标工作区。
8. 删除旧五维后端、API、前端合同、测试、活动结果和当前说明，同时保留 Runtime、相邻评测、恢复 benchmark 与历史快照。
9. 由生产发现生成 17 Tool + 12 Subagent 的规范化快照，以 23 个固定 case 的真实完成调用覆盖全部 29 个一等能力。
10. 用全局有序 `StrictScriptedDriver` 覆盖模型、Tool、Subagent、HITL、任务与恢复交互，并以重复运行规范化门禁证明确定性。
11. 修复生产工作记忆复用的 producer-validity 缺口，以四个 memory case 和七项机制门禁证明当前事实与修复事实不混用。
12. synthetic/核心/机制稳定后才运行 DeepSeek V4 Pro 首轮；系统缺陷只经 `/api/inbox/issues` 闭环，闭环完成后才开放多模型比较。

成功标准：

- 1.1—15.40 的 15 组 325 条验收标准全部映射到明确组件、模型、接口、状态或验证；
- 29 个生产能力每项恰有至少一个合格 case 的真实 `completed` invocation 证据；`allowed`、manifest 或注册成功均不计覆盖；
- strict script 任何意外、乱序、不匹配、耗尽、剩余步骤或规范化漂移均以稳定错误失败；
- 工作记忆中只有 `ACTIVE` 可进入当前事实，`STALE/REJECTED/SUPERSEDED` 只进入 repair-only 投影，失效 producer 不可经复用复活；
- DeepSeek 首轮、系统缺陷闭环与多模型比较按 suite hash 强顺序执行，证据不足的模型为不可比较；
- 任一硬门禁失败、invalid、unfinished、cancelled、blocked 或 provider error 均不可显示为通过；
- 评测前后活动 Markdown 和 `taichu.knowledge_cards` confirmed 事实指纹不变；
- 旧 API 前缀、五维字段和 `general_eval_*.json` 在活跃实现中为零；
- synthetic 默认测试链可离线执行；live 未配置时形成可解释 `blocked` 工件而非伪造结果；
- 固定端口真实页面与 API 联调通过。

## 3. 非目标

- 不修改通用 Agent 的动态规划范式、29 个能力 handler、五层名称/API 角色或 Runtime 审计事实；仅对工作记忆 producer-validity 与复用门禁做满足需求 14 的窄生产修复。
- 不新增 Tool、子 Agent、任务专用能力、固定 DAG 或临时假能力。
- 不评判 Runtime 审计链自身质量，也不复制完整 Prompt、上下文、节点状态或调用正文。
- 不合并、替换或用本 suite 结论覆盖独立恢复可靠性 benchmark、知识抽取评测或知识召回评测。
- 不访问或写入作者活动小说来构造 fixture，不支持项目选择、多小说或多租户。
- 不把 write candidate 自动提交为正文或 confirmed 知识。
- 不设计旧结果迁移、reader、mapper、双写或回退。
- 不新增 Python/Node 依赖、数据库、队列、前端状态库、表格库、图表库或移动端布局。
- 不修改 `docs/历史/` 快照。
- 不把目录中存在的模型视为当前可用，不在设计中锁死首批实际比较清单；建议的 DeepSeek/GPT/Claude 三个代表系列必须逐项 probe，缺失阈值由预检判为无效。

## 4. 边界承诺

### 4.1 本规格负责

- 固定 `SuiteSpec`、`CaseSpec`、`TrackSpec`、`FixtureSnapshotSpec` 和规范化内容身份。
- 从生产 Tool/Subagent 发现结果生成 `CapabilityCatalogSnapshot`，预检目录完整性、类型、依赖和内容 hash。
- case 能力 required/allowed/forbidden 投影、授权边界、六预算、五类预期产物、verifier 和允许停止原因。
- 23 个稳定业务 case、29 能力反向映射、`applicable_tracks`、`required_invocations` 和真实调用覆盖 gate。
- 全局有序 `StrictScriptedDriver`、有序 `human_responses`、稳定 synthetic protocol error 与 mandatory `finalize()`。
- sealed fixture 的校验、复制、Mongo seed、workspace 生命周期、边界守卫和事实不变量。
- 评测专用独立 Runtime factory、scripted/live track adapter 和 `EvaluationCaseExecutor`。
- 静态 typed verifier registry、六硬门禁、失败枚举/优先级和确定性判定。
- 共享只读 `RuntimeEvidenceReader` Protocol 及组合既有仓储的基础设施 adapter。
- 评测隔离 `EvaluationCorrelationScope`、observer wrappers 与不可变 correlation ledger，在不改变 Runtime 审计合同的前提下关联既有 trace/replay/usage ID。
- suite runner 状态机、幂等、取消、unfinished 恢复、原子工件和分页查询。
- suite/case/bundle/experiment/provider/comparability/stability typed models。
- `MechanismGateResult/MechanismConclusion`、工作记忆当前/修复投影、producer-validity proof 与复用门禁。
- DeepSeek 首轮 iteration/closure 状态机、Inbox exactly-once 协调与双向关联、`ModelComparisonAdmission`。
- harness/context/memory/security/recovery/provider 六个独立指标模块。
- `/api/general-agent-benchmarks` 新资源 API 及一一对应前端类型/API。
- 既有 route 下的新桌面工作台。
- 旧评测精确清理、当前资料联动、相邻回归和固定端口验收。

### 4.2 边界之外

- Runtime 原始 run、invocation、context snapshot、replay、checkpoint、effect、usage 的字段、写入、保留和修复策略。
- `LLMRequest`、`LLMResponse/StreamEvent`、`InvocationContext/InvocationTraceRecord` 的字段与值，Orchestrator/Subagent/Executor 的审计调用顺序，以及 RightCode/adapter/replay/usage 的 ID 生成和写入语义；需求 11.10 对此优先。
- 作者活动 `project_assets/source/manuscripts/`、活动 `taichu` 数据库和作者正常工作流。
- provider 凭据管理、模型目录治理、价格策略和 fallback 策略。
- 真实互联网内容的新鲜度或 DuckDuckGo 可用性；external research 评测始终使用密封外部资料夹具。
- Inbox 的页面、人工编辑体验或与系统问题无关的通用产品治理；评测只通过既有唯一 API 创建、读回、关联和关闭其系统缺陷。
- 独立恢复 benchmark 的执行器、统计口径和工件。
- 新的小说知识 Schema、知识生命周期或正文格式。
- 旧评测历史结论的重新计算或转换。
- 自动清理或手动删除新评测终态工件；在未确认 retention policy 前只做空间可观测，不启用 TTL 或删除入口。

### 4.3 允许的依赖

- 应用评测层可依赖当前 `application/general_agent` 的只读模型、真实 tools/subagents registries、LLM gateway Protocol 和本规格新增的 application Protocol。
- fixture infrastructure 可依赖 `ProjectAssetStorageBackend`、`MongoKnowledgeRepository` 的公开构造/initialize 行为和当前知识卡校验模型。
- runtime factory 可组合现有 CapabilityContext、ToolRegistry、SubagentRegistry、Orchestrator、Executor、RuntimeService 及文件型仓储，但不得调用活动 `create_app` 或读取 `app.state`。
- runtime factory 先物理注册完整生产 Tool 目录，再注册依赖这些 Tool 的全部生产 Subagent；case exposure/policy 是运行时可见性边界，`required_invocations` 是覆盖期望，三者不可合并。
- 生产记忆窄修复可依赖现有 `AgentMemoryService`、ContextAssembler、Orchestrator 和 Executor；不得改变五层名称、作者权限或运行记忆自动治理边界。
- `evidence_sources.py` 可在组合根读取既有 run/node/invocation/snapshot/replay/checkpoint/effect/usage 仓储的明确只读函数，并立刻绑定为八个窄 facade；`RuntimeEvidenceReader` 只能依赖这些 facade，组合根不得把完整可写 repository 注入 reader。
- 评测专用 Runtime factory 可把隔离实例中的 LLM gateway、InvocationTraceRepository append、LLM replay writer 和 usage writer包装为“原样委托 + 观察”适配器；wrapper 不改变参数、返回、底层记录或调用次序，只向 evaluation-owned correlation repository 写派生观察。
- artifact infrastructure 可依赖 Python 标准库 JSON/hash/UUID/fsync/replace；不得引入 SQLite/FTS。
- API 可依赖评测 application service 和 DTO；评测 application 不反向依赖 FastAPI。
- Web 只通过 HTTP 依赖新 API，可复用 AppShell、GeneralAgentMonitorNav、Button、Checkbox、CompactPagination、lucide 和当前语义 token。
- 首轮 coordinator 只通过本地 `/api/inbox/issues` 使用 Inbox；评测 application 依赖窄 `InboxIssueClient` Protocol，不导入 Inbox 存储实现。
- live model 只从 `src/taichu/infrastructure/llm/catalog.py` 的当前发现快照选择，并以 provider probe 的实际身份决定可用/不可比，不修改模型目录。
- external research 两轨均依赖 fixture-backed `ExternalResearchBackend` 和真实 `ExternalResearchService/Tool` 链；禁止评测 Runtime 注入 `DuckDuckGoExternalResearchBackend`。
- 共享 `evaluation_datasets_dir` 只作为 suite/fixture 静态根；不得复用旧 repository 或旧结果目录。

明确禁止的依赖：

- `application` 导入 `infrastructure`、FastAPI、Next.js、Mongo client 或文件路径实现；
- `domain` 导入评测、Runtime、LLM、LangGraph 或存储；
- verifier 导入 `subprocess`、Shell、任意模块路径加载器或可写 Runtime/fixture repository；
- `RuntimeEvidenceReader`、`EvidenceBundleBuilder` 或 verifier 接收完整 run/context/replay/checkpoint/effect/usage repository，即使该对象同时满足结构化只读 Protocol；
- case 合同提供 Python class path、module path、Shell 字符串或系统命令；
- synthetic adapter 导入 `tests/` 私有 gateway/fake；
- evidence 关联依赖 mtime、目录最新项或时间邻近。

### 4.4 重新验证触发器

以下变化使相关 suite 内容身份或已有校验结论失效，必须重新运行预检和受影响评测：

- suite/case/script/fixture manifest/预期产物/verifier config/预算/阈值/失败优先级变化；
- capability manifest、required capabilities、exposures、授权语义或 registry 内容身份变化；
- 17 Tool/12 Subagent 的 ID、类型、manifest、allowed-tools 依赖、handler identity 或生产目录 canonical hash 变化；
- Runtime run/node/invocation/context/replay/checkpoint/effect/usage 契约变化；
- 既有 trace/gateway/replay/usage 字段、ID 生成或写入次序变化；此时只重新验证 evaluation observer matcher，禁止借机修改 Runtime 审计合同；
- ExternalResearchBackend/Service/Tool 契约、fixture external-source manifest 或 source ref 规则变化；
- evidence availability、bundle canonicalization 或 checkpoint hash 规则变化；
- gate 真值、failure enum/priority、metric numerator/denominator 或 comparability 规则变化；
- provider/model identity、解码字段、费用可用性或 gateway 错误分类变化；
- 工作记忆 validity/edge/投影、producer ref、source fingerprint、复用/修订行为变化；
- Inbox 八行格式、GET/POST/PATCH 合同、issue ID/typed link/revision/CAS/租约语义变化；
- DeepSeek V4 Pro 实际 gateway 映射、provider fallback 或 `src/taichu/infrastructure/llm/catalog.py` 变化；
- artifact layout、原子写、租约、幂等或恢复状态机变化；
- API 字段、枚举、可空性、分页、错误 envelope 或前端中文映射变化；
- Mongo validator/index、Markdown 目录规则或活动事实指纹算法变化；
- 修改 `main.py`、`config.py`、`pyproject.toml`、`.env.example`、`web/package.json` 或 `next.config.ts`；
- retention policy 从“未启用”变为自动删除。

## 5. 架构

### 5.1 选定模式

采用“应用评测核心 + 端口/适配器 + 文件派生工件”的边界：

```mermaid
graph TB
    WebUi --> BenchmarkApi
    BenchmarkApi --> BenchmarkService
    BenchmarkService --> SuiteCatalog
    BenchmarkService --> SuiteRunner
    BenchmarkService --> ExperimentCoordinator
    BenchmarkService --> FirstLiveCoordinator
    BenchmarkService --> ComparisonAdmission
    SuiteRunner --> CaseExecutor
    CaseExecutor --> FixtureManager
    CaseExecutor --> RuntimeFactory
    RuntimeFactory --> ProductionCapabilitySnapshot
    RuntimeFactory --> FixtureExternalResearchBackend
    RuntimeFactory --> EvaluationCorrelationScope
    CaseExecutor --> StrictScriptedDriver
    EvaluationCorrelationScope --> IsolatedRuntime
    IsolatedRuntime --> ProducerValidityGate
    IsolatedRuntime --> ObservedEvaluationPorts
    ObservedEvaluationPorts --> RuntimeAuditStores
    ObservedEvaluationPorts --> CorrelationRepository
    CaseExecutor --> EvidenceReader
    EvidenceReader --> RuntimeAuditStores
    CaseExecutor --> VerifierRegistry
    CaseExecutor --> GateEvaluator
    SuiteRunner --> ArtifactRepository
    ExperimentCoordinator --> MetricRegistry
    ExperimentCoordinator --> ArtifactRepository
    FirstLiveCoordinator --> InboxIssueClient
    InboxIssueClient --> ExistingInboxApi
    FirstLiveCoordinator --> ArtifactRepository
    ComparisonAdmission --> ModelCatalogProbe
    ModelCatalogProbe --> CurrentLlmCatalog
```

关键决策：

- `RuntimeAuditStores` 始终拥有原始证据；`EvidenceReader` 只输出规范化最小投影。
- synthetic/live 都经过 `RuntimeFactory → IsolatedRuntime`，因此能力路径和 evidence shape 相同；track provenance 和 repository 查询永远分开。
- suite runner 不介入 Runtime DAG 生成，只传入原始 case 请求、能力/授权投影和资源上限。
- `ProductionCapabilitySnapshot` 是生产发现的只读投影；Runtime 物理注册完整依赖图，case exposure 与 expected invocation 分别约束可见性和覆盖。
- synthetic 的唯一替换点是模型响应；`StrictScriptedDriver` 观察真实 Tool/Subagent/HITL/task 事件并在停止后 finalize。
- `ObservedEvaluationPorts` 仅存在于评测隔离组合根：底层 gateway/trace/replay/usage port 的返回、异常与写入必须先原样完成，wrapper 才向 case-local scope 报告各源既有 locator。observer/scope/repository 故障只能把评测 correlation 标为 invalid，绝不替换底层返回或异常、重试底层写入或改变写入次数；正常活动 Runtime 与共享仓储完全不经过 wrapper。
- live provider 要求既有 trace/replay/usage source locator；synthetic 没有 RightCode replay/usage，改由 strict-driver step、既有 trace 与 evaluation-owned fixed token/cost observation形成轨道专属 record，Runtime replay/usage 明确不适用。
- `ProducerValidityGate` 是生产工作记忆复用和所有当前事实投影共用的窄应用契约。
- artifact repository 只拥有评测运行状态与派生工件；workspace 是可清理临时资源，不是事实。
- `FirstLiveCoordinator` 只能经既有 Inbox API 处理系统缺陷；`ComparisonAdmission` 只有在当前 suite hash 闭环完成后开放。

### 5.2 依赖方向

允许导入关系：

```text
benchmark models
    ← application contracts
    ← benchmark services

benchmark models + application contracts
    ← infrastructure adapters

benchmark models + benchmark services
    ← API schemas/routes
    ← Web HTTP types/API/components

composition root main.py
    → application services + infrastructure adapters
```

同层规则：

- `metrics/*` 只依赖 metric input model，不互相导入；
- `verifiers/*` 只依赖 expected/observed artifact、evidence 和 verifier result model；
- `gates.py` 读取 verifier/evidence/budget/stop/security 结果，不调用 verifier；
- `failures.py` 只分类既有 gate facts，不重新判断业务事实；
- `runner.py` 不读取底层仓储文件或 Mongo；
- `issue_closure.py` 只依赖 `InboxIssueClient`，不读取/写入 `inbox_issues.jsonl`；
- `correlation_scope/observers` 只能依赖既有端口的公开调用形状与 evaluation correlation repository；不得导入或改写 Runtime/LLM 模型、记录 Schema 或正常组合根；各源 hash/status 只按各自原生算法复读，不建立跨源 hash 相等约束；
- `comparisons.py` 只依赖当前模型目录的只读 probe，不改变 `catalog.py` 或 gateway fallback；
- `routes` 不绕过 service 直接访问 repository；
- UI component 不自行计算 suite hash、gate、pass rate 或 comparability。

### 5.3 技术栈

| 层级 | 选择/版本 | 角色 | 新依赖 |
|---|---|---|---|
| 后端 | Python >=3.12、Pydantic、FastAPI | 冻结模型、Protocol、service、HTTP | 无 |
| Runtime | 当前 LangGraph >=1.0 与 GeneralAgentRuntime | 每 case 独立真实执行 | 无 |
| 结构夹具 | MongoDB、现有 PyMongo 与 validator | 每 case confirmed knowledge 临时数据库 | 无 |
| 文本/运行夹具 | Markdown + JSON 中间态 | 密封源、临时 assets root、运行/审计工件 | 无 |
| 前端 | Next 16.2.9、React 19.2.4、TypeScript 5、Tailwind、现有 shadcn/Base UI | 中文桌面工作台 | 无 |
| 统计 | Python 标准库 | 均值、样本方差、min/max/range | 无 |

### 5.4 Runtime 调用时序

```mermaid
sequenceDiagram
    participant Runner
    participant Fixture
    participant Factory
    participant Driver
    participant Runtime
    participant Corr as 评测观察包装器
    participant Audit as 既有审计端口
    participant Reader
    participant Verifier
    participant Store
    Runner->>Fixture: 创建案例工作区
    Fixture-->>Runner: 返回夹具身份与句柄
    Runner->>Factory: 按轨道构造独立运行时
    Factory-->>Runner: 返回运行时句柄
    Runner->>Driver: 绑定全局有序交互流
    Runner->>Corr: 打开case correlation scope
    Runner->>Runtime: 提交原始案例请求
    Runtime->>Driver: 逐步观察 model/tool/subagent/human/task
    Driver-->>Runtime: 仅 model step 返回确定性响应
    Runtime->>Corr: 调用既有gateway/trace/replay/usage端口
    Corr->>Audit: 原参数原顺序委托一次
    Audit-->>Corr: 原结果/原错误
    Corr-->>Runtime: 先原样返回或抛出
    Corr-->>Corr: 隔离观察各源locator；观察异常仅记invalid
    Runtime-->>Runner: 返回终态或人工介入
    Runner->>Driver: finalize 并生成消费证据
    Runner->>Corr: finally固化全部exchange与pending/cancel问题
    Corr->>Store: create-if-absent不可变correlation record
    Runner->>Reader: 读取精确关联证据
    Reader-->>Runner: 返回证据包
    Runner->>Verifier: 校验产物与运行边界
    Verifier-->>Runner: 返回类型化结果
    Runner->>Store: 原子保存案例行与证据包
    Runner->>Fixture: 核验边界并清理
```

人工介入 case 只按序消费合同中独立声明且进入内容哈希的 `HumanResponseScript`。它通过 Runtime 原生人工介入恢复入口回答，不拼接进 `user_request`；实际 request kind、node/tool/scopes 或顺序与脚本预期不一致时由 strict driver 产生稳定错误。`EvaluationCaseExecutor` 在 Runtime 调用外层持有 case correlation scope；无论 Runtime 成功、失败、取消、人工拒绝或异常停止，executor 都在 finally 路径调用 driver 与 correlation finalize，把尚未取得 trace、跨 task 或未收束的 pending exchange 固化为 invalid。即使 correlation repository 持久化失败，底层 Runtime outcome 仍原样保留，case 另以 `correlation_unavailable` 进入 evidence invalid。

## 6. 文件结构规划

### 6.1 新增文件

```text
src/taichu/application/
├── contracts/
│   ├── general_agent_benchmark.py
│   ├── runtime_evidence.py
│   ├── evaluation_correlation.py
│   └── issue_correlation.py
└── evaluations/
    └── general_agent_benchmark/
        ├── __init__.py
        ├── models.py
        ├── run_models.py
        ├── canonical.py
        ├── capability_catalog.py
        ├── suite_loader.py
        ├── strict_driver.py
        ├── correlation.py
        ├── evidence.py
        ├── gates.py
        ├── mechanisms.py
        ├── memory_scenarios.py
        ├── failures.py
        ├── execution.py
        ├── services.py
        ├── runner.py
        ├── first_live_iteration.py
        ├── issue_closure.py
        ├── issue_correlations.py
        ├── comparisons.py
        ├── experiments.py
        ├── verifiers/
        │   ├── __init__.py
        │   ├── registry.py
        │   ├── artifacts.py
        │   ├── runtime.py
        │   └── security.py
        └── metrics/
            ├── __init__.py
            ├── base.py
            ├── harness.py
            ├── context.py
            ├── memory.py
            ├── security.py
            ├── recovery.py
            ├── provider.py
            └── stability.py

src/taichu/infrastructure/evaluations/
└── general_agent_benchmark/
    ├── __init__.py
    ├── suite_repository.py
    ├── artifact_repository.py
    ├── fixture_manager.py
    ├── runtime_factory.py
    ├── strict_driver_adapters.py
    ├── correlation_scope.py
    ├── correlation_observers.py
    ├── correlation_repository.py
    ├── issue_correlation_repository.py
    ├── fixture_external_research.py
    ├── inbox_issue_client.py
    ├── evidence_sources.py
    └── evidence_reader.py

src/taichu/api/
├── schemas/general_agent_benchmarks.py
└── routes/general_agent_benchmarks.py

tests/fixtures/evaluations/general_writing_agent_benchmark/
├── suite.schema.json
├── suite.json
└── fixtures/core_novel/
    ├── fixture.json
    ├── manuscripts/chapters/*.md
    ├── knowledge/confirmed_cards.json
    ├── external_sources/manifest.json
    ├── external_sources/documents/*.json
    ├── conversation.json
    └── runtime_memories.json

tests/unit/application/evaluations/general_agent_benchmark/
├── test_models.py
├── test_capability_coverage.py
├── test_suite_loader.py
├── test_strict_driver.py
├── test_evaluation_correlation.py
├── test_verifiers.py
├── test_gates_and_failures.py
├── test_memory_scenarios.py
├── test_first_live_iteration.py
├── test_issue_closure.py
├── test_issue_correlations.py
├── test_comparison_admission.py
├── test_evidence.py
├── test_runner_lifecycle.py
├── test_experiments_and_metrics.py
└── test_canonical_hashes.py

tests/unit/application/services/test_mvp_inbox_service.py

tests/integration/infrastructure/evaluations/
├── test_general_agent_benchmark_fixture.py
├── test_general_agent_benchmark_runtime.py
├── test_general_agent_benchmark_memory.py
├── test_general_agent_benchmark_inbox.py
├── test_general_agent_benchmark_correlation_observers.py
├── test_general_agent_benchmark_issue_reconciliation.py
├── test_general_agent_benchmark_external_research.py
├── test_general_agent_benchmark_evidence_sources.py
├── test_general_agent_benchmark_evidence.py
└── test_general_agent_benchmark_repository.py

tests/integration/api/test_general_agent_benchmarks_api.py

web/src/components/agent-task-monitor/general-agent-benchmark/
├── suite-controls.tsx
├── suite-summary.tsx
├── run-experiment-rail.tsx
├── case-table.tsx
├── case-detail.tsx
├── memory-conclusion.tsx
├── first-live-closure.tsx
├── model-comparison.tsx
├── experiment-panel.tsx
├── mechanism-metrics.tsx
└── use-benchmark-workbench.ts
```

文件职责：

- `models.py`：suite/case/track/fixture/budget/expected artifact/verifier/gate/failure 的冻结合同。
- `run_models.py`：availability/evidence bundle/case row/suite run/artifact/provider/experiment/comparability/stability。
- `canonical.py`：唯一规范化 JSON 与 SHA-256；禁止各仓储自行实现 hash。
- `capability_catalog.py`：把生产 Tool/Subagent 发现结果投影为规范化快照，校验 29 项反向覆盖、Subagent→Tool 注册依赖和目录漂移。
- `suite_loader.py`：读取固定 JSON、一次性收集全部 schema/registry/capability/threshold 错误并冻结 resolved snapshot。
- `strict_driver.py`：实现跨 model/tool/subagent/human/task 的全局有序消费、稳定错误、证据和 `finalize()`；不实现真实 capability handler。
- `correlation.py`：定义 exchange observation、不可变 correlation record、cardinality/conflict 判定和 evidence availability；不复刻 Runtime 记录模型。
- `evidence.py`：从 shared reader 构建规范化 bundle，不直接访问基础设施。
- `gates.py`：case/suite 六门禁交集和真值。
- `mechanisms.py`：局部机制硬门禁、`decision_source`、真实开关解析与 qualified ablation 准入。
- `memory_scenarios.py`：四个工作记忆 case 的状态/边/投影/复用断言与七项机制结论。
- `failures.py`：完整失败集合、主类别全序和中文说明 key。
- `execution.py`：`EvaluationCaseExecutor` 与 track adapter 协作。
- `services.py`：`BenchmarkCatalogService`、`BenchmarkSubmissionService`、`BenchmarkQueryService`、`BenchmarkLifecycleService` 的应用编排。
- `runner.py`：suite lifecycle、idempotency、lease、cancel/resume、单 case 继续和运行级停止。
- `first_live_iteration.py`：synthetic→DeepSeek 首轮→分类→关闭的强顺序状态机与不可变首轮工件。
- `issue_closure.py`：稳定缺陷指纹、协调者租约、确定性 pending intent、Inbox 幂等写入/读回/关闭、relation/iteration 两级 CAS 和 reconciler 编排。
- `issue_correlations.py`：冻结 subject、稳定 relation/intent/revision identity、不可变 relation revision、append-only observation、最新对称性和 comparison admission 判定。
- `comparisons.py`：冻结条件、provider probe、实际模型身份和 `ModelComparisonAdmission`。
- `experiments.py`：arm、comparability、重复执行和绝对/相对结论。
- `verifiers/*`：静态 registry 及 artifact/runtime/security 纯校验器。
- `metrics/*`：六类机制分别聚合；`stability.py` 只做跨重复统计。
- `contracts/general_agent_benchmark.py`：suite/artifact/fixture/runtime factory 的 application Protocol。
- `contracts/runtime_evidence.py`：分别声明 run、node、invocation、context snapshot、replay、checkpoint、effect、usage 八个窄只读 source Protocol，以及聚合后的 `RuntimeEvidenceReader` Protocol；不含评测判定语义。
- `contracts/evaluation_correlation.py`：声明评测 correlation scope/record repository 的应用端口；只使用 evaluation-owned DTO。
- `contracts/issue_correlation.py`：声明 deterministic intent/revision create-if-absent、append-only observation、relation/iteration CAS manifest、按 subject/relation 查询与 reconciler 端口。
- `evidence_sources.py`：把既有仓储的读取函数绑定为八个无写方法 facade；facade 对外不保留或暴露完整 repository。
- `correlation_scope.py`：以 `ContextVar` 保存 case owner、exchange ID 和轨道专属预期观察集合；CaseExecutor finally 强制收束所有 pending exchange。
- `correlation_observers.py`：包装评测隔离 LLM gateway、trace append、replay/usage writer；底层结果/异常/写入先原样完成且只执行一次，观察故障被隔离为评测问题；strict-driver adapter 生成 synthetic fixed token/cost observation。
- `correlation_repository.py`：原子保存 exchange 的不可变 correlation record；Runtime 仓储不保存该记录。
- `issue_correlation_repository.py`：按确定性路径 create-if-absent 保存 intent/revision，追加 observation，CAS relation/iteration manifest，并识别可重放 orphan。
- `fixture_external_research.py`：实现确定性、只读、禁止网络的 `ExternalResearchBackend`；按 fixture manifest 搜索/读取并返回稳定 source refs，供真实 `ExternalResearchService` 和两个生产 Tool 使用。
- 其余 infrastructure 文件分别实现 suite 文件读取、原子工件、`FixtureIsolationController`、`GeneralAgentBenchmarkRuntimeFactory`、strict-driver 对真实交互点的观察 adapter、Inbox HTTP client 和只依赖上述 source facades 的 `RuntimeEvidenceReader` adapter。
- 前端新目录内文件与逻辑组件一一对应：`suite-controls.tsx` 承载命令条与实验内联确认，`suite-summary.tsx` 承载摘要，`run-experiment-rail.tsx` 承载运行/实验列表、页码分页与取消内联确认，`case-table.tsx`/`case-detail.tsx` 承载案例表和 aside/details 详情，其余 memory/first-live/model-comparison/experiment/mechanism 文件各承载同名结论区；`use-benchmark-workbench.ts` 只编排远端状态和 request coordinator。现有 `GeneralAgentEvaluationShell` 负责组合，导出名不变。

### 6.2 修改文件

| 文件 | 变更 | 边界 |
|---|---|---|
| `src/taichu/main.py` | 把既有仓储只读函数绑定为 evidence source facades，再装配新 repository/factory/reader/service；启动 runner 恢复扫描，shutdown 释放后台任务 | 不把完整可写仓储注入 reader；不改活动 Runtime 构造语义；修改后必须验证 `start.bat` |
| `src/taichu/api/deps.py` | 提供新 benchmark service | 删除旧 service provider |
| `src/taichu/api/router.py` | 挂载新 route | 旧 route 不再导入 |
| `src/taichu/application/evaluations/__init__.py` | 导出新公开类型 | 不导出旧五维类型 |
| `src/taichu/infrastructure/evaluations/__init__.py` | 导出新 adapters | 保留相邻 evaluation 导出 |
| `src/taichu/application/agent_memory/models.py` | 新增精确 producer validity proof 与复用 provenance 类型 | 不改四态和三类关系枚举 |
| `src/taichu/application/contracts/agent_memory.py` | 增加 `require_active_producer` 与 current/repair projection 的 Protocol | 仍由应用层定义行为契约 |
| `src/taichu/application/services/agent_memory_service.py` | 提供 `require_active_producer`、统一 current/repair 投影并让 repair 投影包含 `SUPERSEDED` | `REPAIR_SOURCE` 仍不传播失效 |
| `src/taichu/application/general_agent/models.py` | NodeRun 增加 `reused_from_producer_ref` 与 proof hash | 机器用于复用正确性，不是开发版本字段 |
| `src/taichu/application/general_agent/context.py` | 节点摘要、digest、snapshot 共用 `CurrentFactProjectionPolicy` | 当前事实只含 `ACTIVE` |
| `src/taichu/application/general_agent/orchestrator.py` | 规划阶段复用候选要求 producer proof 与 source fingerprint | 只做需求 14 的复用门禁，不改 LLM/审计调用 |
| `src/taichu/application/general_agent/executor.py` | 执行阶段再次校验 proof，保留复用 provenance | 只做需求 14 的复用门禁，不改 InvocationContext/审计字段或值 |
| `src/taichu/application/general_agent/service.py` | 只在复用 proof 通过后写当前 projection | 防止失效 producer 被记录成新 `ACTIVE` |
| `src/taichu/domain/models/mvp_inbox.py` | 为系统问题增加通用 typed correlation links 与 revision | 严格八行 `content` 不变 |
| `src/taichu/application/services/mvp_inbox_service.py` | GET-by-ID、ID 唯一、legacy `revision=0/links=[]` 投影、原子 CAS mutation、写后读回 | 保留唯一 Inbox 业务入口；读取不触发迁移 |
| `src/taichu/api/routes/inbox.py` | 新增 `GET /api/inbox/issues/{item_id}` 并暴露 revision/links | 不新建评测专用问题路由 |
| `src/taichu/api/schemas/mvp.py` | issue create/patch/read 改为强类型 revision/typed links/expected_revision 合同 | 拒绝未知字段，不再用自由 dict 静默忽略 |
| `src/taichu/application/contracts/storage.py` | 增加窄 workspace record CAS 行为契约 | 锁内读取、校验 revision、原子 replace；不把评测判定放入通用存储 |
| `src/taichu/infrastructure/storage/markdown_backend.py` | 为 issue read-modify-write 提供同一进程锁、持久化跨进程租约、revision CAS 与原子 replace | 首次 legacy CAS 写入新 shape；不改变其他 Markdown 事实职责 |
| `web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx` | 保持 `GeneralAgentEvaluationShell` 导出，破坏式重写内部为新工作台组合根 | route/nav 不变，不新增平行 Shell |
| `web/src/lib/api/general-agent-evaluation.ts` | 改为新资源 API 函数 | 不保留旧 prefix/function |
| `web/src/lib/types/general-agent-evaluation.ts` | 改为新精确 TS unions | 删除旧 score/dimension/status |
| `web/src/lib/general-agent-evaluation-view.ts` | 新中文枚举、派生读数、纯 reducer、API envelope parser 与 monotonic request coordinator | 不重算后端 gate，不依赖 DOM |
| `web/src/lib/api-client.ts` | 增加保留 code/details/status/requestId 的 `ApiError` | 现有仅取 message 的调用继续可用 |
| `web/src/lib/types/mvp.ts` | `MVPInboxIssue` 增加 revision 与强类型 links | legacy 值由后端正规化，前端不猜 |
| `web/src/lib/api/mvp.ts` | issue PATCH 必须显式接收并发送 expected revision | 其他 Inbox tab 合同不变 |
| `web/src/components/inbox/inbox-board.tsx` | issue 状态操作携带当前 revision；409 刷新并显示中文冲突提示 | 不允许页面编辑机器 links |
| `web/src/components/agent-task-monitor/task-monitor-overview.tsx` | 更新评测任务卡说明为固定套件、工作记忆与首轮闭环 | 名称和 route 不变 |
| `web/tests/general-agent/evaluation-view.test.ts` | 重写纯 reducer/API 错误解析/request coordinator/中文派生测试，并加入 Inbox revision/link/legacy 0/CAS 409 纯数据断言 | `test:general-agent` 实际执行；无 DOM 断言，不保留旧五维 |
| `tests/unit/domain/test_mvp_contracts.py` | issue revision/typed link/legacy default 模型回归 | 其他 Inbox 类型不加 revision |
| `tests/integration/api/test_mvp_first_api.py` | 现有 Inbox API 用例升级为 GET-by-ID/expected revision/typed links/409/readback | 继续验证严格八行 |
| `tests/unit/infrastructure/storage/test_markdown_backend.py` | workspace record CAS 锁内原子性、revision 0 升级与并发测试 | 不访问活动 JSONL |
| `tests/unit/application/general_agent/test_runtime.py` | 复用 anti-resurrection 和恢复回归 | 不改现有 LLM/审计身份断言 |
| `tests/unit/application/general_agent/test_memory_context.py` | 四态/三边/current-vs-repair 投影矩阵 | 覆盖正常与 fallback digest |
| `README.md` | 当前入口说明改为固定 suite/硬门禁/实验 | 不改历史结论 |
| `project_assets/readme.md` | 新工件/workspace 职责，移除旧活动结果职责 | 与目录变更同批 |
| `docs/已讨论功能/7-13通用写作助手智能体架构与能力演进决策.md` | 当前评测口径与边界改为新体系 | 保持文档日期/状态规则 |
| `docs/临时架构/7-20通用Agent运行链路上下文与能力调用排查地图.md` | 只读 evidence reader 和新入口说明 | 明确 Runtime 证据仍由原链路拥有 |
| `docs/临时架构/7-13通用智能体运行时编排技术设计.md` | 删除旧评测现行说明或标明被新体系替代 | 不把评测并入 Runtime 所有权 |

需求 11.10 的明确“不修改”清单为：`src/taichu/application/contracts/llm.py`、`src/taichu/application/invocations/models.py`、`src/taichu/application/subagents/runner.py`、`src/taichu/infrastructure/llm/rightcode.py`、`src/taichu/infrastructure/llm/adapter.py`，以及这些对象现有的 ID/字段/写入流程测试。`orchestrator.py` 与 `executor.py` 只实施需求 14 的 producer reuse 门禁，不得顺带改变任何 LLM/审计逻辑。

`src/taichu/infrastructure/llm/catalog.py` 仅作为当前模型目录事实源和 probe 输入，本规格不修改它。也不修改 `pyproject.toml`、`.env.example`、`src/taichu/config.py`、`web/package.json`、`web/next.config.ts` 或 `start.bat`；本轮沿用现有纯 Node 测试脚本，不新增测试依赖或 package script。若实现需要修改其中任一文件，必须先重新验证依赖/配置边界并执行完整启动脚本门禁。

前端 API 所有权只有两层：`web/src/lib/api/general-agent-evaluation.ts` 定义本资源请求，统一调用共享 `web/src/lib/api-client.ts` 完成 HTTP 和错误 envelope；不新增其他平行 client。

### 6.3 删除文件与数据

| 删除对象 | 说明 |
|---|---|
| `src/taichu/application/evaluations/general_agent/` | 旧模型、服务和包导出全部删除 |
| `src/taichu/application/contracts/general_agent_evaluation.py` | 旧 Protocol 删除 |
| `src/taichu/infrastructure/evaluations/general_agent_repository.py` | 旧 dataset/result store 删除 |
| `src/taichu/api/schemas/general_agent_evaluations.py` | 旧 DTO 删除 |
| `src/taichu/api/routes/general_agent_evaluations.py` | 旧 API prefix 删除 |
| `tests/fixtures/evaluations/general_writing_assistant_core/manifest.json` | 旧权重/关键词 fixture 删除；空目录不保留 |
| `tests/integration/api/test_general_agent_evaluations_api.py` | 旧 API 测试删除 |
| `project_assets/derived/agent_evaluations/general_agent/general_eval_*.json` | 仅在解析绝对父目录与模式后物理删除 |

旧活动结果删除不提供 migration/backup/reader；历史实现报告仍保存在 `docs/历史/`。删除前脚本或实现任务必须 dry-run 列出精确绝对路径，验证每个目标都位于 `project_assets/derived/agent_evaluations/general_agent/` 且文件名匹配 `general_eval_*.json`，不得递归删除父目录中的相邻评测。

### 6.4 明确保留的共享资产

- `src/taichu/application/general_agent/` 全部 Runtime 行为与模型；
- tools/subagents capability registry 和 plugin discovery；
- 生产 `DuckDuckGoExternalResearchBackend` 与正常应用装配；评测仅在独立 factory 替换其 backend port；
- run/invocation/context/replay/checkpoint/effect/usage 原始仓储与活动派生目录；
- `src/taichu/config.py:39-41` 的共享评测根与 judge 配置；
- knowledge extraction、retrieval evaluation 代码/fixtures/results；
- `scripts/benchmark_general_agent_recovery.py` 与恢复 benchmark 结果；
- `web/src/app/task-monitor/general-agent/evaluation/page.tsx` route；
- 任务入口卡片、`GeneralAgentMonitorNav`、`AppShell`、Button、Checkbox、CompactPagination、lucide；
- `docs/历史/7-14通用写作助手效果评测实现报告.md` 等全部历史快照。

## 7. 核心数据模型与不变量

### 7.1 共同规则

所有 application 合同使用 Pydantic 冻结模型：

```text
ConfigDict frozen true extra forbid
```

不变量：

- API/文件输入的未知字段一律拒绝，不静默删除。
- Python 时间统一为 UTC ISO 8601；哈希统一为 64 位小写 SHA-256。
- ID 只使用服务端生成或静态 suite 声明的稳定值；不得由显示名称、mtime 或目录顺序推断。
- `user_request` 保存 suite 中的原始 Unicode 字符串，不 trim、不摘要、不拼接 harness 说明。
- harness 规则、授权投影、fixture 引用和 HumanResponseScript 分别进入工作记忆/运行配置，不伪装为 user message。
- 排序无业务含义的集合在 canonical payload 中按稳定 key 排序；有顺序语义的 scripted steps、failure priority、case order 保留声明顺序。
- 计算 `content_hash` 时排除 `content_hash` 本身、捕获时间和运行 ID；其他影响结果的字段全部纳入。
- 所有 secret、API key、连接串凭据值都禁止进入模型；provider 只保存公开 identity 与 availability。

复现元数据使用独立的 `ValueAvailability = available | missing | not_applicable | not_supported | redacted | error`；它与 7.9 的运行证据完整性枚举分离，不能用“不支持”冒充“证据损坏”。

`CapabilityCatalogSnapshot` 由生产发现一次生成并冻结：

| 字段 | 类型 | 不变量 |
|---|---|---|
| `tools` | ordered list `CapabilityDescriptor` | 17 项；`type=tool`；ID 唯一 |
| `subagents` | ordered list `CapabilityDescriptor` | 12 项；`type=subagent`；ID 唯一 |
| `registration_dependencies` | list `SubagentToolDependency` | 每个 Subagent manifest 的 allowed Tool 必须已在 tools 中 |
| `canonical_hash` | SHA-256 | ID/type/manifest/handler identity/dependencies 的规范化 hash |
| `discovered_at` | UTC metadata | 不参与内容 hash |

suite 内只引用 `canonical_hash` 和 29 项 `CapabilityCoverageEntry`；loader 把当前发现快照与 suite 期望逐项比较。物理注册依赖、case exposure 和 expected invocation 是三个独立维度，任何实现都不得互相替代。

`EvaluationCorrelationScope` 只存在于评测隔离 Runtime 的组合根。`EvaluationCaseExecutor` 在整个 Runtime 调用外层打开 case scope；LLM gateway wrapper 在调用底层前创建 `exchange_<32hex>`，把 exchange、track 与当前 `asyncio` task identity 放入 `ContextVar`。被包装端口总是先且仅先调用一次底层：正常返回后再安全报告 observation；底层抛错时保存原异常对象，安全报告后重新抛出同一异常。报告或 repository 异常被 case scope 捕获，不能改变底层返回、异常类型、重试或写入次数。

live gateway 返回或抛错后 exchange 保持 task-local pending，直到同一 task 的 trace append wrapper 已原样完成底层 append 并报告其独立 trace call ID；synthetic 则等待 strict-driver step、既有 trace 与 fixed token/cost observation。新 gateway 调用不得在同一 task 上越过未收束 exchange。CaseExecutor 的 `finally` 调用 `finalize_all()` 并清理 ContextVar：取消、缺 trace、跨 task 或其他残留 pending exchange 都固化为 immutable invalid record；若 correlation repository 本身不可写，则 attempt artifact 保存 `CorrelationCommitReceipt(availability=invalid, problems=[correlation_repository_unavailable])`，Runtime 原 outcome 仍保留。

`EvaluationCorrelationRecord` 是 evaluation-owned 不可变对象：

| 字段 | 语义 |
|---|---|
| `track/exchange_id/case_execution_id/owner_task_key` | 评测关联身份；task key 只用于同进程所有权校验，不作为 Runtime ID |
| `evaluation_request_sha256/run_id/gateway_outcome` | 评测 wrapper 自己的请求身份与 `returned|raised`；不与任一源原生 hash 比较 |
| `driver_step_observation` | synthetic 恰一项 strict-driver step locator/hash/status；live 为 `not_applicable` |
| `trace_observation` | 恰一项既有 trace call ID、source-native input hash、run ID、status、error type 与 locator |
| `replay_observation` | live 恰一项既有 gateway call ID、source-native request/response hash、run ID、status 与 locator；synthetic 为 `not_applicable` |
| `usage_observation` | live 为既有 gateway usage call ID/locator、source-native usage hash/status/token availability；synthetic 为 evaluation-owned fixed observation locator、`provider_tokens=0`、cost=`not_applicable` |
| `context_snapshot_id` | finalize 后以 trace run ID 只读查询既有 run record 获得 |
| `availability/problems/content_hash` | `available/invalid`、全部 cardinality/conflict 问题和不可变内容 hash |

每个 observation 只按自己的 source locator 复读，并用该源既有算法重算 source-native content hash、ID、run ID 与 status；`evaluation_request_sha256`、trace `input_sha256` 和 replay `request_sha256` 允许完全不同，绝不做跨源 hash 相等判断。trace ID 与 gateway ID 也允许不同；exchange 关联只由同一 task 的 ContextVar owner 和轨道专属 cardinality 建立，禁止按任务名、模型名、内容 hash、状态、时间、目录位置或 mtime 补配。

轨道与状态矩阵固定如下：

| track / gateway outcome | 必需 observation | 允许状态 |
|---|---|---|
| live / returned | trace + replay + usage | replay/usage=`completed`；trace=`completed`，或仅当既有 trace error type 明确属于返回后的 JSON/Pydantic/schema 校验阶段时为 `failed` |
| live / raised | trace + replay + usage | trace/replay/usage 均为 `failed` |
| synthetic / returned | driver step + trace + fixed usage | driver/fixed usage=`completed`；trace 与 live returned 使用同一允许规则；Runtime replay/usage=`not_applicable` |
| synthetic / raised | driver step + trace + fixed usage | driver/trace/fixed usage=`failed`；Runtime replay/usage=`not_applicable` |

“冲突”只指：同一 source locator 复读出的 ID/hash/run/status 与 observation 不一致、违反上述显式状态映射、观察数量不符、owner task 不符、任一 observation run ID 不等于 case run，或 run/context snapshot 无法精确解析。gateway returned + trace failed 但无法证明是返回后应用 JSON/schema 校验时也 invalid。observer 自身异常归 `observer_failed`，repository 异常归 `correlation_repository_unavailable`；二者不回写 Runtime。

ID 规则：

| 对象 | 格式 | 生成/不变量 |
|---|---|---|
| suite | `^[a-z][a-z0-9_]{2,63}$` | 静态声明；内容变化不改 ID，只改 content hash |
| case | `^[a-z][a-z0-9_]{2,63}$` | suite 内唯一；跨 suite 以 suite + case 定位 |
| fixture | `^[a-z][a-z0-9_]{2,63}$` | 静态声明 |
| fixture snapshot | `fixture_<64hex>` | 由 manifest canonical payload 派生 |
| suite content | `suite_<64hex>` | 由 resolved suite canonical payload 派生 |
| case content | `case_<64hex>` | 由单 case canonical payload派生 |
| suite run | `benchmark_run_<UTCcompact>_<12hex>` | 每次提交新建；重复执行不覆盖 |
| case execution | `benchmark_case_<32hex>` | 每次 attempt 新建 |
| evidence bundle | `evidence_<64hex>` | 规范化 bundle 内容寻址 |
| evaluation correlation | `exchange_<32hex>` | 评测 wrapper 在单次 LLM exchange 前创建；不进入 Runtime 记录 |
| suite artifact | `benchmark_artifact_<run_id>` | 一个 run 最多一个终态 artifact |
| experiment | `benchmark_experiment_<UTCcompact>_<12hex>` | 每次实验新建 |
| idempotency claim | `sha256(idempotency_key)` | 文件名不暴露用户原 key |

### 7.2 Suite、track 与 case

#### `SuiteSpec`

| 字段 | 类型 | 规则 |
|---|---|---|
| `schema` | literal `taichu.general_agent_benchmark.suite@1` | 机器兼容需要的稳定格式标识，不表示开发轮次 |
| `suite_id` | string | 稳定静态 ID |
| `name`、`purpose` | string | 中文、非空 |
| `fixture` | `FixtureRef` | fixture id + snapshot id |
| `case_order` | list case id | 无重复，必须与 cases 完全同集合 |
| `cases` | list `CaseSpec` | 非空 |
| `tracks` | list `TrackSpec` | 至少 synthetic；track kind 不重复 |
| `capability_catalog_hash` | SHA-256 | 必须等于本次生产发现快照 |
| `coverage` | list `CapabilityCoverageEntry` | 29 个一等能力逐项反向映射到至少一个真实调用 case；约束/禁止行为另列 target |
| `suite_gates` | `SuiteGateSpec` | 明确 suite 级硬条件和阈值 profile |
| `stability_profiles` | map string → `StabilityThresholdProfile` | 实验重复性阈值；引用必须可解析 |
| `failure_priority` | list `FailureCategory` | 覆盖封闭枚举全部项且无重复 |
| `metric_modules` | set `MetricModuleId` | 只允许已注册模块 |
| `content_hash` | suite hash | loader 计算并核对声明值 |

`SuiteGateSpec` 不包含总分或权重。它解析一个显式 `ThresholdProfile`，至少给出 suite 最低通过条件、必过 case/category、允许 invalid/unfinished/cancelled 数量和必要门禁聚合；案例六预算由案例合同直接声明，重复性阈值由 `stability_profiles` 声明。任何字段未解析都使 suite `invalid`，`POST /runs` 返回 422 全量问题；系统不补默认值。

#### `TrackSpec`

判别联合：

| kind | 字段 | 语义 |
|---|---|---|
| `synthetic` | `rule_set_id`、`gateway_identity` | 使用 case 内嵌 scripted steps；identity 固定为 synthetic，不声称 provider |
| `live_provider` | `provider_selection=explicit`、`allowed_model_refs`、`decode_constraints` | 运行请求必须选择公开 model ref；不得保存 credential |

`decode_constraints` 只允许当前 `LLMRequest` 真正支持的 `temperature`、`max_output_tokens` 和 response mode。seed、top_p 等当前不存在字段在复现 metadata 中记录 `not_supported`，不得加入 gateway request 或伪造值。

#### `CaseSpec`

| 字段 | 类型 | 规则 |
|---|---|---|
| `case_id`、`name`、`purpose` | string | suite 内唯一；中文 name/purpose |
| `category` | `CaseCategory` | 固定业务类别 |
| `tags` | set string | canonical 时排序 |
| `applicable_tracks` | non-empty set `synthetic/live_provider` | 1—16、18—22 为两轨；17、23 仅 synthetic |
| `path_kind` | `direct_answer/single_capability/subagent/multi_step` | 覆盖最小充分路径 |
| `targets` | list `EvaluationTarget` | 设计能力、约束或禁止行为；至少一项 |
| `user_request` | string | 原文，1—100000 字符 |
| `fixture_snapshot_id` | fixture hash ID | 必须等于 suite fixture |
| `capabilities` | `CapabilityBoundarySpec` | required/allowed/forbidden 三集合 |
| `required_invocations` | list `RequiredInvocation` | 覆盖期望；type/name/min/max/expected_outcome/parent 或 partial order 均必填 |
| `authorization` | `AuthorizationBoundarySpec` | 写入、外部访问、资源范围、预期允许/拒绝 |
| `human_responses` | ordered list `HumanResponseScript` | 可空；与 user request 分离；HITL 顺序和 matcher 进入 hash |
| `budgets` | `ResourceBudget` | 六项上限内联且无默认 |
| `expected_artifacts` | 五项判别联合 | 每类恰好一项，disposition 明确 |
| `verifiers` | list `VerifierSpec` | verifier instance id 唯一 |
| `allowed_stop_reasons` | 非空 set | 只允许 Runtime 当前可观察停止语义 |
| `required_evidence` | set `EvidenceKind` | evidence gate 的必需集合 |
| `scripted_steps` | list `ScriptedStep` | synthetic 必需；与 case 同文件、同 hash |
| `advisory_judges` | list `AdvisoryJudgeSpec` | 可空，不进入硬门禁 |
| `content_hash` | case hash | loader 计算核对 |

`CapabilityBoundarySpec` 不变量：

- 三集合内 ID 均必须在真实 Tool/Subagent registry；suite 预检一次列出未知值。
- `required ⊆ allowed`。
- `allowed ∩ forbidden = ∅`，`required ∩ forbidden = ∅`。
- Runtime factory 先注册 `CapabilityCatalogSnapshot` 内全部生产 Tool，再注册全部 Subagent 及其 Tool 依赖；case exposure/policy 才把模型与 Runtime 的可调用面限制为 `allowed`，不会为 required 缺项伪造能力。
- required 在真实目录缺失使 suite preflight 失败；allowed 中运行时不可用使 case invalid，而不是改走假能力。
- `allowed`/manifest/注册成功都不计覆盖；覆盖要求 `RequiredInvocation` 在真实 invocation tree 中满足次数、类型、结果和父子/偏序，并通过相关硬门禁。

`RequiredInvocation` 字段固定为 `type: tool|subagent`、`name`、`min_calls`、`max_calls`、`expected_outcome`、可选 `parent` 或 `partial_order`；后二者至少一种能确定调用位置。首批 `expected_outcome` 固定为 `completed`。Tool 通常为 1..1，`read_external_source` 为 1..3；首批所有 Subagent 为 1..1。缺失、未知、重复、类型错配、不可追踪父链或 capability catalog hash 漂移均令整个 suite 在启动前无效。

`ScriptedStep` 是 `model/tool/subagent/human/task` 判别联合，共同字段为 `step_id`、`sequence`、精确 interaction identity、matcher 和 evidence projection。model step 携带类型化 `LLMResponse`；tool/subagent step 包裹真实 handler 并观察请求/结果，绝不返回伪 capability output；human step 与 ordered `human_responses` 对齐；task step观察创建、完成、故障和恢复点。

全部 step 构成一个全局有序流并进入 case hash。`StrictScriptedDriver` 的 `observe()` 每次只匹配流首：空流为 `SYNTHETIC_SCRIPT_EXHAUSTED`，匹配到较后 step 为 `SYNTHETIC_OUT_OF_ORDER`，同 kind/name 但内容不符为 `SYNTHETIC_CONTENT_MISMATCH`，完全意外交互为 `SYNTHETIC_UNEXPECTED_INTERACTION`。Runtime 停止后必须 `finalize()`；仍有步骤为 `SYNTHETIC_REMAINING_STEPS`。重复运行规范化结果不同为 `SYNTHETIC_NORMALIZATION_DRIFT`。证据必须带 step id/index、expected/observed、失败 matcher/path 和 remaining IDs；负向协议用例放 runner tests，不算业务 case。

`SyntheticNormalizationArtifact` 记录 script identity、Runtime config identity、逐步消费轨迹和规范化结果 hash。规范化明确排除 UTC 时间戳、随机 UUID、临时 workspace/database/path 等易变值；必须保留节点状态、交互 kind/name/order/outcome、typed artifact 内容 hash、所有 hard gate result 和 stop reason。两次输入/script/config identity 相同却产生不同规范化 hash 时保存逐字段 diff 并触发 drift 错误。

### 7.3 首批固定 suite 内容策略

首批 suite ID 固定为 `general_writing_agent_core`，fixture ID 固定为 `core_novel`；不使用开发版本后缀。内容更新通过新 suite/fixture hash 识别，旧 run 仍保存原 resolved snapshot。

fixture 使用完全合成且专用于评测的单本玄幻小说材料，不复制作者活动小说：

- 多个相互可引用的静态 Markdown 章节，包含直接事实、跨章事实和可安全产生 patch candidate 的目标段落；
- 通过当前知识卡领域模型和 Mongo validator 的 confirmed seed，覆盖角色、地点、事件和规则等当前合法类型；
- 初始对话包含可验证的作者表达偏好；
- 初始 Runtime memory 同时包含应正确使用的 active 条目和应拒绝的 stale/superseded 条目；
- 外部资料 fixture 含稳定 query 匹配键、文档 ID/标题/摘要/正文/来源显示名和逐文件 hash，专供 external research case；
- source IDs 全部指向 fixture manifest 内资源；
- knowledge seed 不含任何已废弃知识字段。

首批固定为以下 23 个稳定业务 case。1—16、18—22 的 `applicable_tracks=both`；17、23 仅 synthetic。实际用户原文、全局 script、阈值和 matcher 必须在 suite 文件中显式给出并进入 hash：

| # | case id | required invocation / 硬断言 |
|---:|---|---|
| 1 | `direct_answer_current_request` | 无能力调用；当前请求原始 hash/空白完全一致；五层固定顺序与归属断言 |
| 2 | `single_manuscript_search` | Tool `search_manuscript` 1..1 completed；命中夹具且 assistant/tool 以 `call_id` 配对 |
| 3 | `structure_coverage_read` | Tool `get_novel_structure`、`get_knowledge_chapter_coverage`、`read_manuscript` 各 1..1 completed；卷章顺序、confirmed-only 覆盖和正文范围正确 |
| 4 | `single_knowledge_retrieval` | Tool `retrieve_knowledge` 1..1 completed；只召回 confirmed 且无无关能力 |
| 5 | `knowledge_catalog_identity_read` | Tool `list_knowledge_catalog`→`resolve_knowledge_identity`→`read_knowledge_cards` 各 1..1 completed；分页、歧义、稳定卡片 ID 和生命周期隔离 |
| 6 | `external_research_grounded` | Subagent `external_research` 1..1；其子 Tool `search_external_sources` 1..1、`read_external_source` 1..3，均 completed、授权明确、`parent_call_id` 和 fixture source refs 可追踪 |
| 7 | `single_canon_evidence` | Subagent `canon_evidence` 1..1 completed；契约化证据且子 Agent 内部消息不进入父历史 |
| 8 | `summary_world_character` | Subagent `narrative_summary` 先完成，`worldbuilding` 与 `character` 再并行，各 1..1 completed；三份独立 producer/artifact 证据不得互相代替 |
| 9 | `architecture_scene_draft` | Subagent `story_architecture`→`scene_planning`→`drafting` 各 1..1 completed；动态 DAG/输入工件绑定正确且候选不写 Markdown |
| 10 | `parallel_review_triad` | Subagent `consistency_reviewer`、`narrative_reviewer`、`style_reviewer` 各 1..1 completed；同一候选三份独立工件、并行无串扰 |
| 11 | `revision_from_reviews` | Subagent `revision` 1..1 completed；消费明确 review refs、保留原意、禁止非目标改动且不直接写正文 |
| 12 | `manuscript_preview_only` | Tool `preview_manuscript_patch` 1..1 completed；基础 hash/差异正确、effect=0、事实指纹不变 |
| 13 | `manuscript_patch_authorized_resume` | Tool `preview_manuscript_patch`→HITL waiting/resume→`apply_manuscript_patch` 各 1..1 completed；ordered response、接续 run/attempt、授权、scope/idempotency/CAS/effect 和三方指纹 |
| 14 | `structure_create_update` | Tool `create_novel_structure_items`→`update_novel_structure` 各 1..1 completed；两次授权/effect 可分、创建 ID 绑定更新、CAS、重试不重复创建 |
| 15 | `structure_delete_second_confirmation` | 两次有序确认后 Tool `delete_novel_structure_items` 1..1 completed；只归档且默认结构视图排除已归档项 |
| 16 | `knowledge_create_update` | Tool `create_confirmed_knowledge`→`update_confirmed_knowledge` 各 1..1 completed；合法 confirmed schema/source、身份冲突阻断、CAS、只写隔离 Mongo |
| 17 | `external_access_denied` | handler 前拒绝；外部 Subagent/Tool invocation 为 0；security outcome=`denied_before_invocation` 并引用 node/policy/access ledger |
| 18 | `write_authorization_denied` | 先 `waiting_human` 后 `author_rejected`；apply invocation/effect 为 0，资源指纹不变 |
| 19 | `memory_active_projection` | ACTIVE producer 进入当前事实；memory ID/前态/fingerprint/关系/投影证据齐全 |
| 20 | `memory_stale_dependency` | BASIS/REVIEW_TARGET 传播 STALE；无关并行 ACTIVE 不受影响 |
| 21 | `memory_rejected_parallel_isolation` | review 只拒绝目标 producer；并行节点、摘要、digest、snapshot 无串扰 |
| 22 | `memory_superseded_repair` | 旧项 SUPERSEDED 仅进入 repair-only；REPAIR_SOURCE 不传染；reuse 不得复活旧 producer |
| 23 | `runtime_checkpoint_recovery` | 故障点、同一 Runtime run 的恢复 attempt、checkpoint hash、no-rerun 证据；`get_novel_structure` 恰一次，但能力覆盖归 case 3 |

29 个一等生产能力反向覆盖固定如下；任一项没有合格调用证据时 capability coverage hard gate 失败：

| 类型 | 能力 | 主覆盖 case |
|---|---|---|
| Tool | `get_novel_structure`、`get_knowledge_chapter_coverage`、`read_manuscript` | `structure_coverage_read` |
| Tool | `search_manuscript` | `single_manuscript_search` |
| Tool | `retrieve_knowledge` | `single_knowledge_retrieval` |
| Tool | `list_knowledge_catalog`、`resolve_knowledge_identity`、`read_knowledge_cards` | `knowledge_catalog_identity_read` |
| Tool | `search_external_sources`、`read_external_source` | `external_research_grounded` |
| Tool | `preview_manuscript_patch` | `manuscript_preview_only` |
| Tool | `apply_manuscript_patch` | `manuscript_patch_authorized_resume` |
| Tool | `create_novel_structure_items`、`update_novel_structure` | `structure_create_update` |
| Tool | `delete_novel_structure_items` | `structure_delete_second_confirmation` |
| Tool | `create_confirmed_knowledge`、`update_confirmed_knowledge` | `knowledge_create_update` |
| Subagent | `canon_evidence` | `single_canon_evidence` |
| Subagent | `external_research` | `external_research_grounded` |
| Subagent | `narrative_summary`、`worldbuilding`、`character` | `summary_world_character` |
| Subagent | `story_architecture`、`scene_planning`、`drafting` | `architecture_scene_draft` |
| Subagent | `consistency_reviewer`、`narrative_reviewer`、`style_reviewer` | `parallel_review_triad` |
| Subagent | `revision` | `revision_from_reviews` |

首批 `required_invocations` 的 parent/partial-order 固定如下；表中所有 outcome 均为 `completed`，未写顺序的同 parent 项可任意顺序：

| case | type/name | min..max | parent / partial-order |
|---|---|---:|---|
| `single_manuscript_search` | tool `search_manuscript` | 1..1 | `case_root` |
| `structure_coverage_read` | tool `get_novel_structure` | 1..1 | `case_root`，先于 read |
| 同上 | tool `get_knowledge_chapter_coverage` | 1..1 | `case_root`，先于 read |
| 同上 | tool `read_manuscript` | 1..1 | `case_root`，在 structure/coverage 后 |
| `single_knowledge_retrieval` | tool `retrieve_knowledge` | 1..1 | `case_root` |
| `knowledge_catalog_identity_read` | tool `list_knowledge_catalog` | 1..1 | `case_root`，先于 resolve |
| 同上 | tool `resolve_knowledge_identity` | 1..1 | `case_root`，在 list 后、read 前 |
| 同上 | tool `read_knowledge_cards` | 1..1 | `case_root`，在 resolve 后 |
| `external_research_grounded` | subagent `external_research` | 1..1 | `case_root` |
| 同上 | tool `search_external_sources` | 1..1 | `subagent:external_research`，先于 read |
| 同上 | tool `read_external_source` | 1..3 | `subagent:external_research`，在 search 后 |
| `single_canon_evidence` | subagent `canon_evidence` | 1..1 | `case_root` |
| `summary_world_character` | subagent `narrative_summary` | 1..1 | `case_root`，先于后两项 |
| 同上 | subagent `worldbuilding` | 1..1 | `case_root`，在 summary 后，与 character 并行 |
| 同上 | subagent `character` | 1..1 | `case_root`，在 summary 后，与 worldbuilding 并行 |
| `architecture_scene_draft` | subagent `story_architecture` | 1..1 | `case_root`，先于 scene |
| 同上 | subagent `scene_planning` | 1..1 | `case_root`，在 architecture 后、drafting 前 |
| 同上 | subagent `drafting` | 1..1 | `case_root`，在 scene 后 |
| `parallel_review_triad` | subagent `consistency_reviewer` | 1..1 | `case_root`，三项 unordered parallel |
| 同上 | subagent `narrative_reviewer` | 1..1 | `case_root`，三项 unordered parallel |
| 同上 | subagent `style_reviewer` | 1..1 | `case_root`，三项 unordered parallel |
| `revision_from_reviews` | subagent `revision` | 1..1 | `case_root`，在 review refs 可解析后 |
| `manuscript_preview_only` | tool `preview_manuscript_patch` | 1..1 | `case_root` |
| `manuscript_patch_authorized_resume` | tool `preview_manuscript_patch` | 1..1 | `case_root`，先于 HITL |
| 同上 | tool `apply_manuscript_patch` | 1..1 | `case_root`，在 author-approved HITL 后 |
| `structure_create_update` | tool `create_novel_structure_items` | 1..1 | `case_root`，先于 update |
| 同上 | tool `update_novel_structure` | 1..1 | `case_root`，在 create 后 |
| `structure_delete_second_confirmation` | tool `delete_novel_structure_items` | 1..1 | `case_root`，在第二次确认后 |
| `knowledge_create_update` | tool `create_confirmed_knowledge` | 1..1 | `case_root`，先于 update |
| 同上 | tool `update_confirmed_knowledge` | 1..1 | `case_root`，在 create 后 |

表中 `case_root` 表示 invocation tree 的无父调用根；`subagent:<name>` 必须解析为该次 Subagent 的真实 `call_id`，不能只比较名称。注意 `preview_manuscript_patch` 在两个 case 中各有一次，但其能力覆盖主映射只取 `manuscript_preview_only`；矩阵共有 30 条调用期望，对应 29 个唯一 `(type,name)` 能力。

所有写能力 case（13—16）都保存 `WriteBoundaryProof`：sealed source、作者活动事实和 case workspace 的前后指纹；授权 scope；idempotency key/result；CAS revision；effect ID/status/resource locator；预期与实际写入差异。case 13/15 的 ordered human responses 必须与真实 HITL request kind/node/tool/scopes 一一匹配。case 17/18 的拒绝发生在 handler 前，使用 evaluation-level `denied_before_invocation/waiting_human/author_rejected`，并引用 node/HITL/policy/access ledger；不得要求或伪造 `InvocationStatus=denied`。

case 1 的 `CurrentRequestAndFiveLayerProof` 保存用户原文 UTF-8 hash、长度与空白敏感 matcher，以及“稳定记忆→工作记忆→长期记忆→历史记忆→当前请求”的固定序列和逐项归属/禁止内容断言；只比较原始 user content，不把 harness 说明伪装成用户输入。case 23 保存 fault point、同一 Runtime run ID、原/恢复 attempt、checkpoint revision/hash、恢复前后 interaction 序列、不得重跑的 capability 集合，以及每项比率的明确 numerator/denominator；这与 suite lifecycle 的 unfinished→新 run 恢复是两套不同机制。

拒绝 case 证明权限边界，不计算被拒能力的覆盖；`runtime_checkpoint_recovery` 证明运行恢复机制，不替代 suite lifecycle 的 unfinished/resume，也不进入 live 排名。strict script 正负协议、evidence missing/corrupt/conflicting/read-only、suite cancel/unfinished/resume-new-run/old immutable/terminal/idempotent 均是 runner tests，不增加业务 case。旧 8 题只能人工提取题意，不能迁移旧 expected、权重、关键词、checksum 或 reference answer。

### 7.4 Fixture snapshot

`FixtureSnapshotSpec`：

| 字段 | 类型 | 规则 |
|---|---|---|
| `fixture_id` | stable id | 单本 fixture |
| `schema` | literal `taichu.general_agent_benchmark.fixture@1` | 机器格式 |
| `manifest_entries` | list `FixtureEntry` | 按相对 POSIX path 排序 |
| `manuscript_root` | relative path | 只能落在 fixture source 内 |
| `knowledge_seed` | relative path | 只含 validated confirmed cards |
| `conversation_seed` | relative path | 原始 user/展示 assistant 历史 |
| `runtime_memory_seed` | relative path | 运行记忆，不用事实 lifecycle |
| `external_source_manifest` | relative path | query index、document IDs、内容 hash 与稳定 source ref；禁止 URL 联网 |
| `snapshot_id` | `fixture_<hash>` | 共同 canonical hash |

`FixtureEntry` 包含 `path`、`kind`、`size_bytes`、`sha256`，禁止绝对路径、`..`、符号链接和未列目录。fixture loader 在复制前后都逐项核对；额外文件、缺文件、hash/size 不一致均为 `benchmark_invalid`。

`CaseWorkspaceHandle`：

- `workspace_id`、`case_execution_id`；
- resolved 临时 assets root；
- 精确 Mongo database `taichu_eval_<32hex>`；
- fixture/source/activity 前置指纹；
- owned runtime/repository/client handles；
- isolation access ledger；
- cleanup 状态与失败详情。

数据库名称不进入 case 合同，不是 project/multi-novel ID。它只由 case execution ID 生成，并在创建/drop 前校验 `^taichu_eval_[a-f0-9]{32}$`。

### 7.5 六预算

`ResourceBudget` 六字段全部无默认；节点、模型调用、Token、运行时长上限为正整数，重规划和能力调用上限为非负整数，以支持明确禁止重规划或能力调用的案例：

| 预算 | 上限字段 | 实际值定义 | 不可用语义 |
|---|---|---|---|
| 节点 | `max_node_executions` | 唯一 `(plan_revision,node_id)` node run 数 | run/node evidence 缺失则 invalid |
| 重规划 | `max_replans` | `GeneralAgentRun.replan_count` | run 缺失则 invalid |
| 能力调用 | `max_capability_calls` | trace 中 tool/subagent call_id 去重数 | trace 冲突/缺失则 invalid |
| 模型调用 | `max_model_calls` | available evaluation correlation record 的 `exchange_id` 去重数 | record 多/少 observation、跨 task 或源复核冲突则 invalid |
| Token | `max_total_tokens` | 遍历 available `EvaluationCorrelationRecord` 并按唯一 token observation 求和：live 以 `usage_observation.locator/gateway_call_id` 读取既有 usage，synthetic 读取 record 内 fixed usage | live 任一 required usage null/missing 不按 0；synthetic 的 provider token 0 只来自 strict-driver 固定合同，不是缺失回填 |
| 运行时长 | `max_runtime_ms` | executor 在 Runtime 提交前至 terminal/HITL stop 后的单调时钟 elapsed | 崩溃无终点则 unfinished/invalid |

`BudgetObservation` 对每项保存 `limit`、`actual: int | null`、`availability`、`within_limit: bool | null` 和 evidence refs。Budget gate 只有六项均 `available` 且 `within_limit=true` 时 passed；超限为 failed，缺失/冲突为 invalid。

### 7.6 五类类型化预期产物

每个 case 必须恰好声明五类，均继承：

- `artifact_id`
- `artifact_type`
- `disposition: required | forbidden | not_applicable`
- `identity_rules`
- `verifier_instance_ids`

| 类型 | 必填内容 | 可选内容 | 观察值与身份 |
|---|---|---|---|
| `final_answer` | answer contract、允许语言、内容规则 | exact hash、必含/禁含 claim IDs | Runtime final answer + full content hash；工件可保留受长度约束正文，Prompt 不随之复制 |
| `source_reference` | allowed fixture source IDs、是否必须可解析 | min/max count、source kinds | node/final answer source refs；每个 ref 必须解析到当前 fixture snapshot |
| `capability_artifact` | capability name/type、artifact kind | producer node/path constraints | artifact ref + run/node/call provenance；不复制巨型 capability output |
| `write_candidate` | candidate kind、target fixture refs、`must_remain_uncommitted=true` | schema-specific expected fields | draft JSON 中间态；活动事实和 fixture source 均不得变化 |
| `human_intervention` | kind、expected state、trigger boundary | tool name、resource scopes、second confirmation | pending human request + node/tool/auth evidence |

`disposition=forbidden` 时实际产物存在即 artifact gate failed；`not_applicable` 不要求实际产物且 verifier 返回 not applicable。Write candidate 只允许 `manuscript_patch/knowledge_card/structure_change` 三种当前业务类别，始终是中间态，绝不调用正式提交仓储。

### 7.7 Verifier 合同与静态注册表

`VerifierSpec`：

| 字段 | 规则 |
|---|---|
| `instance_id` | case 内唯一 |
| `verifier_id` | 封闭 `VerifierId` |
| `expected_artifact_ids` | 必须存在且类型与 registry 声明一致 |
| `required` | required verifier failed/invalid 会使 verifier gate 不通过 |
| `config` | 与 verifier id 对应的判别联合，不允许自由 dict/class path |

`VerifierResult`：

- `instance_id`、`verifier_id`、`rule_identity`、`spec_hash`；
- `status: passed | failed | invalid | not_applicable`；
- `expected_summary`、`observed_summary`；
- `evidence_refs`；
- `failure_categories`；
- `error_code`、中文 message key；
- `deterministic=true`、`started_at`、`finished_at`。

静态 registry 在 composition root 显式构造以下实现，不扫描目录、不 dynamic import：

| verifier id | 接受输入 | 检查范围 |
|---|---|---|
| `final_answer_contract` | final answer | presence、hash、声明的 claim/禁词，不宣称完整语义质量 |
| `source_fixture_resolution` | source reference + fixture | ref 可解析且属于 sealed fixture |
| `capability_artifact_provenance` | capability artifact + bundle | artifact 与 run/node/call/capability 一致 |
| `write_candidate_isolated` | write candidate + boundary evidence | candidate 类型合法且未提交活动事实 |
| `human_intervention_boundary` | HITL + run/node | kind、trigger、state、scopes、二次确认 |
| `six_budget_limits` | budget observations | 六上限、实际和 availability |
| `capability_path_contract` | invocation/node evidence | `required_invocations` 的 type/name/min/max/outcome/parent/偏序全部满足；所有调用 allowed；forbidden 未调用 |
| `security_boundary` | auth/effect/access ledger | 预期 allow/deny、错误码、越权写入/能力 |
| `normal_stop_reason` | run/case execution | 终止原因在 case allowlist |
| `evidence_completeness` | evidence bundle | required kinds available 且无 conflict |
| `current_request_identity` | context/replay hash projection | 原始 request hash 保持且未混入 harness |
| `five_layer_context_boundary` | context stats/refs | 五层命名、归属与禁止项 |
| `tool_call_pairing` | replay/call tree summary | assistant call_id 与 tool result 完整配对 |
| `subagent_scope_isolation` | invocation/subagent result refs | 子 Agent 内部消息未并入父历史 |
| `memory_use_or_reject` | memory state transition/projection/reuse evidence | ACTIVE 当前投影；其余三态 repair-only；传播、并行隔离、producer reuse 均符合 |
| `checkpoint_integrity` | checkpoint revisions | revision hash 链与 integrity status |

禁止项：

- verifier Protocol 只接收冻结的 `VerificationInput`，不接收 repository/client/runtime handle/path writer；
- registry key 不可由 suite 提供模块名；
- config 中不允许 command、script、executable、working directory 或 import path 字段；
- 禁止 `subprocess`、PowerShell、cmd、Shell、`eval`、`exec` 和动态模块加载；
- verifier 不写 case/run、Runtime audit、fixture 或活动事实。

`AdvisoryJudgeSpec/Result` 与 verifier 分开保存。judge result 只有 `supported/unsupported/invalid`、理由、model identity、证据 ref 和 availability；不产生 gate、failure priority 或 pass override。judge 未配置只记 `not_available`，确定性结论仍独立。

### 7.8 Gate、结论与失败分类

六类 `GateKind`：

1. `budget`
2. `verifier`
3. `artifact`
4. `stop_reason`
5. `security`
6. `evidence`

`GateResult` 保存 `scope=case|suite`、gate kind、`status=passed|failed|invalid`、condition results、expected、observed、evidence refs 和 failure categories。

案例真值：

| 前提 | `CaseConclusion` |
|---|---|
| cancel 在 case 开始前或 Runtime cooperative cancel 后 | `cancelled` |
| worker 中断且没有完整 gate 结果 | `unfinished` |
| benchmark/fixture/required evidence/基础设施使事实无法判断 | `invalid` |
| 六 gate 均可判断且任一 failed | `failed` |
| 六 gate 全部 passed | `passed` |

不得存在 `warning_pass`、score threshold override 或 judge override。Invalid/unfinished/cancelled 不进入 pass numerator。

封闭 `FailureCategory`：

```text
benchmark_invalid
fixture_isolation_failed
security_violation
evidence_incomplete
missing_artifact
budget_exceeded
verifier_failed
failure_stop_reason
execution_error
cancelled
unfinished
undetermined
```

suite 必须声明恰好一次的确定性全序；首批 suite 使用上列顺序。分类器从 gate/result facts 生成去重 `failure_categories`，再按 suite priority 选 `failure_category`。分类器不得丢弃原 condition/evidence；无法映射时添加 `undetermined`。中文说明由 API/UI display map 提供，不把 enum 原文直接显示。

套件运行生命周期和业务结论是两个不重叠的字段：

```text
SuiteRunLifecycle = queued | running | cancelling | finalizing | completed | unfinished | cancelled
SuiteConclusion = passed | failed | invalid | not_evaluated
```

唯一不变量是：只有 `lifecycle=completed` 时 `conclusion` 必须为四个 `SuiteConclusion` 之一；其他六种 lifecycle 的 `conclusion` 必须为 null。案例自己的 `CaseConclusion` 仍按上表保留 passed/failed/invalid/unfinished/cancelled，不与 suite lifecycle 混用。

套件真值：

- preflight 失败时不创建 run/case，API 返回 suite invalid 问题列表；
- provider blocked 时创建可查询 run，经 `finalizing` 成功提交受阻工件后成为 `completed + not_evaluated`；
- 运行级 fixture、事实安全、identity 或 required evidence 失效时停止后续 case 并进入 `finalizing`；若能完整提交包含失效证据的工件，则成为 `completed + invalid`，若不能完整提交则成为 `unfinished + null`；
- 正常执行收束后进入 `finalizing`，先保留全部 case conclusion，再计算 suite gates；
- provider 已完成、所有必需 case 可判断且 suite gates 全通过时成为 `completed + passed`；
- 行为硬门禁或 suite hard gate 可确定地失败时成为 `completed + failed`；
- 必需 case invalid 或完整工件证明判定基础无效时成为 `completed + invalid`；
- 操作者取消收束成功时成为 `cancelled + null`；进程中断、lease 过期或工件无法完整提交时成为 `unfinished + null`，二者都不形成业务结论。

能力覆盖是独立 suite hard gate。其分母是 `CapabilityCatalogSnapshot` 中 29 个 `(type,name)`，分子只接受满足以下全部条件的项：contract preflight 通过；至少一个主映射 case 在适用轨道上运行；真实 invocation tree 中所需次数与父子/偏序可追踪；每个计数调用 `status=completed`；相关 capability/artifact/security/evidence gate 全通过。拒绝、missing、unknown、duplicate、untraceable、仅 manifest/allowed/registered 均不进入分子。`runtime_checkpoint_recovery` 的重复读取不替代 case 3 的主覆盖。

局部机制与整体能力使用显式类型：

```text
MechanismGateResult(scope, mechanism_id, status, conditions, evidence_refs)
MechanismConclusion = met | not_met | invalid | not_applicable
MechanismDecisionSource = hard_gate | qualified_ablation
```

所有机制默认由 hard gate 直接给结论，指标只解释。只有 `MechanismSwitchResolver` 能解析到真实 Runtime 配置路径，control/treatment 的 canonical config hash 除该允许开关外完全相同，两臂 invariant gates 全通过，显式收益阈值达到且 core 无回归，才能产生 `decision_source=qualified_ablation`。无真实开关时 `not_applicable` 于实验、但仍必须运行机制硬门禁；禁止 validation/test split、difference workflow、总分或“好看指标”放行。

### 7.9 Evidence availability 与 bundle

`EvidenceAvailability`：

- `available`：精确 ID、hash 和结构校验通过；
- `missing`：声明需要但 reader 未找到；
- `corrupt`：文件/schema/hash/链校验失败；
- `not_applicable`：case 合同明确不需要；
- `conflicting`：同一稳定 ID 出现不一致事实或跨仓储关联冲突。

证据读取分为“单源只读端口”和“跨源聚合端口”。`contracts/runtime_evidence.py` 声明八个互不继承仓储合同的窄 Protocol：

```text
RunEvidenceSource.read_run(run_id) -> EvidenceItem[RunSourceRecord]
NodeEvidenceSource.read_nodes(run_id) -> EvidenceItem[tuple[NodeSourceRecord, ...]]
InvocationEvidenceSource.read_invocations(run_id) -> EvidenceItem[tuple[InvocationSourceRecord, ...]]
ContextSnapshotEvidenceSource.read_snapshot(snapshot_id) -> EvidenceItem[ContextSourceRecord]
ReplayEvidenceSource.read_replays(run_id) -> EvidenceItem[tuple[ReplaySourceRecord, ...]]
CheckpointEvidenceSource.read_revisions(thread_id) -> EvidenceItem[tuple[CheckpointSourceRecord, ...]]
EffectEvidenceSource.read_effects(run_id) -> EvidenceItem[tuple[EffectSourceRecord, ...]]
UsageEvidenceSource.read_usage(call_id) -> EvidenceItem[UsageSourceRecord]
```

每个 source 只有上述读取方法，返回不含仓储句柄的冻结 DTO。`RuntimeEvidenceSources` 是冻结容器，八个字段分别以这八个 Protocol 标注；不存在通用 `repository`、`client` 或 `storage` 字段。

`infrastructure/.../evidence_sources.py` 为每类 source 提供一个 facade。facade 构造器只接受已经绑定的单个只读 `Callable`，例如 `RunEvidenceSourceFacade(read_one=run_repository.get)` 和 `EffectEvidenceSourceFacade(read_many=effect_repository.list_by_run)`；构造完成后只保存该 callable，不保存 `run_repository` 等完整对象。composition root 先绑定这些函数，再把 `RuntimeEvidenceSources` 注入 reader，禁止执行 `RepositoryRuntimeEvidenceReader(run_repository=...)` 之类完整仓储注入。即使一个可写仓储结构上满足某个只读 Protocol，也不能直接作为 source 传入。

聚合后的 `RuntimeEvidenceReader` Protocol：

```text
read_run(run_id) -> EvidenceItem RunSummary
read_nodes(run_id) -> EvidenceItem NodeSummaries
read_invocations(run_id) -> EvidenceItem InvocationTree
read_context(snapshot_id, run_id) -> EvidenceItem ContextSummary
read_checkpoint(thread_id) -> EvidenceItem CheckpointSummary
read_effects(run_id) -> EvidenceItem EffectSummaries
read_llm_replays(run_id) -> EvidenceItem ReplaySummaries
read_llm_usage(call_ids) -> EvidenceItem UsageByCallId
```

所有方法只返回规范化冻结 DTO 和 availability；Protocol 没有 save/delete/repair/append。Reader 的构造参数只有 `RuntimeEvidenceSources`，不接收任一仓储。Adapter 的关联算法：

LLM 跨源关联不塞入 `RuntimeEvidenceReader`。`EvaluationCorrelationReader.read_exchange(exchange_id)` 只读 evaluation-owned correlation repository；`EvidenceBundleBuilder` 先读取该 record，再把其中各源 locator 交给上述窄 Runtime reader。这样 Runtime reader 仍是现有审计的只读投影，correlation 事实归评测所有。

1. 从 case execution 保存的 `run_id` 精确读取 run，验证 conversation id。
2. `thread_id` 必须等于当前 Runtime 约定的 run id，不接受目录最近项。
3. node 以 `(run_id, plan_revision, node_id)` 唯一；attempt/effect 必须回指同一 run/node/revision。
4. invocation 以 call_id 唯一并沿 parent_call_id 构树；root 必须属于 run。
5. context snapshot id 必须同时匹配 run 和 conversation，保存其 `content_sha256` 和 category stats，不返回 envelope 正文。
6. checkpoint 每个 revision 保存 `content_sha256`、previous hash、integrity；`checkpoint_bundle_hash` 由有序 revision 摘要计算。
7. LLM 证据先按 `case_execution_id + exchange_id` 读取 evaluation correlation record；record 必须已 finalize 且 availability=available。reader 不要求既有 trace call ID 等于 gateway replay/usage call ID，也不比较 evaluation/trace/replay 三种请求 hash。
8. live reader 按 record 中保存的精确 source locator 分别复读 trace、replay、usage，并用每个源自己的算法复核该 observation 的 ID/hash/run/status；synthetic 复读 strict-driver step 与 trace，验证 fixed usage observation 的 canonical hash，Runtime replay/usage 保持 `not_applicable`。context snapshot ID 只从 correlation record 指向的 trace run ID 读取既有 run record 获得，再读取 snapshot。
9. 跨源只校验轨道状态矩阵、观察数量、owner task 与 case run ID；gateway returned 后应用 JSON/schema 校验失败允许 trace failed + replay/usage completed。其他源内复读不一致、非法状态映射或 run 不匹配才是 `conflicting/invalid`。
10. Token 聚合遍历 available records 并按 token observation locator 去重：live 以 gateway usage call ID 调用 `get`，synthetic 使用 record 内 fixed provider token 0；不把 replay/trace/usage 三处重复相加。禁止用 task/model 名称、hash 相似、状态相同、时间、捕获近邻、目录顺序或 mtime 修补 correlation。

`EvidenceBundle`：

| 字段 | 内容 |
|---|---|
| identity | bundle id/hash、suite/case/run/case execution/track/fixture hash |
| correlation | conversation → run/thread → node/revision → attempt/effect；call/parent call/context snapshot |
| run | 状态、允许停止原因观察、节点引用 |
| invocation | 能力调用树摘要、counts、错误 |
| context | snapshot id/hash、五层统计、compression/current request hash |
| checkpoint | integrity、revision refs、checkpoint bundle hash |
| effects | effect/attempt/resource/auth/idempotency/status 摘要 |
| llm | call/provider/model/status/token/cost availability，不含 messages/Prompt/response text |
| artifacts | 五类 observed artifact 或明确 absence |
| fixture boundary | source/activity/workspace 前后指纹与 access ledger conclusion |
| availability | 每类状态、问题和 direct locator |

隐私上限：

- suite artifact 可保存 case 原始 user request，因为它本就是固定 benchmark 输入；
- final answer 可保存完整但受 Runtime 200000 字符上限约束；
- Prompt、context envelope、fixture Markdown、confirmed cards、完整 tool/subagent output 不复制；
- 默认 UI 摘要单字段不超过 500 字符，技术详情只显示 hash/count/locator；
- provider credential、Mongo URI secret、绝对活动正文内容永不保存；
- export package 仅聚合上述最小工件，不打包 workspace 或 Runtime 原始目录。

### 7.10 Case row、suite run 与 suite artifact

`CaseResultRow`：

- suite/case/case content/fixture/track/provider identity；
- case execution ID、attempt number、Runtime conversation/run/thread IDs；
- case execution state、case conclusion、stop reason；
- 六个 budget observations；
- observed artifact refs；
- verifier results；
- 六 gate results；
- `failure_category` 与 `failure_categories`；
- evidence bundle ID/hash/availability；
- elapsed/timestamps；
- infrastructure error 与 attribution scope；
- advisory judgement refs；
- immutable artifact path reference。

`SuiteRun` 是可变状态 manifest，包含：

- run id、revision、`lifecycle: SuiteRunLifecycle`、`conclusion: SuiteConclusion | null`；
- resolved suite snapshot/hash、selected case IDs；
- track、provider target/provider state；
- normalized submission hash、idempotency claim；
- progress total/completed/failed/invalid/cancelled/unfinished；
- active case execution IDs；
- lease id/owner/heartbeat/expiry；
- cancel requested at/by；
- case row refs 和 pending case IDs；
- created/started/finished timestamps；
- recovery actions；
- terminal artifact ref。

仓储模型校验 `lifecycle/conclusion` 唯一映射：completed 必须有非空 conclusion，其他 lifecycle 必须为 null；只有 completed 必须有完整 terminal artifact ref。unfinished/cancelled 只保留 manifest、已完成 case/attempt refs 和缺失项，不伪造 suite artifact。

`SuiteArtifact` 是终态不可变聚合：

- reproducibility metadata；
- 完整 resolved suite/case/fixture identities；
- provider/model/decode/locale/timezone/track；
- Git commit/branch/dirty availability；
- 全部 CaseResultRow；
- suite gate、failure 双口径汇总；
- 六类 metric artifact refs；
- evidence bundle refs/hashes；
- provider state；
- final conclusion 和无法取得字段的 availability；
- artifact hash。

Repro metadata 对每项使用 `{availability,value,reason}`。Git 非仓库、分支 detached、dirty 检测失败、model version 不公开、费用不可用都不能省略或猜测。

### 7.11 Experiment、comparability、stability 与 provider state

`ProviderExecutionState`：

```text
not_applicable
pending
running
blocked
error
completed
```

终态语义：

- `blocked`：未配置、凭据缺失、模型禁用、明确配额/可用性前置不满足，未伪造 case；
- `error`：已开始 provider 轨道但调用或 gateway 发生错误；保留已完成尝试和证据；
- `completed`：所有被调度 case 到达可观察终态，不代表 suite 通过。

provider 错误分类由基础设施 adapter 的静态映射完成；未知 code 默认 `error`。不得 fallback 为 synthetic，provider/model identity 不得从显示名称推断。

`ExperimentSpec`：

- experiment id/name、suite content hash、fixture hash；
- `mechanism: context | memory | security | recovery | provider`；
- control arm 与 treatment arm；
- 每 arm 的 track/provider/selected cases/repetition count/declared settings；
- `declared_differences`，只能包含所选 mechanism 的允许路径；
- stability threshold profile；
- idempotency key。

机制允许差异路径是封闭表：context 只允许上下文投影/压缩策略 identity；memory 只允许运行记忆策略 identity；security 只允许授权策略和 capability exposure profile identity；recovery 只允许故障注入与恢复策略 identity；provider 只允许 provider/model/decode settings 且两 arm 都是 live provider。未知策略 identity、跨机制路径或同一字段既未声明又发生变化都使比较 invalid。

`ComparabilityResult` 保存：

- `status: comparable | incomparable | invalid`；
- suite/fixture/case/user input/conditions/track/provider/decode/capability/auth/verifier/gate identity 对比；
- declared differences 与 actual differences；
- undeclared differences；
- evidence refs 和中文 reason key。

除 `declared_differences` 外，两 arm 必须相同。synthetic 与 live、不同 suite hash、不同 fixture、不同 case set、不同 verifier/gate 或未声明 capability 差异一律 incomparable；不得计算机制增益。

`StabilitySummary` 对每个数值 metric 保存：

- `sample_count`
- `mean`
- `variance`，定义为样本方差，`n < 2` 时为 null 且 availability=insufficient
- `minimum`
- `maximum`
- `range = maximum - minimum`
- `repeatability: stable | unstable | insufficient_samples | invalid`
- threshold profile identity。

repeatability 只按显式 profile 判断；profile 缺失不补默认，experiment preflight invalid。实验 artifact 同时保存每次 suite artifact、arm 的绝对 pass/failed/invalid 结论、case/gate/failure 差异和可比时才生成的相对 delta。

### 7.12 工作记忆投影与复用契约

生产侧新增窄应用合同：

```text
ProducerMemoryValidityProof(
  conversation_id,
  producer_ref,
  memory_id,
  validity,
  state_hash,
  source_fingerprint,
  dependency_fingerprint,
  observed_at
)

require_active_producer(
  conversation_id,
  producer_ref,
  expected_source_fingerprint,
  expected_dependency_fingerprint
) -> ProducerMemoryValidityProof
```

proof 必须命中精确 `node:<run_id>:<revision>:<node_id>`，且只有一条当前记录；missing、重复冲突、非 `ACTIVE`、已删除/过期、source/dependency fingerprint 不同都 fail closed。`producer_validities` 改为按最新状态稳定折叠，禁止旧记录覆盖新记录。

`CurrentFactProjectionPolicy` 被 ContextAssembler 的 node summaries、正常/fallback digest、snapshot current refs、Orchestrator 复用校验、Executor 复制和 `record_node_results` 共用：只允许 `ACTIVE`。`RepairProjection` 显式列出 `STALE/REJECTED/SUPERSEDED`，每项带 `repair_only=true`、前态/现态/原因/来源/关系/状态 hash；它不能进入 Tool/Subagent 当前上下文。`BASIS/REVIEW_TARGET` 传播失效，`REPAIR_SOURCE` 不传播。

复用执行双门禁：

1. Orchestrator 接受 `reuse_from_node_id` 前解析源 producer ref 并取得 ACTIVE proof。
2. Executor 复制前以同一 fingerprint 再验证；proof 改变则停止复用而非执行陈旧结果。
3. 新 NodeRun 保留 `reused_from_producer_ref`、proof hash 和 source revision，不能只复制 output。
4. `record_node_results` 仅在 proof 仍有效时建立当前 projection；其 provenance 依赖旧 producer，不能无来源重新铸造 ACTIVE。

四个 memory case 的 evidence 至少保存 memory IDs、前态/后态、source fingerprint、BASIS/REVIEW_TARGET/REPAIR_SOURCE 边、transition reason/source、current-vs-repair 投影和 reuse 断言。七项 `MechanismGateResult` 固定为来源指纹解析、依赖传播、review 目标拒绝、revision/supersession、并行隔离、当前投影、reuse validity；任一项失败或证据不可判定，工作记忆专项整体为 `not_met/invalid`，即使其他指标良好也不能放行。

### 7.13 DeepSeek 首轮、Inbox 与多模型数据模型

`FirstLiveArtifact` 是不可变首轮工件：

- `iteration_id`、suite/code/fixture/capability catalog hashes；
- synthetic qualification artifact refs；
- requested model ref=`deepseek-v4-pro`，实际 provider/model、probe/fallback/replay/usage/cost/error；
- immutable first-run suite artifact ref、immutable failure record refs 和自身 `CorrelationSubjectRef`；
- 不包含 closure state、pending intent、issue ID、relation revision 或 comparison latest 指针。

`FirstLiveIterationManifest` 是独立可变协调状态：`iteration_id`、revision、`state: awaiting_synthetic | ready_for_deepseek | deepseek_running | classifying | closing_system_defects | ready_for_comparison | blocked | invalid`、first-live artifact ref、pending intent refs、confirmed relation refs、comparison refs/latest comparison ref 和 problems。所有更新使用 expected revision CAS。API 的 `FirstLiveIterationResponse` 是 manifest、冻结 artifact 摘要和关联查询结果的视图，不把可变字段写回冻结文件。

只有 synthetic 全量、core capability、工作记忆和所有局部机制硬门禁稳定通过时，状态才能到 `ready_for_deepseek`。DeepSeek 完整 live suite 结束后立即冻结首轮工件，分类固定为 `system_defect | benchmark_verifier_defect | provider_behavior | environment_blocked | unknown`；证据不足使用 `unknown`，不能猜测。仅 `system_defect` 进入 Inbox。`benchmark_verifier_defect` 保存在 iteration 内部闭环记录中，只有受影响 case 与当前 suite hash 的完整 suite 均通过后才能标为 closed；provider/environment 类别只记录行为或阻塞证据。

`CorrelationSubjectRef` 在冻结对象创建时一次形成。先对排除 `correlation_subject` 与最终 artifact hash 字段的 canonical payload 计算 `subject_content_sha256`，再计算：

```text
correlation_subject_id =
  sha256("general_agent_benchmark" + subject_kind + stable_resource_id
         + subject_content_sha256)
```

`subject_kind` 只允许 `run_terminal_artifact | suite_artifact | first_live_artifact | failure_record`。可变 run manifest、iteration manifest、索引、pending intent 和 API view 永远不能成为 subject。插入 subject ref 后再计算最终 artifact hash。后续 issue 创建、更新、关闭或 reconciliation 均不得改写冻结对象；从 subject 到 issue 的反链通过评测所有的 `IssueCorrelationRepository` 解析。

`MVPInboxIssueLink` 是通用 typed link，只保存 `namespace`、`relation_id`、`subject_id`、`relation_kind`、`subject_content_sha256`。它不保存 issue content/status/revision hash，因而 issue 状态变化不会改变 relation identity。严格八行正文继续按既有顺序，未知值按语义填写“待调查”“待处理”“待验证”或“暂无”；`todo` 对应正文“状态：待处理”，`processed` 对应“状态：已处理”，`deprecated` 不用于系统缺陷闭环。

稳定关系身份：

```text
relation_id = sha256(issue_id + correlation_subject_id + relation_kind)
```

`relation_kind` 是封闭枚举 `documents | caused_by | observed_in | closes`。`IssueCorrelationIntent` 的 canonical payload 排除捕获时间并固定排序 relations：

```text
intent_id =
  sha256(operation + issue_id + desired_issue_payload_sha256
         + expected_inbox_revision + sorted(relation_id, subject_id,
                                             relation_kind,
                                             subject_content_sha256))
```

intent 路径固定为 `intents/<intent_id>.json`，create-if-absent 遇到相同 hash 幂等、不同内容冲突。lease owner/token、协调 attempt 或时间不进入 intent identity，只进入 observation。

每个 relation 与一次 Inbox readback 对应的 revision identity 固定为：

```text
revision_id =
  sha256(relation_id + intent_id + observed_inbox_revision + operation)
revision_path =
  relations/<relation_id>/revisions/<revision_id>.json
```

`IssueCorrelationRevision` 保存 revision/relation/intent/issue/subject/relation kind/operation、expected previous relation manifest revision/hash、Inbox readback status/revision/canonical content hash/typed links hash 和自身 content hash；身份与寻址不引入随机值或墙钟时间。repository 先以 create-if-absent 写 snapshot：同 path+同 hash 幂等，同 path+异 hash 冲突；然后以 expected revision CAS relation manifest。若 snapshot 已落盘而 manifest CAS 失败，该文件是带 intent/revision identity 的可识别 orphan；reconciler 复用同一路径，不创建第二条 revision。

`IssueCorrelationObservation` 是 append-only 协调事件：

- `observation_id = sha256(intent_id + operation_attempt_id + phase + outcome + observed_state_sha256)`；
- 保存 intent/relation/revision refs、lease attempt、`intent_written | inbox_read | inbox_mutated | inbox_readback | revision_written | relation_cas | symmetry_checked | iteration_cas` phase、`succeeded | failed | uncertain | conflicting` outcome、安全错误码、观察到的 Inbox/relation/iteration revisions、observed state hash、attempt 固定起始时间和 content hash；
- `operation_attempt_id` 在取得租约时生成并在该次重试内固定；同一 observation 重放同 hash 幂等，不同协调尝试产生新 append-only observation；
- observation 只用于审计和恢复诊断，不改变 relation identity，也不替代 manifest 当前指针。

`IssueCorrelationRepository` 提供 `put_intent_if_absent`、`put_revision_if_absent`、`append_observation_if_absent`、`compare_and_swap_relation_manifest`、`compare_and_swap_iteration_manifest`、按 intent/relation/subject 查询和 orphan 扫描。subject/relation/issue 索引可由 intent/revision 重建，不是事实源；issue 更新只创建新 intent 并追加新 revision/observation，不覆盖旧 revision，也不触碰冻结 subject。

`SystemIssueContentBuilder` 只接收已分类的系统缺陷证据，按高层工程视角描述用户可见现象背后的架构机制、被破坏的职责/数据边界、系统性影响、目标不变量、修复路径与可验证结果；页面字段、函数名、枚举或内部名词只能放“相关代码”，不能替代根因分析。builder 输出仍由 Inbox canonicalizer 做八字段、全角冒号、日期与非空校验。

稳定 `defect_fingerprint = sha256(suite_hash + failure_category + mechanism_id + stable_evidence_root)`，排除 iteration/run/timestamp；issue ID 为 `issue-ga-<fingerprint hex>`。`IssueClosureLease` 以 `(suite_hash, defect_fingerprint)` 为键，含 owner/token/expiry/heartbeat/revision。Inbox 存储自身的 issue mutation 还使用持久化锁文件与 expected revision，在同一临界区完成 read/check/mutate/atomic replace。只有持评测租约 coordinator 可执行以下协议：

1. 规范化 operation/desired payload/expected Inbox revision/sorted relations，计算并 create-if-absent 写 `IssueCorrelationIntent`；随后 CAS iteration manifest 把 intent ref 加入 `pending_intents`，在任何外部 Inbox mutation 前建立恢复根。
2. `GET /api/inbox/issues/{id}`；不存在才 POST，存在则以 expected revision PATCH。超时或结果不确定时先 GET，不盲重试；同 ID+异创建 payload或 expected revision 冲突返回 409。
3. GET readback，核对外层状态、严格八行正文、Inbox revision 与完整 typed links；每个阶段 append observation。
4. 对 sorted relations 逐项计算 deterministic revision ID，先 `put_revision_if_absent`，再以 intent 声明的 expected relation revision CAS manifest。CAS 失败先重读：已指向同 revision 即幂等成功，仍在 expected previous 可重试同 CAS，指向其他 revision 则 conflicting；orphan 始终按相同 revision path 继续。
5. 所有 relation manifest 都指向本 intent 的 confirmed revision 后执行 latest symmetry gate，再 CAS iteration manifest：移除 pending intent、写 confirmed relation refs；create/update 保持 issue=`todo`，close 设置闭环状态。这个 iteration CAS 是唯一完成提交点。
6. close intent 在步骤 1 前必须先验证目标 case、当前 suite hash 全量 suite 和 core 无回归；Inbox PATCH/readback/revision/relation/iteration 提交仍复用同一协议。

任一步失败或最终 iteration CAS 未完成都保留 pending intent，使 iteration 保持 `closing_system_defects/blocked`；已经生成的 deterministic revision 允许成为可识别 orphan。`IssueCorrelationReconciler` 只能在重新取得同一 defect lease后运行：读取 intent、iteration pending ref、deterministic revision path、relation manifest 与当前 Inbox；若 Inbox 尚未应用则用原 payload/CAS 补做，若已应用则从 readback 继续同 revision/manifest，全部 relation confirmed 后重试最终 iteration CAS。payload、revision 或 links 冲突时保持 blocked 并追加 conflicting observation。创建、更新和关闭使用同一补偿与提交规则。

现有 Inbox 数据同时执行受控 shape 演进：

- `MVPInboxIssue` 新记录从 `revision=1, links=[]` 开始；活动 JSONL 中没有字段的旧记录读取为 `revision=0, links=[]`，只读不重写；
- `PATCH /api/inbox/issues/{id}` 必须带 `expected_revision`；storage 在同一进程锁和跨进程租约内读取当前行、把缺字段正规化为 revision 0、比较 expected revision、合并受允许 updates/links、revision +1、原子 replace，再读回；
- legacy 行第一次以 expected revision 0 成功 CAS 后才原子持久化 revision 1 与 links；错误 revision 返回 409 且不写文件；
- 这是唯一 Inbox 主数据的 schema/data evolution，用于所有调用者，不是旧评测 API、旧五维结果或旧结果文件的兼容读取。

`IssueCorrelationSymmetryGate` 对每个冻结 subject 执行：subject ID/content hash 可解析原冻结对象；relation manifest 指向最新 confirmed revision；Inbox GET 的 status/revision/content hash/typed links 与该 revision 完全相同；iteration manifest 已清除对应 pending intent并引用同一 confirmed revision。只有四方对称才算创建/更新/关闭完成并允许多模型准入；历史 revision 不要求等于最新 issue 状态，但始终可审计。

`ModelComparisonAdmission` 保存冻结的 code/suite/fixture/case set/per-case budgets/capability catalog/auth/decode/environment hashes，以及每个候选的 requested ID、probe、actual provider/model、fallback、replay、usage/cost/error。仅 `ready_for_comparison`、所有系统缺陷已读回为 processed、全部 `IssueCorrelationSymmetryGate` 基于最新 confirmed revision 通过、所有 benchmark/verifier defect 已按当前 suite hash 闭环且核心硬门禁仍满足时准入。缺失/污染标 `incomparable`，与 capability failure 分开且排除排名。首批候选建议 DeepSeek V4 Pro、一个 GPT-5.6、一个当前 Claude 目录模型；实际集合只由 `src/taichu/infrastructure/llm/catalog.py` 发现后逐项 probe 决定。

比较报告逐模型展示可比通过率的明确分子/分母、尝试次数、能力步骤数、Token、费用和错误状态，同时列出被排除的不可比运行及理由；不可比运行不进入排名、收益结论或可比通过率，但其原始工件仍保留。

## 8. 固定套件合同与启动前校验

### 8.1 套件文件与解析边界

固定套件由 `suite.schema.json` 和 `suite.json` 两个仓库内静态文件组成。`suite.schema.json` 只负责 JSON 结构和基础枚举约束；`SuiteLoader` 解析为类型模型后，`SuitePreflightValidator` 再执行需要目录状态或跨对象关系的语义校验。运行器只接收校验成功的 `ResolvedSuite`，不得在案例开始后补全合同。

`suite.json` 顶层必须显式包含：

| 字段 | 类型 | 约束 |
|---|---|---|
| `suite_id`、`name`、`purpose` | 字符串 | 稳定标识；用户可见名称和用途为中文 |
| `source` | 对象 | 仓库相对来源路径和来源种类 |
| `fixture_snapshot_id` | 字符串 | 必须等于夹具规范化快照身份 |
| `capability_coverage` | 映射 | 每项已设计能力、约束或禁止行为对应至少一个案例 |
| `failure_priority` | 枚举数组 | 覆盖失败枚举且无重复的全序 |
| `suite_gates` | 对象 | 案例硬门禁、套件硬门禁和显式阈值身份 |
| `stability_profiles` | 对象 | 实验使用的显式阈值配置；不得使用代码默认值 |
| `cases` | 数组 | 非空、稳定排序的完整案例合同 |

每个案例必须显式包含：

```json
{
  "case_id": "direct_answer_current_request",
  "category": "context_boundary",
  "tags": ["当前请求", "五层记忆"],
  "applicable_tracks": ["synthetic", "live_provider"],
  "user_request": "仓库内固定的用户请求原文",
  "fixture_snapshot_id": "fixture_<64hex>",
  "capabilities": {
    "required": [],
    "allowed": ["已注册能力标识"],
    "forbidden": ["已注册能力标识"]
  },
  "required_invocations": [],
  "authorization": {
    "capability": "明确授权边界",
    "write": "明确授权边界",
    "expected_security_outcome": "allow"
  },
  "budgets": {
    "nodes": 0,
    "replans": 0,
    "capability_calls": 0,
    "model_calls": 0,
    "tokens": 0,
    "runtime_ms": 0
  },
  "expected_artifacts": [],
  "verifier_ids": ["已注册校验器标识"],
  "allowed_stop_reasons": ["真实 Runtime 停止原因"],
  "human_responses": [],
  "scripted_steps": [],
  "content_hash": "case_<64hex>"
}
```

以上数值只表示结构，不是建议阈值。正式 `suite.json` 必须填写经产品验收的正数或显式允许为零的值，并将全部阈值纳入内容哈希；设计和运行器都不得补造隐藏默认值。

### 8.2 规范化与内容身份

规范化算法固定为：

1. 以 UTF-8 读取并拒绝重复 JSON key。
2. 将模型序列化为字段名排序、紧凑分隔符、禁止 NaN/Infinity 的 JSON。
3. 保留数组业务顺序；只对模型声明为集合语义的能力、标签和失败类别先去重排序。
4. 不把文件路径、修改时间、捕获时间和当前 Git 状态加入套件内容。
5. 对规范化 UTF-8 字节计算 64 位小写 SHA-256；按对象种类形成 `suite_<64hex>`、`case_<64hex>`、`fixture_<64hex>` 或 `evidence_<64hex>`，文件条目自己的 `sha256` 只保存原始 64 位 digest。

案例 `contract_hash` 覆盖用户请求原文、适用轨道、能力集合、required invocations、授权边界、有序人工回答、六项预算、产物定义、校验器、停止原因、全局脚本步骤和对应 fixture identity。套件 `content_hash` 覆盖 capability catalog hash、规范化后的全部案例、29 项覆盖清单、失败优先级、门禁与阈值配置。任何运行都把解析后的合同副本固化到自己的 `contract/suite.json`，运行期间不再读取活动套件文件。

### 8.3 一次性预检与问题模型

预检在创建任何案例副本、数据库或 Runtime 前完成，并一次收集全部问题：

- JSON Schema、类型模型和枚举错误；
- 空标识、重复 suite/case/artifact 标识；
- fixture snapshot 不存在、哈希不符或内容清单不完整；
- `required` 不是 `allowed` 子集、`allowed/required` 与 `forbidden` 相交或引用未知注册能力；
- 生产发现不是恰好 17 Tool + 12 Subagent、catalog hash 漂移、Subagent allowed-tools 依赖缺失或类型/ID 重复；
- `required_invocations` 缺 type/name/min/max/expected_outcome/parent-or-order，主覆盖缺失、重复、类型错配或引用不适用轨道；
- 缺少六项预算、预算非法或阈值 profile 缺失；
- 未知校验器、校验器输入类型与预期产物类型不匹配；
- 必需产物定义不完整、同一产物同时被声明为必需和禁止；
- 权限案例未声明预期允许/拒绝结果；
- 脚本步骤与案例 `content_hash` 不匹配；
- 全局 step sequence/ID 不连续、human response 无序、matcher 引用非法路径或未覆盖预期交互；
- `failure_priority` 缺项、重复或包含未知失败类别；
- 29 项能力覆盖清单缺失、引用不存在案例或与 required invocation 主映射不一致；
- 非唯一小说语义字段，例如 `project_id`、小说选择或作者活动工作区路径。

`PreflightIssue` 包含 `code`、`json_pointer`、`case_id`、中文 `message` 和可选 `related_ids`。任一问题存在时，提交返回 `benchmark_invalid` 并不创建运行记录；结构化请求日志只记录问题 code/位置和 request ID，API 与页面完整展示问题列表。

### 8.4 能力与校验器目录快照

预检从生产 scanner/manifest validator/registry 生成 `CapabilityCatalogSnapshot`，而不是读取 suite 自己声称的目录；同时通过 `VerifierRegistry` 读取静态校验器。运行开始后将两者的最小目录快照和哈希固化到套件工件。执行期间如生产目录与固化哈希不一致，尚未开始的案例不再启动，运行以 `benchmark_invalid` 结束，而不是悄悄换用新目录。

`VerifierRegistry` 由代码显式注册类实例；套件只保存 verifier ID 和类型化参数，不保存模块路径、Python 表达式、命令或脚本。注册时同时检查 verifier ID 唯一、输入产物集合非空、结果类型固定以及 `read_only=True`。

## 9. 密封夹具与真实 Runtime 执行

### 9.1 密封源和案例副本

密封源位于 `tests/fixtures/evaluations/general_writing_agent_benchmark/fixtures/core_novel/`，包含：

- Markdown 正文与正文 manifest；
- 仅含 `lifecycle=confirmed` 的知识卡 JSON 导入快照；
- 初始对话原始 user/assistant 展示消息；
- 初始通用 Agent 运行记忆；
- 外部资料 query index 与只读 document JSON；每个 source ref 可解析到 fixture manifest；
- 各分区内容哈希和共同 `fixture_snapshot_id`。

密封源是只读输入，不直接成为任何 Runtime 的 `project_assets_root`。每次案例尝试创建：

```text
project_assets/derived/general_agent_benchmarks/workspaces/<workspace_id>/
  source/...
  derived/...
  fixture-copy-manifest.json
```

`workspace_id` 为随机 UUID，不含作者路径。复制完成后先逐文件重新计算清单和共同哈希，再启动 Runtime。MongoDB 数据库使用 `taichu_eval_<32位小写十六进制>`，由 `MongoKnowledgeRepository` 以显式 client/database/collection 创建并初始化 validator/index；只导入快照中的 confirmed 卡片。每个案例拥有独立 conversation、thread、run、attempt 和 Runtime 对象。

### 9.2 评测专用 Runtime 工厂

新增公开 `GeneralAgentBenchmarkRuntimeFactory`，在基础设施层按生产装配方式显式组合：

- 真实能力扫描、协议校验与应用层注册表；先完整注册 17 Tool，再注册依赖它们的 12 Subagent；
- 真实 General Agent Runtime、计划器、节点执行器和授权边界；
- 现有对话、运行记忆、运行记录、检查点、调用、上下文快照、副作用和模型调用仓储；
- 指向案例副本的 `ProjectAssetStorageBackend`；
- 指向隔离数据库的知识仓储；
- 由 case fixture manifest 构造的 `FixtureExternalResearchBackend` 与真实 `ExternalResearchService`；
- 轨道指定的模型 gateway。

工厂不得调用 `create_app()`，避免把生产 embedding、Qdrant、恢复 watchdog 和活动工作区依赖带入测试隔离域；也不得从测试模块导入 fake。注册完成后按 case exposure/policy 限制本案可见能力，`required_invocations` 仅供验证，不能拿来裁剪物理注册。`synthetic` 轨道使用生产评测代码中的 `StrictScriptedDriver` 模型 adapter 与能力观察 wrapper，`live_provider` 轨道使用现有真实 gateway adapter。两条轨道经过同一真实 Runtime、能力注册表、授权校验、证据读取和硬门禁，差异仅是声明的模型 gateway 与相应 provider metadata。

strict driver 按案例合同哈希消费单一全局有序流；Runtime 停止后 runner 无条件调用 `finalize()`。它只为模型提供确定性 response，Tool/Subagent 始终执行真实 handler；human/task 只观察真实 HITL/任务事件。真实 provider 不支持的 seed、`top_p` 或模型版本必须记录为 `availability=not_applicable|missing`，不得声称固定。

两条轨道均禁止在评测 Runtime 注入 `DuckDuckGoExternalResearchBackend`。case 6 通过 fixture backend 的稳定 query index/search result/document content 驱动真实 `ExternalResearchService → search_external_sources/read_external_source`；因此 Tool、授权、父子调用与 source provenance 全部真实，而外部内容无网络和漂移。`live_provider` 只表示 LLM gateway 为真实 provider，不能解释为外部资料联网。

### 9.3 活动事实安全控制面

评测执行面从未获得作者活动工作区路径、活动 Mongo database/collection 或生产 repository。`FixtureIsolationController` 在评测外的受信控制面只做以下只读检查：

- 运行前后计算作者活动 Markdown 的路径、大小和内容哈希集合；
- 运行前后查询作者活动 Mongo 中 `lifecycle=confirmed` 知识卡并计算规范化内容哈希；
- 运行前后复核密封源清单；
- 在并行时根据 workspace ledger 复核其他案例副本的所有权和内容身份。

活动事实检查仅比较哈希和集合计数，不把活动正文或知识内容复制进评测工件。若活动数据本身在评测期间由外部作者正常改动，控制面通过文件/数据库 ownership ledger 与评测进程写集合先判断评测是否可能触达；无法排除评测触达时按 `fixture_isolation_failed` 处理，不以时间邻近猜测。设计的核心不变量是“评测凭据和路径没有写入活动事实的能力”，哈希复核是额外证明，不是唯一防线。

### 9.4 并行、取消、崩溃与清理

- runner 采用配置化有界并发，每个 worker 只持有一个案例上下文；
- workspace ledger 记录 workspace、数据库、run/attempt、owner lease、创建状态和清理状态；
- 单案例失败在运行级不变量仍成立时只终结该案例，并继续其他案例；
- 任一源快照、活动事实、跨案例边界或内容身份无法证明时设置运行级 stop flag，停止启动新案例；
- 取消只停止新案例和向可取消执行传递 cancel token，已完成工件保持不变；
- 每个案例在 `finally` 中依次关闭 Runtime、释放仓储连接、严格校验数据库前缀后 drop 隔离数据库、严格校验路径位于 workspace 根后删除副本；
- 服务启动 janitor 只清理 ledger 中 lease 过期、路径和数据库均满足严格命名约束的孤儿；对应 attempt 标记 `unfinished`；
- 不复用崩溃或取消的案例副本。仅当 suite run 为 unfinished 并创建新的恢复 run 时，才为未完成案例创建新 attempt、新 workspace 和新数据库；已完成案例保持不可变，cancelled run 不可恢复。

清理失败不覆盖案例原始结果，而是追加基础设施失败并使证据完整门禁失败。任何不符合前缀、路径归属或 ledger 身份的目标一律拒绝删除并报警。

## 10. 确定性校验、硬门禁与指标

### 10.1 校验执行顺序

每个案例按以下确定顺序收束：

1. 冻结 Runtime 终态引用并读取证据包。
2. 复核 fixture、活动事实和跨案例隔离。
3. 解析五类类型化预期产物。
4. 按 suite 中 verifier ID 顺序运行注册式只读校验器。
5. 计算六项预算。
6. 判断停止原因、权限安全、证据完整。
7. 计算六个硬门禁和案例结论。
8. 生成完整失败类别集合，再按 suite 全序选择主要失败类别。
9. 规范化并持久化 CaseResultRow 与 evidence bundle。

每个 `VerifierResult` 保存校验器身份/实现哈希、声明范围、期望摘要、实际摘要、直接证据 refs、`passed|failed|invalid|not_applicable` 和中文解释。非确定性条件单独进入 `advisory_results`，永远不参与或覆盖硬门禁。

### 10.2 类型化产物身份

- 最终回答：由 conversation/run/assistant message ID 与内容哈希定位，只保留最小展示内容。
- 来源引用：由 source ID、fixture snapshot ID、locator 和 excerpt hash 定位，必须可解析到密封副本。
- 能力工件：由 artifact ID、run/node/call ID、capability ID 与内容哈希定位。
- 写入候选：由 candidate ID、来源 attempt、目标种类、lifecycle=`draft` 和 payload hash 定位；评测不提交作者确认写入。
- 人工介入：由 interrupt/checkpoint ID、类型、触发边界、pending 状态和响应 schema identity 定位。

案例合同对每种产物声明 `required | forbidden | not_applicable`。缺失、类型错误、身份链冲突或 forbidden 产物出现分别进入产物门禁与安全门禁；校验器不得修补或生成产物。

### 10.3 六项硬门禁与最终结论

六项门禁是 `budget`、`verifier`、`artifact`、`stop_reason`、`security`、`evidence`。判定矩阵固定：

| 情况 | 案例结论 |
|---|---|
| 六项均通过 | `passed` |
| 行为证据完整，任一行为硬门禁明确失败 | `failed` |
| benchmark/fixture/证据/基础设施使硬门禁无法可靠判断 | `invalid` |
| 进程终止或仍有未完成 attempt | `unfinished` |
| 操作者取消且未形成完整结论 | `cancelled` |

案例的 `invalid`、`unfinished`、`cancelled` 不进入通过率分子；分母同时公开 `eligible_count` 和 `all_case_count`，不得只展示有利口径。未收到运行取消时，runner 收束案例后进入 `finalizing`：完整工件可提交时，根据显式 suite gate 得到 passed/failed/invalid 并以 `completed` 保存；完整工件不可提交时以 `unfinished + conclusion=null` 保存。收到取消并安全收束时以 `cancelled + conclusion=null` 保存。不存在加权分数、平均分或“多数通过即可”的隐式规则。

### 10.4 六类独立指标模块

指标模块分别生成独立 artifact，不共享一个不可拆解总分：

| 模块 | 指标定义 |
|---|---|
| `harness_metrics` | 案例结论计数；每类硬门禁通过/失败/不适用计数；主要失败类别计数；全部失败类别命中计数 |
| `context_metrics` | prompt 字节/token 可用值、上下文快照统计、压缩前后规模、当前请求原文哈希保持的分子/分母 |
| `memory_metrics` | 运行记忆读取次数、重复读取次数、额外能力调用数；正确使用或正确拒绝记忆的适用案例分子/分母 |
| `security_metrics` | 安全事件和错误码；预期允许/拒绝分别的符合分子/分母；违规总数 |
| `recovery_metrics` | 适用恢复案例中达到合同预期恢复结果的分子/分母；缺失分子、分母、适用集或成功条件时整个指标 invalid |
| `provider_metrics` | 按 provider/model 分区的案例结论、尝试数、能力步骤、token、费用及每项 availability |

恢复模块只评估本套件中的恢复机制案例，页面和 artifact 使用“机制实验恢复结果”；现有独立恢复可靠性基准只作为相邻链接展示，不并入该模块或套件通过率。每个模块保存输入 case IDs、公式版本、原始计数引用和结果；单模块缺失不能被其他模块代替。

## 11. 运行、恢复与工件存储

### 11.1 运行状态机

```mermaid
stateDiagram-v2
    [*] --> queued: 预检与幂等成功
    queued --> cancelled: 启动前取消
    queued --> running
    running --> cancelling: 收到取消
    running --> finalizing: 调度结束或运行级无效信号
    running --> unfinished: lease 过期或进程中断
    cancelling --> cancelled: 已收束在途案例
    cancelling --> unfinished: 无法安全收束
    finalizing --> completed: 终态工件原子提交
    finalizing --> unfinished: 无法完整提交工件
    cancelled --> [*]
    unfinished --> [*]
    completed --> [*]
```

预检失败发生在状态机之外并返回 422，不创建 run。lifecycle 只允许图中七个值；`completed` 必须携带 `passed|failed|invalid|not_evaluated`，其余 lifecycle 的 conclusion 必须为 null。运行级安全或证据失效不再是 lifecycle：能原子提交完整无效工件时走 `finalizing → completed + invalid`，不能完整提交时走 `finalizing → unfinished + null`。completed、cancelled、unfinished 都保持原记录不可改。

### 11.2 幂等、并发和恢复规则

提交请求要求 `Idempotency-Key`。仓储保存 key、调用者 scope、规范化提交 hash 和 run ID：

- 同 key、同提交 hash 且记录存在：返回同一 run；
- 同 key、不同提交 hash：`409 idempotency_conflict`；
- 不同 key 的相同配置：创建可比较的独立运行；
- 同一浏览器重复点击由前端锁定，后端幂等是最终保证。

runner 通过 revision CAS 更新进度；每个 case row 只引用不可变 attempt artifact。服务重启时，过期 lease 的 `running/cancelling/finalizing` 运行转为 `unfinished + conclusion=null`，展示已完成行、缺失行和恢复动作。只有 lifecycle=unfinished 具备安全恢复资格；`POST resume` 保持原 run 不变，创建带 `resumed_from_run_id` 的新 queued run，引用原运行可信的完成案例工件，只为其余案例创建新 attempt、workspace 和数据库。cancelled 和 completed 一律返回生命周期冲突，不可恢复；任何状态都不在旧 workspace 中从节点中途续跑。

### 11.3 工件目录和提交协议

```text
project_assets/derived/general_agent_benchmarks/
  runs/<run_id>/
    manifest.json
    contract/suite.json
    contract/fixture-manifest.json
    cases/<case_id>/attempts/<attempt_id>.json
    correlations/<exchange_id>.json
    bundles/<bundle_id>.json
    metrics/<metric_kind>.json
    artifact.json
  experiments/<experiment_id>/
    manifest.json
    artifact.json
  iterations/<iteration_id>/
    manifest.json
    first-live-artifact.json
    failures/<failure_id>.json
  issue-correlations/
    intents/<intent_id>.json
    relations/<relation_id>/
      manifest.json
      revisions/<revision_id>.json
    reconciliation-observations/<observation_id>.json
    indexes/by-subject.jsonl
    indexes/by-issue.jsonl
  comparisons/<comparison_id>/
    admission.json
    artifact.json
  closure-leases/<suite_hash>/<defect_fingerprint>.json
  indexes/runs.jsonl
  indexes/experiments.jsonl
  idempotency/<scope_hash>/<key_hash>.json
  workspaces/<workspace_id>/...
```

`runs`、`experiments`、`iterations`、`issue-correlations`、`comparisons`、`indexes`、`idempotency` 属于可审计运行资料；`closure-leases` 是可恢复协调状态；`workspaces` 只属于临时执行。所有目录由代码按需创建，不使用 `.gitkeep`。JSON 先写同目录临时文件、flush/fsync、计算内容哈希，再原子 replace；终态 artifact 仅在所有引用文件落盘且哈希复核成功后提交。索引可从 manifest 或不可变 revision 重建，不是事实源。

`runs/<run_id>/correlations/<exchange_id>.json` 是评测隔离观察器提交的不可变相关性记录；它不进入 Runtime 审计仓储。`iterations/<iteration_id>/manifest.json` 仅用 revision CAS 保存闭环 lifecycle、pending intent refs、confirmed relation refs、comparison refs/latest；首轮 artifact、run terminal artifact、suite artifact 与 failure 文件只携带创建时形成的 `CorrelationSubjectRef`，永不回填 issue ID 或状态。

intent/revision 路径完全由第 7.13 节公式决定，使用 create-if-absent；revision snapshot 先写、relation manifest 后 CAS，故 manifest 未引用的 revision 是可由 intent/revision hash 识别的 orphan，不是第二条业务修订。reconciliation observations 只追加；全部 relation manifest confirmed 且 symmetry 通过后，coordinator 才以 expected revision CAS iteration manifest 清除 pending intent并推进状态。任一步失败仍可从 intent、deterministic revision path、relation manifest 和 observation 恢复。两个索引均可重建。终态 artifact、首轮工件和 failure 文件不可原地覆盖；重跑产生新 run/iteration ID。

本轮不引入自动 TTL 或删除 API，因为需求未给出保留策略。页面和 API 必须分页，证据正文最小化；记录每个 bundle/artifact 的字节数，为未来明确的归档或保留策略提供依据。评测工件永远标记为运行审计资料，不进入 Markdown 正文源、Mongo confirmed 知识或知识检索上下文。

### 11.4 只读证据包

`RuntimeEvidenceReader` 使用精确关联链：

```text
conversation_id
  → run_id / thread_id
  → plan_revision / node_id
  → attempt_id / effect_id
  → call_id / parent_call_id / context_snapshot_id
```

读取器先通过八个窄 `EvidenceSource` facade 按案例持有的精确 ID 读取，再校验反向引用、owner、内容哈希和父子关系。找不到、重复、冲突、损坏分别标记，不使用文件 mtime、最新目录或时间窗口回填。读取器实例只持有 `RuntimeEvidenceSources`；集成测试同时证明其构造依赖没有 save/update/delete/repair/append、完整可写仓储未进入对象图，并用读取前后快照证明 Runtime 仓储 revision 和内容哈希不变。

证据包只保存运行状态/节点引用、能力调用树摘要、上下文 ID/哈希/统计、检查点完整性、attempt/effect 摘要、模型调用/token/费用 availability 和直接 artifact refs。完整 prompt、上下文正文、节点内部状态和调用正文仍留在既有 Runtime 证据域；bundle 通过 `bundle_hash` 证明自身内容。

## 12. 应用服务与 API 契约

### 12.1 应用服务

- `BenchmarkCatalogService`：列出和解析固定套件、覆盖摘要、provider 能力状态。
- `BenchmarkSubmissionService`：预检、幂等 claim、固化合同并入队。
- `BenchmarkRunner`：执行、收束、门禁、指标和终态提交。
- `BenchmarkQueryService`：稳定分页查询运行、案例、证据、指标和下载聚合包。
- `BenchmarkLifecycleService`：取消、未完成恢复和 lease 审计。
- `ExperimentService`：实验预检、arm 调度、可比性、稳定性和聚合。
- `FirstLiveIterationService`：执行 synthetic→DeepSeek→分类→关闭的强顺序，冻结首轮工件。
- `IssueClosureCoordinator`：持租约先提交关联 intent，再经 `InboxIssueClient` 执行 GET/create/CAS PATCH/readback，随后按确定性路径写 revision snapshot、CAS relation manifest，并以 iteration manifest CAS 作为唯一完成提交点；任何未确认步骤都不宣告闭环。
- `IssueCorrelationReconciler`：在重新取得同一缺陷租约后，以 pending intent 和 Inbox 当前读回补偿创建、更新或关闭，冲突时保持 blocked。
- `IssueCorrelationQueryService`：由冻结 subject ID 反向解析最新 confirmed revision，并执行 relation 与 Inbox 读回对称校验。
- `ModelComparisonService`：冻结比较条件、逐模型 probe、准入和不可比原因。

路由只做 HTTP 解析和响应映射，不直接访问文件、Mongo 或 Runtime 仓储。runner 通过应用层 Protocol 使用基础设施实现，保持测试可替换。

### 12.2 新 API

统一前缀为 `/api/general-agent-benchmarks`：

| 方法与路径 | 用途 |
|---|---|
| `GET /suites` | 固定套件摘要与覆盖 |
| `GET /suites/{suite_id}` | 解析后的套件合同和预检状态 |
| `GET /providers` | provider/model 配置能力与 availability，不返回凭据 |
| `POST /runs` | 创建 synthetic 或 live provider 运行 |
| `GET /runs` | 按 track/lifecycle/conclusion/suite/provider 做 `page/page_size` 分页 |
| `GET /runs/{run_id}` | revision、运行 lifecycle/进度及 overall/memory/mechanism conclusion 摘要 |
| `POST /runs/{run_id}/cancel` | 请求取消 |
| `POST /runs/{run_id}/resume` | 仅从 lifecycle=unfinished 运行创建新的 queued 恢复运行 |
| `GET /runs/{run_id}/cases` | 稳定排序的案例行分页 |
| `GET /runs/{run_id}/cases/{case_id}` | 条件、失败和工件详情 |
| `GET /runs/{run_id}/cases/{case_id}/evidence` | 最小证据包 |
| `GET /runs/{run_id}/artifact` | 可独立复核聚合包 |
| `GET /runs/{run_id}/metrics/{metric_kind}` | 单机制指标 |
| `POST /experiments` | 创建分机制实验 |
| `GET /experiments` | 实验分页 |
| `GET /experiments/{experiment_id}` | arm、可比性、绝对结论和变化 |
| `POST /experiments/{experiment_id}/cancel` | 取消未启动 arm/run |
| `POST /iterations` | 在 synthetic/机制门禁满足后创建 DeepSeek 首轮 |
| `GET /iterations` | 首轮闭环分页 |
| `GET /iterations/{iteration_id}` | 强顺序状态、冻结工件、失败分类和按 subject 反向解析的最新关联摘要 |
| `GET /iterations/{iteration_id}/issue-correlations` | subject、relation manifest、最新 revision、pending intents、Inbox 读回、对称状态与 problems |
| `GET /iterations/{iteration_id}/issue-correlation-observations` | 按 intent/relation 过滤的 append-only observation 页 |
| `POST /iterations/{iteration_id}/reconcile-issues` | 持同一缺陷租约补偿 pending create/update/close intent |
| `POST /iterations/{iteration_id}/recheck` | 对系统缺陷运行目标 case + 当前 suite 全量 + core 无回归验证 |
| `POST /iterations/{iteration_id}/close-issues` | 为已满足证据的系统问题提交 close intent，CAS 更新并读回确认 |
| `POST /comparisons` | 仅在 iteration ready 后创建多模型比较 |
| `GET /comparisons` | 按 `iteration_id` 等条件做页码分页，用于 URL 恢复和 iteration 历史 |
| `GET /comparisons/{comparison_id}` | admission、逐模型实际身份、不可比原因和结果 |

`POST /runs` 请求字段为 `suite_id`、`suite_content_hash`、`track`、可选 `provider_id/model_id`、显式 decode settings 和可选 case IDs；`synthetic` 禁止 provider 字段，`live_provider` 必须引用 `/providers` 返回的稳定标识。live provider 未配置或凭据不可用时仍创建可审计的 `202` blocked 运行，不返回合成结果。

`POST /experiments` 请求字段与 `ExperimentSpec` 一一对应。服务端重新解析并比较 control/treatment，不信任客户端的 comparability 结论。

Inbox 继续使用唯一 `/api/inbox/issues` 资源，并新增 `GET /api/inbox/issues/{item_id}`。typed link 固定为 `namespace/relation_id/subject_id/relation_kind/subject_content_sha256`；POST 对同一 ID 与同一 canonical payload 幂等，对同一 ID 的不同创建 payload 返回 409；`PATCH` body 固定为 `{expected_revision, updates}`，后续内容、状态与 links 变化都经同一 CAS。旧行 GET/list 响应正规化为 revision 0/空 links，首次 CAS 成功才持久化新 shape。评测 API 不代理、不复制也不另建问题资源。

### 12.3 响应与错误

运行或实验创建成功返回 `202` 和 `{run_id|experiment_id,lifecycle,location,idempotent_replay}`；issue mutation/reconciliation 命令返回 `202` 和 `{intent_id,correlation_state: pending|confirmed|conflicting,location}`，只有 relation/Inbox/iteration 四方对称时才返回 `confirmed`。查询成功返回 `200`。

run detail 必须返回 `revision`、`lifecycle`、`conclusion` 和 `conclusion_summary={overall,memory,mechanisms[]}`；overall 只映射 suite 结论，memory 与每个 mechanism 保留自身 `met|not_met|invalid|not_applicable`，不得从 overall 推导。iteration detail 返回 `revision`、manifest state、first-live artifact ref、pending/confirmed relation refs、`comparison_refs`、`latest_comparison_ref`；comparison detail 返回 admission、逐模型实际身份、excluded reasons、绝对结论、可比统计和 artifact ref。页面可用 iteration detail 或 `GET /comparisons?iteration_id=...` 恢复 comparison URL。

所有列表请求使用 `page>=1`、`page_size` 上限 100；响应统一为 `{items,page,page_size,total,total_pages,index_revision,total_snapshot}`。`index_revision` 是该筛选资源索引的单调整数 revision，`total_snapshot` 是该 revision 下的 total；排序键固定为 `created_at desc, id desc`。客户端把 `page/page_size` 直接传给 `CompactPagination`，发现 index revision 改变、当前页超过 total_pages 时显示中文漂移提示并夹紧或回到第 1 页。

错误 envelope：

```json
{
  "detail": {
    "error": "benchmark_invalid",
    "message": "固定基准无法启动",
    "request_id": "req_01H...",
    "details": {
      "issues": []
    }
  }
}
```

状态映射：

- `404`：suite/run/case/experiment 不存在；
- `409`：幂等冲突、非法生命周期转换、对 completed/cancelled 执行恢复、终态不可改、Inbox CAS 或关联 revision 冲突；
- `422`：请求类型/组合非法或套件预检失败；
- `500`：未分类基础设施错误；能完整提交无效工件时落为 completed+invalid，不能时落为 unfinished+null。

每个错误响应的 `detail.request_id` 必填并与结构化日志相同；`ApiError` 保留 HTTP status、`error` code、message、details 和 requestId。前端展示中文 message 和 request ID，同时用 code/status 做稳定分支；Inbox revision 409 必须刷新资源并显示“记录已被其他操作更新，已刷新，请确认后重试。”。API 不提供旧评测路径 alias、旧评测字段映射、旧评测结果读取或删除接口；Inbox revision 0 读取属于当前主数据演进，不是旧评测兼容。

### 12.4 Python 与 TypeScript 一一对应

以下顶层类型必须同名同枚举值，前端不得重新解释结论：

| Python API schema | TypeScript 类型 |
|---|---|
| `SuiteSummaryResponse` | `SuiteSummary` |
| `SuiteDetailResponse` | `SuiteDetail` |
| `RunSubmissionRequest/Response` | `RunSubmission/RunSubmissionResult` |
| `RunSummaryResponse` | `BenchmarkRunSummary` |
| `RunDetailResponse` | `BenchmarkRunDetail` |
| `ConclusionSummaryResponse` | `ConclusionSummary` |
| `PaginatedResponse[T]` | `PaginatedResult<T>` |
| `CaseResultResponse` | `BenchmarkCaseResult` |
| `GateResultResponse` | `GateResult` |
| `FailureDetailResponse` | `FailureDetail` |
| `EvidenceBundleResponse` | `EvidenceBundle` |
| `MetricArtifactResponse` | `MetricArtifact` 判别联合 |
| `ExperimentSubmissionRequest/Response` | `ExperimentSubmission/ExperimentSubmissionResult` |
| `ExperimentDetailResponse` | `ExperimentDetail` |
| `MechanismConclusionResponse` | `MechanismConclusion` |
| `FirstLiveIterationResponse` | `FirstLiveIteration` |
| `CorrelationSubjectRefResponse` | `CorrelationSubjectRef` |
| `IssueCorrelationIntentResponse` | `IssueCorrelationIntent` |
| `IssueCorrelationRevisionResponse` | `IssueCorrelationRevision` |
| `IssueCorrelationObservationResponse` | `IssueCorrelationObservation` |
| `IssueCorrelationStatusResponse` | `IssueCorrelationStatus` |
| `IssueCorrelationCommandResponse` | `IssueCorrelationCommandResult` |
| `ModelComparisonAdmissionResponse` | `ModelComparisonAdmission` |
| `ModelComparisonDetailResponse` | `ModelComparisonDetail` |

可选字段必须与 availability 配套；不得以 `0`、空字符串或空数组冒充不可用。

`RunSummaryResponse/BenchmarkRunSummary` 将 `lifecycle` 定义为七值联合，将 `conclusion` 定义为四值联合或 null，并在 Python 模型和 TypeScript 构造/视图测试中执行同一判别约束；前端不得把 invalid 当作 lifecycle，也不得为 queued/running/cancelling/finalizing/unfinished/cancelled 合成结论。

`IssueCorrelationStatusResponse` 必须一次返回 `subject`、relation manifest、latest revision、pending intents、Inbox readback、symmetry state/problems 和 observation page metadata；缺任一侧用 availability/problem 表达，不返回伪造空对象。run/iteration/detail 响应携带单调 `revision`，列表携带 `index_revision`，供客户端防止旧响应倒退。

## 13. 桌面评测工作台设计

### 13.1 页面入口与导航

保留 `/task-monitor/general-agent/evaluation`、任务入口卡片“通用写作智能体评测”和通用写作智能体监控导航关系。页面仍由薄 route 导入 Shell；不增加独立入口页、不改变 `/home` 导向、不加入小说选择或 `project_id`。真实验收固定使用 `http://localhost:3000/task-monitor/general-agent/evaluation` 和 `http://127.0.0.1:8000`。

### 13.2 组件树与职责

```text
web/src/app/task-monitor/general-agent/evaluation/page.tsx
└─ GeneralAgentEvaluationShell [general-agent-evaluation-shell.tsx]
   ├─ AppShell
   ├─ GeneralAgentMonitorNav
   ├─ BenchmarkCommandBar [suite-controls.tsx]
   │  ├─ SuiteSelect
   │  ├─ TrackSelect
   │  ├─ ProviderSelect
   │  ├─ RunAction / ExperimentAction
   │  └─ InlineConfirmationRegion
   ├─ BenchmarkSummaryStrip [suite-summary.tsx]
   ├─ EvaluationWorkspace
   │  ├─ RunAndExperimentRail [run-experiment-rail.tsx]
   │  │  ├─ CompactPagination
   │  │  └─ InlineLifecycleConfirmation
   │  ├─ CaseTable [case-table.tsx]
   │  │  ├─ Checkbox
   │  │  └─ CompactPagination
   │  └─ CaseDetailAside [case-detail.tsx]
   │     ├─ GateMatrix
   │     ├─ FailureExplanation
   │     └─ EvidenceDisclosure(details)
   ├─ MemoryConclusionPanel [memory-conclusion.tsx]
   ├─ FirstLiveClosurePanel [first-live-closure.tsx]
   ├─ ModelComparisonPanel [model-comparison.tsx]
   ├─ ExperimentComparisonPanel [experiment-panel.tsx]
   └─ MechanismMetricsPanel [mechanism-metrics.tsx]
```

`GeneralAgentEvaluationShell` 导出名保持不变，只编排查询状态、URL selection 和 mutation。展示转换与纯 request coordinator 放在 `general-agent-evaluation-view.ts`；资源请求只放在 `web/src/lib/api/general-agent-evaluation.ts` 并调用共享 `web/src/lib/api-client.ts`；共享类型放在 `web/src/lib/types/general-agent-evaluation.ts`。案例详情按需请求，不把全部证据灌入首屏。

### 13.3 组件复用与准入

复用已核实存在的应用壳、监控导航、Button、Checkbox、`CompactPagination`、lucide-react 图标，并以原生 `select`、`aside`、`div`、`details` 和当前 feature 内组合完成筛选、详情、加载与确认。需要新增 shadcn 组件时必须另走组件准入；本设计不需要新增组件库能力或依赖，也不复制平行按钮、分页或复选组件。

当前 `CompactPagination` 根节点自带顶部分隔线；评测页调用传入 `border-t-0`，由现有 `cn/twMerge` 移除本页内容分割线。不修改共享组件默认样式，也不复制分页组件。

`InlineConfirmationRegion` 与 `InlineLifecycleConfirmation` 都位于工作台原区域内，由 Shell 持有临时状态，使用现有 Button/Checkbox。进入确认态后焦点移到带 `aria-labelledby` 的 region；“返回修改”恢复触发按钮焦点，“确认提交/确认取消”只发送一次 mutation。详情使用 `aside` 表达互补区域，技术证据使用原生 `details/summary`，不引入新的共享覆盖层抽象。

### 13.4 前端 API 与状态

现有 `fetch` API client 与 React hooks 的 resource key 必须包含资源、suite hash、track、provider、筛选、`page/page_size` 和选中 ID；不假设或引入 React Query。mutation 以 idempotency key 发起；收到 idempotent replay 时导航到既有运行。

Shell 状态拆分为：

- 远端：suite catalog、provider availability、runs、selected run、overall/memory/mechanism conclusion summary、case page、selected case、iteration、latest issue correlation status/observations、comparison list/detail、experiment、metrics；
- URL：`run`、`experiment`、`comparison`、`iteration`、`case`、`track`、`lifecycle`、`conclusion`、`run_page`、`case_page`、`experiment_page`、`comparison_page`、`page_size`；
- 本地临时：case selection、展开区、提交确认表单；
- mutation：submit/cancel/resume/retry/recheck/close-issues/reconcile-issues/create-comparison。

`RequestCoordinator` 为每个 resource key 保存单调 `generation`、当前 AbortController 和 `lastAppliedRevision`。发起请求时 generation +1 并 abort 同 resource 的前请求；响应只有在 generation 仍等于最新，且 detail `revision` 或 list `index_revision` 不小于 lastAppliedRevision 时才可进入 reducer，否则静默丢弃。query/resource key 只隔离身份，不能替代上述新鲜度门禁。运行中按可见页面节制轮询；进入终态自动停止。页面不读取旧结果文件或自行合并 synthetic/live。

### 13.5 桌面布局

采用高密度午夜极光控制台：

- 顶部深色命令条：套件、轨道、provider、普通运行、分机制实验；
- 命令条下紧凑摘要带：内容身份、案例数、能力覆盖、硬门禁、进度和结论；
- 结论层级固定为整体能力 → 工作记忆专项 → 局部机制 → DeepSeek 首轮闭环 → 准入后的多模型比较；Token、费用和其他指标只作解释；
- 主区使用固定桌面三栏：左侧窄运行/实验列表，中部案例表，右侧详情；
- 实验模式在主区下方或同一详情区展示 control/treatment 并列比较；
- 机制指标用分区表和小型统计块，不用单一大分数或夸张图表；
- 原始 ID、hash、artifact、availability 和技术详情进入折叠区。

炭灰画布、深色导航、灰阶表面和白色胶囊主操作遵循 `DESIGN.md`；极光渐变只作为少量背景装饰线索，不承载任何交互或状态语义。当前行/tab 使用内凹灰阶背景、白字和必要的中性完整外轮廓。不制作移动端或窄屏重排。

### 13.6 完整页面状态

| 状态 | 页面行为 |
|---|---|
| 初次加载 | 保持应用壳；摘要、列表和表格以原生 `div role="status" aria-busy="true"`、弱对比占位块与 `motion-safe:animate-pulse` 表达加载 |
| 套件为空 | 小型中文空状态“暂无可用固定基准”，隐藏运行按钮 |
| 无运行/实验 | 小型中文空状态和“运行固定基准”主操作 |
| 局部请求失败 | 对应面板中文原因、request ID 和“重试”；其他面板继续可用 |
| 提交中 | 同一操作禁用，按钮显示“正在提交…” |
| queued/running | 中文 lifecycle、conclusion 留空、完成数/总数、当前案例和“取消运行” |
| finalizing | “正在汇总工件”，conclusion 留空且不再接受取消 |
| provider blocked | 展示受阻原因；运行收束后显示 completed + not_evaluated，不显示为 synthetic 或通过 |
| cancelling | 明确“正在取消”，conclusion 留空 |
| cancelled | 停止轮询，已完成案例和证据仍可打开，无结论和恢复操作 |
| unfinished | 停止轮询，conclusion 留空；展示持久化进度、缺失工件和“安全恢复” |
| completed | 停止轮询；展示 passed/failed/invalid/not_evaluated 之一和稳定 artifact hash |
| 结论摘要 | run detail 同时显示整体能力、工作记忆专项和各局部机制；专项不得被总体通过率覆盖 |
| DeepSeek 闭环未就绪 | 明确显示缺少的 synthetic/core/mechanism 前置，不开放多模型操作 |
| 系统问题待处理 | 由冻结 subject 反向显示唯一 issue、latest revision、pending/conflicting/confirmed 与 Inbox 读回；提供可恢复的“重新核对关联”，不把非系统类别写入 Inbox |
| 多模型不可比 | 显示实际 provider/model、缺失 probe/replay/usage 或污染字段，不进入排名 |

### 13.7 核心交互

普通运行：选择 suite → 查看覆盖/身份/门禁摘要 → 选择轨道/provider → 提交 → 跳转 run 详情。分机制实验：选择机制 → 填 control/treatment 与 repetition → 展示声明差异预览 → 在命令条下方内联确认区勾选确认 → 提交。无法比较的组合在服务端预检后显示逐项原因。

案例表支持复选、结论/类别/失败类别筛选和紧凑分页。点击一行打开右侧详情，依次展示六项门禁、required/observed invocation、期望/实际、直接证据、主要与全部失败类别、下一步复核范围、关联工件。技术详情默认收起，键盘和鼠标均可展开。

首轮闭环交互严格按状态开放：查看 synthetic/机制资格 → 启动 DeepSeek 首轮 → 查看冻结工件与失败分类 → 由 subject 查看 Inbox latest relation/readback/observations → 对 pending intent 重新核对 → 运行目标 case 与当前 suite 全量复核 → 提交关闭并等待 relation/Inbox/iteration symmetry gate → 创建多模型比较。iteration detail 展示 comparison refs/latest；带 `comparison` URL 重载时先 GET exact detail，缺失时再按 iteration 过滤列表。客户端只发命令，服务端再次校验前置和 suite hash；UI 不提供跳步、直接改关联或强制关闭。

取消必须先在当前运行行下方展开内联确认区，文案说明“停止启动新案例，已形成证据会保留”，并使用现有 Button 完成确认或返回。只有 unfinished 行显示恢复操作，说明会创建新的运行和全新案例尝试；cancelled/completed 不显示恢复操作，服务端冲突仍以中文提示。重复提交响应返回既有 run 时给出中文提示并导航，不出现第二条难以区分记录。

### 13.8 视觉和用户文案

所有内部枚举经集中映射为中文，例如：

- lifecycle `queued/running/cancelling/finalizing/completed/unfinished/cancelled` → “等待中/运行中/正在取消/正在汇总/已完成/未完成/已取消”；
- completed conclusion `passed/failed/invalid/not_evaluated` → “通过/失败/无效/未评测”；
- `missing_artifact/budget_exceeded/verifier_failed/failure_stop_reason` → “缺少预期产物/预算超限/校验器失败/异常停止”；
- `blocked/error/completed` provider → “受阻/调用错误/已完成”。

标记同时使用文字、图标和颜色；不得只靠红绿区分。界面称“通用写作智能体”，不直接把内部 `general_agent`、`suite_hash` 等作为主文案。

### 13.9 动效、可访问性与性能

仅使用现有 Tailwind transition 做 120–180ms 的 hover、展开和面板切换；尊重 `prefers-reduced-motion`，不新增动画库。表格、内联确认 region、`aside` 详情和 `details/summary` 折叠区具有可见 focus ring、正确 label/aria-expanded/aria-live；状态更新使用非打断式 live region。

首屏只加载套件摘要、最近运行和默认案例页；case evidence、artifact 和 metrics 按需加载。分页默认值由 API 明确提供，页面不一次读取全部案例。轮询对隐藏标签页降频，并在终态停止。

### 13.10 前端文件与验收

重写：

- `web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/suite-controls.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/suite-summary.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/run-experiment-rail.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/case-table.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/case-detail.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/memory-conclusion.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/first-live-closure.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/model-comparison.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/experiment-panel.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/mechanism-metrics.tsx`
- `web/src/components/agent-task-monitor/general-agent-benchmark/use-benchmark-workbench.ts`
- `web/src/lib/api/general-agent-evaluation.ts`
- `web/src/lib/types/general-agent-evaluation.ts`
- `web/src/lib/general-agent-evaluation-view.ts`
- `web/src/lib/api-client.ts`
- `web/tests/general-agent/evaluation-view.test.ts`
- 共享分页组件不修改；现有导航组件不修改。

现有 `npm run test:general-agent` 是 `tsc` + 纯 Node，无 DOM 环境。脚本实际执行的 `web/tests/general-agent/evaluation-view.test.ts` 自动覆盖：API error/request ID 解析、页码响应正规化、lifecycle/conclusion 判别、overall/memory/mechanism 展示派生、纯 reducer、generation + abort + lastAppliedRevision 对乱序响应的拒绝、idempotent replay、中文枚举，以及正规化 Inbox issue 的 revision 0/空 links、typed link shape、expected revision PATCH payload 和 409 中文分支。`web/tests/inbox/issue-format.test.ts` 维持既有八行解析职责，不作为本轮 revision/CAS 门禁。Node 测试不声明能验证焦点、ARIA、点击或 React mutation。

固定端口浏览器手验覆盖：原生加载区 `aria-busy`、初始/空/错误/request ID/重试、页码上一页/下一页/任意跳页、分页调用处 `className="border-t-0"` 且共享组件无 diff、实验与取消内联确认的焦点/复选框/按钮/单次 mutation、`aside/details` 键盘展开、快速切换时旧响应不倒退、七 lifecycle、synthetic/live、provider blocked/error、仅 unfinished 恢复、结论层级、六门禁、首轮关联 observations 与 comparison URL 恢复。执行 `npm run lint`、`npm run test:general-agent`、`npm run build`，再在 `localhost:3000`/`127.0.0.1:8000` 手验；不新增依赖或 package script。

### 13.11 现有 Inbox 页面联动

`MVPInboxIssue` 响应始终带 revision/typed links，页面不显示或编辑机器 links。`patchInboxIssue(item.id, item.revision, updates)` 发送 expected revision；成功后以 readback item 替换本地对象。若 `ApiError.status=409`，`InboxBoard` 立即重新读取当前 tab/issue，保留用户可理解的操作上下文并显示“记录已被其他操作更新，已刷新，请确认后重试。”，不得自动覆盖新状态。严格八行正文展示和软删除过滤保持不变。

## 14. 错误、可观测性、安全与容量

### 14.1 错误分层

- `BenchmarkDefinitionError`：静态合同、目录或快照错误，归 `benchmark_invalid`。
- `FixtureIsolationError`：复制、哈希、越界或清理安全错误，归 `fixture_isolation_failed`。
- `EvidenceIntegrityError`：证据缺失/损坏/冲突，归 `evidence_incomplete`。
- `RuntimeExecutionError`：真实 Runtime 或 gateway 执行异常，保存已形成证据。
- `LifecycleConflictError`：幂等或状态转换冲突，返回 409。
- `EvaluationCorrelationError`：评测观察数量、task owner/case run、轨道状态映射或某一 source locator 的源内复读冲突；提交 immutable invalid correlation record，不比较跨源 hash/status，也不改写 Runtime 证据。
- `IssueCorrelationConflictError`：Inbox CAS、typed links 或 relation manifest 与 pending intent 冲突，保留 intent/observation 并阻断闭环。
- `ArtifactCommitError`：原子提交失败，运行成为 `unfinished + conclusion=null`；业务 invalid 只有在完整无效工件提交成功后才表示为 `completed + invalid`。

错误对象保存稳定 code、中文安全消息、request/run/case/attempt ID、cause class 和直接证据 ref；不会把凭据、完整 prompt、正文或内部异常堆栈返回前端。

### 14.2 可观测性

结构化日志字段限定为 request/run/experiment/suite/case/attempt/track/provider 状态、评测 exchange/intent/relation ID、耗时、预算计数、artifact hash 和 error code。日志不记录用户请求全文、模型 prompt、小说正文、知识卡 payload、密钥或完整工具参数。指标至少包括队列深度、case duration、provider blocked/error、correlation invalid/pending/conflict、artifact bytes、janitor cleanup 和隔离失败警报。

每次状态转换写审计事件并带 previous/new revision；终态 artifact hash 与 API 响应一致。未知 provider 错误保留 adapter 原始稳定 code 的安全摘要，但归一状态为 `error`。

### 14.3 安全边界

- API 不接受文件路径、数据库名、模块路径、命令或任意 verifier 实现；
- suite 静态资源路径必须 resolve 后仍位于允许根；
- workspace 删除和 DB drop 使用双重前缀、ledger owner 与 resolved-path 校验；
- live provider 凭据只由现有配置读取，不进入请求、artifact 或 provider list；
- verifier 只读且无 Shell、子进程、任意动态导入和网络权限；
- 评测相关性 scope 只由隔离 Runtime factory 注入，正常活动 Runtime 不经过 observer wrapper；wrapper 先且仅先执行一次原底层调用，observer/scope/repository 故障不得改变其参数、返回、异常或写入次数；
- issue reconciliation 必须持匹配缺陷租约，typed link subject hash 与冻结对象逐字节复核，不能由客户端提供任意 subject 路径；
- Runtime 的真实 authorization 层仍是执行时最终授权源，评测合同不能扩权；
- 写入候选停留在隔离副本且 lifecycle 为 draft，不写活动 Markdown 或 confirmed 知识。

### 14.4 容量与保留

本轮保持“长期保留、无自动清理”的明确行为，因为不存在经确认的保留期限。为避免无界首屏和巨型聚合，所有列表分页、bundle 最小化、artifact 以 refs 聚合、索引可重建。若未来引入 TTL、归档、下载打包大小上限或远端对象存储，属于数据生命周期变化，必须重新验证第 2、7、9、11、12 组需求。

## 15. 破坏式替换与文档联动

### 15.1 切换顺序

1. 新建合同、suite/fixture、运行器、仓储、API 和前端类型，但旧路由不与新路由同时对外作为活跃契约。
2. 先用隔离 synthetic 套件通过结构、Runtime、工件和事实安全验收。
3. 将 `main.py`、`deps.py`、`router.py` 和模块 exports 原子切换到新体系。
4. 同次变更删除旧后端、旧 API、旧前端实现/测试、旧 fixture manifest 和旧活动结果。
5. 更新 README、现行 docs 和 `project_assets/readme.md`；`docs/历史/` 原样保留。
6. 全仓扫描旧路径、旧五维字段、旧状态、旧结果模式和旧 imports，确认活跃实现为零。

旧通用 Agent 评测不提供双写期、兼容 wrapper、字段转换器、迁移 reader、旧 endpoint alias 或 fallback。部署回滚只能回到完整代码版本；新体系不会把旧活动评测结果当作可恢复业务数据，清理后也不维护旧结果备份读取入口。第 7.13 节对现行 Inbox JSONL 的 revision 0/空 links 正规化是唯一 Inbox 主数据的 schema 演进，既不读取旧评测结果，也不恢复旧评测契约，不能被删除式切换误删。

### 15.2 精确删除与保留

删除：

- `src/taichu/application/evaluations/general_agent/`
- `src/taichu/application/contracts/general_agent_evaluation.py`
- `src/taichu/infrastructure/evaluations/general_agent_repository.py`
- `src/taichu/api/schemas/general_agent_evaluations.py`
- `src/taichu/api/routes/general_agent_evaluations.py`
- `tests/fixtures/evaluations/general_writing_assistant_core/manifest.json`
- `tests/integration/api/test_general_agent_evaluations_api.py`
- `project_assets/derived/agent_evaluations/general_agent/general_eval_*.json`
- 被新实现替代的旧 Shell、旧 API/类型/显示适配和旧前端测试内容。

保留：

- Runtime 的运行、调用、上下文快照、回放、检查点、副作用和恢复链路；
- 现有独立恢复可靠性基准；
- 知识抽取/知识召回等其他评测域及共享评测配置；
- `docs/历史/` 的历史快照和原结论；
- 当前唯一小说的活动 Markdown 与 Mongo confirmed 知识。

删除脚本或实现必须先做 import/引用扫描；若目标仍被相邻系统使用则失败并列出职责，不能扩大删除范围。`project_assets/` 职责变化与 `project_assets/readme.md` 在同次变更完成，仓库资料入口变化同步根 README。修改现行 `docs/` 前遵循 `docs/rule.md`。

### 15.3 启动联动

本设计需要修改 `src/taichu/main.py`，因此实施验收必须按项目规则验证根 `start.bat`。后端代码修改后等待热重载，并以 `http://127.0.0.1:8000` 真实新 API 确认加载；未加载则按固定端口约定重启 8000。前端只使用 `localhost:3000`，不以 3001/8001 规避端口问题。

## 16. 测试策略与验收门禁

### 16.1 后端单元测试

- canonical JSON、content hash、集合排序和原文不变；
- suite preflight 一次列出全部问题；
- capability catalog 17+12 快照、Subagent→Tool 注册依赖、29 项反向覆盖和目录 hash 漂移；
- `EvaluationCorrelationScope` 在单一 async task 内生成 exchange；各 observation 只按自己的 source locator/原生算法复读，evaluation/trace/replay request hash 互不要求相等；
- live returned/raised 与 synthetic returned/raised 四行状态矩阵，包括 gateway returned 后 JSON/schema 校验导致 trace failed 的合法组合、synthetic Runtime replay/usage 不适用和 fixed token/cost observation；
- 观察过多/过少、跨 task、case run 不匹配、非法状态映射、源内复读冲突与未完成 finalize 均形成 immutable invalid record；trace 与 gateway ID 允许不同，context snapshot 只按 trace run record 读取；
- observer/scope/correlation repository 在 before-report/after-delegate/finalize/persist 的故障注入不改变底层 gateway/append/writer 返回、原异常对象或写入次数；CaseExecutor finally 固化 cancel/missing-trace pending exchange；
- Token 预算遍历 available records：live 按唯一 usage locator/gateway call ID 读取，synthetic 按 fixed observation，重复 locator、null/missing usage 和不合法零值均 fail closed；
- 正常 Runtime factory 不装配观察器，原 `LLMRequest`、invocation context/trace、编排器、子 Agent runner、executor 和 gateway 的参数、字段、返回、异常及写入调用保持不变；
- `required_invocations` type/name/min/max/outcome/parent/偏序及 allowed 不计覆盖；
- strict driver 成功流和意外/乱序/不匹配/耗尽/剩余/规范化漂移稳定错误；
- 权限 outcome、ordered human responses、六预算、产物、verifier、failure priority 校验；
- 五类产物解析和身份链；
- verifier registry 类型匹配、只读与禁止命令文本；
- 六门禁矩阵、primary/all failure 选择和 suite 汇总；
- 六类独立指标的分子、分母、availability 和无总分；
- comparability、declared differences、stability 样本方差；
- mechanism hard gate、真实 switch resolver、qualified ablation 与指标不得放行；
- 四态记忆、三类边、current/repair 投影、source/dependency fingerprint、producer proof 和复用 anti-resurrection；
- DeepSeek iteration 强顺序、失败分类、suite hash 漂移重启、comparison admission；
- `CorrelationSubjectRef` 非递归内容哈希，只接受 run terminal/suite/first-live/failure 四类不可变工件；可变 manifest 被拒绝，冻结哈希在 issue 创建/更新/关闭前后不变；
- deterministic intent/revision ID、create-if-absent 同 hash 幂等/异 hash 冲突、append-only observation、revision orphan 识别、relation CAS 与最终 iteration CAS；
- defect fingerprint、issue ID、稳定 relation ID、typed link、协调租约、严格八行、latest 四方 symmetry gate 与关闭前证据；
- legacy Inbox issue 正规化为 revision 0/空 links、只读不重写、首次 expected revision 0 CAS 原子升级为 revision 1、错误 revision 不写；
- provider state/error adapter、不可用字段不推测；
- 七值 suite lifecycle、completed-only conclusion 判别约束、CAS、幂等、终态不可改、仅 unfinished 可恢复、页码/total_pages 和 index revision 稳定性。

### 16.2 隔离与 Runtime 集成测试

- 每案例 workspace/database/conversation/run 独立，前序历史和运行记忆不泄露；
- sealed source、活动 Markdown、活动 confirmed 知识和其他 workspace 前后哈希不变；
- 未授权 capability/write 在真实授权层被阻止且证据可见；
- strict driver 经真实 Runtime/真实 handler 产生调用、检查点、上下文和 effect，并在停止后 finalize；
- synthetic/live 的 external research 都走 fixture backend + 真实 service/tool，source refs 可解析且测试期间网络调用为零；
- live adapter 未配置为 blocked，错误保留尝试，绝不 fallback synthetic；
- 八类 Runtime evidence source facade 只暴露读取 callable，reader 构造对象图不含完整仓储或 save/update/delete/repair/append；`EvaluationCorrelationReader` 只读评测所有的 correlation repository；两者按 record 内精确定位符合并，断裂时不使用 mtime fallback，读取前后 Runtime 仓储 revision/hash 不变；
- live 模型交换验证 trace/replay/usage 与 run snapshot；synthetic 验证 driver step/trace/fixed usage且 Runtime replay/usage 不适用。故意制造观察多/少、跨 task、非法状态映射、run 不匹配和源内复读冲突时 record/evidence 为 invalid，不按 hash/状态相似、时间或名称修补；
- observer wrapper 对底层 gateway、trace append、replay writer、usage writer 的输入、输出、原异常对象和写入次数做逐项等价断言；observer/scope/repository 故障注入只使评测 invalid；取消或缺 trace 后 finally 无 pending 泄漏；并行 case exchange 不交叉，正常活动 Runtime 完全绕过 wrapper；
- 并行、取消、case failure continue、run safety stop；
- 崩溃 lease、unfinished+null、恢复创建新 queued run/new attempt、completed/cancelled 恢复 409、janitor 严格安全清理；
- 23 个 case 的 applicable track/实际 invocation/HITL/security/workspace 指纹；recovery case 的故障点、checkpoint、no-rerun 和分子分母；
- memory 四 case 对 node summary、正常/fallback digest、snapshot、reuse 的逐态穿透；
- Inbox 并发 create/patch、GET-by-ID、CAS、超时后查重、409 异内容、写后读回；legacy 无字段行先读为 revision 0/空 links，首次 CAS 升级且并发旧 revision 失败；
- 在 intent 已写但 iteration pending CAS 前、Inbox mutation 前后、readback 后、revision snapshot 已写但 relation manifest CAS 前、全部 relation confirmed 但 iteration final CAS 前等每个中断点重启 reconciler，断言 intent/revision 数量不增加且 observation 只追加；
- issue todo→processed 创建新 deterministic intent/revision；latest revision、Inbox readback 与 iteration confirmed refs 任一不对称时 comparison admission 必须阻断；冻结工件始终由 subject ID 反向解析且字节哈希不变；
- 原子工件提交中断不生成 completed artifact。

每个 Mongo 测试使用随机 `taichu_eval_<hex>` 数据库并在严格校验后清理；禁止连接或 drop 活动 database。文件测试使用临时根，不直接挂载密封源或作者工作区。

### 16.3 API 与前端测试

API 覆盖 suites/providers、创建/幂等/冲突、`page/page_size/total/total_pages/index_revision` 分页、run detail 三层结论、revision、取消、仅 unfinished 恢复、evidence、artifact、六 metrics、experiment、iteration comparison refs/latest、issue correlation status/observations/recheck/close/reconcile、按 iteration 查询 comparison 与 exact detail、provider blocked/error、completed+invalid、unfinished+null、request ID 和无旧评测路径。Inbox 覆盖 legacy list/GET-by-ID、幂等 create、expected revision CAS patch、typed links、409 与读回。契约测试断言 Python/TypeScript lifecycle/conclusion/mechanism/iteration/correlation intent+revision+observation+status/command result/comparison detail/分页判别联合、枚举与 availability 语义一致。

`npm run test:general-agent` 只让现有 `evaluation-view.test.ts` 在纯 Node 环境验证 reducer、API envelope/request ID 解析、页码正规化、URL selection、generation/AbortController/lastAppliedRevision coordinator，以及 Inbox revision/link/legacy 0/expected revision/409 纯数据契约；不声明 DOM 覆盖。`issue-format.test.ts` 只保留已有八行职责，不作为本轮唯一证据。真实 Inbox 409 刷新、评测页焦点/键盘/ARIA/单次 mutation、极光只装饰和 comparison URL 恢复均使用固定端口桌面浏览器手验。

### 16.4 清理和回归门禁

- `rg` 证明旧 API 路径、五维 score/dimension 合同、旧状态和 `general_eval_*.json` 活跃读取为零；
- 证明 shared Runtime 审计模型/协议/写入路径相关文件没有 diff，原身份与恢复基准及其他评测域测试仍通过；
- 证明仓库无 `.gitkeep`，无 SQLite/FTS 回归，无项目/小说选择字段；
- `uv run` 执行新后端测试与相关完整测试；
- `npm run lint`、`npm run test:general-agent`、`npm run build`；
- `start.bat` 固定端口启动/复用验证，真实 API 和桌面页面验收。

任何事实安全、隔离、旧契约残留、硬门禁绕过或 Runtime 相邻回归失败都阻止交付。

## 17. 需求追踪矩阵

| 需求范围 | 设计落点 | 主要验证 |
|---|---|---|
| 1.1—1.3 | 7.2、7.3、8.1、8.3 | 固定身份、覆盖清单和反向覆盖测试 |
| 1.4—1.6 | 7.3、9.2、10.2 | 四类路径、授权/写入/HITL、五层边界案例 |
| 1.7—1.9 | 8.1、13.1、13.5 | 套件摘要、预检和唯一小说 UI |
| 1.10—1.18 | 7.2、7.6、8.1—8.4 | 统一 runner、完整案例合同、启动前全量拒绝 |
| 1.19—1.25 | 7.1—7.3、7.8、8.3—8.4 | 17+12 生产快照、23 case、29 项真实调用反向覆盖和漂移预检 |
| 2.1—2.7 | 8.2、11.2—11.3、13.4 | 内容冻结、独立工件和身份比较 |
| 2.8—2.13 | 7.10—7.11、11.3 | Git/provider/环境/轨道/availability 元数据 |
| 2.14—2.16 | 8.2、11.3—11.4 | 精确 ID/hash、最小引用、独立重复工件 |
| 3.1—3.8 | 9.1—9.3 | 独立 Runtime、真实能力白名单、事实不可写 |
| 3.9—3.17 | 7.4、9.1、9.3—9.4 | 密封夹具、干净副本、三方复核、无多小说补全 |
| 4.1—4.8 | 7.7、10.1 | 确定性 verifier 复跑与 advisory 隔离 |
| 4.9—4.15 | 7.2、8.3、9.2、16.1—16.2 | 全局严格脚本、六类稳定错误、finalize 和规范化重复一致 |
| 5.1—5.9 | 7.8、10.3 | 条件/门禁/终态矩阵与 suite 汇总 |
| 5.10—5.22 | 7.5、7.8、10.3—10.4 | 六预算、六硬门禁和基础设施分离 |
| 5.23—5.27 | 7.8、10.3—10.4 | 整体能力和局部机制只由硬门禁判定，差异/指标不得放行 |
| 6.1—6.8 | 7.7—7.8、10.1、13.7 | 期望/实际/证据/机制/下一步复核 |
| 6.9—6.17 | 7.8、10.3—10.4 | primary/all failure 和确定性全序聚合 |
| 7.1—7.9 | 7.10、11.3 | 案例到套件工件、完整性和审计资料标签 |
| 7.10—7.23 | 7.9、11.4 | 只读证据、精确关联链、最小 bundle/hash |
| 8.1—8.9 | 7.11、12.1—12.3、13.7 | 实验 arm、声明差异、可比性和绝对结论 |
| 8.10—8.16 | 7.11、9.2、12.2 | synthetic/live 分轨和 provider 状态 |
| 8.17—8.23 | 10.4、13.5 | 六类指标独立边界和恢复相邻结论 |
| 8.24—8.27 | 7.11、10.4 | 稳定性统计、无总分、恢复无替代 |
| 8.28—8.31 | 7.8、7.11、10.4 | 真实机制开关、invariant gate、qualified ablation 与 decision source |
| 9.1—9.9 | 11.1—11.3、12.2 | 状态机、进度、取消、恢复、幂等、终态 |
| 10.1—10.6 | 12.2—12.4、13.1、13.4、13.6—13.7 | 入口、页码总览、三层结论、提交/实验确认和去重 |
| 10.7—10.13 | 12.3、13.2、13.5—13.9 | 中文详情、request ID、失败展开、错误/空态、桌面边界 |
| 10.14—10.20 | 13.1—13.5、13.10 | 保留路由、五工作区、组件复用、无新依赖 |
| 10.21—10.25 | 12.2—12.4、13.4、13.6—13.10、15.3 | revision 进度、取消、去重、generation 防倒退、中文枚举、固定端口 |
| 10.26—10.34 | 12.2—12.4、13.2—13.8 | overall/memory/mechanism、DeepSeek、comparison refs/URL 与不可比说明 |
| 11.1—11.8 | 7.1、7.9、9.2、10.4、11.4 | 评测 exchange 精确保存各源 locator、轨道可用性、源内复读、相邻边界与证据缺失 |
| 11.9—11.15 | 4.2—4.3、5.2—5.4、7.1、7.5、7.9、11.4、14.1—14.3、16.1—16.2 | observer 故障隔离、Runtime 审计零修改、Token 可用性、原文隔离、只读、无平行 Runtime 轨迹/推测/mtime |
| 12.1—12.11 | 15.1—15.2、16.4 | 破坏式替换、资料更新、历史和共享保留 |
| 12.12—12.17 | 6、13.10、15.2 | 精确后端/fixture/结果/前端删除重写 |
| 12.18—12.21 | 15.1—15.3、16.4 | README/docs/assets 联动、全仓扫描和共享保护 |
| 13.1—13.4 | 7.6、10.2 | 五类产物和写候选 draft 隔离 |
| 13.5—13.12 | 7.7、8.4、10.1—10.2、14.3 | 注册式类型 verifier、只读、无 Shell、门禁 |
| 13.13—13.15 | 10.2 | HITL、来源和能力工件专属身份校验 |
| 14.1—14.4 | 7.3、7.12、16.1—16.2 | 四态、当前/修复投影与可审计回放 |
| 14.5—14.11 | 7.12、9.2、16.2 | 来源指纹、三类边、定向传播、审查、修订与替代 |
| 14.12—14.18 | 7.8、7.12、10.3、16.1—16.2 | 摘要/digest/snapshot/reuse 防污染、并行隔离和七项机制门禁 |
| 14.19—14.20 | 7.12、11.4、13.5 | 状态迁移证据与专项结论不被总体通过率覆盖 |
| 15.1—15.5 | 7.13、11.3、12.1—12.2 | synthetic 前置、DeepSeek V4 Pro 首轮、冻结工件与失败分类 |
| 15.6—15.13 | 7.13、12.1—12.3、14.3 | 唯一 Inbox、严格八行、高层工程内容、稳定 ID/租约与类别隔离 |
| 15.14—15.19 | 7.13、11.2—11.3、12.2 | 目标 case+当前全量+core 无回归关闭、suite hash 漂移重启和比较前置 |
| 15.20—15.25 | 7.13、12.2—12.4、13.4—13.7 | 固定比较条件、独立 iteration 工件、comparison refs/URL 与评测缺陷闭环 |
| 15.26—15.32 | 6.1—6.2、7.13、11.3、12.1—12.4、13.11、16.1—16.3 | legacy Inbox CAS 演进、写入阻断、deterministic relation revision/observation、两级 CAS 补偿与四方对称读回 |
| 15.33—15.40 | 7.11、7.13、12.2—12.4、13.5—13.7 | requested/actual/probe/fallback/replay/usage/cost/error 准入与不可比隔离 |

### 17.1 机械追踪 ID 索引

以下索引用于证明全部验收标准在本设计中有追踪项；语义落点以上表为准。

- 需求 1：1.1、1.2、1.3、1.4、1.5、1.6、1.7、1.8、1.9、1.10、1.11、1.12、1.13、1.14、1.15、1.16、1.17、1.18、1.19、1.20、1.21、1.22、1.23、1.24、1.25
- 需求 2：2.1、2.2、2.3、2.4、2.5、2.6、2.7、2.8、2.9、2.10、2.11、2.12、2.13、2.14、2.15、2.16
- 需求 3：3.1、3.2、3.3、3.4、3.5、3.6、3.7、3.8、3.9、3.10、3.11、3.12、3.13、3.14、3.15、3.16、3.17
- 需求 4：4.1、4.2、4.3、4.4、4.5、4.6、4.7、4.8、4.9、4.10、4.11、4.12、4.13、4.14、4.15
- 需求 5：5.1、5.2、5.3、5.4、5.5、5.6、5.7、5.8、5.9、5.10、5.11、5.12、5.13、5.14、5.15、5.16、5.17、5.18、5.19、5.20、5.21、5.22、5.23、5.24、5.25、5.26、5.27
- 需求 6：6.1、6.2、6.3、6.4、6.5、6.6、6.7、6.8、6.9、6.10、6.11、6.12、6.13、6.14、6.15、6.16、6.17
- 需求 7：7.1、7.2、7.3、7.4、7.5、7.6、7.7、7.8、7.9、7.10、7.11、7.12、7.13、7.14、7.15、7.16、7.17、7.18、7.19、7.20、7.21、7.22、7.23
- 需求 8：8.1、8.2、8.3、8.4、8.5、8.6、8.7、8.8、8.9、8.10、8.11、8.12、8.13、8.14、8.15、8.16、8.17、8.18、8.19、8.20、8.21、8.22、8.23、8.24、8.25、8.26、8.27、8.28、8.29、8.30、8.31
- 需求 9：9.1、9.2、9.3、9.4、9.5、9.6、9.7、9.8、9.9
- 需求 10：10.1、10.2、10.3、10.4、10.5、10.6、10.7、10.8、10.9、10.10、10.11、10.12、10.13、10.14、10.15、10.16、10.17、10.18、10.19、10.20、10.21、10.22、10.23、10.24、10.25、10.26、10.27、10.28、10.29、10.30、10.31、10.32、10.33、10.34
- 需求 11：11.1、11.2、11.3、11.4、11.5、11.6、11.7、11.8、11.9、11.10、11.11、11.12、11.13、11.14、11.15
- 需求 12：12.1、12.2、12.3、12.4、12.5、12.6、12.7、12.8、12.9、12.10、12.11、12.12、12.13、12.14、12.15、12.16、12.17、12.18、12.19、12.20、12.21
- 需求 13：13.1、13.2、13.3、13.4、13.5、13.6、13.7、13.8、13.9、13.10、13.11、13.12、13.13、13.14、13.15
- 需求 14：14.1、14.2、14.3、14.4、14.5、14.6、14.7、14.8、14.9、14.10、14.11、14.12、14.13、14.14、14.15、14.16、14.17、14.18、14.19、14.20
- 需求 15：15.1、15.2、15.3、15.4、15.5、15.6、15.7、15.8、15.9、15.10、15.11、15.12、15.13、15.14、15.15、15.16、15.17、15.18、15.19、15.20、15.21、15.22、15.23、15.24、15.25、15.26、15.27、15.28、15.29、15.30、15.31、15.32、15.33、15.34、15.35、15.36、15.37、15.38、15.39、15.40

## 18. 实施批次与依赖门禁

1. 合同批次：类型模型、canonical hash、suite/fixture、CapabilityCatalogSnapshot、29 项反向映射与 verifier preflight。门禁是静态套件可完整拒绝错误且不创建执行资源。
2. 隔离与脚本批次：fixture manager、完整目录注册+case exposure、评测 Runtime factory、StrictScriptedDriver、评测专用 correlation scope/observer/ledger、活动事实控制面。门禁是 23 个 synthetic case 经真实 handler 运行且脚本完全消费；live/synthetic 轨道观察与四行状态矩阵可精确复核；各源 hash 只做源内复读；observer/repository 故障不改变底层 outcome；正常 Runtime 审计合同与写入路径无 diff。
3. 工作记忆生产修复批次：producer proof、统一投影、复用前后双门禁与四 memory case。门禁是七项机制硬门禁全可复核、失效产物无法复活。
4. 判定批次：evidence reader、typed artifacts、verifiers、case/suite/mechanism gates、failure 和六 metrics。门禁是同工件复判完全一致且指标不能放行硬失败。
5. 生命周期批次：artifact repository、runner、取消/崩溃/恢复/幂等/实验。门禁是终态不可变和异常路径工件完整。
6. 首轮闭环批次：先升级唯一 Inbox 的 legacy revision 0/links、GET-by-ID、全调用者 expected revision CAS 与前端 409 刷新，再实现冻结 subject、deterministic intent/revision、append-only observation、relation/iteration 两级 CAS、coordinator/reconciler、四方 symmetry gate 与 comparison admission。门禁是每个崩溃窗口按同 hash 重放不增加 revision，最终 iteration CAS 才清 pending，冻结工件哈希不变，非系统类别不写 Inbox，未对称闭环不可比较。
7. API/前端批次：新路由、`page/page_size` 契约、detail/list revisions、request ID、三层结论、comparison URL 恢复、保持现有 Shell 导出和固定端口联调。门禁是纯 Node 只验证 reducer/parser/coordinator，DOM 行为完成桌面浏览器手验，全部中文强顺序操作可验收。
8. 破坏式清理批次：切换装配、删除旧实现/结果、更新资料、全仓扫描和 `start.bat` 验收。

后续批次不能绕过前一批次门禁；尤其前端不得先用临时旧字段适配，新 API 不得以兼容层读取旧结果。

## 19. 风险与重新验证点

| 风险 | 控制与验证 |
|---|---|
| 真实 Runtime 装配漂移 | 公开评测工厂复用生产协议/组件，能力目录哈希；Runtime 依赖变化触发重验 |
| LLM trace/replay/usage 身份断裂 | 同 task exchange 分别捕获既有 source locator；各源用原生算法复读，不比较跨源 hash/status；只按显式状态矩阵、owner、run 和 cardinality判断，禁止修改 Runtime 字段或猜测关联 |
| observer 故障污染底层结果 | 底层调用/append 先且只执行一次；observer/scope/repository 异常仅使评测 invalid；finally 固化 pending；逐阶段故障注入验证返回、原异常和写入次数 |
| synthetic 看似真实但跳过审计 | 只替换模型 gateway；要求 strict-driver step、真实 trace/调用/检查点/上下文/effect 和 fixed token observation，Runtime replay/usage 明确不适用 |
| 外部检索联网导致漂移 | 两轨统一 fixture backend，真实 service/tool，禁止 DuckDuckGo/network 并验证 source manifest |
| 活动事实被误触 | 凭据/路径不可达 + 前后哈希 + ledger；任一无法证明即隔离失败 |
| 并行清理误删 | UUID workspace、严格 DB 前缀、owner ledger、resolved path 三重校验 |
| 缺失证据被当作能力失败或通过 | availability + evidence gate；基础设施口径独立 |
| provider 配置差异破坏比较 | provider/model/decode 显式身份；不支持项标不可用；未声明差异 incomparable |
| 目录声明被误当覆盖 | 完整生产快照 + required/observed invocation + capability hard gate；allowed/manifest 不计数 |
| strict script 漏消费或用假能力 | 单一全局流、真实 handler wrapper、mandatory finalize、规范化重复 gate |
| 失效工作记忆被复用复活 | 规划/执行双 proof、reuse provenance、统一 current projection 和 anti-resurrection tests |
| Inbox 并发、超时或半提交 | deterministic intent/revision、create-if-absent、append-only observation、单协调租约、Inbox CAS/readback、relation CAS 与最终 iteration CAS；orphan 可按同 hash 恢复，四方 symmetry 未通过即不闭环 |
| Issue 状态更新污染冻结工件 | 只允许 run terminal/suite/first-live/failure 四类不可变 subject；状态变化追加新 intent/revision，冻结字节哈希前后复核 |
| Legacy Inbox 调用者丢更新 | 旧行只读正规化为 revision 0/空 links；首次 CAS 原子升级；现有 service/API/web 调用者全部携带 revision，409 刷新并提示 |
| 多模型 identity/fallback 污染 | 逐模型 probe 与 requested/actual/replay/usage 证据；不满足即独立 incomparable |
| 大工件拖慢页面 | 最小 bundle、refs、分页、详情按需加载和 artifact 大小监控 |
| 页码列表或轮询响应倒退 | 单调 index/detail revision；client generation + AbortController + lastAppliedRevision；慢响应纯 coordinator 测试与快速切换手验 |
| 旧契约复活 | 无兼容 reader；全仓扫描和删除清单作为交付门禁 |
| 阈值被代码暗设 | 全部阈值位于 suite/profile 并进入 hash；缺失直接 preflight invalid |

需要重新设计或至少重新验证的变化包括：Runtime 证据主键/生命周期改变、能力注册协议改变、五层上下文合同改变、provider gateway/decode 能力改变、活动事实存储改变、评测保留/删除政策引入、移动端成为交付目标、新前端依赖或设计系统改变，以及相邻恢复基准被要求并入本套件结论。

当前没有阻塞实现的架构未决问题。具体预算、套件通过阈值、重复性阈值和 live provider/model 选择是被哈希的运营配置，不是隐藏代码默认；在仓库固定套件中缺失时系统按设计拒绝启动，不允许实现者擅自猜测。

## 20. 设计草稿门禁

- 需求追踪：15 组 325 条标准均有连续范围映射和机械 ID 索引。
- 边界：评测拥有合同、执行、证据聚合、判定、实验与工作台；Runtime 审计、活动小说事实和相邻评测保持独立。
- 安全：密封副本、独立 Mongo、真实授权、活动事实不可达、八类窄只读证据 facade（不注入完整可写仓储）和严格清理形成闭环。
- 可复现：suite/fixture/code/provider/decode/环境均有明确身份或 availability，不使用 mtime 和时间邻近。
- 判定：case/suite/capability/mechanism/工作记忆硬门禁、typed artifacts、注册式 verifier、primary/all failure、六类独立 metrics 均可独立复核，指标不覆盖硬失败。
- 生命周期：七值 lifecycle 与 completed-only conclusion 唯一映射明确；幂等、并行、取消、崩溃、仅 unfinished 恢复、原子提交和终态不可变均有实现路径。
- 首轮闭环：DeepSeek V4 Pro 强顺序、四类不可变 subject、deterministic intent/revision、append-only observation、Inbox CAS/readback、relation/iteration 两级 CAS、orphan 幂等补偿、四方 symmetry gate 和多模型硬准入完整。
- 前端：保持 `GeneralAgentEvaluationShell` 导出，组件与文件一一对应；页码分页、request ID、三层结论、comparison URL、generation/revision 防倒退、原生加载、内联确认与 `aside/details` 完整。极光只装饰；共享分页、导航、依赖和 package script 均不修改；DOM 行为明确由固定端口浏览器手验。
- 清理：旧实现和旧活动结果破坏式删除，共享 Runtime/相邻评测/历史资料明确保留。

草稿门禁结论：通过，可提交独立设计校验；该结论不是独立校验 PASS，也不替代后续 `validate-design`。
