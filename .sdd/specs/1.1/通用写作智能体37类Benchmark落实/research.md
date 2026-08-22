# 通用写作智能体 37 类 Benchmark 研究与设计决策

## 1. 文档信息

- 规格：`1.1/通用写作智能体37类Benchmark落实`
- 发现级别：完整
- 调查时间：2026-07-30
- 目标：捕获影响固定套件、typed 行为判定、Runtime 恢复、五层上下文、不可变基线、Hydration、API 和桌面网页的真实证据与权衡。
- 前置门禁：`requirements.md` SHA-256 为 `b3f7dbf57cf7cdc00c75427c030ef3e5244354e6923c5f773326b60aafa18a5a`，与独立需求 PASS 报告及 `spec.json` 一致；`state.py validate` 返回 `ok=true`。
- Graphify：根规则明确禁用；本次只使用 `rg`、当前源码、测试、配置、规格输入和官方一手资料。

## 2. 需求与约束摘要

| 需求范围 | 技术约束 | 非功能约束 | 设计结论 |
|---|---|---|---|
| 1.1—3.4 | 精确 37 条、`S37/L21`、唯一活动清单、行为合同不绑定检索实现 | 套件漂移必须执行前失败；合同变化产生新身份 | `suite.json` 是活动案例、顺序、中文名、轨道、场景、终态和证据合同的唯一事实源 |
| 4.1—7.6 | 最小路由、检索、多 Agent、授权/资源、运行工作记忆必须以真实下游消费和后态判定 | 不能把调用成功、存在性或脚本预设结果当正确性 | 新增 typed observation + 可枚举 oracle；脚本只控制协议 |
| 8.1—8.11 | 八类故障窗口、成功结果复用、幂等、副作用对账、坏 Checkpoint 安全失败 | 恢复不得重复成功节点或不确定副作用 | Harness 注入故障；生产 Runtime 提供 durable 能力结果、Effect 和完整性恢复契约 |
| 9.1—9.10 | 五层名称固定；当前请求完整；工作记忆不得误称长期记忆 | 压缩后任务行为、受保护事实和无效信息隔离必须可证明 | 扩展生产上下文决策轨迹，使用成对运行与全载体 oracle |
| 10.1—11.7 | 六 Gate 恰好齐全；证据缺失/损坏/冲突为 `INVALID`；逐案密封 | JSON 仅作评测运行、审计、回放；不得成为正文/结构事实源 | 保留 Gate 聚合器，重建其条件和 evidence ref；每案资源快照及作者事实哨兵 |
| 12.1—14.6 | 新 37 基线不可覆盖；旧 23 历史不可改；跨身份不得聚合；当前/历史计数来自自身 | 相邻评测、运行监控和固定端口继续可用 | 内容寻址工件 + 活动/历史显式索引 + Hydration join gate；UI 只做数据口径适配 |

全部 102 个 EARS ID 已由需求独立门禁确认唯一；正式设计将逐项建立 102/102 追踪矩阵。

## 3. 当前项目事实

### 3.1 权威资料

| 资料 | 状态 | 关键事实 | 影响 |
|---|---|---|---|
| `AGENTS.md` | 当前规则 | 生产 Runtime 使用动态最小充分 DAG；能力目录与单次运行图分离；五层上下文名称固定；运行工作记忆由 Runtime 自动治理 | 不得新建 37 个任务专用 Tool/Subagent 或固定生产 DAG；不得把运行工作记忆称为长期记忆 |
| `AGENTS.md` | 当前规则 | Markdown/MongoDB 分别承担文本/确认结构事实；JSON/JSONL 只作候选、运行、审计和回放 | Benchmark 夹具和结果不是业务事实；所有写案例只操作密封副本 |
| `README.md` | 当前仓库地图 | 当前固定套件、评测模块、Runtime、恢复与上下文均有既有入口 | 在现有评测边界内扩展，不创建平行评测系统 |
| `DESIGN.md` | 当前前端规则 | 中文桌面控制台、高密度低干扰；不得用硬编码技术标识替代用户文案；本规格不得改路由和信息架构 | 页面只替换动态数据、中文映射和结论计算，不做视觉重构 |
| `requirements.md` | 已独立校验 PASS | 37 条精确清单、六门禁证据矩阵、八类恢复、八类上下文、新旧身份和 UI 口径完整 | 设计不得缩为“23 改 37” |
| `gap-analysis.md` | 当前上游产物 | 已确认 suite 双事实、弱 Gate、Runtime 恢复/上下文缺口、Hydration 和前端硬编码 | 采用混合方案并把证据不足转为 RED 测试和重新验证触发器 |

