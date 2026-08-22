# 通用写作智能体评测体系重构——研究与设计决策

## 1. 文档信息

- 规格：`1.1/通用写作智能体评测体系重构`
- 发现级别：完整
- 调查时间：2026-07-27
- 输入对象：`requirements.md`、`independent-validation-report-requirements.md`、`gap-analysis.md`
- 需求 SHA-256：`b5b65cf351b58c6ff72bfc6f76f1d9c3b10470ebc01875670571957fe14a1cf2`
- 前置门禁：`state.py show` 与 `state.py validate` 已确认规格处于 `requirements_validated`，需求独立报告为当前哈希对应的 `PASS`
- 目标：捕获影响新评测边界、密封夹具、Runtime 窄适配、硬门禁、工件、实验、API、桌面工作台、破坏式清理和验证的当前事实与取舍
- 写入边界：本阶段只生成 `research.md` 与 `design.md`，不修改需求、状态、代码、测试、配置、资料或活动数据

## 2. 需求与约束摘要

| 需求范围 | 技术约束 | 非功能约束 | 本次收敛结果 |
|---|---|---|---|
| 1.1—1.25 固定套件与生产目录 | 套件、案例、能力引用、预算、预期产物、校验器和脚本处于同一可哈希合同；生产发现形成 17 Tool + 12 Subagent 内容寻址快照 | 29 项每项至少一个真实 `required` 调用且硬门禁合格的案例；漏项/目录漂移执行前失败 | 使用单一固定 JSON suite 合同、生产发现快照、`required_invocations` 与 observed invocation 反向证明 |
| 2.1—2.16 可复现身份 | 运行期间冻结 suite/fixture/case/条件；元数据不可用必须显式记录 | 不依赖 mtime；敏感内容最小化 | 运行保存解析后的不可变合同快照、哈希、Git/模型/环境可用性 |
| 3.1—3.17 隔离夹具 | 每 case 独立临时 assets root 与 Mongo namespace；不得使用活动 Runtime 或活动事实 | 取消、并发、崩溃后仍能证明边界 | 评测专用 Runtime factory、每案例临时根和独立 Mongo 数据库、边界守卫与清理器 |
| 4.1—4.15 确定性基线 | 确定性检查与非确定性裁判分开；`StrictScriptedDriver` 以一个全局有序流逐步匹配任务、模型、Tool、Subagent 与人工介入交互 | 意外、乱序、内容不符、脚本耗尽、剩余步骤和规范化重复漂移均有稳定错误与证据 | 类型化静态 verifier registry + strict driver 消费轨迹/finalize + 规范化结果身份 |
| 5.1—5.27 判定真值 | 六预算与产物、校验器、停止、安全、证据六类硬门禁取交集；case/suite/mechanism 各自有硬门禁 | 固定 benchmark 直接给整体能力结论；禁止验证集/测试集差异和指标放行 | `GateResult`、`MechanismGateResult`、`MechanismConclusion` 与不可覆盖真值表 |
| 6.1—6.17 失败解释 | 主失败类别和全部类别并存；suite 声明确定全序 | 归因不足时保留“无法确定” | 封闭失败枚举、稳定优先级、证据定位和双口径聚合 |
| 7.1—7.23 证据与工件 | 只读消费 Runtime 记录；精确 ID 链；不复制巨型轨迹 | 跨仓储冲突、缺失、损坏可见 | 共享只读 evidence reader Protocol + 基础设施组合 adapter + 规范化 bundle |
| 8.1—8.31 分轨与机制 | scripted synthetic 与 live provider 共用 case 合同/证据形状但绝不混算 | 无真实开关只做专项硬门禁；只有真实开关、严格可比、收益阈值和核心无回归时才允许 qualified ablation | track adapter、机制资格门禁、comparability gate、独立指标与 `decision_source` |
| 9.1—9.9 生命周期 | 幂等提交、取消不再启动新 case、单 case 失败继续、运行级隔离失败终止 | 中断不能显示通过；终态不可反写 | 持久状态机、租约、unfinished 恢复、原子 JSON 工件 |
| 10.1—10.34 UI | 保留 route/card/nav；新 API/type 一一对应；无新依赖 | 结论层级固定为整体能力→工作记忆专项→局部机制→DeepSeek 闭环→准入后多模型；指标只解释 | 重写 feature shell，复用现有组件，渐进下钻且不使用内容分割线 |
| 11.1—11.15 相邻边界 | 不改 Runtime 审计字段/写入；不拥有恢复基准或其他评测 | 数据事实安全和费用不可用语义 | 新评测只拥有派生评测合同/工件，Runtime 仍是原始证据所有者 |
| 12.1—12.21 清理 | 旧代码、接口、结果、前端合同、测试和现行说明破坏式清除 | 历史快照与共享资产保留 | 不设计 reader、mapper、迁移或回退；以精确清单与全仓扫描验收 |
| 13.1—13.15 typed artifact | 五类产物、注册式 verifier、禁止 Shell/命令/dynamic import | verifier 无副作用且结果可复核 | 判别联合模型、静态构造注册表、只读输入和类型匹配预检 |
| 14.1—14.20 工作记忆专项 | 只有 `ACTIVE` 可进入当前事实；旧三态只进入隔离修复投影；`BASIS/REVIEW_TARGET` 传播、`REPAIR_SOURCE` 不传染 | 节点摘要、digest、snapshot、`reuse_from_node_id` 任一复活即专项整体失败 | 生产端 producer-validity 门禁 + 四个稳定 memory case + 七项机制硬门禁 |
| 15.1—15.40 首轮闭环与多模型 | synthetic 全绿后单独 DeepSeek V4 Pro 完整 live suite；首轮冻结；系统缺陷只经 `/api/inbox/issues` | 冻结工件不回写 issue；Inbox 未持久化/读回/最新关联 revision 不对称均阻断；多模型证据不足即不可比 | iteration/closure 状态机、稳定 subject、versioned correlation repository、pending intent/reconciler、comparison admission |

真实未知仅有各 case 的产品阈值和比较时实际可用的代表模型集合。需求明确禁止擅自预设阈值或伪造模型可用性；设计把阈值建模为必须显式配置并进入 suite hash 的合同，把候选模型建模为运行前 probe 的输入。首批建议比较 DeepSeek、GPT、Claude 三个代表系列各一个当前目录模型，但只有 probe、实际 provider/model、fallback、replay、用量、费用与错误证据齐全的运行才能进入比较。

## 3. 当前项目事实

### 3.1 权威资料

