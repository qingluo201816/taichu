# 独立校验报告

- 规格：`1.1/通用写作智能体37类Benchmark落实`
- 模式：`requirements`
- 校验时间：`2026-07-30T05:48:26.9513060Z`
- 目标对象：`.sdd/specs/1.1/通用写作智能体37类Benchmark落实/requirements.md`
- 目标 SHA-256：`b3f7dbf57cf7cdc00c75427c030ef3e5244354e6923c5f773326b60aafa18a5a`
- discovery：`.sdd/specs/1.1/通用写作智能体37类Benchmark落实/validation-discovery-requirements.md`
- discovery SHA-256：`24ec88d046691882f4f6888db317d841e37d1614ddc6b0230041bccb4f8f8a24`
- Git/工作树基线：分支 `master`，HEAD `82bab37a5514f8a6f4d632872010293a910c2bec`；校验开始前工作树已有大量用户修改、删除和未跟踪文件。本轮除两份允许的独立校验证据外未修改目标、规格状态、源码、测试、前端或文档。

## 结论摘要

目标需求与阶段一独立发现一致，完整定义了 37 条案例的唯一 ID、精确顺序、S37/L21 轨道边界、逐案例行为目标、六类硬门禁最低证据、恢复与上下文压力路径、密封隔离、历史 23 条身份保留以及活动入口动态计数。目标准确区分“当前代码仍是 23 条”与“本规格计划落实 37 条”，没有把计划新增对象误写成现有事实，也没有把检索占坑泄漏为具体 RAG 实现。

机械检查确认第 4 节恰有 37 个唯一 ID，序号连续为 1—37，其中 21 条为 `S+L`、16 条为 `S`；102 条 EARS 验收标准 ID 全部唯一。未发现 critical、major、minor 问题、事实错误、规则冲突或虚构现有对象。

## 独立发现范围与方法

阶段一在未读取、搜索、摘要或计算 `requirements.md` 哈希的前提下完成。独立发现只使用：

- `spec.json` 允许字段中的原始描述和元数据；
- 根 `AGENTS.md`、`README.md`、`DESIGN.md`、`docs/rule.md` 与 SDD 独立门禁/EARS 规则；
- 用户指定的 7-30 历史审计；
- 当前固定套件、能力目录、门禁、合成/真实 runner、冻结、Hydration、API、页面、上下文、恢复、Checkpoint、测试与历史运行工件。

阶段一发现先写入 discovery 并核对非空，随后才计算目标初始 SHA-256、完整读取目标并逐项对比。写报告前再次计算目标 SHA-256，仍为 `b3f7dbf57cf7cdc00c75427c030ef3e5244354e6923c5f773326b60aafa18a5a`，与阶段二开始时一致。项目规则禁用 Graphify，本轮未读取或使用任何 Graphify 派生物。

## 匹配项

