# 通用写作智能体评测体系重构——实现差距分析

## 1. 文档信息

- 规格：`1.1/通用写作智能体评测体系重构`
- 分析日期：2026-07-27
- 输入需求：`requirements.md`
- 需求对象 SHA-256：`B5B65CF351B58C6FF72BFC6F76F1D9C3B10470EBC01875670571957FE14A1CF2`
- 前置门禁：独立需求校验 PASS，报告、`spec.json.validations.requirements.target_sha256` 与本次读取结果一致；现有虚拟环境直接执行 `state.py validate` 返回 `ok=true` 且无错误或警告。
- 分析方法：基于当前源码、测试、配置、活动数据目录说明和已校验需求进行源码降级调查；只陈述现有事实、实现选项、依赖和风险，不作最终设计决定。

## 2. 分析摘要

- 旧评测是绑定既有运行的五维加权单记录评分器，须破坏式替换；旧兼容不可保留。
- 生产目录已有 17 Tool + 12 Subagent，但只有 29 Profile 对齐测试，缺合格案例全覆盖、目录快照与漂移预检。
- 私有 `_ScriptedGateway` 可驱动 Runtime，却缺严格顺序、内容匹配、意外/耗尽/剩余步骤和规范化一致性门禁。
- Runtime 审计、工作记忆四态、Inbox 八字段校验及 provider probe/fallback/replay 可复用；`SUPERSEDED` 投影、节点复用、缺陷闭环与多模型准入仍有关键差距。
- 路由、导航、应用壳和本地 UI 可保留；页面必须结论优先。总体复杂度高，工作记忆防复活、Inbox 闭环和多模型可比准入局部极高。

## 3. 调查范围与证据

### 3.1 已调查资产

| 层/主题 | 当前资产 | 证据 | 结论 |
|---|---|---|---|
| 旧应用模型 | 评测模式、期望、案例、数据集、检查项、五维维度、状态和单条评测记录 | `src/taichu/application/evaluations/general_agent/models.py:20`、`:30`、`:60`、`:95`、`:113`、`:121`、`:136`、`:141` | 结构围绕单案例、既有运行和五维结果；不能直接表达 suite/case workspace/track/gate/evidence bundle/experiment |
| 旧应用服务 | 列数据集、按既有运行进行 post-hoc 评测、列出/读取/删除结果 | `src/taichu/application/evaluations/general_agent/service.py:53`、`:69`、`:81`、`:105`、`:118`、`:127`、`:131`、`:417` | 不是执行套件的 runner；判定核心是五维评分计算 |
| 旧应用契约 | 数据集仓储与结果仓储 Protocol | `src/taichu/application/contracts/general_agent_evaluation.py:11`、`:20` | 可借鉴 Protocol 分层方式，但旧接口与新生命周期不兼容，需删除而非扩展 |
| 旧基础设施 | 从测试 fixture 读取数据集；以 `general_eval_*.json` 保存、查询和删除结果 | `src/taichu/infrastructure/evaluations/general_agent_repository.py:21`、`:59`、`:62`、`:91`、`:109`、`:122`、`:130` | JSON 结果仓储只适合旧单记录；缺 suite/case/bundle/experiment、幂等提交和中断恢复 |
| 旧 API | 数据集查询、创建 post-hoc 评测、列表、详情和删除 | `src/taichu/api/routes/general_agent_evaluations.py:20`、`:23`、`:55`、`:71`、`:96`、`:115`；`src/taichu/api/schemas/general_agent_evaluations.py:11`、`:17`、`:25`、`:29`、`:36` | 无套件提交、运行进度、取消、恢复、案例下钻、证据包、实验或 provider 状态 API |
| 旧装配 | 启动时构造旧服务并挂入 app state、依赖和总路由 | `src/taichu/main.py:27`、`:453`、`:527`；`src/taichu/api/deps.py:8`、`:64`；`src/taichu/api/router.py:14`、`:35` | 新实现必须替换这些装配点并清除旧导入/导出 |
| 旧 fixture/测试 | 8 题清单及旧接口集成测试 | `tests/fixtures/evaluations/general_writing_assistant_core/manifest.json:1`；`tests/integration/api/test_general_agent_evaluations_api.py:1` | 可重新审视题意覆盖，但旧权重、关键词、满分路径和 API 断言不能迁移为兼容合同 |
| 生产 Tool 目录 | `discover_tools("taichu.application.tools")` 扫描生产包、校验 manifest/run/reconcile 并在组合根注册；测试锁定 17 个真实 Tool 名称 | `src/taichu/infrastructure/plugin_discovery.py:67`—`:114`；`src/taichu/main.py:406`—`:423`；`tests/unit/infrastructure/test_plugin_discovery.py:34`—`:68` | 可复用为能力目录唯一事实入口；不得在 suite 内维护第二份手写“生产 Tool 清单” |
| 生产 Subagent 目录 | `discover_subagents("taichu.application.subagents")` 扫描独立 Handler 包、校验 manifest/run；测试锁定 12 个专业子 Agent 及 12 个 model role | `src/taichu/infrastructure/plugin_discovery.py:117`—`:154`；`src/taichu/main.py:418`—`:423`；`tests/unit/infrastructure/test_plugin_discovery.py:70`—`:92` | 与 17 个 Tool 合计 29 个生产能力；suite 预检必须对运行时发现结果做内容寻址快照和反向覆盖核验 |
| 29 能力独立 Profile | 现有静态 Profile 表与生产发现集合严格相等 | `src/taichu/application/evaluations/capability_profiles.py:32`—`:53`；`tests/unit/application/evaluations/test_capability_profiles.py:13`—`:25` | 只证明“每能力一份指标口径”，不证明“每能力至少一个合格案例”；缺 suite case、硬门禁、快照哈希和目录漂移预检 |
| 私有 scripted Runtime 替身 | `_ScriptedGateway` 按任务名选择计划/验证/子 Agent 输出队列、`pop(0)` 消费并记录请求；测试 runtime factory 可注入真实编排器与仓储 | `tests/unit/application/general_agent/test_runtime.py:111`—`:167`、`:1141`—`:1182` | 可提炼注入缝和请求捕获模式；当前没有全局严格顺序、内容 matcher、明确意外/乱序/耗尽/剩余检查或规范化重复结果合同 |
| Runtime 运行证据 | run 仓储、图检查点、副作用、上下文快照已在启动中独立装配 | `src/taichu/main.py:254`、`:257`、`:260`、`:263`、`:440`、`:447`、`:448`、`:449`、`:518`、`:521` | 可复用为只读事实源，不能让评测改变其字段、生命周期或写入流程 |
| Runtime 调用证据 | 运行/节点模型、调用模型、Token/费用、模型回放和执行器 | `src/taichu/application/general_agent/models.py:1`；`src/taichu/application/invocations/models.py:1`；`src/taichu/application/models/llm_usage.py:1`；`src/taichu/application/models/llm_replay.py:1`；`src/taichu/application/general_agent/executor.py:1` | 已具备关联链所需事实，缺统一的只读 reader 与规范化 bundle |
| 工作记忆四态与投影 | 模型已有四态和修复来源关系；上下文会排除非 `ACTIVE` 生产者的节点摘要，并单列失效记忆 | `src/taichu/application/agent_memory/models.py:37`—`:52`；`src/taichu/application/general_agent/context.py:227`—`:268`；`tests/unit/application/general_agent/test_memory_context.py:181`—`:224`、`:230`—`:343` | 可复用状态机、依赖传播与审计证据；仍缺本规格要求的所有投影入口逐项硬门禁 |
| `SUPERSEDED` 与节点复用缺口 | `list_invalidated()` 默认只返回 `REJECTED/STALE`；计划校验与执行复用只检查旧节点 `SUCCESS`、节点 ID 和能力契约 | `src/taichu/application/services/agent_memory_service.py:264`—`:296`；`src/taichu/application/general_agent/orchestrator.py:273`—`:293`；`src/taichu/application/general_agent/executor.py:195`—`:224` | `SUPERSEDED` 不能进入隔离修复投影，且旧成功节点可能不经记忆有效性门禁被复用；这是生产修复和专项评测共同要覆盖的真实风险 |
| 共享调用读取入口 | API 依赖中已有调用轨迹 reader 提供点 | `src/taichu/api/deps.py:80` | 可作为读取边界先例；不能把面向页面的读取器直接当评测领域契约 |
| 系统问题唯一入口 | `/api/inbox/issues` 支持分页列表、创建和 PATCH；服务规范化并严格校验八字段顺序、全角冒号、非空值和日期格式；JSONL 写入有进程内文件锁与原子替换 | `src/taichu/api/routes/inbox.py:203`—`:251`；`src/taichu/application/services/mvp_inbox_service.py:33`—`:50`、`:146`—`:164`、`:215`—`:231`、`:377`—`:412`；`src/taichu/infrastructure/storage/markdown_backend.py:266`—`:309` | 可复用唯一持久化入口和格式校验；缺稳定 ID 唯一性、创建前按 ID 查询、写入不确定性复查、单协调器租约、结构化双向关联和写后读回闭环 |
| DeepSeek/provider 审计 | DeepSeek V4 Pro 已在模型目录；gateway 支持 model probe、RightCode→DeepSeek 官方 fallback，并在用量和 replay 中保存实际 provider、upstream model、fallback 来源、Token、费用和错误 | `src/taichu/infrastructure/llm/catalog.py:23`—`:137`；`src/taichu/infrastructure/llm/rightcode.py:126`—`:235`、`:588`—`:603`、`:655`—`:737`、`:1308`—`:1443`；`src/taichu/application/models/llm_replay.py:36`—`:73`；`tests/unit/infrastructure/llm/test_rightcode_gateway.py:362`—`:430` | 可复用实际执行身份和审计证据；缺 DeepSeek 首轮迭代/冻结/分类/修复复跑状态机，以及固定预算、环境和必需证据驱动的多模型可比准入与排名排除 |
| 共享评测配置 | 评测目录及裁判配置为多个评测域共享 | `src/taichu/config.py:39`、`:40`、`:41` | 配置根可保留；不得因清理旧通用 Agent 评测而破坏知识抽取/召回评测 |
| 恢复基准 | 独立运行恢复 benchmark | `scripts/benchmark_general_agent_recovery.py:1` | 属于相邻独立证据，明确保留，不并入本套件通过率 |
| 活动数据说明 | 旧通用 Agent 结果与 Runtime 派生数据各有目录职责 | `project_assets/readme.md:81`、`:144` | 新增/删除/改变目录职责时必须同步更新；评测工件仍是派生审计资料 |
| 前端入口 | 评测 route 为薄入口，内部交给旧 Shell | `web/src/app/task-monitor/general-agent/evaluation/page.tsx:1`；`web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx:1` | route 可保留，Shell 必须重写 |
| 前端导航与壳 | 通用 Agent 监控导航和应用壳 | `web/src/components/agent-task-monitor/general-agent-monitor-nav.tsx:1`；`web/src/components/app-shell.tsx:1` | 可直接复用 |
| 前端旧合同 | 旧 API、类型、显示适配和测试 | `web/src/lib/api/general-agent-evaluation.ts:1`；`web/src/lib/types/general-agent-evaluation.ts:1`；`web/src/lib/general-agent-evaluation-view.ts:1`；`web/tests/general-agent/evaluation-view.test.ts:1` | 与旧五维状态/字段绑定，按需求破坏式重写；现有视图没有整体能力、工作记忆专项、局部机制、DeepSeek 闭环和多模型准入的结论优先级 |
| 前端基础组件 | 按钮、紧凑分页、复选框和既有图标依赖 | `web/src/components/ui/button.tsx:1`；`web/src/components/ui/compact-pagination.tsx:1`；`web/src/components/ui/checkbox.tsx:1`；`web/package.json:1` | 足以构成桌面高密度工作台，无需新增前端依赖 |
| 历史与当前资料 | 历史评测报告须保留；README、当前 docs 和数据说明须改为新口径 | `docs/历史/7-14通用写作助手效果评测实现报告.md:1`；`README.md:1`；`project_assets/readme.md:81` | 历史快照不改；活动资料必须与新代码同步 |

