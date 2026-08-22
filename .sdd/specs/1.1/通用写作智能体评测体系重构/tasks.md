# 通用写作智能体评测体系重构实现任务

## 执行约束

- 本计划按“契约与持久化基础 → 隔离执行与证据 → 工作记忆硬门禁 → 判定与生命周期 → 首轮闭环 → API 与前端 → 原子切换与真实运行验收”的顺序执行。
- 本规格不设置并行候选：各批次共享评测契约、工件索引、固定端口、Runtime 组合根或首轮冻结状态，且每项必须保持 RED → GREEN → REFACTOR → VERIFY 的可恢复链路，不满足安全并行条件。
- 每个可执行任务都必须先提交或保存失败测试及失败证据；不得先写生产实现再补测试。VERIFY 失败时停留在当前任务修复，不得带病推进。
- 新体系只使用设计文档中的正式名称，不提供旧五维模型、旧 API、旧结果或旧前端契约的别名、适配器、映射器、读取器或回退路径。
- 实现期间不得修改既有 Runtime 审计字段、审计 ID、写入顺序和正常组合根；评测专用组合必须通过独立入口接入。

- [ ] 1. 建立新评测领域契约与权威基准目录

  - [x] 1.1 定义基准、轨道、用例、预算与能力快照的不可变契约
    - RED：先为 `SuiteSpec`、`TrackSpec`、`CaseSpec`、`CapabilityCatalogSnapshot`、`ResourceBudget`、`BudgetObservation` 编写契约测试，覆盖稳定 ID、序列化确定性、非法预算和未知能力拒绝；运行并记录缺少新契约的预期失败。
    - GREEN：实现上述正式契约及校验规则，明确 deterministic synthetic 与 live provider 两条轨道，并确保能力快照只能引用真实注册能力。
    - REFACTOR：抽取共享的稳定标识、枚举和确定性序列化边界，删除任何旧五维评分命名、兼容字段或自由格式能力引用。
    - VERIFY：运行契约测试并生成同一输入两次序列化字节完全一致的证据；非法能力、超预算和重复 ID 均产生结构化失败。
    - _Requirements: 1.1, 1.8, 1.11, 1.13, 1.16, 1.17, 1.19, 1.23, 2.1, 2.2, 2.3, 2.4, 2.5_
    - _Boundary: 新评测领域模型与序列化契约。_

  - [x] 1.2 定义类型化预期工件、验证器和结论契约
    - RED：先为五类预期工件 `final_answer`、`source_reference`、`capability_artifact`、`write_candidate`、`human_intervention` 以及 `VerifierSpec`、`VerifierResult`、`GateResult`、`CaseConclusion` 编写正反例测试；运行并记录旧自由字典无法满足类型约束的失败。
    - GREEN：实现类型化工件、验证器、门禁与用例结论模型，禁止以未声明字段或自由文本替代正式判定来源。
    - REFACTOR：统一判定枚举、错误定位和 JSON Schema 生成逻辑，使每种工件拥有独立且可扩展的验证边界。
    - VERIFY：运行模型与 Schema 快照测试，确认五类工件均能被独立校验，缺失必填字段和非法判定值稳定失败。
    - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7, 13.8, 13.9, 13.10, 13.11, 13.12, 13.13, 13.14, 13.15_
    - _Depends: 1.1_
    - _Boundary: 预期工件、验证器与用例结论模型。_

  - [x] 1.3 定义套件运行、机制判定、证据与提供商状态契约
    - RED：先为 `SuiteRunLifecycle`、`SuiteConclusion`、`MechanismGateResult`、`MechanismConclusion`、`MechanismDecisionSource`、`EvidenceAvailability`、`EvidenceBundle`、`CaseResultRow`、`SuiteRun`、`SuiteArtifact`、`ProviderExecutionState` 编写状态组合测试；运行并记录非法终态和证据伪装的失败。
    - GREEN：实现正式状态机与证据模型，限定只有 `completed` 可拥有 `passed|failed|invalid|not_evaluated` 结论，其他生命周期的结论必须为 `null`。
    - REFACTOR：集中维护生命周期转换表、证据可用性与机制判定来源，避免服务层重复解释状态。
    - VERIFY：运行全状态矩阵测试，确认 `blocked`、`error`、`cancelled`、`unfinished` 被原样保存且不能被折叠为业务失败。
    - _Requirements: 5.5, 5.6, 5.8, 5.9, 5.21, 6.9_
    - _Depends: 1.2_
    - _Boundary: 套件生命周期、机制结论、证据与提供商状态。_

  - [x] 1.4 建立 23 个业务用例与 29 项真实能力调用的权威目录
    - RED：先编写目录完整性测试，逐一断言 23 个正式用例、两条适用轨道、17 个 Tool、12 个 Subagent 以及 30 条调用预期；运行并记录当前旧 manifest 缺项和名称漂移的失败。
    - GREEN：以 `SuiteSpec` 和 `CaseSpec` 建立 23 个业务用例，明确用例 17、23 仅属于 synthetic，其余指定用例覆盖双轨道；为每条能力记录实际 invocation 与 outcome 的验收要求。
    - REFACTOR：把能力引用统一绑定到 `CapabilityCatalogSnapshot`，移除基于 allowed、manifest 或 registration 即视为覆盖的逻辑。
    - VERIFY：运行目录审计，输出 23/23 用例、17/17 Tool、12/12 Subagent、30/30 调用预期均有实际调用与结果断言的机器可读报告。
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8, 1.9, 1.10, 1.11, 1.12, 1.13, 1.14, 1.15, 1.16, 1.17, 1.18, 1.19, 1.20, 1.21, 1.22, 1.23, 1.24, 1.25_
    - _Depends: 1.1, 1.2, 1.3_
    - _Boundary: 基准目录、业务用例与能力覆盖声明。_