`README.md` 的“阶段 04”仍使用旧五层近义名称；本规格不把该文字当作 Runtime 当前命名事实。实现若触及 README 所列入口或运行说明，应按根仓库地图规则同步修正为固定五层名称。

### 3.2 套件、契约与 runner

| 资产 | 状态 | 证据 | 可复用/约束 |
|---|---|---|---|
| 固定套件 | 现有，待破坏式替换 | `tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json` 当前为 23 条 | 文件位置和规范化 hash 可复用；内容替换为精确 37 |
| 活动加载契约 | 现有，待合并 | `suite_loader.py:28-125` 的 `AuthoredCaseSpec/AuthoredSuiteSpec` | 保留为唯一正式加载模型并扩展；删除未被 runner 使用的重复 `CaseSpec/SuiteSpec` |
| 平行案例目录 | 现有，必须清理 | `capability_catalog.py:101-205` 手写 `_CASE_IDS`、轨道和 invocation expectations | 删除活动案例/轨道/调用双份；目录只保留生产能力集合和从 suite 派生的覆盖审计 |
| 轨道执行 | 现有，待加选择门禁 | `synthetic_suite.py:116-154`、`live_runtime.py:668-739` 均遍历传入全部案例 | 新增一个共享 `SuiteSelectionValidator`，runner 与 API 必须共同使用 |
| 严格脚本 | 现有，可复用 | `strict_driver.py:164-349` | 继续证明步骤顺序、人工决定和确定性依赖；不参与最终行为真值 |
| 六 Gate 聚合 | 现有，可复用 | `gates.py:35-171` 支持 `PASSED/FAILED/INVALID`、恰好六类和证据引用 | 聚合器不重写；删除上游空证据、`security=True`、存在性和统一完成态条件 |
| 静态 verifier 注册表 | 现有，可扩展 | `gates.py:171-235`；`models.py:405-501` | 复用注册机制，配置改为可枚举严格 union；禁止路径表达式、Python 代码、shell 或动态 import |

### 3.3 Runtime、恢复与上下文

| 资产 | 状态 | 证据 | 设计影响 |
|---|---|---|---|
| 动态 DAG | 现有 | `general_agent/executor.py:103-170`、`service.py:858-1061` | 保持动态计划；Benchmark 只注入边界故障并观察 |
| 普通 Tool 结果 | 现有缺口 | `executor.py:483-540` 在 Tool 返回后只把 envelope 装入节点结果，节点 Checkpoint 前无独立 durable result | 新增通用能力结果日志；#23 的“结果已产出”定义为结果已原子持久化 |
| 生产组合根 | 现有，需接线 | `src/taichu/main.py:302-311,485-498` 当前只构造/注入 Run、Checkpoint、Effect、Context 等仓储 | CapabilityResult 必须在同一组合根构造并强制注入执行、恢复与删除级联；触及 `main.py` 必须验证 `start.bat` |
| 写 Effect | 现有，可复用 | `executor.py:566-710`、`effect_repository.py:19-74` | #26/#28 直接复用 PREPARED/STARTED/SUCCEEDED/RECONCILED/REQUIRES_HUMAN 及资源对账 |
| Subagent | 现有，边界需明确 | `subagents/registry.py:76-175` 只有完整 envelope 后才进入父节点 | #24 采用整次安全重试；父级不得消费半成品；未来若 Subagent 有副作用须重新设计 |
| Checkpoint 修订 | 现有，可复用/补缺 | `langgraph_checkpoint.py:147-243,422-493,550-576` 校验修订、线程、版本、hash，能回退有效修订 | `recover_interrupted()` 必须先消费完整性摘要；无有效修订不得从业务 run 投影重跑 |
| 恢复入口 | 现有缺口 | `service.py:554-566,754-778` 未先做完整性门禁 | 增加显式 `RecoveryDecision` 持久化和 `FAILED + resumable=false` 安全终态 |
| 五层 envelope | 现有 | `context.py:389-498`；`models.py:321-350` | 直接扩展观测，不复制算法；长期记忆当前保持空，不拿工作记忆填充 |
| 裁剪顺序与拒绝 | 现有基础 | `context.py:501-657` | 保留稳定记忆/当前请求保护；将不可安全组装变成显式非可恢复停止证据 |
| 大节点投影 | 现有基础 | `context.py:792-908` | 增加合同必需路径、原始计数和 source/artifact ref 保持，不以“未展示”推断不存在 |
| 上下文快照 | 现有，可扩展 | `models.py:392-411`、`context_snapshot_repository.py`、`evidence_builder.py:247-272` | 在同一快照新增 assembly trace；不建设第二条上下文轨迹 |