### 3.2 Graphify 降级说明

- 根项目规则当前明确禁用 Graphify，本次未执行任何 `graphify` 命令，也未使用 `graphify-out/` 生成物。
- 事实证据来自当前源码、测试、配置和已校验规格，降级路径为 `rg` 与直接文件阅读。

## 4. 现有架构与不可变约束

1. **领域与应用边界**：新评测合同若形成领域模型，不得依赖 LangGraph、LLM、MongoDB 或文件存储；运行证据读取、夹具复制和 provider 调用分别属于应用协议与基础设施实现。现有仓储以 Protocol 隔离实现是可复用的分层模式（`src/taichu/application/contracts/general_agent_evaluation.py:11`）。
2. **运行事实只读**：评测只能消费既有 Runtime 记录。关联主链为 `conversation_id → run_id/thread_id → node_id/plan_revision → attempt_id/effect_id`，并以 `call_id/parent_call_id/context_snapshot_id` 补充；不得通过 mtime、最近目录项或复制巨型 trace 建立平行事实源（`requirements.md:369`）。
3. **小说事实安全**：密封夹具必须由 Markdown 正文、隔离的 `lifecycle=confirmed` Mongo 知识、初始对话和初始运行记忆共同构成；评测工件仅是派生审计资料，不能写回活动正文或确认知识（`requirements.md:207`）。
4. **能力目录与运行实例解耦**：suite 只能引用真实注册能力；case 合同描述本次 required/allowed/forbidden 集合，不能临时补造任务专用 Tool、Agent 或固定 DAG。
5. **生产目录是覆盖真相**：当前生产目录由插件发现得到 17 Tool 和 12 Subagent；29 个 Profile 是可复用的口径资料，不是固定套件的平行能力清单。套件快照、覆盖表和预检都必须从当次生产发现结果派生。
6. **工作记忆当前事实不变量**：只有 `ACTIVE` 可进入当前事实；`STALE/REJECTED/SUPERSEDED` 只能处于明确隔离的修复区并继续可审计。节点 `SUCCESS` 不能替代记忆有效性门禁，`reuse_from_node_id` 必须与生产者记忆状态共同判定。
7. **Inbox 单一入口与闭环所有权**：真实系统缺陷只能经 `/api/inbox/issues` 写入；格式校验通过不等于缺陷已闭环，必须同时满足稳定 ID 去重、单协调器、持久化读回、双向关联和关闭前完整复跑。
8. **模型声明必须服从实际执行证据**：请求 model ID 不是实际 provider/model 的充分证明。probe、fallback、replay、用量、费用、错误和运行环境均为多模型可比性必需证据；任一不满足只能标不可比，不能算能力失败或进入排名。
9. **替换而非兼容**：旧后端目录、契约、API、前端合同、fixture、测试和活动结果均在删除范围；不允许兼容读取器、字段映射器或旧结果回退（`requirements.md:656`—`:702`）。
10. **相邻评测隔离**：知识抽取、知识召回、共享评测配置和恢复可靠性 benchmark 必须继续独立工作（`src/taichu/config.py:39`；`scripts/benchmark_general_agent_recovery.py:1`）。
11. **前端结论优先**：只交付中文桌面网页，保留既有 route/card/nav/AppShell，复用现有 UI 组件，不新增前端依赖；首屏先展示整体能力与专项硬门禁，分数、均值、费用和排名退居解释层；真实验收固定使用 `localhost:3000` 与 `127.0.0.1:8000`。