- [ ] 2. 在 Runtime 工厂之前完成隔离、仓储、门禁、关联与 Inbox CAS 基础

  - [x] 2.1 实现固定输入快照和隔离工作区控制器
    - RED：先为 `FixtureSnapshotSpec`、`FixtureIsolationController` 编写测试，覆盖不可变输入、每次运行独立工作区、越界写入检测、失败清理和重放一致性；运行并记录缺少隔离层的失败。
    - GREEN：实现 fixture 快照校验、独立工作区创建与销毁、允许写集和越界检测，确保 synthetic 与 live 都不能污染正文、知识结构事实或其他运行。
    - REFACTOR：把路径规范化、快照摘要和隔离清理收敛为单一基础设施边界，所有目录按需创建且不使用 `.gitkeep`。
    - VERIFY：连续运行同一 fixture 两次，确认输入摘要一致、工作区互不共享、越界写入被判为 `fixture_isolation_failed` 且无残留。
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 3.14, 3.15, 3.16, 3.17_
    - _Depends: 1.4_
    - _Boundary: 固定输入、临时工作区与副作用隔离。_

  - [x] 2.2 建立 append-only 工件仓储、索引、幂等与闭包租约
    - RED：先为 `project_assets/derived/general_agent_benchmarks/` 下 runs、experiments、iterations、issue-correlations、comparisons、closure-leases、indexes、idempotency、workspaces 编写仓储测试；运行并记录目录与原子写语义缺失的失败。
    - GREEN：实现运行工件的 append-only 写入、原子替换索引、幂等提交和闭包租约，拒绝覆盖已冻结工件。
    - REFACTOR：统一路径解析、摘要验证、临时文件提交和崩溃恢复逻辑，保持 JSON/JSONL 仅为评测运行与审计中间态。
    - VERIFY：注入写入中断、重复请求和竞争闭包，确认工件不损坏、索引可恢复、冻结对象不可变且重复请求返回同一结果。
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12, 2.13, 2.14, 2.15, 2.16_
    - _Depends: 2.1_
    - _Boundary: 新评测工件根目录、索引、幂等与闭包租约。_

  - [x] 2.3 建立评测关联记录和机制门禁的持久化基础
    - RED：先为 `EvaluationCorrelationScope`、`EvaluationCorrelationRecord`、`EvaluationCorrelationReader`、`CorrelationSubjectRef` 及门禁记录编写仓储与对称查询测试；运行并记录关联只存在单向索引的失败。
    - GREEN：实现运行、用例、能力调用、问题、首轮工件与比较对象之间的稳定关联记录，并保存机制门禁原始决策来源。
    - REFACTOR：将关联主题解析、反向索引和摘要校验集中到仓储层，禁止业务服务直接扫描目录猜测关系。
    - VERIFY：从任意关联端点查询均返回同一闭包集合；删除或篡改单侧索引时可检测并给出结构化不对称错误。
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 7.13, 7.14, 7.15, 7.16, 7.17, 7.18, 7.19, 7.20, 7.21, 7.22, 7.23_
    - _Depends: 2.2_
    - _Boundary: 评测关联事实、反向索引和机制门禁记录。_

  - [x] 2.4 为 Inbox 问题接口补充 revision=0 兼容读取与 CAS 更新
    - RED：先为 `/api/inbox/issues/{issue_id}` GET 和 `{expected_revision, updates}` PATCH 编写 API、仓储和并发测试，覆盖 legacy 无 revision 视为 0、成功递增、陈旧写 409、刷新后重试；运行并记录当前接口缺失的失败。
    - GREEN：实现问题按 ID 读取、`revision` 默认投影、CAS 持久化和 409 结构化冲突响应，不改变 `/api/inbox/issues` 的统一问题入口。
    - REFACTOR：把 revision 比较、合法更新字段和冲突响应抽到共享边界，保持八字段中文 `content` 格式和 `todo|processed` 状态规则。
    - VERIFY：并发提交同一 expected_revision，仅一个成功；失败方收到当前 revision 与 `request_id`，刷新后可无丢失更新地完成提交。
    - _Requirements: 15.6, 15.7, 15.9, 15.10, 15.11, 15.14, 15.15, 15.24, 15.26, 15.27, 15.28, 15.31, 15.32_
    - _Depends: 2.3_
    - _Boundary: Inbox 单问题读取、revision 投影与 CAS 更新。_

- [ ] 3. 建立严格脚本驱动、证据读取和评测专用 Runtime

  - [x] 3.1 实现 `StrictScriptedDriver` 的完全确定性协议
    - RED：先编写严格脚本驱动测试，分别触发 `SYNTHETIC_UNEXPECTED_INTERACTION`、`SYNTHETIC_OUT_OF_ORDER`、`SYNTHETIC_CONTENT_MISMATCH`、`SYNTHETIC_SCRIPT_EXHAUSTED`、`SYNTHETIC_REMAINING_STEPS`、`SYNTHETIC_NORMALIZATION_DRIFT`；运行并记录当前宽松模拟无法失败的证据。
    - GREEN：实现按序交互、内容匹配、脚本耗尽、剩余步骤和规范化漂移的结构化错误，禁止模糊匹配或静默跳步。
    - REFACTOR：将规范化、步骤游标和错误证据封装在驱动边界，保证错误码、位置和观察值稳定可重放。
    - VERIFY：同一脚本重复执行得到字节稳定结果；六类错误均由最小反例独立触发且不会被归并。
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14, 4.15_
    - _Depends: 2.1, 2.2_
    - _Boundary: deterministic synthetic 模型交互驱动。_

  - [x] 3.2 建立八个窄证据源与只读 `RuntimeEvidenceReader`
    - RED：先为 `RunEvidenceSource`、`NodeEvidenceSource`、`InvocationEvidenceSource`、`ContextSnapshotEvidenceSource`、`ReplayEvidenceSource`、`CheckpointEvidenceSource`、`EffectEvidenceSource`、`UsageEvidenceSource` 编写契约测试，覆盖缺失、部分可用、顺序和关联 ID；运行并记录证据只能散落读取的失败。
    - GREEN：实现八个窄协议及聚合的 `RuntimeEvidenceReader`，只读取既有审计事实，不修改审计字段、ID、写入顺序或 Runtime 正常路径。
    - REFACTOR：统一只读查询、可用性标记和关联过滤，明确“证据不存在”与“证据读取失败”的不同状态。
    - VERIFY：通过真实审计样本验证八类证据均可按 run/case/invocation 关联读取；对受保护 Runtime 文件做 diff 断言为零。
    - _Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7, 11.8, 11.9, 11.10, 11.11, 11.12, 11.13, 11.14, 11.15_
    - _Depends: 2.3_
    - _Boundary: Runtime 既有审计事实的只读证据适配。_

  - [x] 3.3 实现独立的 `GeneralAgentBenchmarkRuntimeFactory`
    - RED：先编写组合测试，断言评测工厂只能注入 fixture 隔离、strict driver、评测关联观察器和固定能力目录，并且正常应用组合根对象身份、配置和写序不变；运行并记录专用工厂不存在的失败。
    - GREEN：实现 `GeneralAgentBenchmarkRuntimeFactory`，复用真实 Runtime 能力但在独立组合入口装配 synthetic/live 驱动、隔离存储和证据观察。
    - REFACTOR：收紧工厂输入为显式协议，删除通过全局开关、环境变量或修改正常组合根进入评测模式的路径。
    - VERIFY：同进程创建正常 Runtime 与评测 Runtime，确认正常路径行为不变、评测路径可隔离运行，受保护文件及审计契约无修改。
    - _Requirements: 10.1, 10.4, 10.8, 10.13, 10.21, 10.30_
    - _Depends: 2.4, 3.1, 3.2_
    - _Boundary: 评测专用 Runtime 组合入口。_

  - [x] 3.4 实现 `EvaluationCaseExecutor` 与调用结果关联
    - RED：先编写执行器测试，覆盖直接回答、Tool、Subagent、人工中断、授权拒绝、checkpoint 恢复和异常停止；运行并记录当前无法把用例、节点、调用与结果关联的失败。
    - GREEN：实现 `EvaluationCaseExecutor`，为每次真实调用记录 capability、invocation、outcome、预算观察、停止原因和 `CorrelationSubjectRef`。
    - REFACTOR：将调用观察、结果封装和停止原因提取从用例脚本中分离，禁止用 manifest/allowed/registration 代替 invocation/outcome。
    - VERIFY：执行代表性最小用例，确认每个已调用能力均有配对 outcome，未调用能力不会被计入覆盖率。
    - _Requirements: 4.3, 4.7, 5.12, 7.9, 10.17_
    - _Depends: 3.3_
    - _Boundary: 单用例执行、真实能力调用与结果关联。_

  - [x] 3.5 落实 23 个用例的脚本、fixture 与全部实际能力路径
    - RED：先为 23 个用例逐例编写端到端失败测试，要求 17 个 Tool 与 12 个 Subagent 的实际调用和 outcome 可见；运行并保存缺少脚本、fixture 或真实能力调用的失败清单。
    - GREEN：实现全部用例脚本与固定输入，覆盖直接回答、正文与知识读取、外部研究、结构与知识写入、授权拒绝、三审并行、修订、记忆状态和 checkpoint 恢复。
    - REFACTOR：复用稳定 fixture 构造器和正式能力名称，删除任务专用假 Tool、假 Subagent 与仅为凑覆盖率的空调用。
    - VERIFY：运行目录全量审计，确认 23/23 用例可启动、30/30 调用预期均由实际 invocation/outcome 证明，任何漏项使套件 invalid。
    - _Requirements: 4.1, 4.2, 4.4, 4.5, 4.6, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14, 4.15_
    - _Depends: 3.4_
    - _Boundary: 23 个权威业务用例的可执行定义。_

