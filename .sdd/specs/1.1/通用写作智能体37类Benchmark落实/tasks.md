# 实现计划

## 执行约束

- 全部实现任务遵循 RED → GREEN → REFACTOR → VERIFY；不得通过放宽断言、预置门禁真值或跳过真实后态读取制造通过。
- 活动 `suite.json`、独立 ClaimCatalog、生产能力 Manifest、Runtime observation 和不可变工件各自保持设计规定的唯一职责，不建立平行事实源。
- 合成轨道完整口径固定为 37 条，真实模型轨道适用口径固定为前 21 条；旧 23 条只作为不可改写的历史身份读取。
- `(P)` 只表示已具备列出的前置任务后可在不重叠文件与状态边界内并行；执行前仍须复核工作树。
- 所有评测写入只作用于逐案密封副本；JSON/JSONL 只作为运行、审计和回放中间态，不成为正文或结构事实源。

- [ ] 1. 建立 Suite@2、选择器与能力覆盖基础
  - 先固定活动清单、轨道和能力目录的唯一来源，再解锁 Oracle、Harness 和运行集成。

- [x] 1.1 以 TDD 落实 Suite@2 的 37 条严格合同
  - 先增加会因当前 23 条清单、旧 ID、未知 union kind、缺失六门禁证据或额外字段而失败的加载测试。
  - 将活动套件升级为 `taichu.general_agent_benchmark.suite@2`，按规格顺序声明 37 个唯一 ID、中文名称、原始请求、场景、setup、终态、断言、证据、调用、脚本和预算合同。
  - 把第 2—6 条标记为检索/RAG 占坑合同；非检索案例引用固定上游结果时保留来源身份，不绑定具体检索算法、索引或数据库。
  - 将 recovery/context fixture、fault/pressure plan、人工决定和预期后态纳入 fixture manifest 与执行身份，所有引用必须在执行前可解析。
  - 可观察完成条件：加载器只接受精确的 37/order/name/track 合同，并在任何案例 workspace 创建前拒绝旧 ID、额外案例、漂移、未知类型或坏引用。
  - 验证 Suite 加载、内容哈希、fixture manifest 和 strict Pydantic 回归测试。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.8, 2.1, 2.2, 3.1, 3.4, 11.2_
  - _Boundary: AuthoredSuiteSpec, AuthoredCaseSpec, suite.json, fixture-manifest.json_

- [x] 1.2 建立共享轨道选择器与执行前拒绝
  - 先写 RED 测试覆盖 Synthetic 完整选择 37、Live 完整选择 21，以及未知、重复、乱序和轨道不适用 ID。
  - 实现 `SuiteSelectionValidator`，让 API、Synthetic runner、Live runner 和冻结器消费同一顺序化 `CaseSelection`。
  - partial selection 可以落运行结果，但必须显式为非完整准入；选择失败时不得创建 run/workspace 或调用 provider。
  - 可观察完成条件：Synthetic 只产生 S37，Live 只产生 L21，所有非法请求以 typed error 和中文说明在执行前终止。
  - 验证 selector 单元测试及“拒绝前零 workspace/provider 调用”集成断言。
  - _Requirements: 1.5, 1.6, 1.7, 12.2, 12.3, 12.7_
  - _Boundary: SuiteSelectionValidator, CaseSelection, SelectionError_
  - _Depends: 1.1_

- [x] 1.3 从 Suite 与生产 Manifest 派生能力覆盖并消除双清单
  - 先写 RED 测试证明未知能力、kind 冲突、缺 handler、schema/handler identity 漂移和生产核心能力无覆盖会使套件无效。
  - 从 `required_invocations` 与生产能力快照派生 case coverage、稳定展示项和 catalog hash，不再维护 `_CASE_IDS`、`CORE_CASES`、`CORE_INVOCATION_EXPECTATIONS`。
  - 保留生产能力集合与稳定能力边界，不为 37 个案例创建任务专用 Tool、Subagent 或固定 DAG。
  - 可观察完成条件：活动能力目录可由 Suite 与生产 Manifest 确定性重建，仓库中不存在会与 Suite 漂移的第二份案例/轨道/调用权威清单。
  - 验证派生目录快照、身份哈希和旧双清单缺席测试。
  - _Requirements: 1.2, 1.8, 2.6, 3.4, 14.1, 14.2_
  - _Boundary: DerivedCapabilityCatalog, production capability snapshot, capability_catalog.py_
  - _Depends: 1.1_

- [ ] 2. 建立独立 ClaimCatalog、Observation、Typed Oracle 与六门禁
  - 用实际 observation 和可解析证据替代脚本自证、调用成功、交互存在与预设真值。

- [x] 2.1 建立独立 ClaimCatalog 与静态规范化注册表
  - 先写 RED 测试覆盖 catalog schema、重复/悬空 claim、非法 normalizer、内容身份漂移和 scripted response 混入真值。
  - 在独立 `claim-catalog.json` 保存 typed claim、极性、有限别名、来源 fixture refs 与允许的 normalizer 版本，并纳入 fixture manifest。
  - 实现严格加载和 canonical hash；建立不扫描模块、不动态导入、无网络/文件/数据库访问的静态 `ClaimNormalizerRegistry`。
  - 让规则、别名、描述符或实现快照变化产生新的 `OracleRuleSetIdentity` 和 execution identity。
  - 可观察完成条件：预期 claim 与脚本响应物理分离，未注册、损坏或身份漂移的规则在 Oracle 执行前被拒绝。
  - 验证 ClaimCatalog/Registry 单元测试与 fixture 身份测试。
  - _Requirements: 2.3, 2.4, 3.2, 3.3, 10.3, 10.8, 11.5_
  - _Boundary: ClaimCatalog, ClaimNormalizerRegistry, OracleRuleSetIdentity_
  - _Depends: 1.1_