| 资料 | 状态 | 关键事实 | 对设计影响 |
|---|---|---|---|
| `AGENTS.md` | 当前规则 | 单本小说；能力目录与运行实例解耦；动态 DAG；五层记忆；Markdown/Mongo 事实源；JSON 仅作运行与审计；旧实现需同步清理 | suite 只能引用真实注册能力；夹具是隔离单本小说；评测工件不能成为小说事实 |
| `README.md` | 当前仓库地图 | 当前旧评测报告是历史入口；Runtime、恢复、召回等资料各自独立 | 替换时更新当前地图，不改历史快照 |
| `DESIGN.md` | 当前唯一前端视觉规则 | 午夜极光控制台、高密度低干扰、禁止内容分割线、中文桌面网页 | 新工作台用紧凑行与右侧详情，不能做普通后台大卡片或移动布局 |
| `docs/rule.md` | 当前规则 | 当前资料与历史快照职责不同；资料说明不复制代码 Schema | 更新现行资料，保留 `docs/历史/` 原貌 |
| `project_assets/readme.md` | 当前数据目录说明 | 旧评测结果和 Runtime 派生证据职责不同 | 新目录职责与旧活动结果清理必须同批更新 |
| `requirements.md` | 已独立校验 | 15 组、325 条连续数字验收标准 | 所有设计元素必须回溯到 1.1—15.40 |
| `gap-analysis.md` | 当前上游分析 | A/B/C 均有条件可行，继续扩展旧五维根模型不可行；C 可最大化复用窄共享边界 | 采用方案 C，并在设计中限制 adapter 暴露面 |

`README.md` 的“阶段 04”段落仍使用旧的五层近义名称；该文字不得覆盖 `AGENTS.md` 已固定的“稳定记忆、工作记忆、长期记忆、历史记忆、当前请求”。替换现行资料时应同步纠正，但本设计不修改 Runtime 五层实现。

### 3.2 旧评测代码与测试

| 资产 | 现有状态 | 证据 | 设计判断 |
|---|---|---|---|
| `src/taichu/application/evaluations/general_agent/models.py` | 旧单案例、五维模型 | 旧模型包含 dataset/case/check/dimension/record | 全部旧业务类型删除，不作为新模型基类 |
| `src/taichu/application/evaluations/general_agent/service.py` | 对既有 run 做事后加权评分 | `GeneralAgentEvaluationService` 读取历史 run 并计算五维结果 | 删除；新根流程是 suite 主动执行多个隔离 case |
| `src/taichu/application/contracts/general_agent_evaluation.py` | 旧 dataset/result repository Protocol | 两个旧 Protocol | 删除；只复用项目采用 Protocol 隔离行为的模式 |
| `src/taichu/infrastructure/evaluations/general_agent_repository.py` | 旧 fixture reader 与 `general_eval_*.json` store | 文件名与记录身份耦合 | 删除；不增加旧结果 reader |
| `src/taichu/api/routes/general_agent_evaluations.py` | 旧前缀 `/api/agent-evaluations/general-agent` | datasets/evaluations GET/POST/DELETE | 删除并使用新资源前缀，避免旧路径继续可达 |
| `src/taichu/api/schemas/general_agent_evaluations.py` | 旧 DTO | dataset/case/run_id 的 post-hoc 请求 | 删除并按 suite/run/case/bundle/experiment 新资源重写 |
| `tests/fixtures/evaluations/general_writing_assistant_core/manifest.json` | 旧 8 题、旧权重/关键词合同 | 旧 fixture | 删除；题意只可人工重审后转写为新 case，不做结构迁移 |
| `tests/integration/api/test_general_agent_evaluations_api.py` | 旧 API 集成测试 | 断言旧五维契约 | 删除并新建资源级测试 |
| `project_assets/derived/agent_evaluations/general_agent/general_eval_*.json` | 旧活动结果 | `project_assets/readme.md` 当前说明 | 精确物理清理；不转换、不回退、不列出 |

### 3.3 Runtime 与共享只读证据

| 资产 | 现有事实 | 证据 | 可复用边界 |
|---|---|---|---|
| `GeneralAgentRun` | 不可变且拒绝额外字段；含 run/conversation/request、动态 plan、revision、node runs、HITL、final answer、context snapshot、compression、checkpoint revision 和终态 | `src/taichu/application/general_agent/models.py:14-17`、`:404-489` | 作为只读原始运行证据，不导入为评测根模型 |
| 节点/授权/副作用引用 | node run 含 plan revision、attempt、capability、source/artifact refs、授权与 effect | `models.py:159-191` | 产出能力路径、安全、产物 provenance 和六预算观察值 |
| 调用轨迹 | `InvocationTraceRecord` 含 call/parent call、run、capability type/name、状态、hash、Token、重试、时长和错误 | `application/invocations/models.py:97-126` | 以稳定 ID 构建调用树；不复制完整输入输出 |
| 上下文快照 | snapshot 绑定 conversation/run，保存 `content_sha256` 并自校验 | `general_agent/models.py:370-390` | evidence bundle 只保存 snapshot id、hash 和统计，不保存正文 |
| LLM usage | 可按 gateway `call_id` 精确读取，Token/费用均允许不可用 | `application/contracts/llm_usage.py:14-30`、`application/models/llm_usage.py:15-46` | 当前 trace call ID 与 gateway call ID 不同，不能直接相等 join；评测隔离 observer 必须在同一 exchange 内同时观察两个既有 ID |
| LLM replay | 按 gateway call ID 或 run 读取；记录 request/response hash、model/provider、Token/费用和脱敏信息 | `application/contracts/llm_replay.py:8-15`、`application/models/llm_replay.py:36-77` | 读取 hash/模型/状态/统计；不复制 message、Prompt 或 response 正文到 bundle，也不要求改写其现有 ID |
| 检查点 | saver 可按 thread/run 精确 inspect/list revisions；revision 有 `content_sha256` 链 | `infrastructure/general_agent_runs/langgraph_checkpoint.py:78-110`、`:511-547` | 基础设施 adapter 规范化为只读 checkpoint evidence；不能只用 application recovery summary，因为后者丢弃 revision hash |
| 副作用 | `EffectRecord` 含 effect/attempt/run/node/tool、授权、幂等键、状态和资源范围 | `application/general_agent/recovery.py:57-75` | 生成最小副作用摘要和权限证据 |
| 恢复快照 | Runtime service 已只读聚合 checkpoint/effect 摘要 | `application/general_agent/service.py:414-490` | 可作为行为先例；新评测需要更窄且包含 checkpoint hash 的 adapter |
| 恢复 benchmark | 独立脚本与独立结果 | `scripts/benchmark_general_agent_recovery.py` | 只引用为相邻证据，不进入 suite 通过率 |

已有 reader 的粒度不完全一致：run、snapshot、replay、effect 以 run 为边界；invocation 有 run + call tree；usage 的安全精确入口是 `get(call_id)`；checkpoint 的 hash 只存在于基础设施 revision summary。新 adapter 必须分别校验每个 source locator 的原生身份、内容 hash、状态和 case run 归属，不得把“返回空列表”统一解释为“没有调用”，而要结合 case 的 evidence requirement 产生 `available/missing/corrupt/not_applicable/conflicting`。

### 3.4 密封夹具与独立 Runtime 可行性