| # | 独立预期 | 目标覆盖 | 分类 |
|---:|---|---|---|
| 1 | 精确 37 条、唯一顺序与 S37/L21 | `requirements.md:116-125,127-165,175-189` 明确数量、顺序、轨道和执行前拒绝；机械解析为 37/37 唯一、21 条 `S+L`、16 条 `S` | 匹配 |
| 2 | 每案唯一可观察失败模式 | `requirements.md:191-207` 定义原始输入、唯一行为目标、最终产物、终态、能力边界和六门禁合同；第 4、5 节逐案展开 | 匹配 |
| 3 | 检索/RAG 仅冻结行为 | `requirements.md:209-221` 保留第 2—6 条行为合同并明确禁止绑定算法、索引、向量、图或数据库实现 | 匹配 |
| 4 | 多 Agent、授权、资源与记忆真实消费 | `requirements.md:241-297` 覆盖分支交接、物理并发证据边界、修订保护、预览/批准/拒绝、二次确认、真实身份与记忆污染 | 匹配 |
| 5 | 八类恢复故障窗口 | `requirements.md:299-325` 覆盖规划、Tool、Subagent、授权、写后确认、校验、多次中断、Checkpoint 完整性及不确定副作用安全停止 | 匹配 |
| 6 | 八类五层上下文压力 | `requirements.md:327-351` 覆盖长历史、工作记忆、大结果投影、多来源超限、等价性、无效记忆、长当前请求和安全拒绝 | 匹配 |
| 7 | 六门禁必须由行为证据闭环 | `requirements.md:353-377` 精确规定预算、校验、产物、停止原因、安全、证据六类门禁；缺失/损坏/冲突证据为无效，任一失败或无效均禁止通过 | 匹配 |
| 8 | 每案最低真实证据 | `requirements.md:457-499` 为 37 条逐一给出六门禁最低证据，覆盖输入、调用、下游消费、产物、后态、终态和安全边界 | 匹配 |
| 9 | 密封夹具与事实安全 | `requirements.md:379-397` 要求逐案正文、结构、知识、对话、工作记忆、运行、Effect、Checkpoint 副本，异常退出后也证明作者数据和其他案例未变 | 匹配 |
| 10 | 新基线和旧历史身份隔离 | `requirements.md:399-419` 要求 37/37 才能准入、生成不可覆盖新基线、保留旧 23 条原始数量/身份/结论并阻止跨身份聚合 | 匹配 |
| 11 | 活动入口动态计数与中文展示 | `requirements.md:421-437` 要求查询返回当前套件事实，运行计数来自实际结果，当前 37 与历史 23 分别显示，并保持中文名称和现有桌面信息架构 | 匹配 |
| 12 | 旧活动口径和弱门禁清理 | `requirements.md:439-455` 明确移除旧两个正式案例、保留旧恢复语义于第 27 条、删除统一完成态/交互存在/空证据/预设安全真值路径并检查活动代码中的 23 硬编码 | 匹配 |
| 13 | 异常、边缘、恢复及非功能可测试性 | `requirements.md:501-539` 将漂移、污染、误写、重复副作用、坏 Checkpoint、压缩丢事实、缺证据、部分运行、provider 受阻和历史展示映射为可观察结果 | 匹配 |

## 错误项

无。目标对当前 23 条套件、21 条旧 live 适用集、门禁弱代理、页面/测试硬编码、上下文和恢复现有能力及缺口的描述与阶段一源码证据一致；计划新增的 37 条均明确表述为待落实合同。

## 遗漏项

无。阶段一 E1—E16 以及 37 条逐案例目标均有可测试映射；正常、异常、边缘、恢复、安全、可靠性、显示一致性和历史兼容边界完整。

## 多余项

无。资产探查、证据矩阵、异常表、非功能期望和追踪摘要均服务于原始“落实新的 37 类 Benchmark”目标。目标没有扩大为模型排行、全量真实模型重跑、真实网络研究、RAG 架构选型、移动端、多小说、多租户或无关重构。

## 不可验证或规则冲突

无核心不可验证声明。37 条新套件当前尚未实现是本规格要解决的现状差距，不是需求事实错误；需求要求新案例以真实行为和证据运行，最终 37/37 才形成准入基线，未用预设答案宣称当前已通过。

未发现与以下高优先级规则冲突：

- Markdown/MongoDB 事实源及 JSON 仅作评测运行、审计和回放；
- 运行工作记忆仅由 Runtime 治理，且不冒充长期记忆或小说知识；
- 五层上下文名称和当前请求原文保护；
- 动态最小充分 DAG 与稳定能力边界；
- 逐案隔离、作者活动数据不变；
- 中文桌面网页和现有评测工作台信息架构；
- Graphify 禁用。

## 需求/设计/任务追踪表

### discovery 预期追踪