- [x] 2.2 (P) 建立 owner-aware CaseObservation 与证据完整性投影
  - 先写 RED 测试覆盖缺失、损坏、跨 suite/case/run、owner 冲突和内容 hash 不一致的 EvidenceRef。
  - 从实际请求、计划、节点、调用、最终回答、工件、资源前后态、Result、Effect、Checkpoint、Context 和 Strict Driver 偏差构建最小 `CaseObservation`。
  - 每个 probe 只接受设计枚举的证据类型与 selector，不开放任意 JSONPath、正则代码、模块路径、动态 import、`eval` 或 shell。
  - 可观察完成条件：每个证据引用都能解析到同一 owner tuple 和有效内容身份；任何缺损或跨身份引用都会产生 typed `INVALID`，不回退为空证据或交互存在。
  - 验证 observation/probe 单元测试及跨身份负例。
  - _Requirements: 2.5, 10.4, 10.5, 10.6, 10.7, 10.8, 11.4, 12.1_
  - _Boundary: CaseObservation, EvidenceRef, EvidenceProbeSpec_
  - _Depends: 1.1_

- [x] 2.3 实现确定性 Typed Oracle 与可枚举断言
  - 先写直接回答、证据消费和修订的正反例，证明脚本正确但实际 final/dataflow/resource diff 错误时仍失败。
  - 以 Unicode NFC、固定空白/标点、有限别名和 typed 主谓宾/极性投影实现纯函数规范化，不调用 LLM judge。
  - 对 `VALID` projection 比较 expected/forbidden claim；关键 span 无法解析或映射互斥 claim 时返回 `UNKNOWN/AMBIGUOUS` 并使相关门禁无效。
  - 实现设计列出的调用、数据流、最终 claim、工件、资源、授权、记忆、恢复、上下文和零副作用断言 union。
  - 可观察完成条件：相同实际 observation 在修改 scripted response 后保持相同 projection/hash，明确错误为 `FAILED`，不可判定为 `INVALID`。
  - 验证 `test_claim_oracles.py` 及 Suite assertion 交叉引用测试。
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 10.3, 10.7, 10.8, 10.9_
  - _Boundary: ClaimNormalizer, Typed Oracle, AssertionSpec_
  - _Depends: 2.1, 2.2_

- [x] 2.4 用真实 observation 构建恰好六类硬门禁
  - 先写 RED 负例覆盖“调用成功但答案错”“工件存在但后态错”“预设安全为真”“空证据”“统一 completed”。
  - Budget 使用实际节点、能力、模型、Token、运行时长与上下文消耗；Verifier、Artifact、Stop reason、Security、Evidence 分别消费对应 typed observation。
  - 对拒绝、等待人工、上下文不安全和 Checkpoint 不可恢复等正确终态按案例合同判断，不强制普通完成态。
  - 任一 Gate `FAILED/INVALID` 必须阻止案例和完整套件通过，分数、通过率或其他 Gate 不得覆盖。
  - 可观察完成条件：每个案例恰有 B/V/A/T/S/E 六个非空门禁结果，且门禁结论可下钻到同 owner 的实际证据。
  - 验证 Gate 聚合器、证据完整性和特殊终态单元测试。
  - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 14.3_
  - _Boundary: GateCondition, evaluate_case_gates, evidence_builder_
  - _Depends: 2.3_

- [ ] 3. 建立 CapabilityResult 生产持久化、父生命周期清理与密封销毁
  - 先修复通用 Runtime 的结果复用与既有父生命周期清理缺口，清除越界扩展，再让恢复 Harness 和逐案隔离收尾消费真实生产契约。

- [x] 3.1 (P) 定义 CapabilityResult owner、身份与 Repository 契约
  - 先写 RED 测试覆盖缺 owner、同 run ID 跨 conversation、非法 StablePathId、路径逃逸和非规范 result ID。
  - 定义不可省略的 `(conversation_id, run_id)` owner，以及包含计划、节点、attempt、能力、输入和 handler/schema 身份的 canonical result payload。
  - 规定 `get_completed`、`commit_completed`、`list_for_run`、`delete_run` 的应用层 Protocol、typed error 和未知父 owner 语义。
  - 可观察完成条件：相同调用在相同 owner 下得到稳定 `cr_<sha256>`，跨 owner 无法命中或伪造，非法标识在创建目录前失败。
  - 验证应用层契约、canonical hash 和 owner 错配单元测试。
  - _Requirements: 5.5, 8.2, 8.3, 8.7, 8.11, 10.7, 10.8, 12.1_
  - _Boundary: CapabilityResultOwner, ResultIdentityPayload, GeneralAgentCapabilityResultRepository_
  - _Depends: 1.1_

- [x] 3.2 实现 per-result record/index 的 create-once 持久化
  - 先写 RED 测试覆盖 record→index 提交窄窗、不同 result 并发、同 result 同内容幂等、异内容冲突、补 index 竞争、重启列举和损坏 fail-closed。
  - 每个 result 使用独立 record/index 文件、canonical JSON、flush/`fsync`、root containment 与 create-once 发布，不建立共享可变索引或内存恢复事实。
  - `get_completed` 只定向读取同 ID record/index；只允许 record 已发布而 index 缺失时定向补条目，禁止扫描 `completed/` 掩盖损坏。
  - `list_for_run` 只枚举 per-result index 并按 `(committed_at, result_id)` 稳定排序；所有 entry→record 关系必须复核 owner/hash。
  - 可观察完成条件：并发和进程重启后不丢结果、不覆盖胜出内容，任何 index/record 损坏、冲突或路径逃逸都明确失败。
  - 验证 `test_capability_result_repository.py` 全部并发、重启和损坏场景。
  - _Requirements: 8.2, 8.3, 8.7, 8.11, 10.7, 10.8, 12.1_
  - _Boundary: JsonGeneralAgentCapabilityResultRepository, per-result record/index store_
  - _Depends: 3.1_