### 3.4 工件、冻结与 Hydration

| 资产 | 状态 | 证据 | 设计影响 |
|---|---|---|---|
| 不可变工件 | 现有，可复用 | `artifact_repository.py:71-100` | 保持内容寻址和同 ID 不同内容拒绝 |
| 合成冻结 | 现有，待动态化 | `synthetic_baseline.py:31-107` 含 23/23 硬编码 | 冻结资格从 suite 身份和实际 37 个 case row 推导 |
| Live/Comparison 冻结 | 现有，待动态化 | `freeze_general_agent_first_live.py`、`freeze_general_agent_model_comparison.py` | Live 必须严格 21 条；比较前做共同身份 join |
| Hydration | 现有，待扩展 | `artifact_hydration.py:181-239,390-561` | 从单一活动快照改为显式 manifest 索引；旧 23 原 schema 只读适配，不原地迁移 |
| 比较身份 | 现有模式可复用 | `experiments.py:189-241` 已用“冻结字段相等 + 声明差异”表达可比较性 | 扩展为 ArtifactIdentity、relation-specific ComparabilityKey、DeclaredDifferences，避免把工件唯一性误作所有关系的全字段相等 |

### 3.5 前端架构分析

#### 页面与导航

| 项目 | 当前事实 | 本次设计 |
|---|---|---|
| 路由 | `/task-monitor/general-agent/evaluation`，入口 `web/src/app/task-monitor/general-agent/evaluation/page.tsx` | 保持 |
| 业务组件 | `GeneralAgentEvaluationShell` | 原位数据适配，不拆页面、不改布局 |
| 导航 | `general-agent-monitor-nav.tsx` 已提供“效果评测”入口 | 保持 |
| 页面模式 | 智能体监控下的控制台工作台 | 保持午夜极光控制台与现有信息架构 |

组件树：

```text
web/src/app/task-monitor/general-agent/evaluation/page.tsx
└── GeneralAgentEvaluationShell
    ├── GeneralAgentMonitorNav
    ├── 套件与运行选择区
    ├── 运行结论与动态计数
    ├── 案例与六门禁明细
    └── Live 与比较摘要
```

#### 组件复用与准入

- 复用现有 `GeneralAgentEvaluationShell`、导航、紧凑列表、选择框、状态图标和页面 token。
- 不新增外部组件、不修改 `web/package.json`、不新增动效或视觉素材。
- 不引入移动端、窄屏重排、卡片重构或独立页面。

#### API/类型映射

| 前端函数/类型 | 当前端点/文件 | 当前缺口 | 设计变化 |
|---|---|---|---|
| `listBenchmarkSuites` / `BenchmarkSuiteSummary` | `GET /api/general-agent-benchmarks/suites` | 只有 suite 总数 | 继续作为列表摘要 |
| 计划新增 `getBenchmarkSuite` / `BenchmarkSuiteDetail` | 现有 `GET /api/general-agent-benchmarks/suites/{suite_id}` | 后端当前仍返回 summary | 返回顺序化案例中文名、说明、适用轨道和 suite 身份 |
| `submitBenchmarkRun` | `POST /api/general-agent-benchmarks/runs` | selected IDs 未在 catalog 校验轨道 | 后端执行前拒绝未知、重复、乱序和不适用 ID，并返回中文可操作错误 |
| `BenchmarkSuiteRun` / `BenchmarkSuiteArtifact` | 运行与工件接口 | UI 用“已结束”代理通过/失败 | 从 case rows 的实际 conclusion 计算 passed/failed/invalid/pending |

#### 状态与交互

