# 通用写作智能体 37 类 Benchmark 落实差距分析

## 1. 文档状态与分析摘要

- 操作：`validate-gap`
- 规格：`1.1/通用写作智能体37类Benchmark落实`
- 需求对象 SHA-256：`b3f7dbf57cf7cdc00c75427c030ef3e5244354e6923c5f773326b60aafa18a5a`
- 前置门禁：`state.py validate` 通过；独立需求报告结论为 `PASS`，报告记录哈希与当前 `requirements.md` 一致。
- 分析方法：直接读取当前源码、测试、固定套件、配置、冻结与 Hydration 代码及前端活动入口；未使用 Graphify。

摘要：

1. 当前评测基础设施已具备真实生产 Runtime/Tool/Subagent 组合、逐案隔离、严格脚本、六类门禁聚合、不可变工件、部分恢复和五层上下文能力，可作为新基线的骨架。
2. 当前活动套件仍是 23 条，且案例顺序、轨道适用性与能力覆盖目录存在平行事实；Synthetic 和 Live runner 都直接遍历全部案例，尚不能表达或执行 `S37/L21`。
3. 最大可信性缺口不是“少 14 个 ID”，而是缺少逐案例 typed 行为 oracle 与真实证据消费。现行主要以脚本步骤、调用成功、统一完成态、交互存在和预设 `True` 代理正确性。
4. 八类恢复与八类上下文压力不是单纯夹具扩容：部分场景会暴露生产 Runtime 的真实恢复、结果复用、副作用对账、Checkpoint 完整性和上下文投影缺口。
5. 新旧基线已有不可变工件基础，但当前单一可替换索引和单快照 Hydration 不足以同时证明“37 为当前口径、23 历史不可变、不同 suite 身份禁止水合与聚合”。
6. 前端最小范围是数据口径和中文显示适配，不需要视觉重构；当前仍有 `23` 回退/结论文案，并把“已结束”代理为“已通过”。

## 2. 调查范围与可复现证据

### 2.1 项目规则与规格证据

| 证据 | 当前事实 | 对本规格的约束 |
|---|---|---|
| `AGENTS.md` | 动态最小充分 DAG；能力目录与运行实例解耦；五层上下文名称固定；运行记忆由 Runtime 自动治理；历史与工作轨迹隔离 | 不能创建 37 个任务专用 Tool/Subagent 或固定生产 DAG；评测只能观察真实 Runtime 行为 |
| `README.md` | 固定套件、评测产物和相关源码已有仓库入口 | 延续现有评测边界，不创建平行评测系统 |
| `DESIGN.md` | 当前页面为中文桌面控制台；信息架构不得因本规格重构 | 前端只改口径、显示适配和必要契约 |
| `requirements.md` | 14 组数字需求、37 条精确清单、`S37/L21`、六门禁最低证据、八类恢复和八类上下文合同 | 本分析不得弱化为数量替换 |
| `independent-validation-report-requirements.md` | 结论 `PASS`，目标哈希有效 | 满足差距分析前置门禁 |

### 2.2 当前代码与测试证据

| 范围 | 关键证据 | 已确认事实 |
|---|---|---|
| 套件加载 | `tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json`；`suite_loader.py:30-125` | 当前套件 23 条；案例字段只有请求、必需调用、脚本和预算；加载器校验顺序、内容哈希和生产能力目录哈希 |
| 平行案例目录 | `capability_catalog.py:17-36,101-137,139-205`；`test_capability_coverage.py:18-64` | 第二份 23 案例/轨道/调用期望存在于 Python 常量；测试固定断言 23 |
| 执行轨道 | `synthetic_suite.py:116-154`；`live_runtime.py:668-739` | 两个 runner 都直接遍历 `suite.cases`；案例自身没有适用轨道字段 |
| 真实生产能力 | `runtime_factory.py:62-97,149-293` | Harness 在隔离工作区/数据库中发现并组合真实生产 Tool、Subagent、Orchestrator、Dynamic DAG、记忆、Effect 和 Checkpoint |
| Synthetic 模型 | `synthetic_runtime.py:40-118`；`strict_driver.py:164-349` | 模型响应来自套件预写 `response`；严格脚本能拒绝乱序/未消费步骤，但只能证明协议消费，不证明最终业务正确 |
| 六门禁 | `gates.py:35-74`；`synthetic_environment.py:774-875`；`live_runtime.py:527-540` | 六类聚合器可复用；当前普通条件主要基于完成态、交互存在和 `security_ok=True`，证据引用为空 |
| 案例专属机制 | `synthetic_environment.py:878-974` | 除现有记忆和单一恢复案例外直接返回通过；四类记忆只检查投影状态集合 |
| 不可变工件 | `artifact_repository.py:71-100`；`synthetic_baseline.py:31-107` | 内容寻址工件冲突时拒绝覆盖；冻结入口仍硬编码 23/23 |
| Hydration | `artifact_hydration.py:66-118,181-239,390-561`；`container.py:62-97` | 当前只水合固定索引指向的一套 synthetic/live/comparison 快照；各工件内部有哈希校验，但 synthetic 与 live 之间缺少显式同 suite 身份闭环 |
| API | `services.py:29-104`；`general_agent_benchmarks.py:130-210`；`schemas/general_agent_benchmarks.py:52-68` | 启动目录的 `case_count` 已来自套件长度；套件详情仍只有摘要，未返回顺序、逐案例中文名称和适用轨道；提交未由目录校验案例与轨道适用性 |
| 前端 | `general-agent-evaluation-shell.tsx:367-368,713-719,765-782,1017-1020,1605` | 部分总数来自运行数据，但仍有 `23` 回退、`23/23` 文案和“23 条固定任务”；“失败数”由 `总数-已结束数` 代理 |
| 固定测试 | `test_general_agent_benchmarks_api.py:67-103,524-548`；`test_capability_coverage.py:18-64` | API 和能力目录测试仍将 23 作为活动事实 |