| 主题 | 当前事实 | 证据 | 结论 |
|---|---|---|---|
| Mongo 临时数据库 | `MongoKnowledgeRepository` 支持注入 `client`、`database_name`、`collection_name`；initialize 会设置严格 validator 和两个索引 | `infrastructure/knowledge/mongo_repository.py:43-95`、`:253-345` | 每 case 使用 `taichu_eval_<32hex>` 独立数据库，复用现有 validator/index |
| Mongo 集成测试 | 现有测试使用 `taichu_test_{uuid}`，caller 持有 client，前缀保护后 drop database | `tests/integration/infrastructure/knowledge/test_mongo_repository.py:31-54` | 证明隔离数据库 + 显式清理可实施；评测不得使用活动 `taichu` 数据库 |
| Markdown backend | backend 绑定 `project_assets_dir`，首次访问会创建骨架 | `infrastructure/storage/markdown_backend.py:20-50`、`:149-186` | 不能把密封源直接挂给 Runtime；先校验并复制到 case 临时 root |
| Runtime 派生根 | run/checkpoint/effect/context/memory/index/replay/trace/artifact 都从同一 assets root 构造 | `main.py:248-269` 及对应 repository 构造器 | 每 case 使用唯一临时 root 即可隔离全部文件型状态 |
| Runtime 组装 | CapabilityContext、ToolRegistry、SubagentRegistry、Orchestrator、Executor、RuntimeService 构造边界开放 | `application/capabilities.py:11-35`；tools/subagents registry；general agent orchestrator/executor/service | 新增评测专用 factory，不需要活动 `app.state` |
| 已有测试 | 单元测试手工构造完整临时 Runtime；API 集成测试使用 TemporaryDirectory + Settings root | `tests/unit/application/general_agent/test_runtime.py:170-293`、`:1141-1182`；`tests/integration/api/test_general_agent_api.py:103-120` | 独立真实 Runtime 路径已有可复现实证 |
| `create_app` | 会附带 embedding/Qdrant/recovery/watchdog 等生命周期 | `main.py:206-239`、`:493-500` | 评测 factory 不复用 `create_app`，避免额外副作用与活动实例 |
| scripted gateway | 仅测试私有替身按 task_name 队列消费并记录请求；生产无公共 scripted schema/factory | `tests/unit/application/general_agent/test_runtime.py:111-151` | 不能导入测试私有类；在评测基础设施新增确定性 gateway |
| LLM 请求配置 | `LLMRequest` 只有 response mode、temperature、max output tokens 等当前字段，无 seed/top_p | `application/contracts/llm.py:66-81` | 复现元数据对不存在的参数记 `not_supported`，不得虚构 |

`MongoKnowledgeRepository` 没有 drop database API；评测 workspace handle 必须拥有 Mongo client/database 生命周期，在 `runtime.shutdown()` 之后按严格前缀校验执行 drop，再关闭 client 和删除临时目录。若未来改动 `main.py` 或 `config.py` 抽取共享工厂，将触发 `start.bat` 强制回归；当前设计把 factory 放在新评测基础设施内，不要求修改配置字段。

### 3.5 Graphify

- 当前项目规则明确禁用 Graphify。
- 本次未运行 `graphify query/path/explain/update/watch`，未读取 `graphify-out/` 作为事实源。
- 发现使用 `rg`、当前源码、测试、配置、启动文件、已校验需求和差距分析。
- 设计中的所有“现有”对象均有直接文件证据；“新增”对象明确标为计划新增。

### 3.6 生产能力目录与注册约束

- 当前生产发现目录包含 17 个 Tool 与 12 个 Subagent，共 29 个一等能力。suite 只能保存该发现结果的规范化只读快照，不得手工维护第二份“应有能力”清单。
- `src/taichu/application/subagents/registry.py:45-61` 注册 Subagent 时会校验其 `allowed_tools` 已存在于 `ToolRegistry`。评测 Runtime factory 必须先物理注册完整生产目录及依赖，再以 case exposure/policy 限制本案可调用范围；不能把 `case.allowed` 实现成只物理注册这些 ID。
- `allowed` 只是权限上限，manifest 声明也只是注册事实，均不能证明覆盖。覆盖证据必须来自真实 invocation tree 中 `status=completed` 的 `required_invocations`，并同时通过相关硬门禁。
- 漏项、未知 ID、重复映射、类型错配、父子链不可追踪或生产目录 hash 漂移，必须在任何 case 启动前令 contract preflight 失败。

### 3.7 严格脚本驱动与机制判定

- 现有单元测试私有 scripted gateway 只按任务名消费模型响应，无法证明 Tool、Subagent、HITL、恢复和全局交互顺序。新 `StrictScriptedDriver` 消费一个跨 model/tool/subagent/human/task 的全局有序流；模型步骤给出确定性响应，能力步骤包裹并观察真实 handler，不能用假结果代替生产能力。
- 稳定错误族固定为 `SYNTHETIC_UNEXPECTED_INTERACTION`、`SYNTHETIC_OUT_OF_ORDER`、`SYNTHETIC_CONTENT_MISMATCH`、`SYNTHETIC_SCRIPT_EXHAUSTED`、`SYNTHETIC_REMAINING_STEPS`、`SYNTHETIC_NORMALIZATION_DRIFT`。错误证据包含 step id/index、期望/观察、失败 matcher/path 和剩余 step IDs；Runtime 停止后必须调用 `finalize()`。
- 重复运行规范化只排除时间戳、UUID、临时路径等易变值，保留节点状态、交互序列与结果、typed artifact hash、gate result 和 stop reason；不一致即 deterministic hard gate 失败。负向 strict-driver 用例属于 harness 合同测试，不进入业务 case 集。
- suite/core 与所有局部 mechanism 都必须由硬门禁直接给出结论。没有指向真实运行配置路径的开关时，只运行 mechanism gate，不创建伪对照实验；只有 control/treatment 除该开关外完全同构、两臂 invariant gate 都通过、收益阈值达标且核心无回归时，才允许 `qualified_ablation`。

### 3.8 工作记忆生产缺口

- `AgentMemoryValidity` 已有 `ACTIVE/STALE/REJECTED/SUPERSEDED`；关系已有 `BASIS/REVIEW_TARGET/REPAIR_SOURCE`。传播只沿前两类关系，`REPAIR_SOURCE` 不传染；新修订会把旧项置为 `SUPERSEDED`。
- `AgentMemoryService.list_invalidated` 默认只返回 `REJECTED/STALE`，未把 `SUPERSEDED` 纳入修复专用投影。`ContextAssembler` 会用 producer validity 排除节点摘要，digest 共用 excluded node IDs，snapshot 保存 active 与 invalidated refs。
- 当前复用路径仅校验旧节点 `SUCCESS` 且 capability type/name 相同：`orchestrator.py:273-292`、`executor.py:190-227`。`service.py:952-964` 随后可能把复用结果作为当前 revision 的成功节点再次记录为 `ACTIVE` producer memory，存在“旧失效产物被新 producer ref 复活”的真实缺口。
- 生产修复必须引入精确 producer ref 的有效性证明，并让规划校验和 executor 复用共同要求 source producer 为当前依赖指纹下的 `ACTIVE`；复用保留 `reused_from_producer_ref`，不得靠换 node/run/revision 标识洗白。当前事实投影只含 `ACTIVE`，修复投影显式含其余三态并带 repair-only 标签。

### 3.9 Inbox、首轮闭环与模型目录