## 5. 需求 → 现有资产 → 差距 → 可行选项 → 风险矩阵

状态含义：`需新增` 表示无可表达该职责的现有资产；`需替换` 表示现有资产存在但合同不兼容；`需扩展` 表示可在不破坏原职责的前提下增加窄接口；`可复用` 表示可直接保持现状并作为依赖。

| 需求 | 现有资产与证据 | 差距/状态 | 可行选项 | 风险 |
|---|---|---|---|---|
| 1 固定基准与 29 项生产能力全覆盖 | 生产发现真实得到 17 Tool + 12 Subagent；29 个静态 Profile 与发现集合一一相等，但旧 `GeneralAgentEvaluationDataset/Case` 仍只描述单案例输入（`plugin_discovery.py:67`—`:154`；`test_plugin_discovery.py:34`—`:92`；`test_capability_profiles.py:13`—`:25`） | **需替换/新增预检**：无 suite contract、生产目录内容寻址快照、逐能力“合格案例”反向覆盖、required/allowed/forbidden、目录漂移拒绝、覆盖错误一次列全和预检工件；Profile 不能冒充 case coverage | A：扩展现有发现/Profile 读取面，新增 suite 预检与快照；B：新边界经只读能力目录端口取得 29 项能力；C：新 suite 核心 + 生产发现适配器。三者都必须注入漏案例、未知/重复映射和目录身份漂移并在执行前失败 | 高：手写 29 项平行清单会漂移；只检查“存在 Profile”会形成假全覆盖；预检失败后不得产生整体能力结论 |
| 2 基准身份与复现元数据 | 旧 JSON 记录有单条 ID，但仓储文件名即记录身份（`general_agent_repository.py:91`、`:130`） | **需新增**：缺内容寻址的 suite/fixture 身份、Git/工作树、provider/model/解码、locale/timezone/track 及不可用状态 | B：规范化合同后计算内容哈希并固化运行快照；C：由独立 metadata collector 组合代码、suite、fixture、provider 和环境事实 | 中高：序列化不稳定会制造伪漂移；敏感 Prompt/正文不得为“可复现”被完整复制 |
| 3 密封夹具与案例隔离 | 旧 fixture 是测试清单，不是 Markdown + confirmed Mongo + 对话/记忆的小说快照（`tests/fixtures/evaluations/general_writing_assistant_core/manifest.json:1`） | **需新增**：缺 sealed fixture 合同、逐 case 干净 workspace、活动工作区阻断、前后不变量检查和清理生命周期 | B：建立专用 sealed fixture builder/copier；C：以应用级 fixture Protocol 协调 Markdown、隔离 Mongo 数据集和运行状态适配器 | 极高：Mongo 快照隔离与活动库边界若模糊会污染作者事实；并行 case 的目录/集合命名和回收必须可证明隔离 |
| 4 严格 scripted 确定性基线 | 私有 `_ScriptedGateway` 可按 `task_name` 分流、队列 `pop(0)` 和捕获请求；测试 runtime factory 证明注入边界有效（`test_runtime.py:111`—`:167`、`:1141`—`:1182`） | **需抽取/新增**：当前不是共享套件组件；没有统一 step schema、全局逐步顺序、请求类型与内容 matcher、未声明交互分类、显式乱序位置、脚本耗尽位置、Runtime 停止后的剩余步骤检查、脚本/Runtime 配置身份及规范化重复结果一致性 | A：把私有 fake 提炼为共享严格 driver；B：新建 suite-owned scripted engine；C：共享严格 driver + 新 runner/typed verifier。所有方案均须对意外、乱序、内容不匹配、提前耗尽、剩余步骤和重复漂移分别失败并保存消费轨迹 | 高：现有字典查找/`IndexError` 只能偶然失败，不能提供稳定类别和位置；按任务类型分别排队还允许跨类型乱序；“运行结束”若不触发 finalize 会漏报剩余步骤 |
| 5 六预算与六类硬门禁交集 | 旧五维 `GeneralAgentEvaluationDimension` 和总分路径（`models.py:121`；`service.py:417`）；Runtime 审计已有节点、调用、Token/费用与停止证据 | **需替换/新增**：缺节点、重规划、能力调用、模型调用、Token、时长六预算；缺预算/校验器/产物/停止/权限/证据六类门禁合取与 case/suite/机制三层结论；总分仍可掩盖硬失败 | A：扩展现有证据统计并替换评分服务为 gate evaluator；B：新建独立 gate engine；C：证据 reader 提供规范化实际值，新核心计算逐门禁真值。三者均须保存上限、实际值、适用性与失败来源 | 高：证据缺失、基础设施错误、不可比与 Agent 行为失败必须分开；任一平均、权重或“漂亮指标”覆盖硬失败都会重现旧口径 |
| 6 双失败类别与归因 | 旧记录保存检查和维度，不支持并发失败的稳定主类别与全集（`models.py:113`、`:121`、`:141`） | **需新增**：缺 `failure_category`、`failure_categories`、全序优先级、双口径聚合、无法确定归因 | B：套件声明封闭类别与优先级；C：各 gate/verifier 产生类型化失败事实，再由独立分类器确定主类别并保留全集 | 中高：类别新增会影响内容身份与前端中文映射；只存主类别会丢失根因证据 |
| 7 只读证据包与聚合工件 | Runtime 已有 runs、invocations、snapshots、replays、checkpoints、effects、usage（`main.py:254`—`:263`、`:440`—`:450`） | **需扩展/新增**：缺只读 evidence reader、稳定关联校验、证据可用性、规范化 case bundle、`bundle_hash` 和 suite artifact repository | B：新评测基础设施直接实现多仓储只读聚合；C：先增加窄 `EvidenceReader` Protocol/adapter，再由新评测 bundle builder 使用 | 高：跨文件/仓储读取可能获得不一致切面；不能修改 Runtime，也不能复制完整 Prompt、上下文或调用正文 |
| 8 分轨、机制硬门禁与合格实验 | 旧服务每次只对一个历史 run 形成一条结果；gateway 已能产出 provider/费用/错误事实，但没有 experiment 语义（`service.py:81`、`:373`；`rightcode.py:655`—`:737`） | **需新增**：synthetic/live 严格分轨、机制是否有真实开关的资格检查、控制/实验唯一差异、不变量/收益阈值/核心无回归、重复运行、分机制指标和 blocked/error/completed 状态均不存在 | A：在共享 evaluations 框架扩展 track/experiment；B：新建 track-aware runner 与 experiment coordinator；C：新 runner/仓储 + 可注册机制聚合器。无真实开关时三者都只能展示专项硬门禁，不得构造虚假对照 | 高：混轨、条件漂移或把单次波动当收益会制造虚假机制结论；恢复专项不得吞并独立 recovery benchmark；不可比运行不得进入分子 |
| 9 生命周期、取消与恢复 | 旧 API 为同步创建后读取/删除；无等待、运行、取消、未完成或幂等提交（`routes/general_agent_evaluations.py:55`、`:71`、`:96`、`:115`） | **需替换**：缺持久化进度、运行级终止条件、取消、服务中断后的 unfinished、恢复动作、重复提交保护和终态不反写 | B：独立 suite-run 状态机与持久仓储；C：应用服务拥有状态机，执行器仅消费 case lease/命令并写原子进度 | 高：进程中断和取消存在竞态；终态不可被后台任务反向改写；幂等键需绑定完整提交身份 |
| 10 桌面评测工作台与最终结论优先级 | route/nav/AppShell/Button/CompactPagination/Checkbox/lucide 可复用；旧 Shell/API/types/view/tests 与“案例—既有运行—五维分数”绑定 | **需替换并保留入口**：缺 suite 总览、轨道/provider 操作、进度取消、紧凑 case 行、证据下钻和实验；更关键的是缺“整体能力 → 工作记忆专项 → 局部机制 → DeepSeek 闭环 → 合格后多模型比较”的结论层级 | A：在旧 route 下扩展现有 Shell 但彻底更换内部合同；B：新建页面 feature 边界；C：保留轻 shell，把结论总览、suite/run、case detail、闭环和比较拆为职责单一组件/hooks。均复用本地 primitives、无新增依赖 | 高：总分、费用或排名若视觉上更突出会违反结论语义；多模型未准入时必须显示缺失条件而不是空排名；高密度信息必须渐进展开且枚举统一映射中文 |
| 11 相邻系统与数据边界 | Runtime、恢复 benchmark、知识评测和共享配置均现存（`main.py:240`、`:347`—`:364`；`config.py:39`—`:41`；`benchmark_general_agent_recovery.py:1`） | **需扩展但不得改写相邻资产**：缺评测专用只读访问契约、审计不足与行为失败分离、费用不可用保留 | B：评测侧 adapter 读取现有仓储；C：在 application contract 增加最小 evidence reader，由既有基础设施组合实现 | 高：错误复用共享删除/写入接口可能破坏审计；恢复实验指标不得与独立恢复 benchmark 合并 |
| 12 破坏式替换与清理 | 旧后端、装配、fixture、API 测试、JSON 结果、前端合同及当前资料均可定位（`main.py:27`、`:453`、`:527`；`router.py:14`、`:35`；`project_assets/readme.md:81`） | **需删除/替换**：旧路径、字段、状态、结果模式和现行说明必须从活跃实现消失；历史/共享资产必须保留 | B/C 均需使用同一清理清单、全仓旧标识扫描、相邻回归和固定端口验收；不存在兼容迁移选项 | 高：删除范围大且与共享 `evaluations` 配置相邻；活动旧 JSON 删除是物理清理，需先精确解析目标目录和文件模式 |
| 13 类型化预期产物与安全校验 | 旧 expected/check 不是五类产物的注册式 verifier 契约（`models.py:30`、`:113`；`service.py:399`） | **需新增**：缺 final answer/source reference/capability artifact/write candidate/HITL 类型、required/forbidden/N/A、verifier registry 与禁止 Shell 边界 | B：封闭 discriminated union + 注册表；C：核心类型归合同层，具体 verifier 按稳定 ID 注册到应用层，只接受规范化只读输入 | 高：任意命令、动态 import 或案例文本驱动执行都会突破安全边界；verifier 不得改变 run、fixture 或小说事实 |
| 14 工作记忆四态、修复与防复活 | 四态、三类依赖、来源刷新、部分传播测试和非 `ACTIVE` 生产者节点摘要过滤已存在；`list_invalidated()` 默认漏 `SUPERSEDED`，复用只按节点 `SUCCESS`（`models.py:37`—`:52`；`agent_memory_service.py:264`—`:296`；`context.py:227`—`:268`；`orchestrator.py:273`—`:293`；`executor.py:195`—`:224`） | **需扩展生产修复并新增专项**：`SUPERSEDED` 无法稳定进入“仅供修复”区；`reuse_from_node_id` 未核验来源记忆 `ACTIVE`；缺来源指纹、BASIS/REVIEW_TARGET 传播、否决目标、REPAIR_SOURCE 不传染、新旧替代、并行隔离、节点摘要/digest/snapshot/reuse 全投影的独立硬门禁 | A：扩展 AgentMemoryService/复用校验并在现有 memory 测试上建立专项；B：新建评测侧记忆场景驱动器并要求生产端提供有效性查询；C：生产端最小修复 + suite-owned 专项与证据 reader | 极高：只修上下文列表而不修复用链仍会复活旧事实；把 `SUPERSEDED` 混入当前事实或完全丢弃都会破坏“可修复且不可当真”；并行候选传播必须按依赖图隔离 |
| 15 DeepSeek 首轮、Inbox 缺陷闭环与多模型准入 | DeepSeek V4 Pro、probe、fallback、replay、Token/费用/错误已存在；Inbox 有 list/create/PATCH、八字段校验和 JSONL 原子写（`catalog.py:23`—`:137`；`rightcode.py:126`—`:235`、`:588`—`:737`、`:1308`—`:1443`；`inbox.py:203`—`:251`；`mvp_inbox_service.py:146`—`:231`、`:377`—`:412`） | **需新增协调与状态机**：无“合成全绿→单独 DeepSeek 全套→首轮冻结→四类失败分类→定向修复+全套复跑→闭环准入”；Inbox 无稳定 ID 唯一/查询、单协调器、确定失败/格式拒绝/未持久化阻断、套件/运行/迭代/证据双向关联和写后读回；多模型无固定代码/suite/fixture/case/预算/授权/解码/环境比较合同及不可比排除 | A：扩展现有评测服务并增加闭环 coordinator；B：新建 iteration/issue-link/comparison 边界；C：新评测核心编排，窄适配现有 Inbox 与 gateway 审计。三者都必须把写入失败、格式拒绝、读回失败、关联断裂、probe 失败、fallback 污染、实际身份不符和 replay 缺失设为硬阻断 | 极高：Inbox patch 为读后整文件重写且没有跨流程 lease，竞争可丢更新；用户指定 ID 目前无唯一性门禁；请求模型名不能证明实际执行身份；闭环不全就比较会把系统/基准/供应商/环境问题混入排名 |