| 预期 | 目标映射 | 结果 |
|---|---|---|
| E1：37 个精确 ID/顺序，移除旧 17/23 | 第 4 节；1.1—1.4；14.1—14.2 | 匹配 |
| E2：S37、L21、执行前轨道校验 | 1.2、1.5—1.7；12.7；第 4 节轨道列 | 匹配 |
| E3：逐案唯一失败模式和可判终态 | 第 4 节；2.1—2.6；4—9 | 匹配 |
| E4：逐案六门禁行为证据 | 10.1—10.10；第 6 节 37 行矩阵 | 匹配 |
| E5：INVALID/FAILED/PASSED 语义，不以弱化合同制造通过 | 2.3—2.4；7.5；9.10；10.8—10.10；12.2—12.3 | 匹配 |
| E6：套件、夹具、运行与工件身份可复现 | 1.8；3.4；11.2；12.1、12.4、12.6、12.8 | 匹配 |
| E7：旧 23 条历史不可覆盖或混冒 | 1.8；12.5；13.4；14.5 | 匹配 |
| E8：活动消费者动态计数，清理现行硬编码 | 3.1 范围；13.1—13.4；14.1、14.4 | 匹配 |
| E9：套件、轨道、所选数量及历史数量分开显示 | 12.1、12.7—12.8；13.1—13.5 | 匹配 |
| E10：原始请求身份和长请求逐字保持 | 2.1；9.7；11.2；12.1；矩阵第 36 条 | 匹配 |
| E11：逐案隔离、零真实网络越界、作者数据不变 | 6.1—6.8；11.1—11.7；矩阵第 6、12—17 条 | 匹配 |
| E12：固定脚本不自证正确，verifier 读取真实行为 | 2.3—2.5；10.3—10.8；11.5—11.6 | 匹配 |
| E13：live 只跑 L21 且不污染 synthetic 准入 | 1.6—1.7；12.7—12.8；范围外 provider 门禁 | 匹配 |
| E14：页面只同步动态中文口径，不做视觉/移动端扩展 | 3.2 范围外；13.3、13.5—13.6 | 匹配 |
| E15：受影响回归与启动规则继续适用 | 非功能“相邻稳定性”；14.6；根 `AGENTS.md` 启动联动规则未被覆盖 | 匹配 |
| E16：第 2—6 条不冻结具体 RAG 实现 | 3.1—3.4；3.2 范围外 | 匹配 |

### 37 条案例追踪