- [x] 3.3 将 CapabilityResult 接入生产执行与恢复顺序
  - 先写 RED 测试证明只读 Tool/Subagent 在结果已提交后恢复时不重调，而写 Tool 仍只通过 Effect/reconcile 恢复。
  - 在唯一生产组合根构造持久 Repository，必填注入 Run Service、执行器与恢复协调器；Harness 只能显式注入 case-scoped 根。
  - 固定恢复顺序为 owner → Effect → Checkpoint integrity → result ID → completed record/index → Context；跨 owner、冲突或损坏立即 fail closed。
  - result record 与 index 都持久后才允许节点成功投影、下游消费和 Checkpoint 推进；记录 reuse/retry 及证据 hash。
  - 同步 `project_assets/readme.md` 的运行/审计职责与非业务事实边界，目录按需创建且不提供单条手工 CRUD。
  - 可观察完成条件：生产 Runtime 与 Harness 使用同一实现，重启后可复用完整结果，写副作用不被 CapabilityResult 绕过。
  - 验证 CapabilityResult 恢复聚焦测试、组合根测试和项目资产目录契约。
  - _Requirements: 8.2, 8.3, 8.7, 8.10, 8.11, 10.6, 10.7, 11.7, 14.6_
  - _Boundary: GeneralAgentRunService, DynamicDagExecutor, recovery coordinator, production composition root_
  - _Depends: 3.2_

- [x] 3.4 移除未授权全局删除扩展并恢复既有父生命周期边界
  - 删除当前工作树中超出本规格授权的删除合同、持久仓储、跨仓储编排、应用启动接线，以及只为这些扩展存在的测试和资产目录说明。
  - 移除稳定删除 scope、删除进度清单、七仓储协调与启动时续跑路径，不保留兼容入口、僵尸配置或孤儿说明。
  - 保留既有 conversation/run 删除入口、CapabilityResult Repository 和 `FixtureIsolationController` 的职责边界，不把 Effect、Checkpoint、Context、Replay、Event 或 Memory 纳入本规格的新删除协议。
  - 可观察完成条件：活动代码、测试、组合根和资产说明中不再存在该越界扩展，既有 conversation/run 生命周期入口与逐案工作区清理入口仍可独立调用。
  - 验证聚焦编译/导入、既有父生命周期与 fixture 清理回归，并用仓库扫描证明越界符号、入口和说明均已清除。
  - _Requirements: 11.3, 11.4, 11.7, 14.6_
  - _Boundary: unauthorized deletion extension cleanup, existing conversation/run lifecycle boundary_
  - _Depends: 3.3_

- [x] 3.5 接通 CapabilityResult 父生命周期清理与 FixtureIsolationController 密封销毁
  - 先写 RED 测试锁定：会话删除在移除父 run 前冻结全部已知 owner，单 run 删除先核对 conversation，并由两条既有入口按 owner 调用 CapabilityResult `delete_run`。
  - CapabilityResult 清理必须幂等；错 owner、清理失败或清理后仍可列举 record/index 时不得把父生命周期清理报告为成功，也不得留下该 owner 的结果孤儿。
  - Benchmark 正常与异常收尾均使用已冻结的 case conversation/run 身份：先走既有父生命周期入口清理 CapabilityResult，再精确删除 case MongoDB，最后由 `FixtureIsolationController` 以原 handle 完成 containment 校验和物理目录销毁。
  - 保存并比较作者活动数据与其他案例工作区 sentinel；CapabilityResult、case 数据库或工作区任一残留、越界变化或清理边界无法证明时，将该案及完整套件判为 `INVALID` 并保留现场。
  - 可观察完成条件：两条父生命周期入口完成后目标 owner 不可再列举；逐案正常/异常收尾均密封销毁自身数据库与工作区，作者数据和其他案例 sentinel 保持不变。
  - 验证 CapabilityResult 父清理、重复/失败语义、workspace handle/路径所有权、正常/异常 case 收尾及残留即 `INVALID` 的聚焦测试。
  - _Requirements: 8.10, 8.11, 10.6, 10.7, 10.8, 11.1, 11.3, 11.4, 11.7, 12.1, 14.6_
  - _Boundary: GeneralAgentRunService parent lifecycle, CapabilityResultRepository.delete_run, FixtureIsolationController, SyntheticEnvironment cleanup_
  - _Depends: 3.3, 3.4_

- [ ] 4. 落实第 1—21 条行为合同与密封夹具
  - 按四个内聚案例族接入真实能力、后态读取和六门禁，不在 Runtime 增加 case-ID 分支。

- [x] 4.1 落实第 1—6 条最小路由、检索与外研合同
  - 先为零能力直接回答、单次正文、三源覆盖、确认态知识、目录真实身份和许可外研建立会失败的端到端断言。
  - 构造逐案独立正文、结构、知识和固定外部来源；第 2—6 条只冻结行为与来源身份，不冻结 RAG 实现。
  - 让最终回答真实消费命中片段/卡/来源，动态检查调用次数、范围、lifecycle、目录解析身份、许可与零真实网络越界。
  - 对非检索主目标使用固定来源时显式标注 fixture provenance，禁止冒充动态检索效果。
  - 可观察完成条件：案例 1—6 分别以规格矩阵的 B/V/A/T/S/E 证据通过，任一错答案、越界来源或未消费结果都会失败/无效。
  - 验证案例 1—6 synthetic 聚焦运行及各自负例。
  - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 11.5_
  - _Boundary: sealed fixtures and behavior oracles for cases 1-6_
  - _Depends: 2.4, 3.5_

- [x] 4.2 落实第 7—11 条证据、多分支、流水线与修订合同
  - 先写 RED 测试覆盖事实/推测混淆、分支输入不同、分支污染、流水线断链、三审依赖和修订破坏受保护内容。
  - 记录 source→evidence→answer、summary→two branches→aggregate、architecture→scene→draft、same draft→three reviews 和 review→diff→revision 的数据流身份。
  - 三审只有存在 overlap interval 证据时才声明物理并发，否则只声明独立可交错；分支消息和工件保持隔离。
  - 草稿始终为候选，正文 byte hash 与写 Effect 保持不变；修订同时验证目标修复和非目标保护。
  - 可观察完成条件：案例 7—11 各自产生可引用工件与真实下游消费证据，任何只调用未消费、串行伪并发或受保护内容漂移都会失败。
  - 验证案例 7—11 synthetic 聚焦运行、分支载体扫描和修订 diff 正反例。
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: sealed fixtures and behavior oracles for cases 7-11_
  - _Depends: 4.1_