## 6. 可行实现方案及权衡

### 方案 A：扩展现有共享评测与运行组件

- **边界**：删除精确列出的旧五维 `general_agent` 业务对象，但继续以现有 `application/evaluations`、插件发现、Runtime 测试注入缝、LLM gateway/replay 和 Inbox service 为主要承载点；在这些组件中增加 suite、严格 scripted、gate、iteration、issue link 和 comparison 能力。
- **集成点**：`discover_tools/discover_subagents`、现有评测配置根、Runtime 组合根、`RightCodeLLMGateway`、`MVPInboxService`、现有 route/nav/AppShell。
- **数据所有权**：由现有 evaluations 区域拥有新 suite/run/artifact；Runtime、Inbox 和 gateway 继续拥有各自原始事实。
- **清理与迁移**：仍须删除旧五维目录、合同、API、结果和前端合同，不迁移旧记录；同路径开发不能保留兼容字段。
- **测试优势**：可以最大化复用已证明的插件发现、Runtime 注入、八字段校验和模型审计。
- **主要风险**：职责扩张最明显；把评测闭环租约塞进 Inbox、把 suite 身份塞进 Runtime 或把可比性塞进 gateway 都会破坏现有边界。现有 `_ScriptedGateway` 是测试私有类，直接搬入生产 evaluations 还会混淆测试基础设施与业务运行。
- **可行性结论**：真实可行，但前提是扩展只增加窄 Protocol/查询/协调接口，不能修改相邻系统的数据所有权，也不能继续使用旧五维根模型。