- [ ] 4. 修复工作记忆生产与投影，并建立硬门禁

  - [x] 4.1 实现 producer 端记忆有效性证明
    - RED：先为 `ProducerMemoryValidityProof` 编写测试，覆盖 ACTIVE、STALE、REJECTED、SUPERSEDED 四种状态以及依赖摘要、来源节点和替代关系；运行并记录当前生产者无法证明有效性的失败。
    - GREEN：在 orchestrator/executor 的既有工作记忆生产边界生成正式有效性证明，不改变 Runtime 审计字段和正常消息角色。
    - REFACTOR：统一状态推导和依赖摘要计算，避免消费者通过文本猜测记忆是否有效。
    - VERIFY：构造四种状态的独立运行，确认每条 producer 记忆都有可验证证明且篡改依赖后摘要校验失败。
    - _Requirements: 14.1, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10, 14.11, 14.12, 14.13, 14.14, 14.15, 14.16, 14.17, 14.18, 14.19, 14.20_
    - _Depends: 3.4_
    - _Boundary: orchestrator/executor 工作记忆生产有效性。_

  - [x] 4.2 实现当前事实投影与修复投影契约
    - RED：先为 `CurrentFactProjectionPolicy`、`RepairProjection` 编写测试，覆盖 BASIS、REVIEW_TARGET、REPAIR_SOURCE 三种角色以及跨分支、跨轮次、替代链隔离；运行并记录旧摘要混入当前事实的失败。
    - GREEN：实现当前事实投影和修复投影，只允许有效 producer 结果按明确角色进入下游上下文。
    - REFACTOR：把角色选择、替代链解析和依赖闭包从提示词拼接中移入类型化投影服务。
    - VERIFY：对同一运行的当前回答、评审与修复上下文做快照，确认各层只含允许角色且不存在无来源文本。
    - _Requirements: 14.2, 14.3, 14.5, 14.6, 14.7, 14.8, 14.9, 14.10, 14.11_
    - _Depends: 4.1_
    - _Boundary: 工作记忆当前事实与修复上下文投影。_

  - [x] 4.3 建立摘要、digest、snapshot 与复用抗污染硬门禁
    - RED：先编写污染测试，将 STALE、REJECTED、SUPERSEDED 内容注入 summary、digest、snapshot、reuse 和并行分支；运行并记录污染未被发现的失败。
    - GREEN：实现四种载体的有效性过滤和来源证明校验，任何污染均生成失败门禁并阻止套件通过。
    - REFACTOR：统一所有复用入口到 `CurrentFactProjectionPolicy`，删除绕过投影服务直接拼接内部结果的路径。
    - VERIFY：运行用例 19–22 与变异测试，确认 ACTIVE 正常投影，其他三态不会成为当前事实，修复来源仅在授权角色出现。
    - _Requirements: 14.1, 14.4, 14.12, 14.13, 14.14, 14.15, 14.16, 14.17, 14.18, 14.19, 14.20_
    - _Depends: 4.2_
    - _Boundary: summary、digest、snapshot、reuse 与并行分支抗污染。_