- [x] 4.3 落实第 12—17 条预览、授权、拒绝与资源后态合同
  - 先写 RED 测试覆盖预览时写入、授权目标漂移、创建返回未被更新消费、缺少二次确认删除、误删旁项和拒绝后仍 Apply。
  - 动态读取正文、结构和 MongoDB 知识副本的 before/after；所有写入仅作用于批准目标且由真实 Effect/返回 ID/并发值串联。
  - 授权续接绑定逻辑任务、目标资源、预览与授权输入，不要求复用同一 run ID 或内部计划对象。
  - 删除测试同时覆盖取消/缺确认零调用与批准后精确删除；拒绝必须经过预览→授权请求→拒绝→逻辑续接终态。
  - 可观察完成条件：案例 12—17 的资源差异、Effect、人工决定和终态与各自合同完全一致，作者活动事实和其他对象保持不变。
  - 验证案例 12—17 synthetic 聚焦运行、MongoDB/Markdown 后态和授权负例。
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 11.3_
  - _Boundary: sealed fixtures and behavior oracles for cases 12-17_
  - _Depends: 4.2_

- [x] 4.4 落实第 18—21 条运行工作记忆行为合同
  - 先写成对 RED 测试，证明仅检查 active/repair 投影对象集合不足以判定最终行为。
  - 让 active 约束可观察地改变答案；stale 及失效依赖、rejected 错误和 superseded 旧结论在所有模型可见载体与最终输出中缺席。
  - rejected 案扫描父工作记忆、两个分支输入/输出、Subagent envelope、聚合、摘要与最终回答；superseded 只保留隔离审计历史。
  - 始终使用“运行工作记忆”语义，不把它改称长期记忆或小说知识事实。
  - 可观察完成条件：案例 18—21 的最终答案和分支行为准确反映 validity，任一无效内容复活都会使案例失败。
  - 验证案例 18—21 synthetic 聚焦运行、paired answer delta 和全载体 sentinel 扫描。
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: sealed fixtures and behavior oracles for cases 18-21_
  - _Depends: 4.3_

- [ ] 5. 恢复第 22—29 条 Harness 与生产不变量
  - 以持久 FaultPlan 和真实 Runtime 恢复入口验证八个故障窗口。

- [x] 5.1 建立 typed FaultPlan 与恢复密封夹具
  - 先写 RED 测试覆盖未知故障点、重复 ordinal、非 once 触发、跨 case 状态共享和异常退出后作者事实变化。
  - 用固定 `FaultPoint`、ordinal、once 和 run identity 持久化已触发序号；Harness 只调用生产通用 fault hook，不传 case ID。
  - 为 22—29 分别准备计划、结果、Subagent、授权、Effect、校验、多中断和 Checkpoint revision 夹具及预期后态。
  - 每案复制正文、结构、知识、对话、工作记忆、Run、Result、Effect、Checkpoint、Context，并在正常/异常结束后校验作者活动事实与其他 workspace 哨兵。
  - 可观察完成条件：同一 run 的故障按声明顺序各触发一次，跨案例无共享可变状态，异常退出仍能证明隔离。
  - 验证 fault plan、fixture hash、Strict Driver 偏差与事实哨兵测试。
  - _Requirements: 8.11, 11.1, 11.2, 11.3, 11.4, 11.6, 11.7_
  - _Boundary: FaultPlan, fault_pressure adapter, recovery fixtures_
  - _Depends: 3.5, 4.4_

- [x] 5.2 落实规划后恢复与 Tool 结果复用案例 22—23
  - 先写 RED 故障测试分别停在 plan durable/首节点前，以及 Result record+index durable/下游消费前。
  - 案例 22 恢复同一 plan hash，planner 与首节点累计各一次；首节点前保持零副作用。
  - 案例 23 以同 owner 定向 rehydrate 原 Tool 结果，下游消费同一 result/index hash，Tool 累计一次。
  - 单独覆盖 record 已发布/index 未发布的定向补完，以及真正 commit 前只读安全重试，避免混冒 #23。
  - 可观察完成条件：两案恢复后完成且计划/Tool 不重跑，证据包显示明确复用项、重试项和累计次数。
  - 验证案例 22—23 故障注入测试和 CapabilityResult 恢复回归。
  - _Requirements: 8.1, 8.2, 8.11, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: recovery cases 22-23, plan checkpoint and completed capability result reuse_
  - _Depends: 5.1_

- [x] 5.3 落实 Subagent 中断与授权等待恢复案例 24—25
  - 先写 RED 故障测试证明 Subagent 半成品会被误消费或授权等待重启后预览/资源身份漂移。
  - 案例 24 只把完整 Subagent envelope 作为父级可见提交点；半成品在工作记忆、Result、Checkpoint、artifact 和最终答案中全部缺席。
  - 无父级可见副作用的 Subagent 可整次重试，已成功上游保持一次，最终完整结果只提交/消费一次。
  - 案例 25 重建同一授权请求摘要、预览和目标资源，保持 WAITING_HUMAN，等待与恢复期间零写入。
  - 可观察完成条件：案例 24 只消费完整结果，案例 25 恢复同一待处理请求且不重复计划/预览/写入。
  - 验证案例 24—25 故障注入、全载体半成品扫描与 pending human identity 测试。
  - _Requirements: 8.3, 8.4, 8.11, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: recovery cases 24-25, Subagent complete-envelope boundary, authorization recovery_
  - _Depends: 5.2_