### 方案 B：创建完整独立的新评测边界

- **边界与职责**：新建 suite/case/fixture/script/artifact/gate/failure/iteration/issue-link/comparison 合同，独立 suite runner、strict scripted driver、fixture manager、typed verifier registry、gate evaluator、failure classifier、evidence bundle builder、closure coordinator、artifact repository 和 aggregator；旧边界在切换时整体删除。
- **入站接口**：新 API 提交 suite/experiment、查询运行/案例/证据/DeepSeek 迭代/问题闭环/多模型比较、取消和恢复。
- **出站接口**：通过只读或窄命令 Protocol 使用生产能力目录、通用 Agent Runtime、Runtime 证据仓储、密封 fixture、Inbox API 和 provider gateway。
- **数据所有权**：新边界拥有 suite 定义、case workspace 生命周期、评测运行状态、严格脚本消费轨迹、case bundle、DeepSeek iteration、issue link、comparison 和最终结论；不拥有 Runtime 原始审计、Inbox 记录或小说事实。
- **清理与迁移**：无旧合同迁移；切换时删除旧 API/结果/前端，保留历史与共享资产。首轮和后续迭代工件内容寻址、不可覆盖。
- **测试优势**：29 能力预检、strict scripted、工作记忆专项、Inbox 故障注入和多模型准入可在边界内独立构造。
- **主要风险**：新抽象最多；若自行复制能力清单、Runtime trace、模型身份或 Inbox 记录，会形成第二事实源。所有 adapter 必须最小化且可验证只读/幂等语义。
- **可行性结论**：真实可行，隔离最强，但设计必须控制抽象数量和避免平行审计链。

### 方案 C：新评测核心 + 现有共享能力窄适配

- **新增部分**：suite/case/fixture/strict-script/verifier/gate/failure/artifact/iteration/comparison 核心与运行服务；旧五维业务全部删除。
- **扩展/复用部分**：
  - 生产发现适配器每次读取 17 Tool + 12 Subagent 并形成内容快照；
  - Runtime/evidence adapter 只读组合 run/invocation/snapshot/replay/checkpoint/effect/usage；
  - AgentMemory adapter 暴露状态变化与生产者有效性，不让评测操纵单条记忆；
  - Inbox coordinator 只经 `/api/inbox/issues` 做稳定 ID 查询、写入、PATCH 和读回；
  - provider adapter 读取请求/实际 provider-model、probe、fallback、replay、Token、费用和错误；
  - 前端保留 route/card/nav/AppShell 和本地 UI primitives。
- **集成顺序约束**：
  1. 固定新合同、29 能力快照、suite/fixture/script/runtime-config 身份；
  2. 建立 strict scripted driver、isolated case runner、typed verifier、六预算/六门禁与工作记忆专项；
  3. 建立只读 evidence bundle、DeepSeek iteration、Inbox 单协调器/双向关联/读回门禁；
  4. 建立多模型固定条件与不可比排除，再接 API/UI 的结论优先视图；
  5. 一次性清除旧实现、旧结果和现行说明并全仓扫描。
- **清理与迁移**：同方案 B；不提供旧结果转换、兼容读取或 fallback。Inbox 已有问题只按稳定 ID 复用，不能创建平行问题文档。
- **测试优势**：复用真实生产事实源，同时把评测规则、闭环和比较留在新核心；故障可在 adapter 边界机械注入。
- **主要风险**：adapter 若暴露完整底层对象会把 Runtime/Inbox/gateway 模型耦合进评测合同；单协调器和跨工件双向关联需要明确原子性/补偿语义。
- **可行性结论**：真实可行；本阶段不在 A/B/C 中作最终选择，设计角色需用职责、事务边界和故障测试进一步裁决。

### 不适用变体：继续扩展旧五维根模型

继续使用旧 `GeneralAgentEvaluationRecord`、五维字段、旧 API 或 `general_eval_*.json` 并加兼容字段，与需求 12.1—12.20 的精确删除和禁止兼容直接冲突，因此不是上述方案 A 的组成部分，也不进入设计候选。

## 7. 旧实现清理与保留矩阵

| 动作 | 精确范围 | 联动点/验证 |
|---|---|---|
| 删除旧后端业务 | `src/taichu/application/evaluations/general_agent/`、`src/taichu/application/contracts/general_agent_evaluation.py`、`src/taichu/infrastructure/evaluations/general_agent_repository.py`、`src/taichu/api/schemas/general_agent_evaluations.py`、`src/taichu/api/routes/general_agent_evaluations.py` | 清理包导出、旧 Protocol、旧 API prefix、旧状态/字段/五维分数引用 |
| 替换装配 | `src/taichu/main.py:27`、`:453`、`:527`；`src/taichu/api/deps.py:8`、`:64`；`src/taichu/api/router.py:14`、`:35` 及相关 `__init__.py` | 只装配新服务；真实调用 `127.0.0.1:8000` 证明热重载后的新接口可达 |
| 删除旧 fixture/测试 | `tests/fixtures/evaluations/general_writing_assistant_core/manifest.json`、`tests/integration/api/test_general_agent_evaluations_api.py` | 新 suite fixture 和 API 集成测试不得复用旧权重/字段/状态 |
| 清理活动旧结果 | `project_assets/derived/agent_evaluations/general_agent/general_eval_*.json` | 删除前解析绝对目标并限制在精确目录；新列表、搜索、统计不得返回旧结果 |
| 重写前端旧合同 | `general-agent-evaluation-shell.tsx`、API、types、view、`evaluation-view.test.ts` | 保留 route/card/nav/AppShell；旧五维字段和旧状态全仓扫描为零 |
| 更新当前资料 | 根 `README.md`、当前 `docs/`、`project_assets/readme.md` | 说明新入口、工件职责和判定口径；目录职责改变与代码同批更新 |
| 明确保留 | `docs/历史/`、`src/taichu/application/evaluations/capability_profiles.py` 及其 29 能力一致性测试、生产插件发现/注册、`src/taichu/config.py:39`—`:41`、Runtime/工作记忆/Inbox/LLM replay 派生证据、`scripts/benchmark_general_agent_recovery.py`、知识抽取/召回评测 | 这些是新体系可读取的相邻事实或共享资产，不属于旧五维合同；跑相邻回归，任何清理触及其职责即失败 |
| 防僵尸扫描 | 旧 API 路径、`GeneralAgentEvaluationDimension`、五维字段、旧状态、`general_eval_*.json`、旧前端类型和旧当前资料口径 | 活跃源码/测试/前端/当前资料必须为零；`docs/历史/` 命中应明确排除，不得为清零篡改历史 |