- 系统问题唯一入口已有 `GET/POST /api/inbox/issues` 与 `PATCH /api/inbox/issues/{item_id}`，但缺少 GET-by-ID。`MVPInboxIssue` 也没有机器可读关联链接或修订字段。
- create 接受 caller-supplied ID 或随机 UUID，却没有唯一性检查；patch 是“先 list、后 rewrite”，锁不覆盖读改写整体，可能丢失并发更新，且写后没有读回验证。
- 当前 `project_assets/source/workspace/inbox_issues.jsonl` 有 16 条活动记录，均没有 `revision/links`。`MVPInboxIssue`、`Create/PatchInboxItemRequest`、`MVPInboxService`、`ProjectAssetStorageContract`、`ProjectAssetStorageBackend` 和 `test_mvp_first_api.py/test_mvp_contracts.py/test_markdown_backend.py` 都需要同批升级；只改评测 coordinator 会破坏现有 Inbox 读写。
- 前端 `web/src/lib/types/mvp.ts` 的 issue 类型没有 revision/link，`web/src/lib/api/mvp.ts` 的 PATCH 只传 updates，`web/src/components/inbox/inbox-board.tsx` 状态操作也没有并发版本。现有页面必须携带当前 revision；409 后刷新并用中文提示用户确认，不能让评测专用客户端成为唯一遵守 CAS 的调用者。
- 内容必须严格保持“记录日期、状态、现象、根因、影响、修复、验证、相关代码”八行、全角冒号与固定顺序。机器关联不能塞进这八行文本。冻结 suite/首轮/failure 工件在创建时只嵌入由自身种类、稳定 ID 和内容 hash 派生的 `correlation_subject_id`，不在 issue 创建或关闭后回写。
- `IssueCorrelationRepository` 应归评测所有：relation ID 只由 issue ID、subject ID 与 relation kind 生成，不含可变 issue content/status/revision；不可变 relation revision 保存每次 Inbox readback observation，CAS manifest 指向最新 revision。Inbox typed link 只保存 relation/subject/kind/subject content hash。
- 单协调者租约以 `(suite_hash, defect_fingerprint)` 为键；稳定 issue ID 由缺陷指纹派生。intent 与 relation revision 必须按操作输入确定性寻址并使用 create-if-absent，否则“revision 已写、manifest CAS 未写”的崩溃窗口会在重放时制造重复 revision。协议固定为“租约→确定性 pending intent→Inbox CAS→readback→确定性 revision snapshot→relation manifest CAS→iteration manifest CAS”；任何一步失败都保持闭环未完成，reconciler 按同一 intent/revision hash 继续。每次尝试另写 append-only observation。
- 旧 Inbox 记录读取时投影为 `revision=0, links=[]`，读取本身不改文件；第一次 `expected_revision=0` 的成功 CAS 才把该行原子升级为新 shape 和 revision 1。它是活动 Inbox 数据合同演进，不是旧通用 Agent 评测结果兼容或回退。
- 只有全部 relation manifest confirmed、iteration manifest 已清 pending intent、最新 correlation revision 与 Inbox readback 对称，且“目标 case + 当前 suite hash 全量重跑 + core 无回归”满足后，才能关闭并准入比较。
- 模型目录的正确当前路径是 `src/taichu/infrastructure/llm/catalog.py`。当前目录包含 DeepSeek V4、GPT-5.6、Claude 系列条目，但目录存在不等于 provider 可用；live 前必须 probe 并记录 requested ID、实际 provider/model、fallback、replay、usage/cost/error。
- 固定顺序是 synthetic 全绿及所有核心/机制门禁稳定后，单独运行 DeepSeek V4 Pro 完整 live suite，冻结首轮工件，分类与闭环系统缺陷，最后才允许多模型比较。suite hash 改变即重启整条序列。

### 3.10 评测关联观察与外部资料夹具缺口

- `LLMRequest` 当前已有 `run_id/context_snapshot_id`，但没有由调用方提供的相关性字段。编排器写 invocation trace 时生成 `call_*`，RightCode gateway/replay/usage 另生成 `llm-call-*`；两者无法按字段相等直接 join。Subagent 的 LLM request 也不携带 context snapshot。
- 需求 11.10 明确禁止因评测读取改变 Runtime 审计字段、生命周期和写入流程，因此不能通过修改 `LLMRequest`、`InvocationContext`、trace、Orchestrator、Subagent runner、Executor 或 RightCode 来统一 ID。合法缝隙只存在于评测隔离 Runtime 的依赖注入。
- 三个源的原生 hash 不能横向比较：Orchestrator trace 对 `str(request)` 的投影做 hash，Subagent trace 只 hash messages，RightCode replay 则 hash 脱敏规范字段。gateway 已返回但应用 JSON/Pydantic 校验失败时，replay/usage 为 `completed` 而 trace 合法地为 `failed`；因此“hash/status 必须跨源相等”会把真实证据误判为冲突。
- 评测 factory 可在不改变底层写入的前提下包装评测专用 LLM gateway、InvocationTraceRepository append、replay writer 和 usage writer。`EvaluationCorrelationScope` 以 context-local `exchange_id` 绑定同一 async task，observer 只记录各源既有 locator、源原生内容 hash、run ID 和 status。exchange 关联只依赖同 task scope 与观察基数；每个 observation 再按自己的源算法和 locator 复读。冲突只包括源内复读不一致、非法状态映射、观察多/少、owner 或 run 不匹配。
- live provider 的 available record 要求既有 trace/replay/usage locator；gateway returned 映射 replay/usage completed，trace 可 completed，或在可证明的 JSON/schema 校验阶段 failed；gateway raised 映射三者 failed。synthetic 没有 RightCode replay/usage：它要求 strict-driver step、既有 trace 和 evaluation-owned fixed usage/cost observation，Runtime replay/usage 明确 `not_applicable`。Token 预算统一遍历 available record 的 token observation：live 按 usage locator/gateway call ID 读取，synthetic 使用冻结的 inline 观察，不把不存在的 Runtime 源标为 missing。
- 底层 gateway/append/writer 必须先原样完成；observer、scope 或 correlation repository 的异常不得替换底层返回、异常类型或写入次数，只能让该评测 attempt 的 correlation 变为 missing/invalid。CaseExecutor 在整个 Runtime 调用外层持有 case correlation scope，并在 `finally` 中把取消、缺 trace 或残留 pending exchange 固化为 invalid；不能依赖 task 结束后仍可取得 ContextVar。
- context snapshot 不从 Subagent request 推断：observer 取得 trace `run_id` 后，通过只读 run source 精确读取该既有 run record 的 `context_snapshot_id`。正常活动 Runtime、共享仓储和所有原审计字段/值/写入调用完全不变。
- case 6 的生产 `search_external_sources/read_external_source` 依赖 `ExternalResearchService`。若评测 factory 注入生产 DuckDuckGo backend，会引入网络、内容漂移和非密封来源；若不注入则真实 Tool 无法完成。
- synthetic 与 live_provider 两轨都应使用 fixture-backed deterministic `ExternalResearchBackend`，再通过真实 `ExternalResearchService`、Tool handler、授权和 invocation 链执行。外部文档清单/正文进入 fixture snapshot 与 hash；“live”只表示 LLM provider live，不表示外部资料后端联网。