- [x] 5.4 落实写后对账与校验中断恢复案例 26—27
  - 先写 RED 故障测试分别停在真实写入后/Effect success 前，以及 verification started/verdict 前。
  - 案例 26 优先依据真实资源与 Effect 对账；确定成功时副作用累计一次，无法确定时进入可审计人工处理状态并禁止盲目重写。
  - 案例 27 以同一 run 继续校验，故障前成功只读节点保持一次，最终产生校验与恢复证明。
  - 第 27 条明确承接被移除旧 `runtime_checkpoint_recovery` 的校验中断语义，不保留旧正式案例。
  - 可观察完成条件：案例 26 的 Effect 链和资源后态一致，案例 27 不重跑已成功节点并完成校验。
  - 验证案例 26—27 故障注入、Effect reconcile 和只读节点累计次数测试。
  - _Requirements: 8.5, 8.6, 8.10, 8.11, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 14.2_
  - _Boundary: recovery cases 26-27, Effect reconciliation, verification resume_
  - _Depends: 5.3_

- [x] 5.5 落实多次中断与 Checkpoint 完整性案例 28—29
  - 先写 RED 测试覆盖两次有序故障、计划漂移、成功节点/Effect 重复、坏尾回退、线程错配、版本不兼容和全修订损坏。
  - 案例 28 在同 owner 下执行两个不同 fault ordinal，保存两次 RecoveryDecision，确保每个 Result/Effect 唯一且最终完成。
  - 案例 29 在恢复前 `inspect_thread`，只选择最新明确有效修订并保留坏修订证据；无有效修订时 STOP、`FAILED,resumable=false`、零静默重跑。
  - 任一 Effect `UNKNOWN/REQUIRES_HUMAN` 优先于 Checkpoint 自动恢复，停止在可审计安全终态。
  - 可观察完成条件：案例 28 两次恢复无重复副作用，案例 29 只从有效修订恢复或明确不可恢复，绝不从业务投影从头执行。
  - 验证案例 28—29、有/无有效 revision、线程/版本和零重跑测试。
  - _Requirements: 8.7, 8.8, 8.9, 8.10, 8.11, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: recovery cases 28-29, ordered FaultPlan, Checkpoint integrity decision_
  - _Depends: 5.4_

- [ ] 6. 落实第 30—37 条五层上下文压力与 AssemblyTrace
  - 保持固定五层名称、当前请求原文和无效记忆隔离，用结果合同而非 Token 未超限判定。

- [x] 6.1 扩展 AssemblyTrace 与上下文快照兼容读取
  - 先写 RED 测试覆盖缺失 pre/post 分类统计、protected/omitted refs、required paths、current request hash 和投影来源身份。
  - 在 Context Snapshot 保存五层前后 count/char/token estimate、裁剪、digest/fallback、受保护/遗漏引用和大结果投影统计。
  - 旧快照只读时允许 trace 默认空；新 37 上下文案例缺少 trace 必须无效，不得用当前数据回填旧工件。
  - 长期记忆保持当前真实空值，不把工作记忆、小说知识或检索片段迁入长期记忆制造五层非空。
  - 可观察完成条件：每次新上下文装配都可从 snapshot 复核五层输入、收缩决策、保留/遗漏事实和当前请求内容身份。
  - 验证 context snapshot round-trip、旧 JSON 兼容和 AssemblyTrace 完整性测试。
  - _Requirements: 7.6, 9.9, 10.2, 10.7, 11.2, 12.1_
  - _Boundary: GeneralAgentContextSnapshot, AssemblyTrace, context_snapshot_repository_
  - _Depends: 1.1, 2.2_

- [x] 6.2 落实长历史、工作记忆、大结果与多来源压力案例 30—33
  - 先写固定 seed/hash 的 RED 压力测试，使早期有效事实、直接依赖、required paths 或多来源关键事实丢失时失败。
  - 案例 30 保留早期有效作者约束、近期原始消息和当前请求；案例 31 先移除低优先级过程并保留当前指令、未决问题和直接依赖。
  - 案例 32 投影超大结构化结果时保留合同字段、完整计数与 source refs，不把未展示条目推断为不存在。
  - 案例 33 按五层边界和任务必要性收缩历史、工作记忆、检索结果、节点工件与当前请求，保护稳定记忆和当前请求。
  - 可观察完成条件：案例 30—33 在压力下完成目标，AssemblyTrace 明确证明保留事实影响最终答案且遗漏项符合优先级。
  - 验证案例 30—33 聚焦运行、pre/post trace 和错误裁剪负例。
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.9, 9.10, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: context pressure cases 30-33, ContextAssembler projection and trimming_
  - _Depends: 6.1, 5.5_

- [x] 6.3 落实等价、无效记忆、长请求与安全拒绝案例 34—37
  - 先写 RED 成对/哨兵测试，使语义合同漂移、无效内容经任一摘要载体复活、请求字节变化或拒绝前发生能力调用时失败。
  - 案例 34 比较固定 claim IDs、必要能力集合/拓扑、protected refs、目标工件和资源差异，不比较逐字输出且不调用 LLM judge。
  - 案例 35 扫描 basis、repair、digest、fallback、history、node、Subagent 与 final，确保 stale/rejected/superseded sentinel 零复活。
  - 案例 36 比较 intake/snapshot/model-visible 当前请求 byte hash，保持空白、顺序和约束；案例 37 在规划前返回中文不安全组装原因并保持零 Tool/Subagent/Result/Effect。
  - 可观察完成条件：案例 34—37 分别证明结果合同等价、无效载体隔离、当前请求逐字保持和无法安全容纳时 fail-closed。
  - 验证案例 34—37 聚焦运行、全载体扫描、byte hash 和拒绝前零调用测试。
  - _Requirements: 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7_
  - _Boundary: context pressure cases 34-37, result_contract_equivalence, context unsafe terminal_
  - _Depends: 6.2_

- [ ] 7. 集成 Synthetic、Live、Observation、Oracle 与不可变工件
  - 两条 runner 共享选择和判定，仅替换模型网关与轨道适用集。