- [ ] 5. 建立证据工件、验证器、门禁、失败分类与指标

  - [x] 5.1 从 Runtime 事实构建类型化 `EvidenceBundle`
    - RED：先为证据构建器编写测试，覆盖八类证据的完整、缺失、不可读取和关联错位；运行并记录旧结果只存汇总分数、无法追溯原始事实的失败。
    - GREEN：实现从 `RuntimeEvidenceReader` 到 `EvidenceBundle` 和五类预期工件的确定性构建，不制造 Runtime 未记录的事实。
    - REFACTOR：分离原始证据、派生工件与可用性说明，保留每个派生值的来源引用。
    - VERIFY：抽查每类工件均可回溯到具体审计记录；移除任一必需证据后结论变为 evidence_incomplete 或 invalid，而非猜测通过。
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 7.9, 7.10, 7.11, 7.12, 7.13, 7.14, 7.15, 7.16, 7.17, 7.18, 7.19, 7.20, 7.21, 7.22, 7.23_
    - _Depends: 3.2, 3.5, 4.3_
    - _Boundary: Runtime 原始证据到类型化评测工件。_

  - [x] 5.2 实现验证器注册、机制门禁和安全门禁
    - RED：先为 budget、verifier、artifact、stop_reason、security、evidence 六类 gate 编写逐类失败测试和未知 gate 拒绝测试；运行并记录当前判定无法区分门禁来源的失败。
    - GREEN：实现验证器执行、`MechanismGateResult` 与 `MechanismDecisionSource`，将每个结论绑定到正式证据和验证器版本。
    - REFACTOR：统一 gate 执行顺序、短路规则和结果聚合，禁止分数覆盖硬门禁失败。
    - VERIFY：运行门禁矩阵，确认任一硬门禁失败均阻止 passed，所有判定可定位到明确证据、规则和错误码。
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 5.9, 5.10, 5.11, 5.12, 5.13, 5.14, 5.15, 5.16, 5.17, 5.18, 5.19, 5.20, 5.21, 5.22, 5.23, 5.24, 5.25, 5.26, 5.27_
    - _Depends: 5.1_
    - _Boundary: 类型化验证器与机制硬门禁。_

  - [x] 5.3 实现穷尽且互斥的失败分类
    - RED：先为 benchmark_invalid、fixture_isolation_failed、security_violation、evidence_incomplete、missing_artifact、budget_exceeded、verifier_failed、failure_stop_reason、execution_error、cancelled、unfinished、undetermined 编写最小反例；运行并记录分类重叠或丢失的失败。
    - GREEN：实现正式失败分类器和优先规则，保持 blocked/error/cancelled/unfinished 的原始执行状态，不将其伪装为普通模型失败。
    - REFACTOR：将状态、门禁和分类的映射集中为纯函数，移除前后端自行推断结论的逻辑。
    - VERIFY：执行全分类表与属性测试，确认每个非通过结果恰好一个主分类、保留全部次级证据且未知组合落入 undetermined。
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12, 6.13, 6.14, 6.15, 6.16, 6.17_
    - _Depends: 5.2_
    - _Boundary: 失败状态、失败类别和原始证据映射。_

  - [x] 5.4 计算用例、能力、预算和稳定性指标
    - RED：先为覆盖率、通过率、预算观察、重复运行一致性和 `StabilitySummary` 编写边界测试，明确 allowed/manifest/registration 不计实际覆盖；运行并记录旧五维加权分数仍被使用的失败。
    - GREEN：实现基于 actual invocation/outcome 与正式 gate 的指标计算，不引入旧五维兼容字段。
    - REFACTOR：把指标输入限制为不可变 `CaseResultRow` 和证据引用，保证计算可重放。
    - VERIFY：用固定样本手工核对指标，确认增加未调用的 manifest 能力不会提高覆盖率，重复运行差异会被稳定性摘要识别。
    - _Requirements: 2.5, 4.7, 6.9, 12.9_
    - _Depends: 5.3_
    - _Boundary: 新体系的覆盖、预算和稳定性指标。_

- [ ] 6. 实现套件生命周期、持久化、查询和实验服务

  - [x] 6.1 实现 `BenchmarkRunner` 生命周期与取消/恢复语义
    - RED：先为 queued → running → cancelling/finalizing → 终态编写状态机测试，覆盖进程中断、取消竞态、未完成和恢复；运行并记录非法跳转未被阻止的失败。
    - GREEN：实现 `BenchmarkRunner` 与 `BenchmarkLifecycleService`，在每个可恢复边界持久化状态并遵守结论只在 completed 出现的约束。
    - REFACTOR：集中状态转换、检查点和最终化事务，确保重复恢复不会重跑已冻结步骤。
    - VERIFY：逐个注入中断与取消，确认恢复后的工件、计数和结论一致，unfinished/cancelled 不被伪造 completed。
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_
    - _Depends: 2.2, 5.4_
    - _Boundary: 套件运行生命周期、取消、恢复与最终化。_

  - [x] 6.2 实现基准目录、提交、查询与分页服务
    - RED：先为 `BenchmarkCatalogService`、`BenchmarkSubmissionService`、`BenchmarkQueryService` 编写测试，覆盖幂等提交、按 ID 查询、页边界和快照一致性；运行并记录服务缺失的失败。
    - GREEN：实现三项应用服务，列表统一返回 `items,page,page_size,total,total_pages,index_revision,total_snapshot`。
    - REFACTOR：把分页、索引 revision 和对象装配移入查询边界，禁止 API 路由直接扫描工件目录。
    - VERIFY：在并发新增运行时翻页，确认同一 `total_snapshot` 不漏项不重复；同一幂等键不产生重复套件。
    - _Requirements: 13.2, 13.4, 13.6, 13.8, 13.10, 13.12, 13.14_
    - _Depends: 6.1_
    - _Boundary: 基准目录、提交与快照分页查询。_

  - [x] 6.3 实现实验与模型可比性契约
    - RED：先为 `ExperimentSpec`、`ComparabilityResult`、`ModelComparisonAdmission` 编写测试，覆盖 suite/fixture/catalog/provider 参数漂移和未闭环首轮；运行并记录不可比运行仍能进入比较的失败。
    - GREEN：实现 `ExperimentService` 的实验创建、运行绑定和可比性检查，未满足入场条件时返回具体阻断原因。
    - REFACTOR：将可比性摘要和差异路径实现为确定性纯函数，禁止 UI 依据显示字段自行判断可比。
    - VERIFY：对完全一致与单字段漂移样本运行比较，确认前者 admitted、后者 blocked 且精确指出差异来源。
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 8.13, 8.14, 8.15, 8.16, 8.17, 8.18, 8.19, 8.20, 8.21, 8.22, 8.23, 8.24, 8.25, 8.26, 8.27, 8.28, 8.29, 8.30, 8.31_
    - _Depends: 6.2_
    - _Boundary: 实验定义、可比性与模型比较准入。_