## 8. 前端差距与集成分析

### 8.1 页面与组件职责

```text
/task-monitor/general-agent/evaluation（保留）
└─ 评测工作台 Shell（重写）
   ├─ 最终结论总览（首要）
   │  ├─ 整体能力硬门禁
   │  ├─ 工作记忆细粒度失效专项
   │  ├─ 各局部机制结论
   │  ├─ DeepSeek V4 Pro 迭代与问题闭环
   │  └─ 多模型准入/不可比原因（准入前不显示排名）
   ├─ 固定套件选择、29 能力覆盖预检与内容身份摘要
   ├─ 运行控制：轨道、provider、提交、取消、恢复
   ├─ 紧凑案例行、筛选、复选与分页
   ├─ 案例详情：预期/实际/证据/失败类别/关联工件
   └─ 解释层：分数/均值/费用、实验可比性、机制指标与稳定性
```

- AppShell、监控导航、Button、CompactPagination、Checkbox 和 lucide 图标直接复用。
- 页面必须遵循“结论先于指标”：总分、通过率、费用和排名不能替代或在视觉上压过整体能力/专项硬门禁；多模型未准入时展示未满足条件，不渲染提前排名。
- 原始工件、内部标识和低频技术字段必须按需展开，不能把巨型 trace 填入主表。
- 状态、provider 状态、失败类别和内部枚举必须由单一显示适配层映射为中文。
- 页面属于高密度午夜极光控制台工作台；不增加前端依赖、移动布局、卡片套卡片、营销式说明或平行组件体系。

### 8.2 API 与状态所有权

| 前端动作 | 所需新 API 能力 | 状态所有者 | 关注点 |
|---|---|---|---|
| 浏览固定套件 | suite 列表/详情/覆盖/内容身份 | 服务端固定合同，前端只读筛选 | 禁止前端重新计算内容身份 |
| 提交普通运行 | 创建 suite run，返回唯一 ID/幂等冲突 | 服务端运行状态机 | 提交中禁用；重复请求导航或提示既有运行 |
| 查看进度/取消/恢复 | run 详情、进度、取消命令、恢复可用性 | 服务端持久化进度 | 取消不删除完成 case；中断显示未完成 |
| 案例下钻 | case result、gate、failure、bundle reference | 服务端工件仓储 | 按需加载；不可复制完整敏感正文 |
| 分机制实验 | 创建/查询 experiment 和重复汇总 | 服务端 experiment coordinator | 不可比时不显示增益；synthetic/live 不混算 |
| 查看 DeepSeek 闭环 | iteration、失败分类、issue link、定向/全套复跑和关闭门禁 | 服务端闭环协调器 | 首轮工件不可覆盖；Inbox 失败/读回/关联错误均显示未闭环 |
| 查看多模型比较 | comparison 可比条件、逐模型实际身份与证据、不可比原因 | 服务端 comparison gate | 准入前不生成排名；不可比与能力失败分开展示 |

### 8.3 前端验证关注点

- 类型级测试覆盖所有终态、provider 状态、双失败类别、工作记忆专项、闭环/准入状态和中文映射。
- 组件测试覆盖加载失败/重试、空状态、提交禁用、重复提交、取消反馈、分页筛选和详情渐进展开。
- 视觉/层级验收覆盖整体能力结论首要展示、工作记忆专项独立展示、局部机制结论、多模型未准入不显示排名，以及分数/费用退居解释层。
- 真实联调只使用 `http://localhost:3000/task-monitor/general-agent/evaluation` 与 `http://127.0.0.1:8000`。
- 不增加移动/窄屏逻辑，不增加新前端依赖，不建立第二套组件体系。

## 9. 复杂度与风险矩阵

| 工作流/风险 | 复杂度 | 严重性 | 依据/触发条件 | 缓解与验证关注点 |
|---|---|---|---|---|
| 29 项生产能力全覆盖预检 | 高 | 高 | 生产发现可变；现有测试只证明 29 Profile 对齐，不证明合格案例和硬门禁全覆盖 | 直接读取 17 Tool + 12 Subagent；内容寻址目录快照；逐能力反向映射；漏项/重复/未知/漂移执行前失败 |
| 新 suite/case/track/experiment 合同 | 高 | 高 | 根聚合和生命周期完全替换；合同同时约束能力、预算、产物、fixture 和 verifier | schema 预检一次列全错误；内容哈希重复测试；未知能力/校验器在执行前拒绝 |
| 密封 Mongo + Markdown + 对话/记忆 fixture | 极高 | 高 | 跨两类事实源及运行状态，且必须与作者活动工作区物理/逻辑隔离 | 使用专用库/集合或等价隔离策略；每 case 干净副本；前后哈希与活动事实不变量测试 |
| Runtime 只读 evidence bundle | 高 | 高 | 多仓储证据可能跨时刻不一致，关联链可能断裂或冲突 | 稳定 ID 校验、availability 枚举、内容哈希、禁止 mtime、reader 无写能力、故障注入 |
| strict scripted driver | 高 | 高 | 私有 fake 只有分流队列；意外、跨类型乱序、内容不匹配、隐式耗尽、剩余步骤和重复漂移均无稳定合同 | 单一有序 step stream；matcher 与稳定错误类别；finalize 断言全消费；消费轨迹与规范化结果哈希；六类负向注入 |
| typed verifier | 高 | 高 | verifier 若允许命令文本、动态 import 或副作用会形成执行漏洞 | 封闭注册表、类型匹配预检、只读输入、命令注入/副作用回归；明确禁止 Shell |
| 六预算和六类硬门禁交集 | 高 | 高 | 缺失证据、基础设施错误与行为失败容易混淆；平均分会掩盖失败 | 逐 gate 保存输入/实际/状态；真值表测试全部组合；任一硬失败永不被覆盖 |
| 工作记忆四态与 `reuse_from_node_id` | 极高 | 高 | `SUPERSEDED` 默认不在修复投影；成功节点复用未检查来源记忆是否 `ACTIVE` | 统一有效性查询；旧三态只进隔离区；复用前核验生产者；摘要/digest/snapshot/reuse 全投影专项；并行依赖隔离 |
| 运行状态、取消、中断与幂等 | 高 | 高 | 后台执行、取消和服务重启存在竞态，终态可能反写 | 原子状态转换、幂等键、终态保护、取消边界和重启故障测试 |
| DeepSeek 首轮冻结与完整复跑 | 高 | 高 | 首轮、修复轮和 suite 合同可能被覆盖或哈希变化；局部通过容易被误当闭环 | 每轮不可变 artifact；四类失败与未知分类；suite hash 变化强制从头；定向案例+当前 hash 全套+核心无回归共同关闭 |
| Inbox 持久化闭环 | 极高 | 高 | 现有 create 可接收重复 ID，缺单协调器与双向关联；PATCH 是读后整文件重写，跨流程并发可能丢更新 | 稳定 ID 唯一/查询；协调器 lease；超时先查后重试；确定失败/格式拒绝/未持久化/读回或关联失败一律阻断；关闭后再读回 |
| 多模型实际身份与可比准入 | 极高 | 高 | 请求 model ID 可能经 fallback 变成另一 provider/model；probe/replay/费用/错误/环境证据可能缺失 | 固定代码/suite/fixture/case/逐案预算/能力/授权/解码/环境；请求与实际身份核验；probe/fallback/replay 硬门禁；不可比排除排名且不算能力失败 |
| 聚合、重复性和机制实验 | 高 | 中高 | 样本少、条件漂移或混轨会产生虚假机制增益 | comparability gate；保存每次运行；样本数/方差/范围；绝对通过与相对变化分开 |
| 破坏式旧清理 | 高 | 高 | 后端、前端、测试、活动数据和资料均受影响；共享评测资产相邻 | 精确清理清单、全仓旧标识扫描、相邻评测回归、历史目录不改 |
| 桌面高密度工作台 | 高 | 中高 | 信息量大、状态多、证据层级深；漂亮指标/排名容易压过硬门禁 | 现有组件复用、结论优先、渐进展开、单一中文映射、未准入不显示排名、固定端口端到端测试 |
| 性能与存储膨胀 | 中 | 中 | 重复 run/case/bundle/experiment 可快速增长；复制 trace 会放大 | suite 仅引用 bundle ID/hash；正文最小引用；分页读取；设计阶段明确保留/清理策略 |