### 2.3 机械只读发现

- 当前 `suite.json`：`case_count=23`、`case_order_count=23`。
- 套件只声明两种 suite 级轨道：`synthetic`、`live_provider`；逐案例没有轨道字段。
- 当前 92 个脚本 matcher 只有三种路径：`/phase` 55 次、`/capability_name` 31 次、`/approved` 6 次。
- `AuthoredCaseSpec` 当前字段为：`case_id,name,user_request,user_request_raw,required_invocations,scripted_steps`。
- `models.py:251-275,557-595` 另有未被正式 runner 使用的 `CaseSpec/SuiteSpec`，其中 `CaseSpec` 已包含 `applicable_tracks`；这构成可复用 typed 模型，同时也是需要消除的重复契约。

### 2.4 Graphify 降级说明

根项目规则明确禁用 Graphify。本轮未读取 `graphify-out/`，未执行任何 Graphify 命令；全部结论来自 `rg`、当前源码、测试、夹具和规格门禁。Graphify 缺失不构成阻塞。

## 3. 现有架构与不可突破的边界

### 3.1 可复用架构骨架

1. `GeneralAgentBenchmarkRuntimeFactory` 已在隔离工作区和隔离 MongoDB 中组合真实生产能力，适合作为“生产行为被测对象”。
2. `StrictScriptedDriver` 适合控制确定性输入、人工决定和故障前置步骤，并能 fail closed 地拒绝乱序、额外交互与未消费步骤。
3. `evaluate_case_gates` 已支持六类门禁、同类多个条件以及 `PASSED/FAILED/INVALID` 聚合。
4. 逐案环境已有正文、结构、知识、运行记忆、Effect 与 Checkpoint 等隔离基础。
5. 不可变 JSON 工件和规范化哈希可继续承担新旧基线身份与复现证据。
6. 生产 Runtime 已有动态计划、授权续接、Effect 对账、Checkpoint 与五层上下文基础；新套件应先真实暴露缺口，再定向修复。

### 3.2 责任边界

```text
固定 suite/fixture
  └─ 声明场景、轨道、唯一行为目标、预期终态、证据合同
       └─ Harness：密封环境、确定性依赖、故障/压力注入、证据采集、typed oracle
            └─ 生产 Runtime：动态计划、真实 Tool/Subagent、授权、记忆、Effect、Checkpoint、上下文
                 └─ Oracle：读取真实调用、产物、资源后态和运行证据后判定六门禁
```

- Harness 可以替换模型、固定外部资料、复制业务事实、注入进程中断和制造压力，但不能预写最终正确答案后再用同一答案自证。
- 生产 Runtime 只能注册长期稳定的 Tool/Subagent；不得为某个 Benchmark ID 新增能力，也不得写死 37 条任务图。
- oracle 属于评测应用边界，不应进入领域层或生产能力注册表。
- 对生产 Runtime 的修改只应来自新行为测试暴露的通用缺陷，例如 Tool 结果不可复用、无有效 Checkpoint 时静默重跑或 Effect 不确定时盲目重试。

## 4. 需求到资产矩阵

| 需求 | 当前资产 | 分类 | 主要差距与约束 |
|---|---|---|---|
| 1. 37 条清单与 `S37/L21` | 套件顺序/哈希校验；`CaseSpec.applicable_tracks`；Python 能力目录轨道 | 需替换、需整合 | 活动清单仍 23；逐案例轨道不在正式套件；两个 runner 不过滤；执行前无精确 `S=37/L=21` 拒绝门禁 |
| 2. 每案唯一行为合同 | `AuthoredCaseSpec`、必需调用、严格脚本 | 需新增 | 缺 typed 唯一目标、最终产物、预期终态、oracle 和最低证据合同；必需调用不能替代行为 |
| 3. 第 2—6 条检索占坑 | 现有真实检索 Tool/Subagent 与隔离夹具 | 可复用、受规则约束 | 需补结果相关性、身份、来源边界与最终答案消费断言；不得绑定具体 RAG 实现 |
| 4. 简单路由与检索 | 真实生产能力组合、调用审计 | 需扩展 | 只能证明调用完成，不能证明零不必要调用、命中正确身份、三源共同消费或外研事实边界 |
| 5. 证据与多 Agent | 真实 Subagent、严格脚本、调用父级/偏序声明 | 需扩展 | runner 不验证 `parent/partial_order`；缺输入输出交接、同源分支、物理并行边界、互不污染、修订保护内容和最终综合消费 |
| 6. 授权与资源治理 | Runtime 预览/授权续接、Tool 写入、Effect 基础 | 需扩展 | 缺逐案资源前后快照、预览与应用输入同一、拒绝真实分支、二次确认、精确目标写入和零副作用 oracle |
| 7. 运行工作记忆 | 当前投影与 Repair 投影 | 需扩展 | 现行案例只验证 validity 集合，不验证最终答案、并行作用域和旧结论不复活 |
| 8. 八类恢复 | 活动运行恢复、单一验证中断案例、Effect 对账、Checkpoint 修订 | 需扩展、部分需新增 | 只有一个正式恢复案例；Tool 结果复用、Subagent 中断、授权等待、多次中断、无有效修订和不确定副作用尚未形成八个可判合同 |
| 9. 八类上下文压力 | 五层装配、预算、裁剪、压缩、当前请求保护和显式拒绝 | 需扩展、部分未知 | 没有正式压力案例、压力夹具、压缩前后投影证据、等价 oracle 和无效记忆零复活证明；部分压缩语义能否满足合同当前证据不足 |
| 10. 六类门禁 | 六类聚合器完整 | 可复用框架、需替换条件 | 统一完成态、交互存在、空证据引用、硬编码安全真值和非记忆/恢复默认 `True` 必须删除 |
| 11. 密封夹具 | 逐案工作区/数据库和清理基础 | 需扩展 | 需纳入 37 条正文/结构/知识/对话/记忆/Effect/Checkpoint 副本、压力数据、故障点、人工决定、预期后态和作者活动事实未变证明 |
| 12. 新基线与证据包 | 内容哈希、不可变写入、冻结索引、内部身份校验 | 需扩展、需迁移 | 冻结器硬编码 23；可替换单索引只暴露最新基线；跨 synthetic/live/comparison 身份水合隔离不完整 |
| 13. 活动接口与显示 | 启动目录总数已动态；现有页面/路由可复用 | 需扩展 | API 不返回逐案例中文名称/顺序/轨道；页面仍硬编码 23，且通过/失败计数不是实际案例结论 |
| 14. 破坏式替换与清理 | 已有旧实现清理测试模式 | 需删除/替换 | 要移除活动旧 17/23、平行 23 常量、23 断言、弱门禁和旧展示口径，同时保留旧工件与 `docs/历史/` |