- [ ] 7. 实现首轮冻结、问题关联、修复闭环与比较准入

  - [x] 7.1 实现首轮 live 工件与迭代清单冻结
    - RED：先为 `FirstLiveArtifact`、`FirstLiveIterationManifest`、`FirstLiveIterationService` 编写测试，覆盖 DeepSeek V4 Pro 单独首跑、完整性、冻结后不可覆盖和失败状态保留；运行并记录首跑可被后续运行改写的失败。
    - GREEN：实现首轮 live 创建、完成性检查、冻结摘要和 append-only 迭代清单，其他模型在闭环前不得启动。
    - REFACTOR：将首轮身份、冻结条件和后续迭代关系集中管理，禁止通过文件名顺序猜测“第一轮”。
    - VERIFY：冻结后尝试覆盖必定失败；新一轮只能追加 manifest；blocked/error 工件保留原态且不能冒充完整首轮。
    - _Requirements: 15.1, 15.2, 15.3, 15.16, 15.18, 15.23_
    - _Depends: 6.3_
    - _Boundary: DeepSeek V4 Pro 首轮 live 与迭代清单。_

  - [x] 7.2 实现确定性问题意图与 revision 关联仓储
    - RED：先为 `IssueCorrelationIntent`、`IssueCorrelationRevision`、`IssueCorrelationObservation`、`IssueCorrelationRepository` 编写测试，覆盖 intent 去重、revision 单调递增、legacy issue revision=0 和竞争写入；运行并记录重复问题或关联丢失的失败。
    - GREEN：实现评测失败到 Inbox 问题意图、问题 revision 与观察证据的 append-only 关联，使用 CAS 更新既有问题。
    - REFACTOR：统一稳定 intent key、问题状态映射和关联摘要，禁止用标题模糊匹配或静默覆盖。
    - VERIFY：重复分类同一失败不新增重复问题；并发更新只有一个成功；每个 issue revision 均可追溯对应运行证据。
    - _Requirements: 15.6, 15.7, 15.8, 15.9, 15.10, 15.11, 15.14, 15.15, 15.24, 15.26, 15.27, 15.28, 15.29, 15.30, 15.31, 15.32_
    - _Depends: 2.4, 7.1_
    - _Boundary: 首轮失败与 Inbox 问题 revision 的持久关联。_

  - [x] 7.3 实现关联 reconciler、对称门禁和查询服务
    - RED：先为 `IssueCorrelationReconciler`、`IssueCorrelationSymmetryGate`、`IssueCorrelationQueryService` 编写断链、单侧更新和重复关联测试；运行并记录不对称关系未阻止闭环的失败。
    - GREEN：实现可重放 reconciler、双向索引修复建议、对称性硬门禁和分页查询。
    - REFACTOR：把观察、期望和修复结果分层，reconciler 不直接篡改冻结首轮工件。
    - VERIFY：对损坏样本运行 reconciliation，确认报告确定、门禁失败；完成合法修复后双向查询一致且门禁通过。
    - _Requirements: 15.9, 15.10, 15.11, 15.29, 15.30, 15.31, 15.32_
    - _Depends: 7.2_
    - _Boundary: Inbox 与评测工件关联的协调、对称门禁和查询。_

  - [x] 7.4 实现问题关闭协调与模型比较入场门禁
    - RED：先为 `IssueClosureCoordinator` 和 `ModelComparisonService` 编写测试，覆盖未修复、未复跑、门禁未过、租约竞争、问题未 processed 与首轮未冻结；运行并记录比较可提前开始的失败。
    - GREEN：实现“系统缺陷修复 → 定向复跑 → 全量复跑 → 问题关闭 → 硬门禁通过”的关闭协调，满足全部条件后才允许多模型比较。
    - REFACTOR：把关闭判定和比较准入统一依赖冻结摘要及关联事实，不依赖人工勾选或 UI 本地状态。
    - VERIFY：逐项移除前置条件均被 blocked；全部条件满足时只发放一次有效比较入场记录。
    - _Requirements: 15.14, 15.15, 15.18, 15.19, 15.20, 15.21, 15.22, 15.25, 15.28, 15.33, 15.34, 15.35, 15.36, 15.37, 15.38, 15.39, 15.40_
    - _Depends: 7.3_
    - _Boundary: 首轮问题关闭、复跑证明和多模型比较准入。_

- [ ] 8. 接入应用服务和新 `/api/general-agent-benchmarks` API

  - [x] 8.1 组装新评测应用服务且保持正常 Runtime 组合根不变
    - RED：先编写应用组装测试，断言所有正式服务通过显式依赖注入可用、正常 Runtime 组合保持原对象图，旧 evaluation 服务不再被新路径引用；运行并记录新服务尚未装配的失败。
    - GREEN：组装目录、提交、runner、查询、生命周期、实验、首轮、问题关联、关闭和比较服务。
    - REFACTOR：将评测组合限定在独立模块，避免向正常 Runtime 注入评测状态或测试驱动。
    - VERIFY：运行容器契约测试和对象图快照，确认新服务完整、正常 Runtime 快照不变、无循环依赖。
    - _Requirements: 10.3, 10.13, 13.5, 14.5_
    - _Depends: 7.4_
    - _Boundary: 新评测应用服务组合。_

  - [x] 8.2 实现新 API 的目录、运行、生命周期与证据资源
    - RED：先按设计资源表为 `/api/general-agent-benchmarks` 编写 API 契约测试，覆盖目录、提交、运行详情、结果、证据、取消和恢复；运行并记录路由 404 的预期失败。
    - GREEN：实现资源路由与 Schema，所有错误携带 `request_id`，列表使用统一快照分页包络，状态和结论保持正式枚举。
    - REFACTOR：路由仅负责协议转换，状态推导、目录扫描和结论计算留在应用服务。
    - VERIFY：运行 API 契约与 OpenAPI 快照测试，确认成功/失败/冲突/取消响应完整且无旧五维字段。
    - _Requirements: 1.10, 2.4, 5.8, 7.4, 7.8, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_
    - _Depends: 8.1_
    - _Boundary: 基准目录、套件运行、证据与生命周期 API。_

  - [x] 8.3 实现实验、首轮、问题关联和模型比较资源
    - RED：先为 experiments、iterations、issue-correlations、comparisons 与 admission 资源编写 API 测试，覆盖分页、不可比、未闭环和关联不对称；运行并记录资源缺失的失败。
    - GREEN：实现设计指定资源，服务端返回正式阻断原因、冻结摘要和关联 revision。
    - REFACTOR：复用统一分页、错误和 request_id 中间件，避免为各资源复制状态解释。
    - VERIFY：运行端到端 API 测试，确认未闭环比较返回结构化 blocked，合法比较可创建并能恢复关联 URL。
    - _Requirements: 15.3, 15.7, 15.11, 15.15, 15.19, 15.23, 15.27, 15.31, 15.35, 15.39_
    - _Depends: 8.2_
    - _Boundary: 实验、首轮闭环、问题关联和模型比较 API。_

  - [x] 8.4 在 FastAPI 主组合根注册新路由并验证热重载
    - RED：先编写路由注册测试，断言新前缀存在且旧前缀在切换后不存在；运行并记录新前缀未注册的失败。
    - GREEN：在 `src/taichu/main.py` 注册新路由，保持其他启动与中间件顺序不变。
    - REFACTOR：清理重复注册和临时兼容入口，确保路由表只有一个正式评测前缀。
    - VERIFY：等待源码热重载后通过 `http://127.0.0.1:8000` 请求健康检查和新 API；若仍是旧代码，按 `start.bat` 约定清理并重启 8000 后复验。
    - _Requirements: 15.2, 15.6, 15.10, 15.14_
    - _Depends: 8.3_
    - _Boundary: FastAPI 正式路由注册与本地热重载。_