总体复杂度为**高**，局部工作记忆防复活、Inbox 闭环和多模型可比准入达到**极高**。原因是本变更横跨应用、基础设施、API、Runtime 只读集成、工作记忆生产语义、外部模型审计、数据派生目录和前端工作台；没有旧业务数据迁移需求，但存在活动旧结果物理清理、密封 fixture 数据隔离、跨文件协调和故障注入验证负担。

## 10. Pico 机制复刻边界

### 可复刻机制

- 固定 benchmark/suite 与内容身份；
- 隔离 fixture 副本；
- scripted synthetic baseline；
- 多条件通过判定；
- 逐 case 完整行与复现元数据；
- 运行工件聚合；
- 重复执行和分机制实验。

参考入口：`pico-v3/pico/evaluation/evaluator.py:1`、`pico-v3/pico/evaluation/harnessbench.py:1`、`pico-v3/pico/evaluation/metrics.py:1`。

### 不得复制的缺陷

- 不执行 Shell、案例合同命令或任意系统命令；
- 不按 fixture 名称硬编码预期产物路径；
- 不以最后一个失败覆盖其他并发失败；
- 不用 mtime 或最近文件关联工件；
- 不把 synthetic 与 live provider 结果混入同一结论；
- 不把代码任务/仓库操作假设套入小说写作 Agent；
- 不用单一总分掩盖任一硬门禁失败。

这些不是可选优化，而是已校验需求中的安全、追溯和结论完整性边界（`requirements.md:42`、`:185`、`:297`、`:325`、`:419`、`:637`）。

## 11. 测试与验收关注点

1. **能力目录与合同预检**：直接发现 17 Tool + 12 Subagent；每项至少一个合同有效且含必需硬门禁的案例。删除覆盖案例、增加生产能力、篡改目录身份、制造重复/未知/不可反查映射时，整套必须在第一个 case 前失败并一次列全。
2. **合同与身份测试**：suite/case/fixture/script/runtime-config/artifact/verifier/track/iteration/comparison schema；规范化 suite/fixture/script/bundle hash 相同内容稳定、任一实质变化产生新身份。
3. **严格 scripted 负向测试**：分别注入未声明交互、跨类型乱序、内容不匹配、提前耗尽、Runtime 停止后剩余步骤和相同输入规范化结果漂移；断言稳定失败类别、步骤位置、实际请求与全部剩余步骤。
4. **隔离测试**：前序 case 不能污染后序 case；活动 Markdown/Mongo confirmed 知识、密封源和其他副本前后不变。
5. **安全测试**：越权能力/写入被阻止；verifier 命令注入、动态执行和状态修改均不可达。
6. **判定测试**：六预算、六类硬门禁全组合；invalid/failed/unfinished/cancelled/blocked/uncomparable 不计通过；`failure_category` 与 `failure_categories` 同时正确；任何总分、均值或费用不能覆盖硬失败。
7. **工作记忆专项**：四态分别覆盖；来源指纹只传播到 BASIS/REVIEW_TARGET 下游；否决只作用目标；REPAIR_SOURCE 不传染修订；替代后旧项为 `SUPERSEDED`；并行无依赖候选隔离；节点摘要、digest、snapshot、`reuse_from_node_id` 任一回流旧三态即专项整体失败。
8. **证据测试**：关联链完整、断裂、冲突、缺失、损坏、不适用；禁止 mtime 补配；bundle 不复制巨型正文；实际 provider/model、probe、fallback、replay、Token、费用和错误可定位。
9. **生命周期测试**：单 case 失败继续、运行级隔离失败停止、取消保留完成工件、服务重启显示未完成、幂等重复提交、终态不反写。
10. **DeepSeek 首轮与复跑**：合成和全部硬门禁未稳定通过时拒绝真实首轮；首轮 artifact 不可覆盖；四类失败及证据不足未知分类；suite hash 改变强制全套重跑；定向案例、当前完整套件和核心无回归缺一项均不能关闭。
11. **Inbox 故障注入**：同一稳定问题 ID 去重；单协调器竞争；确定 HTTP/服务失败、八字段格式拒绝、超时结果不确定、允许重试后仍未持久化、读回失败、状态/正文不符、正反关联断裂或 ID 冲突均保持 `todo`/未闭环并阻止多模型比较。
12. **多模型准入测试**：逐案例改变预算、环境、能力、授权或解码配置；注入 probe 失败、fallback 污染、请求/实际身份不符、replay/Token/费用/错误缺失或冲突；对应运行必须标不可比、与能力失败分开并排除排名/收益/可比通过率。
13. **分轨/实验测试**：synthetic/live 完全分开；provider blocked/error/completed；无真实开关时拒绝实验并展示专项门禁；不可比实验无增益；重复运行报告样本数和离散度。
14. **API/UI 测试**：suite/run/case/bundle/iteration/issue-link/comparison 新合同、中文枚举、错误重试、紧凑空状态、分页筛选、取消和下钻；首屏整体能力结论优先、工作记忆专项独立、DeepSeek 闭环可见、未准入不出现排名、指标退居解释层。
15. **清理回归**：全仓扫描旧 API 路径、五维字段、旧状态、`general_eval_*.json` 和旧前端合同为零；排除 `docs/历史/`；29 能力 Profile/发现、知识抽取、召回、Inbox、LLM replay、Runtime 监控与恢复 benchmark 继续通过。

## 12. 设计阶段需继续研究