| 用户动作 | 状态变化 | API/副作用 | 成功 | 失败/恢复 |
|---|---|---|---|---|
| 选择套件 | 载入 suite detail 与自身适用集 | `GET /suites/{id}` | 中文名称和真实数量出现 | 保留原错误区和重试 |
| 选择轨道 | 从 suite detail 派生可选案例 | 无写副作用 | synthetic 显示 37，live 显示 21 | 不允许选择不适用案例 |
| 发起运行 | 提交当前轨道适用 ID | `POST /runs` | 新运行进入列表 | 422 显示中文不适用案例清单 |
| 查看当前/历史运行 | 使用该 run 自己的 selected IDs 与 rows | 只读 | 37 与 23 各显自身总数 | 工件缺失时不伪造通过 |

#### 视觉、文案与验证

- 文案使用“37/37 Benchmark 全部通过”这一动态模板；只有 `passed===total===37` 且无 invalid/pending 才显示。
- 历史 23 运行显示自己的 23；不套当前 suite 数量。
- 默认案例名称与一句话说明来自 suite detail；旧 23 只读工件缺名称时使用现有中文历史映射。
- 技术 ID/hash 保留在证据/技术详情，不作为主标签。
- 自动验证使用 `npm run test:general-agent`、`npm run lint`、`npm run build`。
- 手动验收固定使用 `http://localhost:3000/task-monitor/general-agent/evaluation` 与 `http://127.0.0.1:8000`。

### 3.6 Graphify

- 状态：项目规则禁用。
- 查询：无。
- 降级：已使用 `rg --files`、`rg -n`、源码、测试、配置和当前规格输入。

## 4. 外部依赖与技术研究

### LangGraph 持久化与恢复边界

- 一手来源：[LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)、[LangGraph Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api)。
- 发现：官方持久化以 thread/checkpoint 保存图状态，并支持恢复成功步骤；官方同时要求可能重执行的外部调用具备幂等设计。
- 约束：LangGraph Checkpoint 不自动证明太初业务写副作用、普通 Tool 返回到父节点投影之间的持久化边界，也不替代太初的 Effect/结果身份与完整性门禁。
- 对设计影响：继续使用当前 checkpointer；普通能力结果和写 Effect 分别建立明确提交点；无有效修订时 fail closed。

### Pydantic 严格 tagged union