- [x] 7.1 接通完整 Synthetic 37 的统一执行与密封销毁
  - 先写 RED 集成测试证明脚本走完、交互存在或能力成功不能绕过 observation/oracle/Gate。
  - Synthetic 由 selector 获取 37 条，逐案构造密封环境，执行真实 Runtime，再按统一 Observer → Typed Oracle → 六 Gate 生成结论。
  - Strict Scripted Driver 只控制模型/人工决定/固定外研/故障时机；意外交互、乱序、未消费、额外交互或输入不匹配形成可定位失败/无效证据。
  - 正常与异常退出均先通过既有 conversation/run 父生命周期清理该案 CapabilityResult，再精确删除 case MongoDB，并由 `FixtureIsolationController` 密封销毁 handle 所属工作区；任一残留即 `INVALID`，同时证明作者活动事实与其他案例 sentinel 未变。
  - 可观察完成条件：完整 Synthetic 运行产生 37 个各含六 Gate 和完整证据的 case rows；缺任一案例/Gate/evidence 时绝不形成完整准入。
  - 验证 Synthetic 37 集成运行、脚本偏差、隔离越界与部分运行测试。
  - _Requirements: 1.5, 2.3, 2.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 11.1, 11.3, 11.4, 11.6, 11.7, 12.1, 12.2, 12.3_
  - _Boundary: SyntheticBenchmarkRunner, SyntheticEnvironment, StrictScriptedDriver_
  - _Depends: 4.4, 5.5, 6.3_

- [x] 7.2 (P) 接通 Live 21 的统一判定与 provider 隔离
  - 先写 RED 集成测试覆盖 Live 误跑第 22—37 条、绕过 selector、使用不同 Oracle/Gate 和 provider 受阻污染 Synthetic。
  - Live 只替换模型 gateway，其余 selection、observation、normalizer、Oracle、Gate 和工件合同与 Synthetic 相同。
  - provider `BLOCKED/ERROR` 形成独立轨道结论；调用前必须满足同 Suite 前 21 条资格，失败不修改 Synthetic admission。
  - 可观察完成条件：Live 完整选择精确为 21，轨道不适用请求在 provider 调用前拒绝，provider 受阻不改变 37 条合成结论。
  - 验证 Live selection、共享判定、provider blocked/error 和零提前调用测试。
  - _Requirements: 1.6, 1.7, 12.7, 12.8_
  - _Boundary: LiveBenchmarkRunner, live model gateway adapter_
  - _Depends: 1.2, 2.4, 4.4_

- [x] 7.3 统一案例证据包、真实计数与运行结论
  - 先写 RED 测试覆盖 owner/row 不完整、跨身份 evidence、partial run、failed/invalid/pending 和缺失 case 时误报完整通过。
  - 每条 case row 保存原始输入身份、轨道、实际调用、assertion、六 Gate、EvidenceRef、最终产物/资源后态、终态和 Result/Effect/Checkpoint/Context refs。
  - 从实际 rows 计算 total、pending、passed、failed、invalid、unfinished/cancelled；完整准入只允许完整 Synthetic 37 且全部通过。
  - 同身份重复运行比较规范化案例结论、Gate 与关键证据身份，报告非预期漂移。
  - 可观察完成条件：任一总览数字都能下钻到运行自身 rows 和同 owner 证据，partial/invalid/provider blocked 不会冒充 37/37。
  - 验证 run model、evidence builder、完整性与重复运行漂移测试。
  - _Requirements: 10.7, 10.8, 10.9, 12.1, 12.2, 12.3, 12.6, 12.7, 12.8, 13.2_
  - _Boundary: Benchmark run models, evidence package, run summary aggregation_
  - _Depends: 7.1, 7.2_

- [ ] 8. 建立三层身份、历史 Hydration 与冻结目录
  - 让新 37、Live 21、模型比较和旧 23 只通过关系专属合同连接。

- [x] 8.1 (P) 实现 ArtifactIdentity、ComparabilityKey 与声明差异
  - 先写 RED 正反例覆盖 suite/fixture/catalog/oracle/runtime 漂移、case projection 错配、差异漏报/多报和调用方自选忽略字段。
  - 区分单工件完整身份、关系必须相等的可比键和关系固定 allowlist 内的声明差异。
  - 分别实现 Synthetic37→Live21 资格与 Live 多模型比较；失败返回 typed `NOT_QUALIFIED`、`CASE_SET_MISMATCH`、`INCOMPATIBLE_*` 或 `UNDECLARED_DIFFERENCE`。
  - 可观察完成条件：合法 37→21 和 Live 模型差异可连接，任何禁止或未声明差异都不返回拼接/聚合对象。
  - 验证 `test_artifact_identity.py` 与关系专属正反例。
  - _Requirements: 1.8, 12.7, 12.8_
  - _Boundary: ArtifactIdentity, ComparabilityKey, DeclaredDifferences, experiments relation validation_
  - _Depends: 1.1, 2.3_

- [x] 8.2 实现当前 37 与旧 23 的只读 Hydration
  - 先写 RED 测试覆盖 child ref/hash 冲突、用当前身份补旧字段、把历史 23 参与 37 聚合和旧身份进入 Live 比较。
  - 每个工件先校验自身 schema/hash/ref，再由关系专属 Joiner 处理；关系失败时双方仍可独立查询但不拼接。
  - 旧 @1 缺少新字段时只显示自身 rows/counts 与 `unknown/not_available`，不得回写旧工件或填入当前 Suite/fixture/oracle 值。
  - 可观察完成条件：同一列表可同时读取当前 37 与旧 23，并各自保持原数量、中文名称、身份和历史结论。
  - 验证当前/历史 Hydration、identity substitution 和不可变旧工件测试。
  - _Requirements: 12.5, 12.8, 13.4, 14.5_
  - _Boundary: BenchmarkIdentityJoiner, artifact_hydration, historical @1 adapter_
  - _Depends: 7.3, 8.1_