- [ ] 9. 重建桌面评测工作台与并发请求防护

  - [x] 9.1 先建立纯 Node 的 API 客户端、状态归一化和请求协调测试
    - RED：先为新 API 客户端、正式枚举、分页包络与 `RequestCoordinator` 编写纯 Node 测试，覆盖 generation、AbortController、lastAppliedRevision、乱序响应和 request_id；运行并记录旧客户端契约失败。
    - GREEN：实现新类型、客户端与请求协调器，陈旧响应不得覆盖新 revision，取消请求不得显示为业务失败。
    - REFACTOR：把状态归一化和请求竞争控制保持为无 DOM 纯模块，不增加依赖或 package script。
    - VERIFY：运行现有 Node 测试入口，确定性重现先发后到场景并确认最终状态始终来自最新 generation/revision。
    - _Requirements: 15.4, 15.8, 15.12, 15.16, 15.20, 15.24, 15.28, 15.32, 15.36, 15.40_
    - _Depends: 8.3_
    - _Boundary: 前端 API 契约、纯状态逻辑与并发协调。_

  - [x] 9.2 重建 `GeneralAgentEvaluationShell` 的结论优先工作台
    - RED：先为 Shell 视图模型和可见文案编写测试，覆盖套件结论、机制门禁、证据缺失、blocked/error/cancelled/unfinished、能力实际调用和预算；运行并记录旧五维卡片仍出现的失败。
    - GREEN：在保留 `/task-monitor/general-agent/evaluation` 与 `GeneralAgentEvaluationShell` 名称的前提下重建桌面工作台，使用现有 AppShell、GeneralAgentMonitorNav、Button、Checkbox 和 lucide。
    - REFACTOR：将结论、证据、能力、预算和失败详情拆为清晰视图边界，所有用户可见文案使用中文，极光装饰遵循 `DESIGN.md`。
    - VERIFY：运行纯 Node 视图测试并检查渲染快照，确认首屏先显示结论与阻断原因，旧五维字段、旧接口文案和旧结果兼容入口均不存在。
    - _Requirements: 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 10.9, 10.10, 10.11, 10.12, 10.13, 10.14, 10.15, 10.16, 10.17, 10.18, 10.19, 10.20, 10.21, 10.22, 10.23, 10.24, 10.25, 10.26, 10.27, 10.28, 10.29, 10.30, 10.31, 10.32, 10.33, 10.34_
    - _Depends: 9.1_
    - _Boundary: 桌面评测工作台 Shell 与结论优先展示。_

  - [x] 9.3 接入服务端分页且不修改 `CompactPagination`
    - RED：先编写分页状态测试，覆盖 page/page_size/total_pages、index_revision、total_snapshot、空页回退和运行中索引增长；运行并记录客户端全量拉取或页码漂移的失败。
    - GREEN：接入所有列表的服务端分页，复用现有 `CompactPagination` 并以调用方样式 `border-t-0` 消除重复边框。
    - REFACTOR：集中 URL 查询参数与分页状态同步，不修改共享 `CompactPagination` 实现。
    - VERIFY：检查 git diff 确认共享分页组件零修改；跨页新增数据时同一快照无重复、无漏项，刷新可恢复当前页。
    - _Requirements: 15.6, 15.14, 15.22, 15.30, 15.38_
    - _Depends: 9.2_
    - _Boundary: 工作台列表分页和 URL 状态。_

  - [x] 9.4 实现首轮闭环、Inbox CAS 冲突和比较 URL 恢复交互
    - RED：先编写交互状态测试，覆盖 409 刷新、revision 更新、重复 issue intent、关联对称失败、首轮冻结和比较查询参数恢复；运行并记录陈旧响应覆盖新状态的失败。
    - GREEN：实现首轮工件、问题关联、CAS 冲突提示与刷新、多模型比较准入及 URL 恢复交互。
    - REFACTOR：复用 `RequestCoordinator` 处理所有可能竞争的请求，页面不自行猜测问题是否关闭或运行是否可比。
    - VERIFY：以纯 Node 测试复现 409 和乱序响应，确认用户可见中文提示包含 request_id，刷新后 revision 正确且比较 URL 可完整恢复。
    - _Requirements: 8.6, 8.16, 8.26, 14.7, 14.17, 15.7, 15.15, 15.23, 15.31, 15.39_
    - _Depends: 9.3_
    - _Boundary: 首轮闭环、Inbox CAS 和比较页面交互状态。_