## 4. 前端架构分析

### 4.1 页面与导航

| 项目 | 当前事实 | 本次关系 |
|---|---|---|
| route | `web/src/app/task-monitor/general-agent/evaluation/page.tsx` 是薄入口，直接渲染 `GeneralAgentEvaluationShell` | 保留 |
| task card | 任务入口已有“通用写作智能体评测”入口 | 保留名称和跳转关系 |
| monitor nav | `GeneralAgentMonitorNav` 的 `evaluation` 项指向固定 route，当前中文短标签为“效果评测” | 保留关系；页面标题使用完整中文名称 |
| AppShell | 现有应用壳承担全局导航与页面表面 | 复用，不新增平行壳 |
| feature shell | 旧 Shell 围绕 dataset/case/历史 run/五维分组织 | 同文件破坏式重写为 suite 工作台 |

### 4.2 当前组件树

```text
web/src/app/task-monitor/general-agent/evaluation/page.tsx
└── GeneralAgentEvaluationShell
    ├── AppShell
    ├── GeneralAgentMonitorNav
    ├── 旧数据集与案例选择
    ├── 旧既有运行匹配与评测提交
    └── 旧五维结果列表与详情
```

目标树保留前三个真实入口对象和 `GeneralAgentEvaluationShell` 导出名，内部重写为套件控制、汇总、紧凑案例行、右侧详情、实验与机制指标；具体职责在 `design.md` 第 13.2 节定义。

### 4.3 组件准入

| 能力 | 现有组件 | 决策 |
|---|---|---|
| 页面壳与导航 | `AppShell`、`GeneralAgentMonitorNav` | 直接复用 |
| 主次操作 | `Button` | 复用白色胶囊/线框变体 |
| case/机制筛选 | `Checkbox` | 复用 |
| 分页 | `CompactPagination` | 组件合同直接需要 `page/pageSize/total` 并支持任意跳页；新 API 必须返回页码总量，调用处传入 `border-t-0` |
| 图标 | `lucide-react` 已安装，monitor nav 已使用 | 复用，不新增 icon 依赖 |
| 加载反馈 | 原生 `div` + `aria-busy` + Tailwind | 使用当前技术栈内已有能力 |
| 取消/实验确认 | 工作台内联确认区 + 现有 Button/Checkbox | 确认状态由 Shell 持有，不新增共享覆盖层组件 |
| 详情展开 | 原生 `aside/div/details` | 不新增组件依赖，使用 `aria-expanded`/可见焦点 |

`CompactPagination` 当前根节点包含 `border-t border-[var(--tc-border-subtle)]`，其 class 合并使用项目现有 `cn/twMerge` 语义。评测页在调用处传入 `border-t-0` 即可移除本页内容分割边，不必把局部需求扩散为共享组件全局视觉变化；输入框/按钮自身完整外轮廓仍符合 `DESIGN.md`。其输入是数字 `page/pageSize/total` 并支持任意跳页，因此新列表统一采用 `page/page_size/total/total_pages`，可附带单调 `index_revision/total_snapshot` 提示列表漂移。

### 4.4 旧 API 与类型

当前前缀为 `/api/agent-evaluations/general-agent`：

- `GET /datasets`
- `GET /datasets/{dataset_id}`
- `POST /evaluations`
- `GET /evaluations`
- `GET /evaluations/{evaluation_id}`
- `DELETE /evaluations/{evaluation_id}`

前端 `general-agent-evaluation.ts` 与后端旧路由一一绑定；旧类型包含 assessment mode、旧 case expected、reference answer、五个 dimension、score/weight/overall score、`completed_with_warnings` 等合同。新设计不保留同名前缀、字段转换、删除旧结果操作或兼容读。

`apiRequest` 已能从 `{detail: {error: {code, message}}}` 或 `{error: ...}` 提取中文 message，但会丢失结构化 code/details/request ID。新 API 需要前端区分 409 幂等或 revision 冲突、422 suite 错误列表和 404，并把 request ID 展示给操作者，因此设计要求 error envelope 显式带 `request_id`，基础函数新增兼容的 `ApiError(status, code, message, details, requestId)` 而不破坏其他调用者。

### 4.5 状态所有权

| 状态 | 所有者 | 前端职责 |
|---|---|---|
| suite 定义、内容身份、覆盖 | 服务端固定合同 | 只读显示、筛选，不重算哈希 |
| run/experiment 生命周期与进度 | 服务端 artifact repository/state machine | 轮询当前详情、处理取消/恢复命令 |
| case 筛选、页码、选中行、右侧详情 tab | 页面 | 本地状态；切 run 时重置 |
| 提交中/idempotency key | 页面 action controller | 同一提交禁用；收到确认前保留 key |
| 详情与列表请求 | case/bundle/metrics hooks | 每个 resource key 使用单调 generation token + AbortController；只有 generation 仍为最新且 response revision/index_revision 不小于 `lastAppliedRevision` 才应用 |
| 中文状态 | 单一 view adapter | 不在组件内散落英文枚举判断 |

### 4.6 核心交互

| 用户动作 | API/副作用 | 成功 | 失败/恢复 |
|---|---|---|---|
| 选择 suite/track/provider | 读取 suite 详情或 provider 可用性 | 显示内容身份、覆盖与门禁摘要 | 中文错误、重试；无 provider 时 live 操作显示“模型提供商未配置” |
| 提交 run | `POST /runs` + idempotency key | 跳转/选中返回 run | 重复命中现有 run；409 异键冲突可操作提示 |
| 取消 | `POST /runs/{id}/cancel` | 状态进入“正在取消”，保留完成 case | 终态返回当前资源；失败可重试 |
| 恢复 unfinished | `POST /runs/{id}/resume` | 新 execution attempt 从干净 workspace 开始 | 不可恢复时展示原因和“重新运行” |
| 选择 case | 按需 GET case/bundle | 右侧展示预期/实际/gates/failure/evidence | 取消上一详情请求，错误只影响详情区 |
| 建实验 | `POST /experiments` | 显示控制/实验组和可比性 | 未声明差异/不可比时不显示增益 |

### 4.7 视觉与文案

- 页面模式：控制台工作台。
- 桌面基准：1280px 及以上；不增加移动断点、折叠菜单或触控流程。
- 主区高密度：顶部紧凑 suite 控制；摘要采用读数和短标签；case 使用窄行；右侧详情按需展开。
- 不使用横线、竖线、`divide-*` 或连续边框分组；通过灰阶表面、留白、圆角和 hover 建立层级。
- 极光只作为背景装饰线索，不承载任何功能状态。当前行、当前 tab 和当前导航使用灰阶表面、白字与中性完整外轮廓。
- 所有状态、错误、failure category、provider state、track 和 gate 使用中文映射；颜色仅辅助，不是唯一信息。
- 原始内部 ID、hash、Token、费用、evidence locator 进入技术详情，不占据默认行。

### 4.8 文件规划结论