## 5. 七类核心差距

### 5.1 Suite 单一事实源、轨道适用性与 `S37/L21`

现状：

- `suite.json` 是正式执行清单和脚本来源，但不含逐案例适用轨道。
- `capability_catalog.py` 再维护一份案例 ID 与 `applicable_tracks`，并另维护调用期望。
- `AuthoredCaseSpec` 与 `models.py::CaseSpec` 是两套并行 typed 契约；正式加载/执行只使用前者。
- Synthetic 和 Live runner 都全量遍历 `suite.cases`。
- API 提交只接收任意 `selected_case_ids + track`，应用服务未用当前套件验证集合、顺序与轨道。

缺口：

1. 活动事实存在 `suite.json`、`CORE_CASES`、`CORE_INVOCATION_EXPECTATIONS` 三处重复。
2. 当前不能在任何执行前机械证明准确 `S37/L21`。
3. Live 可能接收本应 synthetic-only 的故障/压力案例；部分运行也可能把不适用案例混入结果。
4. 轨道过滤若仅在 UI 做，会被脚本、API 和直接 runner 绕过。

设计阶段应明确的真实选项：

- 让 `suite.json` 成为逐案例身份、顺序、中文名称、轨道、行为合同和调用预算的唯一事实源，Python 目录只保存生产能力覆盖关系。
- 或保留 Python typed 目录为权威并生成/校验套件；但必须消除手写双份清单，且生成物身份纳入 suite hash。
- 不适用：简单把所有 `23` 常量替换为 `37`。它不能实现 `L21`、轨道拒绝、历史 23 或部分运行语义。

### 5.2 Typed 行为 oracle、六门禁与真实证据

可复用：

- `GateConditionInput`、`GateResult` 和六类聚合器。
- `StrictScriptedDriver` 的顺序、额外交互和未消费步骤检测。
- 真实调用的 `call_id`、handler identity、运行轨迹、Effect、Checkpoint 和资源存储。
- `models.py` 已有 ExpectedArtifact/Verifier 等 typed 资产，可评估复用，避免再造松散字典。

真实弱点：

| 弱路径 | 当前证据 | 为什么不能通过新合同 |
|---|---|---|
| preset truth | `synthetic_runtime.py:66-105` 直接返回套件 `step.response` | 脚本同时控制答案又把脚本消费当正确性，无法发现内容错误 |
| 存在性代理 | `artifact_ok/evidence_ok=bool(interaction_records)` | 有调用记录不等于有目标产物、正确后态或可关联证据 |
| 统一完成态 | verifier 与 stop reason 都检查 `run_status=="completed"` | 拒绝、等待人工、不可安全压缩、不可恢复等正确终态会被误判 |
| 硬编码安全 | synthetic/live 都传入 `security_ok=True` | 没有读取作者事实、案例副本或真实网络边界 |
| 空证据 | `_gate_conditions` 和调用契约的 `evidence_refs=()` | 门禁无法下钻复核；缺证据仍可能通过 |
| 默认机制通过 | 非记忆/非恢复案例返回 `True` | 绝大多数案例没有唯一行为断言 |
| 调用代理行为 | `_invocation_problems` 只检查名称、次数和 outcome | 不消费声明的父级/偏序，也不检查输入、输出、下游消费或副作用 |

需要新增/扩展：

1. 每案 typed 行为合同：目标、期望终态、产物类型、资源后态、必需证据类型和 oracle 配置。
2. typed 观察快照：最终回答、调用输入/输出摘要与身份、分支/父子关系、产物、资源前后态、Effect、Checkpoint、上下文统计及拒绝/等待原因。
3. oracle 注册与结果类型：固定可审计规则消费真实观察，不从脚本 `response` 直接推导通过。
4. 证据完整性校验：缺失、损坏、无法解析、跨 suite/run/case 引用或内容冲突均返回 `INVALID`。
5. 六门禁映射：同一行为证据可被多个门禁引用，但每个门禁仍需非空、身份一致的证据引用。