- [ ] 10. 原子切换新体系并彻底清理旧实现

  - [x] 10.1 在原子切换前建立新旧边界和受保护文件回归清单
    - RED：先编写静态边界测试，枚举必须删除的旧后端、旧 API、旧 manifest、旧结果、旧前端引用和不得修改的 Runtime 审计文件；运行并记录当前旧引用存在的失败。
    - GREEN：建立只针对新体系的导入、路由和前端引用断言，并保存受保护文件基线摘要。
    - REFACTOR：将静态扫描规则限定为正式路径和符号，避免宽泛匹配误伤历史资料与保留评测。
    - VERIFY：切换前测试准确报告全部旧实现待清理项，同时确认运行监控、恢复 benchmark、知识评测和历史资料属于保留集合。
    - _Requirements: 1.21, 6.12, 10.24, 15.34_
    - _Depends: 8.4, 9.4_
    - _Boundary: 原子切换清单、保留集合与 Runtime 保护基线。_

  - [x] 10.2 删除旧后端、契约、仓储、路由、manifest 和集成测试
    - RED：先运行 10.1 的静态边界测试并保存旧路径存在的失败证据。
    - GREEN：删除 `src/taichu/application/evaluations/general_agent/`、旧 contract/repository/schema/route、旧 manifest 与旧 API 集成测试，并移除全部导入和注册。
    - REFACTOR：清除孤儿配置、僵尸依赖引用和旧五维命名，但不删除运行监控、恢复 benchmark 或知识评测。
    - VERIFY：运行静态扫描与测试收集，确认旧模块无法导入、旧路由不存在、新路由正常且保留测试仍被收集。
    - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6, 12.7, 12.8, 12.9, 12.10, 12.11, 12.12, 12.13, 12.14, 12.15, 12.16, 12.17, 12.18, 12.19, 12.20, 12.21_
    - _Depends: 10.1_
    - _Boundary: 旧后端实现、契约、路由和测试资产。_

  - [x] 10.3 删除旧派生结果并替换旧前端内容与测试
    - RED：先运行旧结果、旧 API 字符串、旧五维字段和旧视图断言的扫描测试，记录当前残留失败。
    - GREEN：删除 `project_assets/derived/agent_evaluations/general_agent/general_eval_*.json`，替换 Shell/API/types/view/test 中的旧内容，不保留读取回退。
    - REFACTOR：移除仅服务旧结果的 mapper、alias、fallback 和无用前端状态，保持路由与 Shell 正式名称。
    - VERIFY：全仓 `rg` 确认旧结果路径、旧 API 和旧五维字段在当前实现中零残留；新页面测试全部通过。
    - _Requirements: 2.8, 6.5, 12.6, 15.18_
    - _Depends: 10.2_
    - _Boundary: 旧派生结果、旧前端契约与兼容代码。_

  - [x] 10.4 同步当前文档与 `project_assets/readme.md`
    - RED：先编写或运行文档链接与目录职责检查，记录新工件根目录未登记、旧入口仍被描述的失败。
    - GREEN：按 `docs/rule.md` 更新当前实现文档，并因新增/删除/改变 `project_assets/` 目录职责同步更新 `project_assets/readme.md`；历史文档保持不变。
    - REFACTOR：删除当前文档中的旧五维、旧 API 和旧结果说明，README 地图只保留一个当前入口。
    - VERIFY：运行链接/路径扫描，确认当前文档与代码一致、历史快照未改、新派生目录职责和可重建属性已登记。
    - _Requirements: 1.6, 5.19, 6.16, 15.26_
    - _Depends: 10.3_
    - _Boundary: 当前文档、仓库地图与 project_assets 目录说明。_

- [ ] 11. 先完成 deterministic synthetic 全量套件并冻结基线

  - [x] 11.1 运行全量 synthetic 套件的首次 RED 基线
    - RED：先在固定 fixture 和 strict driver 下运行 23 个 synthetic 用例，保存所有失败、脚本漂移、缺失工件和门禁证据，不跳过失败用例。
    - GREEN：只修复 synthetic 基准、脚本、隔离、执行器、证据与判定中的确定性缺陷，直到所有正式用例可完成。
    - REFACTOR：合并重复 fixture/脚本步骤并保持内容摘要稳定，不降低匹配严格度或放宽硬门禁。
    - VERIFY：再次运行全量 synthetic，要求 23/23 用例有结果、全部必需调用有 invocation/outcome、所有硬门禁通过。
    - _Requirements: 4.5, 5.20, 9.9, 12.21, 13.15_
    - _Depends: 10.4_
    - _Boundary: deterministic synthetic 全量运行与确定性修复。_

  - [x] 11.2 重跑验证确定性、隔离性和稳定性
    - RED：先编写双运行摘要对比测试，并用扰动脚本证明 normalization drift、跨工作区污染和索引覆盖会失败；记录预期失败。
    - GREEN：修复所有非确定来源，确保运行 ID 之外的权威结果、工件摘要和 gate 顺序稳定。
    - REFACTOR：将时钟、随机数和 ID 生成通过明确依赖注入隔离，禁止测试依赖机器偶然状态。
    - VERIFY：连续两次全量 synthetic 均通过；规范化后的 SuiteArtifact、23 个 CaseResultRow 和稳定性摘要一致，工作区无交叉写入。
    - _Requirements: 3.17, 5.27, 6.17, 9.8, 13.14_
    - _Depends: 11.1_
    - _Boundary: synthetic 双运行确定性、隔离与稳定性。_

  - [x] 11.3 冻结 synthetic 通过基线及其可追溯摘要
    - RED：先为 synthetic 基线冻结、摘要校验和不可覆盖编写测试，运行并记录尚无冻结记录的失败。
    - GREEN：写入通过基线、suite/fixture/catalog 摘要、完整证据索引和冻结标记。
    - REFACTOR：仅保存可重建索引和必要审计引用，不把派生评测数据升级为小说事实源。
    - VERIFY：冻结后覆盖尝试失败；从冻结摘要可定位全部 23 个用例、能力调用、门禁和原始 Runtime 证据。
    - _Requirements: 6.3, 7.23, 12.20, 14.3_
    - _Depends: 11.2_
    - _Boundary: synthetic 全量通过基线冻结。_