- 保留 route、task card、monitor nav、AppShell。
- 破坏式重写现有 `GeneralAgentEvaluationShell`、API、types、view adapter 和 `evaluation-view.test.ts`；不改导出名。overview 任务卡说明可更新；当前 nav 没有独立说明字段，保持原组件和标签不改。
- 新增同 feature 目录下职责单一且与逻辑组件逐一对应的 suite controls、summary、run/experiment rail、case table、case detail、memory、first-live、model comparison、experiment、metrics 组件与 hook。
- 复用 `CompactPagination` 并由评测页传入 `border-t-0`，不修改共享组件默认样式。
- 加载使用 `div[aria-busy]` 与 Tailwind 弱表面；确认使用工作台内联确认区；详情使用 `aside/div/details`。纯状态转换在现有 Node 测试验证，焦点、键盘、ARIA 和真实 mutation 在固定端口浏览器手验，不虚称无 DOM 的 Node 脚本能覆盖。
- 无新前端依赖；`web/package.json` 不需要改动。

### 4.9 测试与固定端口

现有脚本：

- `npm run lint`
- `npm run test:general-agent`
- `npm run build`

`test:general-agent` 当前只是 TypeScript 编译加纯 Node 执行，没有 DOM 环境。实际会被脚本执行的 `web/tests/general-agent/evaluation-view.test.ts` 测试纯 reducer、API envelope/request ID 解析、request coordinator，以及 Inbox revision/link/legacy revision 0/CAS 409 的纯数据契约；`web/tests/inbox/issue-format.test.ts` 不在该脚本执行列表，仍只承担已有八行格式职责，不能作为本轮唯一门禁。不新增测试框架、依赖或 package script。真实交互验收固定使用：

- `http://localhost:3000/task-monitor/general-agent/evaluation`
- `http://127.0.0.1:8000`

### 4.10 前端风险

- 轮询、详情切换和取消可能产生迟到响应；同 resource 使用单调 generation token + AbortController + `lastAppliedRevision`，query key 只负责隔离资源身份，不能单独证明响应新鲜度。
- 相同提交在网络超时后重试可能重复；前端 idempotency key 与后端 submission hash 双重约束。
- suite/case 数量增长可能拖慢主视图；服务端分页，默认只取 summary，bundle 按需读取。
- `CompactPagination` 是共享组件；评测页只做调用侧无边框覆盖，不能为评测页新增平行分页组件。

## 5. 外部依赖与技术研究

### 5.1 结论

本规格不需要新增 Python、Node、数据库、消息队列或前端组件依赖：

- 后端现有 Python 3.12、Pydantic、FastAPI、LangGraph、PyMongo 已覆盖强类型合同、API、独立 Runtime 和临时 Mongo 数据库。
- JSON 原子写可复用项目现有 `temp + fsync + replace` 模式。
- 前端现有 Next.js、React、TypeScript、shadcn/Base UI、Tailwind 和 lucide 足够。
- 统计只需要样本数、均值、样本方差、min/max/range，可使用 Python 标准库实现。
- 内容哈希、规范化序列化、UUID/时间、临时目录和清理均由标准库支持。

因此没有需要验证版本、许可或迁移的新增外部依赖，本次未进行网络搜索。技术事实来自当前锁定项目源码和配置，而不是二手资料。

### 5.2 现有版本边界

| 层 | 当前配置 | 对设计影响 |
|---|---|---|
| Python | `>=3.12` | 使用 `StrEnum`、Protocol、精确 union 和标准库统计 |
| Pydantic/FastAPI | `pydantic-settings>=2.7`、`fastapi>=0.115` | 边界模型 `extra="forbid"`、冻结合同、HTTP response model |
| Mongo | `pymongo>=4.13,<5` | 复用 validator/index 和独立数据库 |
| LangGraph | `langgraph>=1.0` | 复用独立 Runtime/checkpointer，不复制审计 |
| Next/React/TS | Next 16.2.9、React 19.2.4、TypeScript 5、strict | 精确判别联合，无 `any` |

## 6. 架构候选

| 选项 | 边界与工作方式 | 优势 | 风险/限制 | 与当前架构契合 |
|---|---|---|---|---|
| A 原地扩展旧五维组件 | 在旧 models/service/repository/API 上增加 suite/track/gate | 初始装配改动少 | 直接违反 12.12—12.17；旧根聚合和新生命周期不兼容；形成双口径 | 不满足需求，排除 |
| B 完整新边界并自行读取所有 Runtime 存储 | 新评测重建 suite、fixture、runner、reader、artifact、experiment | 评测内部自治 | 容易复制 Runtime 语义、扩大所有权、产生平行巨型轨迹 | 部分契合，风险过高 |
| C 新评测核心 + 现有共享能力窄适配 | 新建全部评测合同/执行/判定/工件；通过共享只读 evidence Protocol、真实能力目录和独立 Runtime factory 适配现有资产 | 满足破坏式替换；不重建 Runtime；依赖方向清晰；UI 可复用 | adapter 若泄漏完整底层对象会重新耦合；需严守最小 DTO | 最契合，采用 |

## 7. 设计综合

### 7.1 泛化

- 把 15 组 325 条需求收敛为九个稳定边界：固定合同与生产能力目录、隔离执行、严格脚本、类型化判定、只读证据、工作记忆正确性、工件与状态、DeepSeek/Inbox 闭环、多模型准入与指标。
- suite/case/track/fixture/verifier/gate/artifact/experiment 是长期评测概念，不以某个 UI 流程或某个案例建临时类。
- `RuntimeEvidenceReader` 是 Runtime 审计的共享只读投影，不把其字段和写入职责迁入评测。
- `TrackExecutor`、`MechanismEvaluator` 和 `MetricAggregator` 的接口容纳 synthetic/live、工作记忆专项与局部机制，但固定 benchmark 仍由硬门禁而非指标给出结论。

### 7.2 构建 vs 采用

- 采用现有：真实 capability registry、RuntimeService 组装边界、Mongo validator/index、所有 Runtime 原始仓储、AppShell/nav/UI primitives、FastAPI/Pydantic、JSON 原子写模式。
- 自建必要部分：suite schema、capability snapshot、sealed fixture manager、evaluation runtime factory、strict scripted driver、track executor、typed verifier registry、gate/failure evaluator、memory scenarios、evidence adapter、artifact repository、iteration/Inbox closure coordinator、comparison admission、experiment coordinator、metrics modules。
- 不采用 Shell verifier、任意动态 import、mtime 关联、旧加权评分、SQLite/FTS、新数据库或外部 benchmark 框架。

### 7.3 简化

- 不创建第二套能力发现器；suite 预检直接读真实 registry 的只读目录。
- 不创建评测专用 Runtime DAG；仍由高层 Agent 对 case 用户原文动态规划。
- 不复制完整 Runtime trace；只保存 bundle 摘要、hash 与 locator。
- 不设计旧结果迁移、兼容包装、双写或回退。
- 不把 synthetic 写成另一套 case schema；同一 case 合同内嵌 scripted steps，并进入同一内容哈希。
- 不把所有指标塞进一个巨石 aggregator；六个小模块共享一个窄输入合同。
- 不新增全局前端状态库、图表库、表格库或分页组件。