### 5.3 八类恢复窗口

| 案例 | 可复用现状 | 当前真实缺口 | 复杂度 |
|---|---|---|---|
| 22 计划后、首节点前 | 外层图按 `run_id` Checkpoint；计划节点先保存 `plan_created` 再进入执行（`service.py:941-953,1068-1079`） | 缺“图中 plan 已提交、首节点未开始”的语义故障点与计划身份断言；业务 run 与图 Checkpoint 提交窄窗可能重新规划，是否需生产侧提交边界需设计研究 | 中 |
| 23 Tool 结果后、下游消费前 | Tool 调用与 invocation 审计存在 | 成功输出只在 handler 返回后装入 node result，再随节点返回持久化（`executor.py:483-540`）；没有独立 durable result journal，返回与节点 Checkpoint 提交间中断不能保证调用一次 | 高 |
| 24 Subagent 中断 | 上游成功节点可由能力 DAG Checkpoint 复用；Subagent 完整输出校验后才保存工件（`subagents/registry.py:76-153`） | Subagent 无内部 Checkpoint；整次重试可能符合合同，但半成品不可消费、最终工件身份和内部可见副作用当前证据不足 | 中—高 |
| 25 等待授权 | 写节点冻结输入、资源范围和 hash；等待态不进入自动恢复集合；决定后逻辑续接（`executor.py:435-480`；`service.py:554-566,631-722`） | 缺进程重建前后预览、资源身份、授权摘要同一和等待期间零 Effect/零写的 Harness 证明 | 中 |
| 26 写后、Effect 成功前 | 已有精确故障钩子、STARTED/UNKNOWN 恢复对账、`RECONCILED`/`REQUIRES_HUMAN` 安全分流和 fsync Effect 仓储（`executor.py:557-710`；`effect_repository.py:19-74`） | Benchmark factory 尚未暴露 fault injector；需把真实资源后态、Effect 链和写调用次数接入 oracle，并抽查各写 Tool reconcile 的真实性 | 中 |
| 27 校验中断 | 当前 `runtime_checkpoint_recovery` 已覆盖校验重试、同 run 和成功 Tool 不重跑 | 可迁移为第 27 条，但不能代表其他七个窗口；旧案例 ID 必须退出活动清单 | 中 |
| 28 多次中断 | Checkpoint 有修订链，Runtime 有恢复入口，可组合复用 #26/#27 基础 | Harness 仅支持一次 task-name crash；缺同一运行的故障序列、两次恢复累计节点/Effect/计划身份审计 | 高 |
| 29 完整性/版本 | Checkpointer 校验 format/thread/revision/hash/state、隔离坏尾并可回退有效修订（`langgraph_checkpoint.py:147-209,550-576`） | 无有效修订时仅标记 `invalid`；`recover_interrupted()` 未先检查完整性，图无 next/values 时仍可能从业务 run 投影重新执行（`service.py:554-566,748-778`），是明确生产缺口 | 高 |

恢复专项的关键结论：

- 八案需要可声明的故障窗口与一次/多次触发策略，不能在生产代码按 Benchmark ID 分支。
- 故障注入属于 Harness；结果持久化、幂等、对账和安全恢复属于生产 Runtime。
- 任何“通过重跑得到正确结果”的路径都必须结合调用次数、Effect 链和资源后态判断，不能只看最终内容。
- Tool 结果持久化粒度与 Subagent 中断恢复粒度仍需用 RED 行为测试确定；“无有效 Checkpoint”则已发现明确生产缺口，必须设计为不可恢复/人工处理等安全终态，禁止静默从业务投影重跑。

### 5.4 八类上下文压力

现有 `context.py` 已有五层装配、总预算、压缩阈值、类别统计、裁剪顺序、稳定记忆/当前请求保护和超限异常；这是一组可复用生产能力，不应在 Harness 复制另一套上下文算法。当前共同观测缺口是：

- `GeneralAgentContextCategoryStat` 只有裁剪后的选中数、字符数和遗漏数，缺少压缩前统计与保留/遗漏事实身份（`models.py:231-237`；`context.py:955-1009`）。
- `compression_stats.input_char_count` 取裁剪后 envelope，`output_char_count` 是 digest 或同一 envelope 长度，不构成真实压缩前后上下文对（`service.py:1189-1215`）。
- Token 仅按固定字符比估算（`context.py:1081-1107`），不能单独作为预算真实性证据。
- 现有 `evidence_builder.py:247-272` 可按 `context_snapshot_id` 捕获快照，是可复用证据入口。