- [ ] 12. 独立执行 DeepSeek V4 Pro 首轮并闭合真实系统缺陷

  - [x] 12.1 单独启动并完整执行 DeepSeek V4 Pro 首轮 live
    - RED：先运行首轮入场检查，证明 synthetic 基线、fixture/catalog 摘要、提供商配置或隔离条件任一缺失都会 blocked，并记录预期阻断。
    - GREEN：在没有其他模型并发比较的条件下执行 DeepSeek V4 Pro 全量 live 首轮，持续保存 provider 状态、预算、证据和中间恢复点。
    - REFACTOR：仅修复运行基础设施中阻止首轮完整记录的非业务性问题，不在首轮中途改写 benchmark 结论标准。
    - VERIFY：首轮全部用例到达可解释状态；blocked/error 原样保留；完整工件满足冻结条件并生成 `FirstLiveArtifact`。
    - _Requirements: 15.1, 15.2, 15.3_
    - _Depends: 11.3_
    - _Boundary: DeepSeek V4 Pro 单模型首次 live 全量运行。_

  - [x] 12.2 冻结首轮工件并分类真实失败
    - RED：先为首轮完整性、冻结和失败分类编写验收测试，使用缺证据、未完成和分类冲突样本记录预期失败。
    - GREEN：冻结首轮工件，对每个非通过结果应用正式分类，并区分 benchmark 缺陷、提供商/执行状态与真实系统缺陷。
    - REFACTOR：把人工分析说明作为关联观察保存，不修改冻结事实或用自由标签覆盖正式分类。
    - VERIFY：冻结摘要校验通过；每个失败恰有主分类、证据引用和处置路径，且首轮工件不可覆盖。
    - _Requirements: 15.3, 15.4, 15.5, 15.13_
    - _Depends: 12.1_
    - _Boundary: 首轮工件冻结与失败分类。_

  - [x] 12.3 仅将真实系统缺陷写入统一 Inbox 问题入口
    - RED：先用混合失败样本测试问题筛选，证明 benchmark_invalid、blocked 或纯提供商错误不会被误建为系统缺陷，并记录预期失败。
    - GREEN：对真实系统缺陷调用 `/api/inbox/issues`，`content` 严格按记录日期、状态、现象、根因、影响、修复、验证、相关代码八字段顺序使用中文全角冒号；未解决为 todo。
    - REFACTOR：通过 `IssueCorrelationIntent` 去重并保存 issue revision、首轮证据和失败分类关联，不绕过 Inbox API 直接写 JSONL。
    - VERIFY：每个真实系统缺陷恰有一个问题记录和双向关联；非系统缺陷零误建；legacy/current revision 查询一致。
    - _Requirements: 15.6, 15.7, 15.8, 15.9, 15.10, 15.11, 15.12, 15.24, 15.26, 15.27, 15.28, 15.29, 15.30, 15.31, 15.32_
    - _Depends: 12.2_
    - _Boundary: 真实系统缺陷到统一 Inbox 问题入口。_

  - [ ] 12.4 对真实系统缺陷执行定向 TDD 修复与全量复跑
    - RED：为每个 Inbox 系统缺陷先新增能稳定复现的失败测试，保存失败输出并关联 issue revision。
    - GREEN：只修改被证据证明的系统缺陷，保持 benchmark 标准、Runtime 审计契约和无关功能不变。
    - REFACTOR：清理被新修复取代的旧实现、旧状态和旧测试，避免兼容分支残留。
    - VERIFY：先运行定向测试，再运行完整 synthetic 与 DeepSeek V4 Pro live 套件；全部硬门禁通过且无新回归。
    - _Requirements: 15.14, 15.15, 15.16, 15.17, 15.18, 15.23, 15.25_
    - _Depends: 12.3_
    - _Boundary: 首轮发现的真实系统缺陷及其回归范围。_

  - [ ] 12.5 通过 CAS 关闭问题并完成首轮对称闭环
    - RED：先测试未验证、未全量复跑、revision 陈旧或关联不对称时关闭必定失败，并记录预期冲突。
    - GREEN：用 expected_revision CAS 将已验证问题更新为 processed，补全修复、验证和相关代码字段，生成关闭观察与对称关联。
    - REFACTOR：由 `IssueClosureCoordinator` 统一关闭顺序和租约，禁止客户端直接宣告闭环。
    - VERIFY：所有关联问题为 processed、revision 单调、八字段齐全；对称门禁和首轮闭环门禁均 PASS。
    - _Requirements: 15.14, 15.15, 15.18, 15.19, 15.31, 15.32_
    - _Depends: 12.4_
    - _Boundary: Inbox 问题关闭、revision 与首轮闭环证明。_

- [ ] 13. 完成多模型比较、全回归、固定端口验收与独立验证

  - [ ] 13.1 在闭环门禁后执行多模型可比运行
    - RED：先在首轮闭环条件被移除时请求模型比较，记录 `ModelComparisonAdmission` blocked；再用 fixture/catalog/provider 参数漂移样本记录不可比失败。
    - GREEN：仅在首轮闭环与可比性门禁通过后创建实验并执行其他模型运行，完整保留 pending/running/blocked/error/completed 状态。
    - REFACTOR：比较层只消费冻结工件和 `ComparabilityResult`，不重新解释单次运行证据。
    - VERIFY：生成可追溯比较工件，确认每个模型的 suite/fixture/catalog 摘要一致；不可比或未完成模型不进入排名式结论。
    - _Requirements: 15.19, 15.20, 15.21, 15.22, 15.33, 15.34, 15.35, 15.36, 15.37, 15.38, 15.39, 15.40_
    - _Depends: 12.5_
    - _Boundary: 闭环后的多模型实验与比较工件。_

  - [ ] 13.2 运行后端、前端、迁移清理和受保护边界全回归
    - RED：先运行完整测试、静态扫描和受保护文件摘要校验，保存任何失败、旧引用残留或未收集测试。
    - GREEN：修复新体系引入的回归并清理被替代实现，不修改 `CompactPagination`、不新增前端依赖或 package script、不恢复旧兼容路径。
    - REFACTOR：合并重复测试夹具与断言，保持测试能独立证明契约、隔离、记忆、判定、生命周期、API、UI 和清理边界。
    - VERIFY：后端与前端完整测试通过；325 项需求追踪可回溯；旧实现扫描为零；Runtime 审计保护摘要和保留评测集合验证通过。
    - _Requirements: 1.24, 4.15, 5.26, 10.33, 11.15, 15.40_
    - _Depends: 13.1_
    - _Boundary: 全仓自动化回归、清理和受保护边界。_

  - [ ] 13.3 验证 `start.bat`、固定端口 API 与桌面 DOM
    - RED：启动前先探测 3000/8000，并运行固定端口烟雾与 DOM 验收脚本，记录服务未启动、旧代码或页面契约不符的失败。
    - GREEN：按 `start.bat` 约定启动或复用项目服务；若后端热重载失败则自动清理并重启 8000，不使用 3001/8001 规避。
    - REFACTOR：修正启动联动和验收脚本中的环境偶然性，不更改固定端口与桌面交付边界。
    - VERIFY：`http://127.0.0.1:8000` 新 API 返回真实新代码；`http://localhost:3000/task-monitor/general-agent/evaluation` 完成桌面 DOM 手动验收，覆盖结论优先、分页、409 刷新、request_id、陈旧响应防护和比较 URL 恢复。
    - _Requirements: 5.8, 10.28, 13.12, 15.8, 15.24_
    - _Depends: 13.2_
    - _Boundary: start.bat、固定 3000/8000 与桌面浏览器验收。_

  - [ ] 13.4 生成实现报告并执行全新上下文独立实现验证
    - RED：先由独立验证入口对需求、设计、实际 diff、测试、旧实现清理、首轮闭环和启动证据做 fresh-context 审计，记录所有缺证据或不一致为 FAIL。
    - GREEN：补齐实现报告中的需求追踪、设计组件覆盖、测试证据、冻结摘要、问题闭环、固定端口和清理证明；只修复独立验证发现的真实缺口。
    - REFACTOR：将报告引用绑定到稳定工件、命令输出和哈希，不依赖当前会话口头结论。
    - VERIFY：独立实现验证报告为 PASS，确认 325/325 需求、全部设计组件/契约/集成点/运行前提/迁移/清理/验证均有实现和可复验证据。
    - _Requirements: 1.25, 2.16, 3.17, 4.15, 5.27, 6.17, 7.23, 8.31, 9.9, 10.34, 11.15, 12.21, 13.15, 14.20, 15.40_
    - _Depends: 13.3_
    - _Boundary: 实现报告与全新上下文独立验证。_