## 8. 设计决策

### 决策 1：采用方案 C

- 背景：新旧生命周期、判定与数据所有权完全不同，但 Runtime/能力/UI 基础资产可安全复用。
- 替代方案：A 原地扩展；B 全部自建。
- 选择：新评测核心 + 共享 Runtime/能力/前端资产窄适配。
- 理由：同时满足破坏式替换、职责边界、证据真实性和实现复杂度约束。
- 权衡：需要设计一份严格的 shared evidence DTO，避免 adapter 泄漏。
- 需求：1.1—1.25、7.10—7.23、11.1—11.15、12.1—12.21、13.1—13.15。
- 后续验证：依赖扫描、只读故障注入、旧标识全仓扫描。

### 决策 2：每 case 独立 Runtime，不使用活动 app 或活动事实

- 背景：现有 `create_app` 会构造额外服务和恢复任务，活动 Runtime 与活动数据库不满足隔离。
- 替代方案：借用 `app.state`；为 case 只替换部分仓储。
- 选择：评测 factory 为每 case 创建唯一临时 assets root、唯一 Mongo database、真实选择性 registry 和独立 Runtime handle。
- 理由：当前构造边界和测试已证明可实施，且能物理隔离所有文件派生状态。
- 权衡：workspace 生命周期与清理器成为关键基础设施。
- 需求：3.1—3.17、11.2、11.10、12.21。
- 后续验证：并发、取消、崩溃、孤儿清理、活动事实前后指纹。

### 决策 3：synthetic 与 live 共享合同与真实能力，工件严格分轨

- 背景：scripted baseline 必须确定但不能伪装为 provider 结果。
- 替代方案：synthetic 直接构造假 case result；synthetic 使用测试私有 gateway。
- 选择：两条 track 都运行独立真实 Runtime 和真实已注册能力；差别仅在 LLM gateway adapter。scripted steps 内嵌在 case 合同，live 使用显式 provider 配置。
- 理由：得到同形 Runtime evidence，同时明确 provenance。
- 权衡：scripted 内容必须覆盖 Runtime 的模型调用序列，预检和消费顺序要严格。
- 需求：1.14、4.1—4.15、8.1—8.31。
- 后续验证：混轨查询拒绝、同工件重复 verifier、一处 case 改动改变全部相关 hash。

### 决策 4：确定性 verifier 和非确定性裁判分层

- 背景：语义质量可能需要模型判断，但硬门禁不得被其覆盖。
- 替代方案：把裁判分数加入总分；允许 case 提供命令。
- 选择：静态 typed verifier registry 只运行纯确定性实现；可选语义裁判结果进入 `advisory_judgements`，不进入硬 gate。
- 理由：可复现、安全、可解释。
- 权衡：确定性 verifier 只声明实际检查范围，不声称完整语义质量。
- 需求：4.1—4.15、5.1—5.27、13.1—13.15。
- 后续验证：命令/dynamic import 注入、judge 与 gate 冲突、同 bundle 重放。

### 决策 5：JSON 评测工件为派生审计事实，原始写入原子化

- 背景：评测工件允许使用 JSON/JSONL；SQLite/FTS 禁止；旧 JSON 合同不可兼容。
- 替代方案：Mongo 持久化评测运行；复用旧结果目录。
- 选择：新 `project_assets/derived/general_agent_benchmarks/` 保存新工件，manifest 原子 CAS，case/bundle/final artifact 写后不可变，索引可重建。
- 理由：符合数据宪法，避免引入新存储所有权。
- 权衡：需要租约、修订和索引重建处理进程中断。
- 需求：2.12、7.1—7.23、9.1—9.9、11.6、12.15—12.16。
- 后续验证：故障注入、终态保护、分页/索引重建、空间增长。

### 决策 6：新 API 使用资源化前缀，前端 route 不变

- 背景：用户要求保留页面入口，但禁止旧 API 兼容。
- 替代方案：保留旧 prefix 并更换 payload。
- 选择：后端新前缀 `/api/general-agent-benchmarks`；页面仍为 `/task-monitor/general-agent/evaluation`。
- 理由：从路由层机械证明旧 API 已删除，同时不改变用户入口。
- 权衡：前端 API/type 必须一次性切换。
- 需求：10.1—10.34、12.1—12.20、15.30—15.40。
- 后续验证：OpenAPI/路由清单、旧 prefix 全仓扫描、固定端口联调。

### 决策 7：覆盖只认真实完成调用，23 个固定 case 覆盖 29 个生产能力

- 背景：权限声明、manifest 和可发现性不能证明运行时能力可用。
- 选择：每个 case 声明 `applicable_tracks` 与 `required_invocations[{type,name,min_calls,max_calls,expected_outcome,parent/partial_order}]`；覆盖只统计真实 invocation tree 中完成且父子链可追踪的调用，并要求相关 case 硬门禁通过。
- 边界：23 个业务 case 是首批实用下限；strict-driver 负向、evidence 故障和 suite lifecycle 恢复放入 runner tests，不冒充业务能力覆盖。拒绝在 handler 前发生，用 evaluation-level security outcome 及 node/HITL/policy/access ledger 证明，不能伪造 `InvocationStatus=denied`。
- 需求：1.19—1.25、4.9—4.15、5.23—5.27、8.28—8.31。
- 后续验证：29 项反向映射、0/重复/错类型/错父链故障注入、生产目录漂移预检。

### 决策 8：工作记忆正确性同时修复生产复用门禁并纳入专项结论

- 背景：现有失效传播基本正确，但复用仅按 SUCCESS 与能力同名判断，可能复活旧产物。
- 选择：新增 producer-validity proof、统一当前/修复投影策略，并以四个稳定 memory case 和七项机制硬门禁覆盖来源指纹、传播、拒绝、修订/替代、并行隔离、投影、复用。
- 边界：`ACTIVE` 才是当前事实；`STALE/REJECTED/SUPERSEDED` 仅是 repair-only；`REPAIR_SOURCE` 不传染。任何节点摘要、digest、snapshot 或 reuse 泄漏都会使工作记忆专项整体不满足。
- 需求：14.1—14.20。
- 后续验证：状态迁移前后像、三类边、精确 producer ref、跨 plan revision 复用反例。

### 决策 9：DeepSeek 首轮与 Inbox 系统问题形成强顺序闭环

- 背景：首轮真实模型结果只有在可复现、可分类、可追踪修复后才具有比较资格。
- 选择：synthetic 与核心/机制全绿后运行单独 DeepSeek V4 Pro 完整 suite，冻结工件并分类；只有系统缺陷调用既有 Inbox API。subject 只绑定 run terminal artifact、suite artifact、first-live artifact 或 failure record。intent ID 由 operation/issue/desired payload/expected Inbox revision/有序 relations 确定性生成；revision ID 由 relation/intent/observed Inbox revision/operation 确定性生成。revision snapshot 先 create-if-absent，再 CAS relation manifest，最后 CAS iteration manifest；orphan 可识别、重放不重复。每次协调尝试另存 append-only observation。
- 边界：benchmark/verifier 缺陷、provider 行为、环境阻塞不创建系统问题；关闭必须有目标 case、当前 suite hash 全量重跑和 core 无回归证据。suite hash 漂移重启闭环。
- 需求：15.1—15.29。
- 后续验证：并发协调、超时后查重、409 异内容、旧 JSONL revision 0 首次升级、八行格式、Inbox 成功/关联确认失败及其反向故障、revision 已写但 manifest CAS 前崩溃、iteration manifest 最终 CAS 重放、关闭读回、最新 revision 链接不对称、冻结对象 hash 不变。