| 案例 | 可复用现状 | 缺失的正式证据/oracle | 当前判断 |
|---|---|---|---|
| 30 长历史事实保持 | 早期消息摘要、近期原文保留和当前请求排除已有实现（`context.py:731-789`） | 摘要按原顺序逐条压缩并在预算耗尽时停止，不识别仍有效约束；缺约束真实影响最终答案的证据 | 高 |
| 31 长工作记忆优先级 | 活动记忆召回、类型配额和固定裁剪顺序（`context.py:579-646,693-719`） | 主要按类型/位置裁剪，不按当前节点直接依赖或任务必要性；缺必要状态支撑最终任务的证明 | 高 |
| 32 大节点输出投影 | 大结果已有 `compressed/omitted`、原始计数、前 N 项结构概览及来源引用（`context.py:792-908`） | 通用投影不理解能力合同关键字段；被省略字段能否供下游消费无证据 | 中—高 |
| 33 多来源共同超限 | 总预算与固定五层裁剪顺序（`context.py:55-79,501-653`） | `long_term_memory` 当前恒空（`context.py:451-469`）；尚不能形成五层/多来源共同真实施压及必要事实闭环 | 高 |
| 34 压缩等价 | 上下文快照哈希与同策略复用基础（`models.py:392-411`；`context.py:194-203`） | 快照一致不等于任务结果等价；缺正常版/压力版成对执行、关键结论和能力合同比较 | 高 |
| 35 无效记忆隔离 | 当前投影与 Repair 投影区分 validity、失效生产者节点排除（`context.py:193-320`） | 失效内容仍可能作为 repair-only 工作记忆进入 envelope；缺摘要、节点投影、分支和最终回答全载体零复活证明 | 高 |
| 36 长当前请求保持 | 请求上限 100,000 字符，直接使用未 strip 的 `run.user_goal`，稳定记忆/当前请求不裁剪（`models.py:292-297`；`context.py:465-469,648-653`） | 缺模型实际可见请求逐字同一及必要 Tool/Subagent 链完成的端到端证据 | 中 |
| 37 不可安全压缩拒绝 | 稳定记忆与当前请求仍超限时抛出中文 `ContextAssemblyError`，且规划前组装上下文（`context.py:494-498,656-657`；`service.py:871-886`） | Runtime 将异常统一映射为 `FAILED,resumable=True`（`service.py:808-818`），尚无专属安全拒绝终态、用户可见结果和零 Tool/Subagent/Effect 证明 | 中—高 |

当前主要缺口：

1. `suite.json` 没有第 30—37 条，也没有压力输入身份或 expected context evidence。
2. Harness 的 normalized result 主要只有运行状态、节点状态和 Effect 工具，未携带上下文快照、层级预算、压缩/裁剪统计和模型可见请求身份。
3. 现有单测证明部分局部算法，不证明完整 Runtime 在压力下保持最终行为。
4. 长期记忆层当前为空；不得为了“凑五层”把小说知识或运行工作记忆伪装为长期记忆。
5. 第 32—35 条所需的合同感知投影、真实压缩前后统计、语义等价和全载体零复活边界，当前证据不足，设计阶段必须先明确可观测契约再选实现。
6. 第 37 条的拒绝时机基础正确，但生产终态语义不满足需求，不能由 Harness 把通用 `FAILED,resumable=True` 改名后冒充安全拒绝。

### 5.5 37 新基线、旧 23 历史与跨身份 Hydration

可复用：

- `append_immutable` 已能拒绝同 ID 不同内容覆盖。
- synthetic baseline identity 已包含 `suite_content_hash + runtime_config_identity`。
- synthetic、live、comparison 工件各自已有哈希与内部引用校验。
- 历史 JSON 和 `docs/历史/` 可以保持只读，不需要迁移成新格式。

缺口：

1. `SyntheticBaselineFreezer`、first-live 冻结脚本和模型比较冻结脚本仍硬编码 23。
2. `synthetic-passed-baseline` 是可替换的单一活动索引；新 37 冻结后旧 23 工件仍在，但当前查询水合只恢复索引指向的一套运行。
3. `BenchmarkQueryHydration` 只有一个 `suite_run/suite_artifact`；活动 API 的 run 列表不能天然同时寻址旧 23 和新 37。
4. Hydration 分别校验 synthetic 与 live/comparison 内部身份，但顶层加载流程没有显式证明当前 synthetic baseline 的 suite hash/case set 与当前 live manifest 相同。
5. first-live manifest 保存 synthetic 资格引用，但当前水合未读取该引用并验证其确切 suite 身份。
6. 旧 23 运行若被水合，页面总数应来自该运行自己的案例集合；不能从当前 37 套件目录覆盖。

设计阶段需研究：

- 活动索引与历史索引/清单的职责；不可用目录扫描替代明确权威索引。
- 旧 23 工件保持原 schema 读取，还是提供只读兼容适配；不得原地重写旧工件。
- synthetic/live/comparison 聚合所需的最小共同身份：至少 suite hash、case-set hash、轨道、夹具、能力目录及运行策略。
- 跨身份时是整组 Hydration `UNAVAILABLE`，还是只隔离不一致分支；不得静默聚合。

### 5.6 前端动态计数与中文显示的最小范围

页面和导航无需重构。最小后端/前端契约范围：

1. 套件详情返回当前套件身份、精确顺序、逐案例中文名称、一句话说明和适用轨道。
2. 运行汇总返回或可可靠推导总数、已完成、通过、失败、无效和待处理；不能用 `selected-pending` 当“通过”，也不能用 `total-completed` 当“失败”。
3. 当前完整合成运行动态显示 `${passed}/${total} Benchmark 全部通过`；只有当前运行实际为 37/37 才显示 37/37。
4. 历史 23 运行的总数和结论来自历史运行/工件自身。
5. 默认展示中文名称和说明；ID/hash 留在技术详情。
6. 删除 `general-agent-evaluation-shell.tsx` 的 `23` 回退、`23/23` 分支和“23 条固定任务”文案，并同步相关 API/视图模型测试。

可复用组件：

- 现有评测路由、`GeneralAgentEvaluationShell`、API client、类型文件和控制台信息架构。
- 不新增外部 UI 依赖，不改主题、布局、导航或移动端。

### 5.7 生产 Runtime 与测试 Harness