- [x] 8.3 实现不可覆盖基线 Manifest、活动目录与冻结脚本
  - 先写 RED 测试证明 partial、缺 Gate/evidence、非 37 selection、Live 结果或当前 `23` 常量不能冻结 Synthetic admission。
  - 写 immutable baseline artifact 与 `BaselineManifest`，记录完整身份、实际计数和 artifact ref/hash，再原子更新 baseline catalog。
  - 从旧 active ref 建只读 history manifest 后才切 `active_synthetic_ref` 到新 37；冻结或历史生成失败时保留旧指针，新 immutable 工件不删除。
  - 三个冻结脚本从 Suite/结果派生 37/37 或 21/21，不含活动 23 常量；Live 只能形成自身轨道工件，不能生成 Synthetic admission。
  - 可观察完成条件：只有完整 37 条六 Gate 全通过时产生新的不可覆盖准入 Manifest，旧 23 仍由历史 ref 原样可读。
  - 验证冻结资格、原子指针回滚、历史目录和重复身份测试。
  - _Requirements: 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 14.4, 14.5_
  - _Boundary: BaselineManifest, benchmark-baseline-catalog, synthetic/live freeze scripts_
  - _Depends: 8.2_

- [ ] 9. 接通 Benchmark API 与最小桌面 UI
  - API 与页面只消费套件/运行自身事实，不重构既有路由、导航、布局或视觉。

- [x] 9.1 扩展 Suite detail、运行提交校验与动态 API 汇总
  - 先写 RED API 测试覆盖 37 顺序/中文名/轨道、selection 422、拒绝前零 run/workspace 和历史运行自身计数。
  - Suite detail 返回 content hash、case count/order、track counts 及案例 ordinal/ID/中文 name/summary/tracks，不泄漏脚本响应、Oracle 配置或敏感 fixture。
  - POST runs 在创建前调用 selector；未知、重复、乱序、不适用和 identity mismatch 返回 HTTP 422 中文消息与最小技术详情。
  - 运行汇总从自身 rows 计算状态；历史 @1 缺 summary 时从自身 rows Hydrate，禁止使用当前 Suite 回填。
  - 可观察完成条件：真实接口返回 S37/L21 和运行真实计数，非法选择不产生持久化副作用。
  - 验证 Benchmark API 集成测试和历史 Hydration API 回归。
  - _Requirements: 1.5, 1.6, 1.7, 13.1, 13.2, 13.4, 13.5_
  - _Boundary: Benchmark application service, FastAPI schemas and routes_
  - _Depends: 7.3, 8.2_

- [x] 9.2 让既有评测 Shell 动态显示当前 37 与历史 23
  - 先写前端 RED 测试覆盖当前 37、Live 21、历史 23、partial、failed、invalid、pending、suite 切换和请求错误。
  - 扩展 strict TypeScript detail/case/summary 类型和 suite detail 客户端，切换 Suite 时 abort 旧请求，提交期间禁止重复提交。
  - view/display 从实际 rows 计算结论，优先 API 中文 name/summary；旧工件缺 detail 时只使用历史 fallback。
  - 删除“23 条固定任务”和当前 23 默认值；仅在 `passed===total && total>0` 时显示动态 `${passed}/${total} Benchmark 全部通过`。
  - 复用 `GeneralAgentEvaluationShell` 和现有本地组件，不新增依赖、路由、布局、视觉、动效或移动端适配；所有错误与状态文案为中文。
  - 可观察完成条件：当前完整运行显示 37/37，Live 显示 21 条适用案例，历史显示自己的 23/23，partial/invalid 不显示完整通过。
  - 验证 `npm run test:general-agent` 中的 evaluation view/display 测试。
  - _Requirements: 13.2, 13.3, 13.4, 13.5, 13.6, 14.4_
  - _Boundary: general-agent-benchmark TypeScript client/view/display, GeneralAgentEvaluationShell_
  - _Depends: 9.1_

- [ ] 10. 执行破坏式替换与旧活动口径清理
  - 在新合同和消费者接通后移除所有已被替代的活动实现，同时保留历史快照。

- [x] 10.1 清除旧正式案例、重复模型和 case-ID 特判
  - 先写防回归测试/扫描，要求活动套件、能力目录、runner、测试预期和当前展示均不含旧 `external_access_denied`。
  - 移除旧 `runtime_checkpoint_recovery` 正式案例，仅由第 27 条保留校验中断行为语义。
  - 删除被 Suite@2 合并后的重复 `CaseSpec/SuiteSpec` 或 `Authored*` 模型，以及 runner/environment 中被 typed Oracle 替代的 case-ID 分支。
  - 复核任务 3.4 的越界扩展清理，确保活动代码、测试、组合根和资产说明只保留 CapabilityResult 父生命周期与 `FixtureIsolationController` 两条获授权清理边界。
  - 保留旧 immutable artifacts 和历史文档原内容，不修改或重新标记旧 23 身份。
  - 可观察完成条件：活动执行路径只承认 37 条新 ID，旧两个 ID 在执行前被拒绝，历史 23 仍可读，且越界清理实现没有残留或旁路。
  - 验证全仓活动路径扫描、Suite banned-ID 和历史 Hydration 回归。
  - _Requirements: 1.3, 1.4, 11.3, 11.4, 14.1, 14.2, 14.5, 14.6_
  - _Boundary: active suite/catalog/runner model cleanup_
  - _Depends: 7.3, 8.2, 9.2_

- [x] 10.2 清除弱 Gate 与预设通过路径
  - 先写负例确保统一完成态、交互存在、空 `evidence_refs`、`security_ok=True` 和非目标案例默认机制通过都会阻止验收。
  - 删除 Synthetic/Live/environment 中的预设安全真值、`bool(interaction_records)`、空证据和统一 `completed` 判定。
  - 删除仅验证记忆对象状态集合和普通案例默认机制通过的旧逻辑，所有案例统一依赖 typed observation/oracle/Gate。
  - 可观察完成条件：活动代码不存在弱代理通过路径，拒绝/等待/安全失败按 typed terminal 正确判定，其余案例必须提供真实行为证据。
  - 验证 Oracle/Gate 负例、特殊终态和全仓弱模式扫描。
  - _Requirements: 2.3, 2.4, 7.5, 9.10, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 14.3_
  - _Boundary: legacy Gate condition and mechanism cleanup_
  - _Depends: 2.4, 7.3_