| # | 案例 ID | 行为合同 | 六门禁证据 | 结果 |
|---:|---|---|---|---|
| 1 | `direct_answer_current_request` | `requirements.md:129,229` | `requirements.md:463` | 匹配 |
| 2 | `single_manuscript_search` | `requirements.md:130,231` | `requirements.md:464` | 匹配 |
| 3 | `structure_coverage_read` | `requirements.md:131,233` | `requirements.md:465` | 匹配 |
| 4 | `single_knowledge_retrieval` | `requirements.md:132,235` | `requirements.md:466` | 匹配 |
| 5 | `knowledge_catalog_identity_read` | `requirements.md:133,237` | `requirements.md:467` | 匹配 |
| 6 | `external_research_grounded` | `requirements.md:134,239` | `requirements.md:468` | 匹配 |
| 7 | `single_canon_evidence` | `requirements.md:135,247` | `requirements.md:469` | 匹配 |
| 8 | `summary_world_character` | `requirements.md:136,249` | `requirements.md:470` | 匹配 |
| 9 | `architecture_scene_draft` | `requirements.md:137,251` | `requirements.md:471` | 匹配 |
| 10 | `parallel_review_triad` | `requirements.md:138,253-255` | `requirements.md:472` | 匹配 |
| 11 | `revision_from_reviews` | `requirements.md:139,257` | `requirements.md:473` | 匹配 |
| 12 | `manuscript_preview_only` | `requirements.md:140,265` | `requirements.md:474` | 匹配 |
| 13 | `manuscript_patch_authorized_resume` | `requirements.md:141,267-269` | `requirements.md:475` | 匹配 |
| 14 | `structure_create_update` | `requirements.md:142,271` | `requirements.md:476` | 匹配 |
| 15 | `structure_delete_second_confirmation` | `requirements.md:143,273-275` | `requirements.md:477` | 匹配 |
| 16 | `knowledge_create_update` | `requirements.md:144,277` | `requirements.md:478` | 匹配 |
| 17 | `write_authorization_denied` | `requirements.md:145,279` | `requirements.md:479` | 匹配 |
| 18 | `memory_active_projection` | `requirements.md:146,287` | `requirements.md:480` | 匹配 |
| 19 | `memory_stale_dependency` | `requirements.md:147,289` | `requirements.md:481` | 匹配 |
| 20 | `memory_rejected_parallel_isolation` | `requirements.md:148,291` | `requirements.md:482` | 匹配 |
| 21 | `memory_superseded_repair` | `requirements.md:149,293` | `requirements.md:483` | 匹配 |
| 22 | `recovery_after_plan_before_execution` | `requirements.md:150,305` | `requirements.md:484` | 匹配 |
| 23 | `recovery_tool_result_before_consumption` | `requirements.md:151,307` | `requirements.md:485` | 匹配 |
| 24 | `recovery_subagent_interrupted` | `requirements.md:152,309` | `requirements.md:486` | 匹配 |
| 25 | `recovery_waiting_authorization` | `requirements.md:153,311` | `requirements.md:487` | 匹配 |
| 26 | `recovery_after_write_before_effect_success` | `requirements.md:154,313` | `requirements.md:488` | 匹配 |
| 27 | `recovery_verification_interruption` | `requirements.md:155,315` | `requirements.md:489` | 匹配 |
| 28 | `recovery_multiple_interruptions` | `requirements.md:156,317` | `requirements.md:490` | 匹配 |
| 29 | `recovery_checkpoint_integrity_or_version` | `requirements.md:157,319-323` | `requirements.md:491` | 匹配 |
| 30 | `context_long_history_fact_retention` | `requirements.md:158,333` | `requirements.md:492` | 匹配 |
| 31 | `context_long_working_memory_priority` | `requirements.md:159,335` | `requirements.md:493` | 匹配 |
| 32 | `context_large_node_output_projection` | `requirements.md:160,337` | `requirements.md:494` | 匹配 |
| 33 | `context_multi_source_overflow` | `requirements.md:161,339` | `requirements.md:495` | 匹配 |
| 34 | `context_compression_result_equivalence` | `requirements.md:162,341` | `requirements.md:496` | 匹配 |
| 35 | `context_invalid_memory_pressure_isolation` | `requirements.md:163,343` | `requirements.md:497` | 匹配 |
| 36 | `context_long_current_request_preserved` | `requirements.md:164,345` | `requirements.md:498` | 匹配 |
| 37 | `context_unsafe_compression_refusal` | `requirements.md:165,347` | `requirements.md:499` | 匹配 |

## 测试与机械检查

| 检查 | 结果 |
|---|---|
| 阶段二开始前目标 SHA-256 | `b3f7dbf57cf7cdc00c75427c030ef3e5244354e6923c5f773326b60aafa18a5a` |
| 报告写入前目标 SHA-256 | 与初始哈希完全一致 |
| discovery 非空与哈希 | 35,186 字节、244 行；`24ec88d046691882f4f6888db317d841e37d1614ddc6b0230041bccb4f8f8a24` |
| 第 4 节清单机械解析 | 37 行、37 个唯一 ID、序号 1—37 连续；`S+L=21`、`S=16` |
| EARS ID 机械解析 | 102 条、102 个唯一 ID |
| 后端聚焦回归 | `34 passed in 6.97s` |
| 前端通用 Agent 回归 | `npm run test:general-agent` 成功；TypeScript 编译及 4 个测试脚本通过 |
| Graphify | 按项目规则禁用，未运行 |

这些回归只证明当前资产探查与相邻基线可复现，不代表 37 条新 Benchmark 已实现或已 37/37 通过；目标需求本身也没有作出该错误陈述。

## 分级问题

- Critical：0
- Major：0
- Minor：0
- Info：0

## 修正项（FAIL 时）

不适用。

## 门禁理由

目标满足原始目标、项目不可变规则、阶段一 E1—E16、37 条案例逐项追踪、六门禁真实证据、异常/恢复/非功能可测试性、计划与现状区分以及对象哈希一致性条件。必需机械检查均实际完成且通过；没有 critical、major、事实错误、规则冲突、虚构现有接口或核心不可验证项，因此 requirements 独立门禁通过。

结论：PASS