| 职责 | 应保留位置 | 禁止越界 |
|---|---|---|
| 真实动态计划和能力选择 | `application/general_agent` | 不按案例 ID 写固定 DAG |
| 稳定 Tool/Subagent | 生产插件发现/注册 | 不增加任务专用 Tool/Subagent |
| 模型确定性响应 | Synthetic Harness | 不把脚本响应当行为真值 |
| 夹具、故障、压力和人工决定 | Harness/fixture | 不污染作者活动事实 |
| 行为 oracle 和六门禁判定 | 评测应用边界 | 不进入领域模型或能力注册 |
| 真实副作用、幂等、Checkpoint 和上下文修复 | 生产 Runtime | 只有通用缺陷被 RED 测试证明后才修改 |
| 证据快照与引用 | Harness 采集生产运行/存储事实 | 不建设第二条伪运行轨迹 |

现有 `runtime_factory.py` 已正确发现并组合真实能力，应优先复用。新增工作应围绕观察、故障注入、typed oracle 与必要的通用 Runtime 修复，而不是复制 Tool/Subagent 或构造 37 条假能力。

## 6. 可行方案

### 方案 A：在现有 suite/runner/environment 内直接扩展

边界：

- 扩展 `AuthoredCaseSpec`，把轨道、行为合同、终态、产物和证据声明加入 `suite.json`。
- 在 `synthetic_environment.py`/`live_runtime.py` 增加资源快照和案例分支判定。
- 继续使用现有 runner、严格脚本和六门禁聚合器。

优点：

- 调用链变化较小，最大化复用现有评测设施。
- 现有 23 条测试容易按同一模块迁移。

风险：

- `synthetic_environment.py` 已同时承担环境组装、续跑、绑定、门禁与案例特判，继续加入 37 条 oracle、八类故障和八类压力会形成高耦合大模块。
- 容易继续用 `if case_id` 写死行为，模糊 suite 数据与判定代码边界。
- 无法仅靠 Harness 修复 Tool 结果复用、Checkpoint 无有效修订等真实 Runtime 缺陷。

复杂度：高。影响评测加载、两轨 runner、环境、工件、API 和测试；无业务数据迁移，但验证矩阵大。

### 方案 B：新建 typed oracle、证据采集与故障/压力边界

边界：

- suite 只声明 typed 合同和配置。
- 新建案例 oracle 注册表、真实观察快照、故障计划/压力计划与证据完整性验证器。
- runner 负责轨道选择和编排，环境负责隔离与注入，oracle 负责判定。
- 生产 Runtime 通过通用接口暴露必要证据，并只定向修复失败能力。

优点：

- 职责清晰，避免 37 个案例特判堆积在环境类。
- 负例、证据损坏、跨身份和未来行为合同更易独立测试。
- 能明确区分“脚本协议正确”和“业务行为正确”。

风险：

- 新边界较多，必须避免与现有 `models.py` 的 ExpectedArtifact/Verifier 体系重复建设。
- 如果 observation schema 过宽，可能把完整运行轨迹复制进评测工件，违反最小投影原则。
- oracle 注册必须稳定、可审计，不能演化为 37 个任务专用生产能力。

复杂度：高。新增评测应用边界和多类集成测试，迁移旧 runner 的门禁输入。

### 方案 C：混合方案

边界：

- suite 成为唯一案例/轨道/行为合同事实源。
- 复用现有 runner、真实 Runtime factory、严格脚本、六门禁和不可变工件。
- 新增独立 typed oracle/证据/故障/压力边界。
- 对恢复与上下文 RED 测试实际暴露的通用缺陷，定向扩展生产 Runtime。
- API/前端只同步动态事实和中文显示。

优点：

- 同时控制现有模块膨胀和架构改动范围。
- 能让“先由真实案例暴露缺陷，再修生产 Runtime”形成可复核链路。
- 历史、当前基线和两轨身份可统一纳入工件边界。

风险：

- 需要设计清楚 suite 声明、oracle 注册和生产证据三者的身份关联。
- 恢复与上下文实现可能跨多个模块，必须防止 Harness 特例泄漏进生产。
- 迁移期间不能长期保留旧/新两套活动事实和弱门禁双实现。

复杂度：极高。跨 suite、Harness、Runtime、Checkpoint/Effect、上下文、工件、水合、API 和前端，但每层都有可复用基础。

### 不适用方案

- 只扩充 `suite.json` 到 37 行：不能提供行为 oracle、恢复/压力语义或真实证据。
- 只把所有 `23` 替换为 `37`：会破坏历史 23，并继续错误执行 Live 37。
- 为每条 Benchmark 创建 Tool/Subagent：违反稳定能力边界和动态 DAG 决策。
- 用 mock Tool/Subagent 代替生产插件：只能测试 Harness，自称不了解真实 Runtime。
- 让脚本/LLM judge 单独决定通过：会复现 preset truth，且无法证明资源后态、幂等与隔离。

## 7. 影响文件、复用/新增/删除清单

以下是设计候选影响面，不是最终文件承诺。

### 7.1 可直接复用

- `src/taichu/application/evaluations/general_agent_benchmark/gates.py` 的六门禁聚合框架。
- `strict_driver.py` 的严格顺序与 fail-closed 协议。
- `runtime_factory.py` 的真实生产能力发现与隔离组合。
- `artifact_repository.py` 的不可变工件写入。
- 现有 Effect、Checkpoint、上下文快照、调用审计和资源存储。
- 现有评测页面、API client 和桌面控制台组件。

### 7.2 必须修改或评估修改

套件与 Harness：