- [x] 10.3 清除活动 23 常量并保留历史自身口径
  - 先增加仓库级扫描，区分允许的历史 fallback/不可变工件与禁止的活动代码、测试、API、冻结器和用户文案。
  - 删除活动 `23`、`23/23`、23 条默认值和固定任务文案，所有当前数量从 Suite 或运行 rows 派生。
  - 保留历史只读 adapter 对旧 23 自身计数和中文说明的明确支持，禁止用当前 37 覆盖。
  - 可观察完成条件：活动入口没有写死当前 23，加载旧工件时仍准确显示其自己的 23 条身份和结论。
  - 验证仓库级扫描、当前/历史 API/UI 和冻结脚本回归。
  - _Requirements: 12.5, 13.2, 13.3, 13.4, 14.4, 14.5_
  - _Boundary: active count constants across backend, API, freeze scripts, tests and UI_
  - _Depends: 8.3, 9.2, 10.1_

- [ ] 11. 完成全量回归、固定端口验收与新 37 基线
  - 以可复现命令和真实服务证据证明所有案例、相邻系统、启动约束和历史兼容。

- [x] 11.1 执行 37 条机械合同、负例与后端全量相关回归
  - 运行 Suite@2 的 37/order/name、S37/L21、旧 ID 缺席、union strict、selector 零副作用和活动 23/弱模式扫描。
  - 运行 ClaimCatalog/Oracle/Gate 正反例、CapabilityResult 并发/损坏/重启与父生命周期清理、`FixtureIsolationController` 正常/异常密封销毁、八恢复与八上下文压力测试。
  - 执行完整 Synthetic 37，逐案核对唯一目标、六 Gate、证据、资源后态和隔离；验证 partial/failed/invalid 不产生完整准入。
  - 回归通用 Runtime、运行监控、知识抽取、知识召回、现有 Effect/Checkpoint/Context、既有 conversation/run 生命周期和历史工件读取。
  - 可观察完成条件：全部聚焦及相邻后端测试通过，37 个 case row 各有六 Gate 且没有作者事实或跨 case 污染。
  - 把实际命令、通过数量、工件身份和失败修复记录纳入实现报告，供独立实现校验复验。
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 3.1, 3.2, 3.3, 3.4, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9, 9.10, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.1, 14.2, 14.3, 14.4, 14.5, 14.6_
  - _Boundary: backend specification regression and sealed Synthetic 37 acceptance_
  - _Depends: 10.1, 10.2, 10.3_

- [x] 11.2 执行前端自动回归与桌面信息架构检查
  - 运行 `npm run test:general-agent`，覆盖当前 37、Live 21、历史 23、partial、failed、invalid、pending 和中文错误。
  - 运行 `npm run lint` 与 `npm run build`，确认 strict 类型、无新增依赖且既有页面路由/导航/布局/视觉不变。
  - 检查所有用户可见案例名、说明、状态和错误为中文，技术 ID/hash 只在详情或证据视图出现。
  - 可观察完成条件：前端测试、lint、build 全部通过，现有桌面 Shell 仅发生数据契约和动态显示变化。
  - 记录实际命令与输出到实现报告，供独立实现校验复验。
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.4, 14.6_
  - _Boundary: web automated regression and desktop information architecture_
  - _Depends: 9.2, 11.1_

- [x] 11.3 验证 start.bat、固定端口 API 与桌面页面
  - 启动前探测 `127.0.0.1:8000` 和 `localhost:3000`；正常本项目服务直接复用，异常时按 `start.bat` 规则处理固定端口，禁止换用 8001/3001。
  - 因生产组合根修改 `src/taichu/main.py`，运行并验证根 `start.bat`；等待热重载后用真实后端接口确认新代码已加载，失败时自动按固定端口规则重启 8000。
  - 调用 Suite detail 核对 37/order/中文名/S37/L21；提交非法轨道选择核对 422 与零 run/workspace；核对 partial/invalid 不显示完整通过。
  - 在既有评测页面同时查看当前 37 与历史 23，确认各自总数、中文名称、结论和技术详情正确。
  - 可观察完成条件：固定端口真实服务完成 API/UI 端到端验收，启动脚本未被组合根和依赖注入变更破坏。
  - 记录端点响应、页面验收和启动证据到实现报告，供独立实现校验复验。
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 14.4, 14.6_
  - _Boundary: start.bat, production composition root, fixed-port API/UI acceptance_
  - _Depends: 11.2_

- [x] 11.4 冻结新 37/37 基线并复核历史与分轨身份
  - 在与测试一致的代码、Suite、fixture、catalog、Oracle 和 Runtime 身份下执行完整 Synthetic 37；只有 37 案各自六 Gate 全部通过才调用冻结入口。
  - 复跑相同身份并比较规范化 case/Gate/关键证据，任何非预期漂移必须阻止新 active 指针切换。
  - 冻结新的 immutable baseline/Manifest，确认 catalog active 指向新 37、history refs 保留旧 23，旧工件内容/hash/结论未改变。
  - 验证 Synthetic37→Live21 资格合同；provider 不可用时只记录 Live 受阻，不改变新 Synthetic admission。
  - 可观察完成条件：获得可独立复核的新 37/37 基线，旧 23 原样可读，Live 只具 21 条资格且不存在跨身份混合。
  - 汇总最终对象 hash、测试/端口证据和清理扫描到实现报告；随后由全新 `validate-impl` 上下文独立核对实际 diff、测试、旧实现清理、启动约束和基线工件。
  - _Requirements: 1.5, 1.6, 1.8, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 13.2, 13.3, 13.4, 14.5, 14.6_
  - _Boundary: immutable Synthetic 37 baseline, history catalog, relation-specific identity verification_
  - _Depends: 11.1, 11.2, 11.3_