### 决策 10：多模型比较是独立硬准入，不是缺证据时的降级路径

- 背景：requested model 不等于实际 provider/model，fallback 或 replay 缺失会污染比较。
- 选择：`ModelComparisonAdmission` 冻结代码、suite、fixture、case 集、预算、能力目录、授权、解码与环境；逐模型 probe 并记录实际身份、fallback、replay、usage/cost/error。任一缺失或污染即 `incomparable`，排除排名。
- 边界：首批只建议 DeepSeek、GPT、Claude 三个代表系列各一项；实际集合必须由运行前 probe 决定，不在设计中声称模型当前可用。
- 需求：15.30—15.40。
- 后续验证：身份漂移、fallback、环境差异、缺 usage/replay、suite hash 漂移。

## 9. 风险与缓解

| 风险 | 严重性 | 触发条件 | 缓解 | 验证 |
|---|---|---|---|---|
| 活动小说事实被访问或修改 | 高 | case 误用活动 root/database/repository | factory 只注入临时 root 与前缀保护数据库；suite 控制面做活动事实前后指纹 | 故意越权 fixture、前后 hash、Mongo/路径守卫 |
| 并行 workspace 互相污染 | 高 | 共用目录、数据库、实例内锁 | 每 case 唯一 root/database/client/runtime；访问台账；suite quiescence 总核验 | 并发 case 写不同工件并检查无交叉 |
| Runtime evidence 跨仓储冲突 | 高 | run/call/snapshot/checkpoint/effect identity 断裂 | correlation record 保存精确 source locator；各源原生算法复读、availability/conflict、无 mtime fallback、bundle hash | 缺失/重复/源内冲突故障注入 |
| usage 重复或错误汇总 | 高 | replay、trace、usage 使用不同既有 ID 或重复观察 | 遍历 available correlation records；live 按 token observation 的 usage locator/gateway call ID 精确读取，synthetic 使用冻结 inline token observation；不做多源相加 | 多/少 observation、跨 task、重复 locator、缺 usage、冲突数值 |
| observer 故障污染 Runtime | 高 | scope/report/repository 抛错 | 底层委托结果和写入先完成；观察异常仅记评测 invalid，CaseExecutor finally 固化 pending | observer/repository 每个阶段故障注入、返回/异常/写入次数等价 |
| scripted 与 case 漂移 | 高 | 独立 script 文件或按 fixture 名硬编码 | scripted steps 内嵌 case；统一规范化 hash；step 引用 expected artifact id | 单字段改动 hash 测试、缺引用预检 |
| verifier 任意执行 | 高 | command/class path/dynamic import 被 case 控制 | 封闭 ID + 静态 registry；配置判别联合；只读 DTO | Shell/路径/import payload 均在 preflight 拒绝 |
| 硬失败被聚合覆盖 | 高 | 总分、平均或 judge 参与 pass | 六 gate 交集真值；judge 旁路；无 overall score | 真值表穷举与 UI 显示 |
| 取消/崩溃后伪终态 | 高 | worker 死亡、迟到任务写回 | 租约、revision CAS、stale -> unfinished、终态保护、resume 新 attempt | kill/restart/cancel race |
| provider 未配置或不可用 | 中高 | 无凭据、配额、服务不可达 | `blocked/error/completed` provider state；不造 synthetic fallback | 未配置、配额、网络错误测试 |
| 存储增长 | 中 | 重复 suite、case、bundle、experiment | 最小 evidence、bundle 引用、页码分页、记录字节数、禁止复制 trace；本轮不引入 TTL、删除 API 或保留策略 | 大量工件分页性能；未来引入归档/删除策略时重新验证 |
| 旧资产误删共享职责 | 高 | 粗粒度删除 evaluations/derived 根 | 精确删除清单、路径前缀保护、共享回归、历史目录只读 | dry-run + 全仓扫描 + 相邻测试 |
| 前端迟到响应覆盖 | 中 | 轮询与详情切换并发 | monotonic generation token + AbortController + lastAppliedRevision | 纯 coordinator 的乱序响应测试与固定端口快速切换手验 |
| 分页组件违反设计规则 | 中 | 复用当前 `border-t` | 调用处传 `border-t-0`，不改共享默认值且不新建平行分页 | 组件测试与评测页视觉回归 |

## 10. 参考文献

- `AGENTS.md` — 当前不可变项目规则、数据宪法、通用 Agent 与前端边界
- `README.md` — 当前仓库地图和活动/历史资料入口
- `DESIGN.md` — 唯一前端视觉与交互规则
- `docs/rule.md` — 当前资料与历史快照规则
- `.sdd/specs/1.1/通用写作智能体评测体系重构/requirements.md` — 已校验需求
- `.sdd/specs/1.1/通用写作智能体评测体系重构/independent-validation-report-requirements.md` — 当前 PASS 报告
- `.sdd/specs/1.1/通用写作智能体评测体系重构/gap-analysis.md` — 存量差距、候选方案和风险
- `src/taichu/application/general_agent/` — 当前 Runtime 模型、编排、执行、恢复与服务边界
- `src/taichu/application/invocations/`、`src/taichu/application/models/llm_*` — 调用、Token/费用和回放证据
- `src/taichu/application/contracts/llm.py`、`src/taichu/application/general_agent/orchestrator.py`、`src/taichu/application/subagents/runner.py`、`src/taichu/infrastructure/llm/rightcode.py` — LLM call/context identity 生成与透传现状
- `src/taichu/application/contracts/external_research.py`、`src/taichu/application/external_research/`、`src/taichu/infrastructure/external_research/duckduckgo.py` — external research port、真实 service/tool 依赖与生产联网 backend
- `src/taichu/infrastructure/general_agent_runs/` — run、checkpoint、effect、context snapshot 存储
- `src/taichu/infrastructure/knowledge/mongo_repository.py` — Mongo validator/index 与可注入数据库
- `tests/unit/application/general_agent/test_runtime.py`、`tests/integration/infrastructure/knowledge/test_mongo_repository.py` — 独立 Runtime 与临时 Mongo 的实证
- `web/src/app/task-monitor/general-agent/evaluation/page.tsx` 及旧 Shell/API/types/view/tests — 当前入口和待替换合同
- `pico-v3/pico/evaluation/evaluator.py`、`harnessbench.py`、`metrics.py` — 仅参考固定 benchmark、隔离、基线、判定、工件与实验机制；不复制 Shell、coding task、mtime、单失败覆盖或混轨缺陷