| 研究项 | 必须回答的问题 | 依赖/验证方式 |
|---|---|---|
| 密封 Mongo 快照形式 | 如何保证只含 confirmed 知识、可内容寻址、逐 case 可复制、绝不访问活动库？ | MongoDB 隔离策略、索引/validator 复用边界、活动库前后不变量测试 |
| case workspace 生命周期 | workspace 的创建、并行命名、取消、进程崩溃、清理和保留失败证据如何协调？ | fixture manager 契约、故障注入、孤儿 workspace 恢复/清理规则 |
| 29 能力目录快照与合格覆盖算法 | 如何从生产发现稳定序列化 17 Tool + 12 Subagent；何种 case 条件才计作 required hard-gate 覆盖；漂移如何在执行前原子失败？ | 插件发现输出、manifest 稳定字段、反向映射和漏项/重复/未知/漂移注入 |
| strict scripted step 合同 | 一条 step 如何声明交互类型、全局序号、task/capability、内容 matcher、响应/异常；何时 finalize 并判剩余；规范化结果排除哪些随机字段？ | `_ScriptedGateway` 注入缝、真实 Runtime 调用形状、六类负向测试、重复结果 hash |
| Runtime evidence reader 一致性 | 跨 run/invocation/snapshot/replay/checkpoint/effect/usage 的读取切面如何定义？ | 现有仓储行为、稳定 ID 链、缺失/冲突可用性状态、只读测试 |
| suite runner 与现有 Runtime 的调用边界 | 如何发起真实 Agent 运行并绑定 case/suite 身份，而不修改 Runtime 审计模型或创建假能力？ | 现有 Runtime 服务入口、能力授权模型、conversation/run/thread 标识传播 |
| scripted synthetic 的真实度 | synthetic 轨道怎样覆盖相同合同/证据形状，又不伪装为 live 运行？ | 独立 track 类型、artifact repository 分区、混轨拒绝测试 |
| typed artifact 提取 | 五类产物分别从最终回答、调用结果、候选和 HITL 状态的何处安全提取？ | 现有输出/调用模型，禁止完整正文复制，类型与身份回溯测试 |
| 工作记忆有效性与节点复用契约 | `SUPERSEDED` 如何进入隔离修复区；producer validity 如何绑定旧/新 node ID；复用前后如何证明 `ACTIVE`；digest/snapshot 如何统一过滤？ | AgentMemoryService、ContextAssembler、Orchestrator、Executor、来源指纹/依赖传播/并行候选专项 |
| 状态机与恢复 | queued/running/completed/failed/invalid/unfinished/cancelled 的允许迁移、终态和恢复命令是什么？ | 原子仓储语义、服务重启测试、取消竞态、幂等提交 |
| artifact repository 布局 | suite/case/bundle/experiment 如何按 ID/hash 引用而不复制巨型 trace，保留与清理策略是什么？ | `project_assets/readme.md` 联动、分页查询、空间增长测试 |
| 机制 aggregator 扩展点 | 总体、上下文、记忆、安全、恢复、provider 指标如何保持独立且可注册？ | 输入合同、适用 case 集、分子/分母、不可用语义和统计测试 |
| DeepSeek iteration 与冻结 | “合成稳定”的机器条件是什么；首轮何时冻结；四类失败与未知如何保存；修复轮如何绑定 suite hash、issue 和全套复跑？ | 内容寻址不可变 artifact、iteration 状态机、分类 schema、定向+全套+无回归关闭门禁 |
| Inbox 稳定 ID 与单协调器 | 稳定问题 ID 如何计算并保证唯一；GET-by-ID 缺失时如何查询；lease/CAS/补偿如何防止重复和丢更新；双向链接存在哪一侧且不破坏八字段正文？ | `/api/inbox/issues` 当前 list/create/PATCH、JSONL 锁语义、确定失败/超时/格式/读回/并发注入 |
| 多模型固定环境与实际身份 | 环境 identity 包含哪些可重建字段；逐案例预算如何固定；请求身份如何与实际 provider/upstream model 对账；probe/fallback/replay 缺失如何形成不可比而非能力失败？ | catalog/gateway/usage/replay、比较合同、环境快照、不可比排除测试 |
| API 资源模型 | suite/run/case/bundle/experiment 是否使用分层资源及何种分页/过滤/取消/恢复操作？ | 桌面交互需求、幂等语义、错误码与中文显示映射 |
| 最终结论视图模型 | 整体能力、工作记忆专项、局部机制、DeepSeek 闭环和多模型准入如何形成稳定优先级；何时允许显示排名；解释指标如何下沉？ | 新 API 结论合同、中文枚举适配、桌面层级/无数据/未准入组件测试 |
| 具体基准内容与阈值 | 首批 suite/case/provider/repetition 数量及各硬阈值由何处确认和固化？ | 当前需求明确未预设数值；设计不得擅自发明产品阈值 |
| 旧活动结果清理程序 | 物理删除如何限制到精确 `general_eval_*.json`，并证明不触及共享/历史数据？ | 绝对路径核验、dry-run 清单、全仓扫描和 `project_assets/readme.md` 更新 |

## 13. 差距分析结论

- **可直接复用**：生产插件发现与注册（当前 17 Tool + 12 Subagent）、29 能力独立 Profile、Runtime 原始证据与仓储、工作记忆四态/依赖模型、Inbox 八字段校验与唯一 API 入口、LLM probe/fallback/replay/usage 证据、共享评测配置、恢复 benchmark、前端 route/card/nav/AppShell 和现有 UI primitives。
- **需要窄扩展**：生产能力目录内容快照、只读 Runtime evidence reader、AgentMemory 生产者有效性查询与 `SUPERSEDED` 修复投影、`reuse_from_node_id` 有效性门禁、Inbox 稳定 ID/单协调器/读回、实际 provider-model 可比证据适配，以及新服务在 `main/deps/router` 的装配。
- **必须新增**：固定 suite/case 合同、29 项合格案例覆盖预检、密封 fixture、case workspace、strict scripted step driver 与消费/规范化身份、scripted/live 分轨 runner、typed verifier、六预算/六门禁、双失败类别、repro metadata、bundle/suite/experiment artifact repository、工作记忆细粒度专项、DeepSeek 首轮冻结/分类/修复/全套复跑、issue 双向链接、comparison gate、aggregators、运行状态机和新 API/UI。
- **必须删除/替换**：旧五维后端组、旧装配/导出、旧 manifest/API test、旧活动 `general_eval_*.json`、旧前端合同/测试和当前资料中的旧口径。
- **页面最终结论**：新工作台不能继续以五维分数或漂亮指标为中心；必须优先展示整体能力、工作记忆专项、局部机制、DeepSeek 闭环和多模型准入，只有准入完成才展示排名，分数/均值/Token/费用仅解释结论。
- **未知但不阻塞差距分析**：Mongo 快照与 workspace 的具体实现、strict matcher/规范化字段、Runtime reader 一致性、复用来源记忆身份、Inbox lease/双向链接存储、环境 identity、状态机存储形式、首批 suite/provider/阈值及 API 资源形态；这些应在设计阶段继续研究。

本产物不在扩展型方案 A、新建型方案 B 或混合型方案 C 中作最终选择；三者都必须满足同一 29 能力预检、strict scripted、工作记忆防复活、Inbox 持久化闭环、多模型不可比排除、破坏式清理、安全和固定端口验收门禁。只有“继续扩展旧五维根模型并保留兼容”这一变体因与已校验需求直接冲突而排除。