- 一手来源：[Pydantic discriminated union 使用错误与约束](https://docs.pydantic.dev/2.12/errors/usage_errors/)。
- 发现：判别 union 的每个分支必须具有稳定的 `Literal` discriminator；当前项目已用 `Annotated[..., Field(discriminator=...)]` 表达 typed 契约。
- 约束：suite oracle、fault、pressure、assertion 和 evidence probe 使用枚举 + 判别 union；`extra="forbid"`；不接受任意表达式、模块路径或代码片段。
- 对设计影响：无需新增依赖，复用当前 Pydantic 2 模式。

### 技术栈与依赖结论

- 后端继续使用当前 Python、Pydantic、FastAPI、LangGraph 和 JSON 仓储；前端继续 Next.js 16.2.9、React 19.2.4、TypeScript、Tailwind 与本地组件。
- 本规格不新增第三方依赖，不引入 SQLite/FTS，不改变 MongoDB/Markdown 业务事实源。

## 5. 架构候选

| 选项 | 边界与工作方式 | 优势 | 风险/限制 | 结论 |
|---|---|---|---|---|
| 仅扩展现有 environment | 在 `synthetic_environment.py` 继续增加 37 个 case 分支 | 文件变化少 | 模块继续膨胀；case-ID 特判和弱代理难清理 | 拒绝 |
| 全新平行评测引擎 | 新 suite、runner、证据和工件系统 | 表面隔离 | 重复真实 Runtime、Gate、工件和 UI；历史兼容复杂 | 拒绝 |
| 混合方案 | suite 唯一事实源；复用 runner/Runtime/Gate/工件；新增 typed oracle、observation、fault/pressure plan；定向修复生产缺口 | 责任边界清楚，能以真实行为判定且保留历史 | 跨模块，需要严格迁移顺序 | 采用 |

## 6. 设计综合

### 6.1 泛化

- 37 条不是 37 个生产能力，而是少量通用评测原语的组合：场景构造、轨道选择、真实观察、typed assertion、证据完整性、故障计划、压力计划、六 Gate 聚合。
- 恢复生产修复泛化为“durable 能力结果 + 写 Effect + Checkpoint 完整性决策”，不按 case ID 分支。
- 上下文生产修复泛化为“压缩前后决策轨迹 + 受保护引用 + 合同必需路径”，不内置 Benchmark sentinel。

### 6.2 构建 vs 采用

- 采用当前 Pydantic strict model、LangGraph checkpointer、Effect repository、context snapshot、Gate 聚合器、不可变 artifact repository 和前端组件。
- 自建的仅是太初业务特有的 suite contract、oracle registry、能力结果日志、身份 join 和上下文证据适配；外部通用库不能替代这些业务不变量。

### 6.3 简化

- 删除重复 `CaseSpec/SuiteSpec` 或 `Authored*` 中未保留的一套；最终只留一个正式 suite model。
- 删除 `CORE_CASES`、`CORE_INVOCATION_EXPECTATIONS` 和 case-ID Gate 特判。
- 不建 DSL 解释器、不执行任意代码、不执行 shell、不接通用 JSONPath/JMESPath。
- 不新增 UI 组件、不新增索引数据库、不迁移旧 23 工件。

## 7. 关键设计决策

### 决策 1：`suite.json` 是活动案例唯一事实源

- suite 声明 `case_id/order/name/summary/applicable_tracks/scenario/setup/expected_terminal/behavior_assertions/required_evidence/required_invocations/budgets/scripted_steps`。
- Python capability catalog 只保留生产能力集合，从 suite 的 required invocations 按 case order 派生覆盖关系并与实际 discovery/handler identity 校验。
- suite load 后机械验证精确 37、`synthetic=37`、`live_provider=21`、旧 ID 缺席、所有引用可解析。

### 决策 2：typed oracle 只执行可枚举规则

- `AssertionSpec` 使用判别 union：文本 claim、调用拓扑、数据流绑定、产物字段、资源 diff、授权/Effect、记忆载体、恢复状态、上下文事实、语义等价。
- `EvidenceProbeSpec` 使用固定 probe enum：run、invocation、artifact、resource snapshot、Effect、Checkpoint、context snapshot、fixture sentinel。
- 预期 claim 的唯一物理来源是 `tests/fixtures/evaluations/general_writing_agent_benchmark/claim-catalog.json`；suite 只引用 claim/normalizer ID。目录纳入 fixture manifest/hash，不包含 scripted response。
- `oracles.py` 静态注册纯函数 `ClaimNormalizerRegistry`。输入只有实际文本、实际 source projection 和固定 normalizer ID/version；输出 typed observed claims、span/source 绑定、未知/歧义状态和 normalization trace。
- Oracle rule-set hash 同时覆盖 ClaimCatalog、Registry descriptor/version 和 normalizer code snapshot。Live/Synthetic 走同一 deterministic projection；未知或歧义为 `INVALID`，明确错误为 `FAILED`。
- 配置只允许字段 enum、稳定 ID、数量、hash、有限别名和比较器；禁止表达式语言、任意路径代码、动态 import、eval、shell 或 LLM judge。

### 决策 3：脚本驱动与最终判定彻底分离

- Strict driver 只保证确定性模型协议、人工决定、固定外研/检索输入及步骤消费。
- Synthetic 与 Live 均构造同一 `CaseObservation` 并调用同一 oracle/Gate pipeline。
- Live 只运行 1—21；LLM 文本差异由行为 claim/来源/后态断言判定，不另设弱化 live oracle。

### 决策 4：普通能力结果以 durable commit 为“已产出”

- 新增 `CapabilityResultRecord` 与 repository，记录 `run/plan/node/attempt/capability/input hash/output/source/artifact/trace/content hash/status`。
- 唯一生产位置是 `project_assets/derived/general_agent_capability_results/{conversation_id}/{run_id}/completed/{result_id}.json`；Harness 只通过显式依赖注入改用逐案隔离根。
- `main.py` 在唯一生产组合根构造仓储并注入 Service/Executor/Recovery；不提供生产内存 fallback。`project_assets/readme.md` 同步记录目录职责和父 run 生命周期。
- 执行器调用前先按稳定 result identity 查询；已完成且身份一致则复用，不再次 invoke。
- Tool 返回后使用同目录临时文件、flush/fsync 和 create-once 原子发布完成记录；同 ID 异内容拒绝。发布后才允许节点投影和下游消费；#23 故障点位于 commit 后、消费前。
- 返回后、commit 前不宣称“结果已产出”；读 Tool 可安全重试但不计入 #23 窗口。写 Tool 继续只走 Effect 协议。
- 恢复顺序固定为 Effect 风险 → Checkpoint 完整性/有效修订 → 从 revision 重算 result ID → 校验/复用 CapabilityResult → Context/graph 继续。父 run 保留则结果保留；整会话删除按 run 级联 Result/Effect/Checkpoint/Context，不提供单条结果操作或独立 TTL。
- CapabilityResult JSON 只用于 Runtime 运行、审计与回放，不是 Markdown/MongoDB 业务事实或回退源。

### 决策 5：Subagent 中断采用完整结果边界

- 父 Runtime 只接受 schema 校验通过并 durable commit 的完整 Subagent envelope。
- 中断的 attempt 不产生可消费结果；成功上游由 Checkpoint/结果日志复用；Subagent 以相同输入整次重试。
- 当前不新增 Subagent 内部 Checkpoint。未来若 Subagent 产生外部副作用、流式可见半成品或需要内部恢复，触发独立规格重新验证。

### 决策 6：Checkpoint 恢复先做完整性门禁

- `recover_interrupted()` 对每个活动 run 先读取 checkpointer integrity summary。
- `valid/recovered + 至少一个明确修订` 才允许 `ainvoke(None)` 或复用 state。
- `invalid/missing/thread mismatch/version unsupported` 且无有效修订时，持久化 `RecoveryDecision(STOP)`，将 run 置为 `FAILED,resumable=false`，记录中文原因，禁止从业务 run 投影静默从头执行。
- Effect 为 UNKNOWN 时继续 `REQUIRES_HUMAN`，不得因 Checkpoint 可用而盲目重写。

### 决策 7：上下文压力复用生产装配并增加决策轨迹

- `GeneralAgentContextSnapshot` 增加兼容默认的 `assembly_trace`：五层 pre/post count、char/token estimate、omitted refs、protected refs、fallback/digest、当前请求 hash、合同必需路径。
- 压力夹具只构造密封数据与 sentinel；不复制 ContextAssembler。
- oracle 比较 protected fact presence、模型可见当前请求 hash、required path、最终 claim、调用拓扑和资源后态；总字符数单独不能通过。
- 无效工作记忆在 basis、repair digest、fallback digest、history summary、node summary、Subagent scope 和 final answer 全载体扫描必须为零复活。

### 决策 8：工件唯一性、可比较性与声明差异分层

- `ArtifactIdentity` 保存单个不可变工件的完整 suite/case-set/track/fixture/catalog/oracle/runtime/runner/provider/script 身份；字段变化意味着工件不同，不自动意味着禁止建立受限关系。
- `ComparabilityKey` 按 relation kind 只保存必须相等的语义字段和共同案例投影 hash；`DeclaredDifferences` 只能声明该关系 allowlist 中的实际差异，不能忽略 suite/fixture/catalog/oracle/runtime 漂移。
- Synthetic37→Live21：共同 1—21 case contract、suite、fixture、catalog、oracle、runtime 必须相等；允许声明 track、37/21 case-set 和 script/provider/model/decode 差异，且 Synthetic 必须 37/37 passed。
- Live 多模型：完整 21 case-set 与语义身份必须相等；只允许声明 provider/model/decode、运行 ID、usage/latency/output 差异。
- 历史 Hydration：当前 37 和旧 23 可只读并列，但不合并；旧 @1 缺字段保持 unknown，禁止从当前 identity 补值或进入比较。
- 活动索引只指当前 37；历史 manifest 列出旧 23 immutable artifact ref，不复制、不重写内容。冻结器从实际结果和 suite 资格推导 37/37 或 21/21，不保留数字常量。

### 决策 9：前端只消费真实目录与运行事实

- suite detail 是中文名称、说明和轨道的活动来源。
- 当前与历史总数都来自 run selected IDs/case rows；passed/failed/invalid/pending 来自实际 conclusion。
- 保留旧历史中文 fallback，移除活动 23/23 文案和 23 默认数。

## 8. 风险与缓解

| 风险 | 严重性 | 触发条件 | 缓解 | 验证 |
|---|---|---|---|---|
| oracle 自证 | 高 | 脚本 response 同时成为 expected truth | oracle 只读独立 observation；负例故意给错误 response | 调用成功但答案/后态错误必须失败 |
| suite 双事实回归 | 高 | Python 再出现 case ID/轨道/调用清单 | 删除双份并加 `rg`/机械 schema 测试 | 任一漂移在案例开始前拒绝 |
| 普通 Tool commit 窄窗 | 高 | Tool 返回后进程在结果 commit 前退出 | 明确定义 durable commit 边界；读 Tool 可重试，写 Tool 走 Effect | #23 只在 commit 后注入；另测 commit 前安全重试 |
| CapabilityResult 接线或孤儿数据 | 高 | Harness 私有实例、生产内存 fallback、会话删除不级联 | `main.py` 单一构造；唯一 derived 路径；父 run 生命周期级联 | 重启复用、同 ID 冲突、会话删除与 `start.bat` 回归 |
| Subagent 隐性副作用 | 高 | Subagent 内部未来写外部资源 | 当前仅允许无父级可见副作用的整次重试；触发器要求重审 | #24 半成品缺席、完整结果唯一 |
| Checkpoint 静默重跑 | 高 | 无有效修订仍从业务 run 启动 | 完整性门禁 + STOP 决策 + non-resumable | #29 全损坏负例零能力调用 |
| 上下文通过预算但丢事实 | 高 | 只检查 char/token | protected refs + 结果等价 + required path | #30—37 行为 oracle |
| 无效记忆在摘要复活 | 高 | fallback/repair 摘要携带内容 | invalid carrier denylist + 全载体 probe | #35 所有载体零命中 |
| 历史 23 被覆盖 | 高 | 单活动索引或当前 suite 覆盖 run 总数 | immutable ref + history manifest + run-own count | 同页加载 37 当前和 23 历史 |
| 跨身份水合/误拒合法比较 | 高 | 全字段相等拒绝 S37→L21/多模型，或任意忽略字段导致误聚合 | ArtifactIdentity + relation key + strict differences | 三种关系分别做正例、逐字段负例和身份不完整测试 |
| Live claim 无法确定投影 | 高 | 自由文本未命中或命中互斥 claim | 独立 ClaimCatalog + 静态 pure Registry；unknown/ambiguous 为 INVALID | 直接回答、证据消费、修订端到端正反例 |
| 前端误把已结束当通过 | 中 | 继续用 pending 差值计算 | view model 从 case conclusion 聚合 | passed/failed/invalid/pending 组合测试 |
| 生产基线 hash 保护冲突 | 中 | 有意修复 Runtime 后受保护 hash 漂移 | 先 RED/GREEN，再按现有保护流程更新并保存理由 | 保护测试和相邻回归同时通过 |

## 9. 重新验证触发器

- 37 条任一 case 输入、轨道、行为断言、证据合同、fault/pressure plan 或 fixture 变化。
- 生产 Tool/Subagent manifest、handler identity、授权策略、side-effect 分类或输出 schema 变化。
- LangGraph/checkpointer 版本、Checkpoint format/thread/revision 规则或恢复入口变化。
- Effect/CapabilityResult 的身份、原子持久化、幂等或对账语义变化。
- 五层名称、裁剪优先级、当前请求保护、工作记忆 validity 或节点输出投影变化。
- suite/baseline/history manifest 或 Hydration join identity 变化。
- Benchmark API case detail、selection validation、run/case conclusion 字段变化。
- 前端主题、路由、页面信息架构或组件依赖变化。

这些事项不是当前阻塞；实现阶段必须以 RED 测试证实后再修改生产 Runtime，并在变更后执行完整 synthetic 37 与相邻回归。

## 10. 参考文献

- `requirements.md`、`independent-validation-report-requirements.md`、`gap-analysis.md` — 本规格已校验输入。
- `src/taichu/application/evaluations/general_agent_benchmark/` — 当前 suite、Gate、工件与 API 应用边界。
- `src/taichu/infrastructure/evaluations/general_agent_benchmark/` — 当前 Harness、runner、冻结和 Hydration。
- `src/taichu/application/general_agent/`、`src/taichu/infrastructure/general_agent_runs/` — 当前 Runtime、恢复、Effect、Checkpoint 和上下文。
- `src/taichu/main.py`、`project_assets/readme.md` — 生产组合根与派生运行数据目录职责。
- `src/taichu/application/evaluations/general_agent_benchmark/experiments.py` — 冻结字段与声明差异的现有可比较性模式。
- `web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx` 及相关 `web/src/lib/` — 当前页面、类型和显示适配。
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence) — thread/checkpoint、pending writes 与 fault tolerance。
- [LangGraph Functional API](https://docs.langchain.com/oss/python/langgraph/functional-api) — durable task result 与幂等重执行边界。
- [Pydantic Validation 使用错误](https://docs.pydantic.dev/2.12/errors/usage_errors/) — discriminator 必须由稳定 Literal 字段区分。