- `tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json`
- `tests/fixtures/evaluations/general_writing_agent_benchmark/fixtures/core_novel/fixture-manifest.json`
- 该 fixture 下正文、结构、知识、对话、运行记忆、外研及计划新增的故障/压力数据
- `suite_loader.py`
- `models.py`
- `capability_catalog.py`
- `synthetic_suite.py`
- `synthetic_environment.py`
- `synthetic_runtime.py`
- `live_runtime.py`
- `synthetic_baseline.py`

生产 Runtime（仅在 RED 证据证明后）：

- `application/general_agent/context.py`
- `application/general_agent/executor.py`
- `application/general_agent/recovery.py`
- `application/general_agent/service.py`
- `application/subagents/runner.py`、`application/subagents/registry.py` 或现有 Subagent 执行边界
- `infrastructure/general_agent_runs/langgraph_checkpoint.py`
- `infrastructure/general_agent_runs/effect_repository.py`
- Effect、运行结果或上下文快照仓储的现有实现
- `application/evaluations/general_agent_benchmark/evidence_builder.py`

工件、冻结与 Hydration：

- `artifact_hydration.py`
- `application/.../hydration.py`
- `application/.../container.py`
- `scripts/run_general_agent_synthetic_baseline.py`
- `scripts/freeze_general_agent_first_live.py`
- `scripts/freeze_general_agent_model_comparison.py`
- 相应 first-live/comparison identity 模型和测试

API 与前端：

- `application/.../services.py`
- `api/schemas/general_agent_benchmarks.py`
- `api/routes/general_agent_benchmarks.py`
- `main.py`（若 catalog detail 组装变化）
- `web/src/lib/types/general-agent-benchmark.ts`
- `web/src/lib/api/general-agent-benchmark.ts`
- `web/src/lib/general-agent-benchmark-display.ts`
- `web/src/lib/general-agent-benchmark-view.ts`
- `web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx`

测试：

- `tests/unit/application/evaluations/general_agent_benchmark/`
- `tests/unit/infrastructure/evaluations/general_agent_benchmark/`
- `tests/integration/infrastructure/evaluations/`
- `tests/integration/api/test_general_agent_benchmarks_api.py`
- `tests/unit/application/general_agent/` 中恢复、记忆、上下文和动态 DAG 测试
- `web/tests/general-agent/evaluation-view.test.ts`
- `web/tests/general-agent/display.test.ts`

### 7.3 计划新增的责任边界

文件名由设计阶段决定，责任至少包括：

- typed 行为合同与 oracle 配置。
- `CaseObservation`/证据快照和非空证据引用验证。
- 故障计划、压力计划及其 Harness 适配。
- 资源前后态/作者事实未变比较器。
- 跨 suite/run/case/track 的 Hydration 身份连接校验。
- 37 条清单、`S37/L21`、六门禁最低证据和负例的机械合同测试。

### 7.4 必须删除/替换

- 活动 `external_access_denied` 正式案例。
- 活动 `runtime_checkpoint_recovery` ID；其校验中断语义迁入第 27 条。
- Python 与 JSON 中重复维护的活动 23 案例/轨道/调用清单之一。
- 未被正式执行使用的重复 `CaseSpec/SuiteSpec` 或 `Authored*Spec` 契约之一；保留者需承接全部 typed 字段。
- 所有活动 `23` 硬编码、23/23 冻结条件、API/前端/测试固定断言。
- 统一完成态、交互存在、空证据引用、硬编码安全 `True` 和默认机制通过路径。
- 被新 oracle 取代的 case-ID 特判。

### 7.5 明确保留

- 旧 23 不可变运行/基线工件及其原始数量、身份和结论。
- `docs/历史/` 原始内容。
- 相邻知识抽取、知识召回、运行监控和恢复基础设施。
- 生产稳定 Tool/Subagent 的能力身份；除非独立通用缺陷要求修复，不因 37 条套件改名或复制。

## 8. 复杂度与风险

### 8.1 总体复杂度

总体：**极高**。

依据：

- 影响面横跨固定套件、typed 合同、两轨 runner、密封夹具、生产 Runtime、恢复、Effect、Checkpoint、上下文、工件、Hydration、API 和前端。
- 未知项集中在 Tool 结果复用、Subagent 中断、全损坏 Checkpoint、安全压缩等通用 Runtime 语义。
- 无作者业务数据迁移，但存在活动索引/历史工件读取迁移和新 suite 身份切换。
- 验证必须覆盖 37 案 × 六门禁、负例、两轨隔离、历史身份和相邻回归，不能由单一 happy path 替代。

### 8.2 主要风险

| 风险 | 等级 | 说明 | 缓解方向 |
|---|---|---|---|
| oracle 自证 | 高 | 脚本预写结果或 case 特判直接返回通过 | oracle 只消费独立真实观察；为每类弱代理写负例 |
| suite 双事实漂移 | 高 | JSON、Python 目录、API/前端各维护清单 | 单一权威清单，其他层派生并核对身份 |
| Harness 泄漏生产 | 高 | 为测试增加任务专用能力或 Runtime case-ID 分支 | 故障/压力/oracle 留在 Harness；生产只修通用能力 |
| 恢复重复副作用 | 高 | 中断窗口误判导致 Tool/写入重复 | 调用、结果、Effect、资源后态和对账证据共同判定 |
| Checkpoint 静默重跑 | 高 | 无有效修订时从业务投影重建会重复不确定副作用 | 明确安全失败/人工处理终态，禁止无证据重跑 |
| 上下文“预算过了但事实丢了” | 高 | 只看 Token/字符统计会掩盖行为漂移 | 压缩前后事实身份、下游消费和结果等价共同判定 |
| 无效记忆复活 | 高 | 摘要或分支投影绕过 validity | 对所有载体做零复活证明 |
| 历史 23 被当前 37 覆盖 | 高 | 单活动索引/当前目录污染历史显示 | 不可变工件 + 明确历史索引/读取契约 + run 自身计数 |
| 跨身份工件聚合 | 高 | synthetic/live/comparison 单体有效但不属于同套件 | Hydration 顶层 join 门禁和负例 |
| 前端计数误导 | 中 | 已结束、通过、失败含义混用 | API/视图模型使用实际案例结论，移除回退常量 |
| 现有 Runtime 保护基线冲突 | 中 | `protected_runtime_baseline.json` 会把有意通用修复视为漂移 | 设计明确保护门禁更新条件；先 RED，再更新受保护哈希 |
| 相邻能力回归 | 中 | 评测改动触及运行监控、知识评测或启动装配 | 聚焦回归、固定端口 API/页面验收、启动链检查 |

## 9. 设计阶段推荐调查方向

以下是推荐的调查顺序，不替代设计角色的最终选择：

1. 定义单一 suite typed schema，先机械锁定精确 37 顺序、中文名称、逐案轨道和 `S37/L21`；确定如何清理 `CaseSpec/AuthoredCaseSpec` 重复。
2. 定义最小 `CaseObservation` 与 evidence identity，使 oracle 能读取最终回答、真实调用、产物、资源后态、Effect、Checkpoint、上下文和停止原因，但不复制完整内部轨迹。
3. 为六类门禁分别建立至少一个“旧代理会误过、新 oracle 必须失败”的负例：错误最终回答、错误后态、缺证据、硬编码安全、正确拒绝终态、调用成功但未被消费。
4. 用八个恢复 RED 场景区分 Harness 缺口与生产 Runtime 缺口；优先研究 Tool 结果持久化、Subagent 中断粒度、写后对账和全损坏 Checkpoint。
5. 用八个压力 RED 场景明确 `context.py` 的当前可观察契约，特别是大节点结果投影、压缩等价、无效记忆零复活和零调用拒绝。
6. 明确新旧基线索引与 Hydration join：当前 37、历史 23、synthetic、live 和 comparison 都必须由自身身份决定，不得由页面常量或当前目录覆盖。
7. 最后同步 API/前端动态计数和中文显示；不扩大为页面视觉、导航或移动端改造。

### 当前证据不足、必须继续研究

- Tool 返回结果在何种持久化边界下可由恢复后下游复用，而不复制 Tool 业务事实。
- Subagent 中断后“整次安全重试”与“内部恢复”的正式产品合同及适用边界。
- 所有 Checkpoint 修订无效时已存在从业务 run 投影重新执行的风险；需研究新的显式不可恢复/人工处理状态及兼容影响。
- `context.py` 对第 32—35 条所需结构化投影、语义等价和无效内容跨载体隔离是否已具备足够钩子。
- 旧 23 工件当前的完整可查询集合、现有固定索引保留策略和未来历史分页入口。
- 有意修改生产 Runtime 后，`protected_runtime_baseline.json` 应如何更新而不削弱保护门禁。

## 10. 测试与验证关注点

### 10.1 机械合同

- 精确 37 个唯一 ID、顺序 1—37、中文名称非空。
- `synthetic=37`、`live_provider=21`，任何漂移在案例开始前拒绝。
- suite、fixture、oracle、故障/压力计划、预算和最低证据均纳入内容身份。
- 活动源码、测试、接口和用户文案无当前 `23` 硬编码。

### 10.2 行为与门禁

- 每案六门禁均有非空、存在、哈希/身份一致的证据引用。
- 缺失、损坏、冲突或跨案例证据得到 `INVALID`。
- 调用成功但输出错误、输出正确但后态错误、交互存在但未消费、预设 `True` 均不能通过。
- 正确拒绝、等待人工和不可恢复终态按案例合同判定，不强迫 `completed`。

### 10.3 恢复与上下文

- 八个故障窗口逐项验证累计调用、成功节点不重跑、Effect 精确一次和安全停止。
- 八个压力场景逐项比较压缩/裁剪前后统计、事实身份、模型可见输入和最终行为。
- 当前请求逐字保持；无法安全容纳时零 Tool/Subagent/副作用。

### 10.4 身份、历史和 UI

- 新 37 基线不可覆盖旧 23 工件。
- synthetic/live/comparison suite 身份不一致时禁止聚合和水合。
- 同时读取当前 37 与历史 23 时，各自显示自身数量和结论。
- 页面动态显示通过、失败、无效、待处理和总数，中文名称来自当前套件契约。

### 10.5 相邻与启动

- 通用 Agent Runtime、知识抽取、知识召回、运行监控和恢复回归。
- 若修改 `src/taichu/main.py`、`src/taichu/config.py`、`.env.example`、`web/package.json` 或 `web/next.config.ts`，按根规则验证 `start.bat`。
- 后端真实接口固定 `http://127.0.0.1:8000`，前端固定 `http://localhost:3000`。

## 11. 结论

当前代码库不是绿地：真实 Runtime、密封环境、严格脚本、六门禁聚合、不可变工件、部分恢复和上下文治理均可复用。但现有 23 条套件的“协议消费 + 调用成功 + 完成态 + 存在性/预设真值”不能承载 37 条新准入合同。

后续设计应优先围绕“suite 单一事实源 + typed oracle/证据边界 + 八类恢复/八类压力真实 RED 场景 + 新旧身份隔离 + 最小 UI 同步”综合，而不是把范围缩成数量替换，也不应先决定为每个场景新增生产能力。
