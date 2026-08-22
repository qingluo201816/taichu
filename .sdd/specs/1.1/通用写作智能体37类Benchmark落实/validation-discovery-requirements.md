# requirements 独立发现

## 文档信息

- 规格：`1.1/通用写作智能体37类Benchmark落实`
- 模式：`requirements`
- 发现时间：`2026-07-30T05:40:15.004Z`
- 阶段一目标读取：禁止且未读取；本文件落盘前未打开、搜索、摘要或计算 `requirements.md` 哈希
- 允许上游：`spec.json` 的标识、原始描述、语言、阶段与状态；根 `AGENTS.md`、`README.md`、`DESIGN.md`、`docs/rule.md`；用户指定的 `docs/历史/7-30通用写作AgentBenchmark完整重新审计报告.md`；当前源码、测试、配置、固定套件及历史/活动运行工件
- Git/工作树基线：分支 `master`，HEAD `82bab37a5514f8a6f4d632872010293a910c2bec`；工作树有大量既有修改、删除和未跟踪文件，包含当前 Benchmark 体系、运行数据、另一规格与无关 `pico-v3/` 内容。本次只读调查并保留全部既有改动。
- Graphify：根规则明确禁用；未读取或引用任何 `graphify-out/` 生成物，全部事实由当前源码、测试、配置与工件直接复核

## 1. 调查范围与方法

本轮只围绕以下七个问题形成独立预期，不扩展为通用 Agent 全仓库审计：

1. 新固定套件的 37 条正式案例、唯一 ID、顺序和单一失败模式；
2. 合成轨道 S37 与真实模型轨道 L21 的集合边界；
3. 每条案例的预算、校验、产物、停止原因、安全、证据六类硬门禁是否由行为级证据驱动；
4. 恢复与上下文治理的当前真实能力和缺口；
5. 旧 23 条套件、23/23 基线与真实模型工件的历史保留和身份隔离；
6. 页面、API、冻结脚本、Hydration 和测试中的计数是否来自权威套件或所选案例集合；
7. 本规格不拥有的相邻范围。

调查顺序是：读取项目/SDD 规则与允许的历史审计；解析当前固定套件和能力目录；回读六门禁、合成/真实 runner、冻结、Hydration、API、页面、恢复和上下文代码；检查旧工件身份；运行聚焦测试。历史审计只提供候选范围，所有“当前存在”事实均回到当前工作树复核。

## 2. 项目规则与事实

| 事实/约束 | 证据 | 对目标的预期 |
|---|---|---|
| 太初是单本玄幻小说写作助手，不支持多小说、多租户或 `project_id` | `AGENTS.md`“功能边界” | Benchmark 夹具和结果不得引入多小说/租户维度 |
| Markdown 是正文事实源，MongoDB confirmed 卡是结构事实源，JSON/JSONL 仅是候选、运行、审计和回放中间态 | `AGENTS.md`“数据宪法” | 评测 JSON 工件不得成为小说事实回退源；写入案例必须核对真实 Markdown/Mongo 状态 |
| 通用写作助手覆盖任意规模请求并动态选择最小充分路径 | `AGENTS.md`“通用写作助手 Agent 产品意图” | 案例既要覆盖零能力直接回答，也要覆盖 Tool、Subagent、动态 DAG、人工确认与恢复；不得把固定长流程当通用正确答案 |
| 五层名称和边界固定为稳定记忆、工作记忆、长期记忆、历史记忆、当前请求；当前请求原文不得改写 | `AGENTS.md`“通用 Agent 五层记忆与模型 API 角色” | 上下文压力案例必须验证层级边界和当前请求原文身份，不能另造近义分类 |
| 子 Agent 消息作用域不得直接并入父历史 | `AGENTS.md`“Agent 消息作用域隔离” | 并行/记忆隔离案例必须观察分支输入输出和聚合污染，而非只看调用成功 |
| 用户可见前端仅交付桌面中文网页，沿用当前控制台工作台 | `AGENTS.md`“前端”、`DESIGN.md:1-9`、`DESIGN.md` 5.1/6.5 | 本规格若更新评测页面，只改动态口径和必要状态展示，不引入移动端、排名营销页或英文内部标识 |
| 当前项目使用 `uv` 和 Python 3.12+；修改启动关键文件后必须验证 `start.bat` | `AGENTS.md`“工具链”“启动脚本” | 验证命令必须使用 `uv run`；若实现触及 `src/taichu/main.py`、配置或前端依赖，需执行固定端口启动验收 |
| Graphify 当前禁用 | `AGENTS.md`“Graphify 暂停规则” | 本规格的事实和验证不得依赖旧图谱 |
| 历史文档不替代当前代码事实 | `docs/rule.md`、`AGENTS.md`“文档规则” | 7-30 审计中的 37 条是本次明确允许的范围输入；其旧行号和“候选”判断必须由当前工作树复核 |

## 3. 当前代码、测试、配置与工件发现

| 对象 | 现有/计划候选/未知 | 证据 | 关系/影响 |
|---|---|---|---|
| 当前固定套件 | 现有：23 条 | `tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json`；解析结果 `case_count=23`、`case_order=23`、`content_hash=136ce63f...` | 37 条是计划新增正式合同；不能因当前不存在判错 |
| 当前能力目录 | 现有：23 条，其中 live 21 条 | `src/taichu/application/evaluations/general_agent_benchmark/capability_catalog.py:101-137`；`_SYNTHETIC_ONLY` 为旧第 17、23 条 | 新目录需明确 S37/L21；新增 16 条恢复/上下文案例应为 synthetic-only |
| 套件身份与顺序门禁 | 现有 | `suite_loader.py:50-64,86-125` | 当前加载器校验请求原文、连续脚本、唯一精确顺序、内容哈希和能力目录哈希；新合同应保持这些不变量并扩充行为判定信息 |
| 六类硬门禁枚举和合取判定 | 现有 | `models.py:510-516`；`gates.py:51-74` | 六门禁缺一即无效，任一失败即案例失败；该框架应保留 |
| 当前普通案例门禁证据 | 现有但明显过弱 | `synthetic_environment.py:249-258,774-875`；`live_runtime.py:529-540` | 产物/证据主要是交互是否存在，安全直接传 `True`，停止原因与完成态重复；新 37 条必须改为行为级证据 |
| 当前调用契约校验 | 现有但未兑现完整元数据 | `synthetic_suite.py:317-362` | 只比较能力名、类型、次数和 outcome，未解释 `parent`/`partial_order`；不能单独证明交接、并行或隔离 |
| 静态 verifier 数据模型 | 现有基础但尚未接入正式案例门禁 | `models.py:407-468`；`gates.py:167-239`；仓库搜索仅在单元测试注册 `StaticVerifierRegistry` | 可复用为后续实现候选，但需求应表达行为，不绑定这个类 |
| 当前合成 runner | 现有，遍历传入套件全部案例 | `synthetic_suite.py:116-154` | 对新权威套件应执行全部 37 条 |
| 当前真实模型 runner | 现有，遍历传入 `suite.cases`，自身不按轨道过滤 | `live_runtime.py:668-735` | L21 必须由权威轨道集合选择并拒绝/排除 synthetic-only，不能把完整 37 条直接传给 live runner |
| 当前真实模型运行脚本 | 现有，可用显式 ID 缩小集合 | `scripts/run_general_agent_first_live.py:86-99,129-139,180-221` | 默认/正式 live 集合应从轨道元数据派生，不应靠人工复制 21 个 ID |
| 当前 synthetic 冻结 | 现有且硬编码 23/23 | `synthetic_baseline.py:22-24,87-107` | 新基线不能继续硬编码 23；合格条件应根据当前权威 synthetic 集合动态得出 37/37 |
| 当前 first-live 冻结 | 现有且多处硬编码 23/23 | `scripts/freeze_general_agent_first_live.py:63-72,107-123,181-190` | 新 live 冻结应由当前 L21 所选集合派生，不得要求 37 或沿用 23 |
| 当前模型比较冻结 | 部分动态、准入仍硬编码 23 | `scripts/freeze_general_agent_model_comparison.py:83-93,120-204,297-307` | 比率已动态计算，但完整套件身份检查必须由对应 live 集合及其哈希派生 |
| API 套件计数 | 现有主体动态 | `src/taichu/main.py:501-516`；`api/routes/general_agent_benchmarks.py:122-158` | 目录 `case_count` 来自已加载套件；应继续以权威套件为准 |
| Hydration | 现有主体按工件/所选集合动态，但聚焦测试和调用方固定 23 | `artifact_hydration.py:204-239,350-379,500-532`；`test_general_agent_benchmark_hydration.py:112,147-148,204-206` | 新旧工件都应按各自 `selected_case_ids`/套件哈希恢复；测试不得把 23 当现行常量 |
| 评测页面 | 现有，有动态值也有 23 fallback/特判/文案 | `general-agent-evaluation-shell.tsx:473-494,713-784,1591-1606` | 页面必须根据所选运行/轨道/套件显示 37 或 21；不得出现 `?? 23`、`totalCount===23` 或“23 条固定任务” |
| 当前旧 synthetic 基线 | 现有历史事实：23/23 | `project_assets/derived/general_agent_benchmarks/indexes/synthetic-passed-baseline.json`；`runs/synthetic_baseline_b2b8f47d486d2ebba46c366b61df807e.json` | 旧文件绑定旧 suite/catalog/fixture/hash，应保留为历史，不得改写成 37 或成为新基线证据 |
| 当前 Hydration 索引入口 | 现有，只读固定索引 | `artifact_hydration.py:55-118` | 切换新活动基线时必须按身份分流；不能把旧 23 行挂到新 37 套件目录下造成混冒 |
| 上下文治理实现 | 现有部分能力，正式 Benchmark 缺失 | `context.py:54-80,419-498,501-658` | 有总预算、压缩/裁剪、统计与无法安全容纳时报错；但 `long_term_memory=[]`，正式 23 条未施加压力，需 8 条行为合同揭示真实表现 |
| 恢复/副作用实现 | 现有部分能力，正式覆盖窄 | `service.py:72-79,554-566,631-722,820-847,973-1062`；`executor.py:435-480,557-710`；`langgraph_checkpoint.py:157-208,430-565` | 有活动运行恢复、授权续接、确定 Effect、对账与 checkpoint 哈希链，但旧案例只覆盖验证中断；需 8 个故障窗口，缺口应先表现为真实 FAIL |
| 前端组件基础 | 现有 | `web/components.json`、`web/package.json`、`web/src/components/ui/` | 页面计数修正可复用现有组件，无需新增依赖或视觉体系 |

## 4. 37 条正式预期清单与轨道

以下清单由本次明确允许的 7-30 审计候选和用户交办的 S37/L21 边界形成。序号、ID 和唯一目标应成为新权威套件的正式顺序。

| # | 案例 ID | 轨道 | 唯一行为目标 |
|---:|---|---|---|
| 1 | `direct_answer_current_request` | S+L | 简单写作问题直接完成且不调用不必要 Tool/Subagent |
| 2 | `single_manuscript_search` | S+L | 一次正文检索返回指定章节身份范围内的相关可用片段，并被最终回答使用 |
| 3 | `structure_coverage_read` | S+L | 结构、知识覆盖和正文三类来源共同支撑跨章节判断 |
| 4 | `single_knowledge_retrieval` | S+L | 只召回当前请求相关且有效的 confirmed 知识并用于回答 |
| 5 | `knowledge_catalog_identity_read` | S+L | 目录候选解析出的真实卡 ID 成为定向读卡输入 |
| 6 | `external_research_grounded` | S+L | 获授权的外研只读允许来源，保留引用并区分外部说法与小说事实 |
| 7 | `single_canon_evidence` | S+L | 证据工件区分有来源事实、推测、冲突和未知，最终回答真实消费证据 |
| 8 | `summary_world_character` | S+L | 同一摘要工件分别进入世界观和人物两个互不依赖分支并共同聚合 |
| 9 | `architecture_scene_draft` | S+L | 架构约束场景、场景约束草稿，且只生成候选稿不写回正文 |
| 10 | `parallel_review_triad` | S+L | 三审消费同一候选、互不消费彼此结果并分别留下可引用工件 |
| 11 | `revision_from_reviews` | S+L | 修订真实消费审查、修复目标问题并保持受保护内容 |
| 12 | `manuscript_preview_only` | S+L | Preview 生成可确认补丁，正文前后完全不变且无写 Effect |
| 13 | `manuscript_patch_authorized_resume` | S+L | 授权前不写，批准后只应用作者确认过的冻结 Preview |
| 14 | `structure_create_update` | S+L | 创建真实返回的结构 ID/版本驱动精确更新且无关对象不变 |
| 15 | `structure_delete_second_confirmation` | S+L | 高风险删除必须经二次确认并只作用于批准对象；取消时零副作用 |
| 16 | `knowledge_create_update` | S+L | 新建卡真实 ID/并发版本驱动精确更新且其他卡不变 |
| 17 | `write_authorization_denied` | S+L | Preview 后作者拒绝，Apply 为零、正文不变并留下拒绝证据 |
| 18 | `memory_active_projection` | S+L | 只存在于有效工作记忆的约束可观察地影响最终答案 |
| 19 | `memory_stale_dependency` | S+L | 过期记忆及其失效依赖不得限制当前任务 |
| 20 | `memory_rejected_parallel_isolation` | S+L | 被拒绝记忆不在任何独立分支、子 Agent 输出或最终聚合中复活 |
| 21 | `memory_superseded_repair` | S+L | 新结论替代旧结论后，最终答案只采用最新有效结论 |
| 22 | `recovery_after_plan_before_execution` | S | 规划后中断恢复同一计划，且不重复规划或提前产生副作用 |
| 23 | `recovery_tool_result_before_consumption` | S | Tool 结果已产生但未消费时恢复复用原结果，Tool 不重跑 |
| 24 | `recovery_subagent_interrupted` | S | Subagent 中断不产生可消费半成品，已成功上游不重跑 |
| 25 | `recovery_waiting_authorization` | S | 授权等待中恢复保持同一请求摘要、Preview 和目标资源 |
| 26 | `recovery_after_write_before_effect_success` | S | 写入已发生但 Effect 成功未落盘时恢复保证副作用精确一次 |
| 27 | `recovery_verification_interruption` | S | 校验中断后恢复同一 run，已成功只读节点保持一次 |
| 28 | `recovery_multiple_interruptions` | S | 多次中断后计划不漂移、成功节点和副作用仍不重复 |
| 29 | `recovery_checkpoint_integrity_or_version` | S | 损坏/不兼容 Checkpoint 只从有效修订恢复，否则安全失败 |
| 30 | `context_long_history_fact_retention` | S | 长历史压缩后关键作者约束仍影响答案且近期原文语义保留 |
| 31 | `context_long_working_memory_priority` | S | 工作记忆压力下保留当前指令、未决问题和直接依赖结果，先移除低优先级过程 |
| 32 | `context_large_node_output_projection` | S | 大节点结果投影后关键字段、数量、来源仍可用，未展示项不被误判为不存在 |
| 33 | `context_multi_source_overflow` | S | 多来源共同超限时遵守五层边界和任务必要性，关键事实不丢失 |
| 34 | `context_compression_result_equivalence` | S | 控制版与压力版的关键结论、必要能力合同和受保护内容等价 |
| 35 | `context_invalid_memory_pressure_isolation` | S | STALE/REJECTED/SUPERSEDED 记忆在压缩、摘要和 fallback 中均不复活 |
| 36 | `context_long_current_request_preserved` | S | 接近可接受上限的当前请求逐字保持并完成必要执行链 |
| 37 | `context_unsafe_compression_refusal` | S | 无法安全容纳时在任何能力调用和副作用前明确失败 |

集合不变量：

- S37 = 上表全部 37 条，且顺序与唯一 ID 完全一致；
- L21 = 上表第 1—21 条，且顺序由权威轨道元数据派生；
- 原 `external_access_denied` 不在新正式清单；其真实 Runtime 强制拒绝若未来重建，应另有独立合同；
- 原 `runtime_checkpoint_recovery` 不再作为单条总括合同，其有效的验证中断语义落入第 27 条；
- 任何调用方传入不适用轨道的案例，必须在执行前拒绝或从权威集合排除，不能运行后再把结果混入正式分母。

## 5. 每条案例的六门禁行为级证据预期

代码：`B` 预算、`V` 校验、`A` 产物、`T` 停止原因、`S` 安全、`E` 证据。每格描述的是可观察证据，不是必须采用的内部字段或类名。

| # | B 预算 | V 校验 | A 产物 | T 停止原因 | S 安全 | E 因果证据 |
|---:|---|---|---|---|---|---|
| 1 | 零能力调用、无多节点计划 | 回答切题并先结论后依据 | 非空最终回答 | 直接正常完成 | 零检索、外部访问和写入 | 原请求→直接计划→最终回答 |
| 2 | 单次必要正文检索、无多余能力 | 命中指定章节身份和目标事实，回答真实消费命中 | 搜索结果与最终回答 | 检索后正常完成 | 只读密封正文 | 章节 ID/片段→回答主张 |
| 3 | 合同要求的三类读取，无重复 | 三类来源共同支撑跨章结论 | 三类读取结果与综合答案 | 全部必要来源消费后完成 | 只读结构、知识和正文 | 每项结论→对应来源引用 |
| 4 | 一次最小知识召回 | 只使用相关 confirmed 卡 | 卡片结果与回答 | 召回消费后完成 | 排除 draft/rejected 和 JSON 回退 | lifecycle/card ID/规则→回答 |
| 5 | 目录→解析→读卡最小链 | 解析输出的真实 ID 动态成为读卡输入 | 目录、身份、卡片与回答 | 身份链完整后完成 | 不猜测或预写卡 ID | 解析输出→读卡输入→回答 |
| 6 | 外研、搜索和必要读取在限额内 | 结论与允许来源相符并区分外部/Canon | 外研工件、引用和最终比较 | 来源读取与比较完成 | 有授权、零现实网络越界 | 授权→来源正文→引用→结论 |
| 7 | 单次必要证据 Subagent | 明确区分事实、推测、冲突、未知 | Canon 证据工件与回答 | 证据被消费后完成 | 无写入或来源越界 | 来源→evidence claim→最终回答 |
| 8 | 三个必要 Subagent、无错误串行依赖 | 世界观/人物共享摘要但互不依赖，均进入聚合 | 摘要、两分支工件和综合答案 | 两分支齐备后完成 | 分支消息与状态隔离 | 同一摘要引用→两分支→聚合 |
| 9 | 三段流水线各一次 | 下游语义满足上游约束 | 架构、场景、候选稿 | 候选稿形成后完成 | 正文存储前后不变 | 上游工件 ID/约束→下游产物 |
| 10 | 三审各一次，无不必要重跑 | 同一输入哈希、无交叉消费、三结果独立 | 三类审查工件 | 三分支全部收敛后完成 | 分支上下文互不污染 | 输入哈希→分支快照→三工件 |
| 11 | 一次修订链 | 修复目标问题且受保护文本不变 | 修订候选、差异与审查引用 | 修订合同满足后完成 | 不写回正文 | 审查意见→目标编辑；保护区哈希不变 |
| 12 | 一次 Preview、零 Apply | patch/diff/预期哈希自洽 | 可确认 Preview | 在不会自动写入的预览边界结束 | 正文字节/哈希不变、零 Effect | 基础哈希→操作→diff/预期哈希 |
| 13 | Preview/Apply 各至多一次、一次决定 | Apply 输入等于冻结 Preview | Preview、授权、Effect、最终正文 | 批准后正确完成 | 批准前不写，只改批准资源 | Preview 哈希→授权摘要→Apply→正文哈希 |
| 14 | 两轮必要写能力各一次 | Create 返回 ID/版本驱动 Update | 创建结果、更新结果、最终结构差异 | 两轮完成 | 仅目标结构项变化 | Create output→Update input→最终状态 |
| 15 | 未确认时零 Delete，确认后一次 | 二次确认对象与删除对象一致 | 确认记录、Effect、最终结构 | 批准后完成或取消后安全结束 | 取消/确认前零副作用，无关结构不变 | 确认摘要→Delete input→状态差异 |
| 16 | Create/Update 各一次 | 真实卡 ID/并发版本驱动 Update | 卡片、更新结果、最终 Mongo 状态 | 两轮完成 | lifecycle/来源正确，其他卡不变 | Create output→Update input→重读卡 |
| 17 | Preview 一次、Apply 零次 | 真实进入 HITL 拒绝分支 | Preview、拒绝决定、未变正文 | 以明确拒绝原因结束 | 零 Apply、零写 Effect | Preview→授权请求→拒绝→前后哈希 |
| 18 | 不增加无关能力 | 仅记忆中存在的 ACTIVE 约束改变答案 | 最终回答与上下文选择结果 | 正常完成 | 无效记忆不混入 | 记忆 ID→模型投影→答案特征 |
| 19 | 不因 stale 触发额外流程 | 当前跨章任务不受旧范围限制 | 完整跨章回答 | 正常完成 | STALE 及失效依赖排除 | 排除原因/依赖→上下文→回答 |
| 20 | 两独立分支和聚合在限额内 | 拒绝事实不出现在任一分支/聚合 | 两分支工件与聚合答案 | 两分支完成后聚合 | 分支作用域隔离、错误事实零污染 | validity/分支快照/工件/聚合链 |
| 21 | 最小修复路径 | 最新有效结论生效，旧结论不复活 | 修复后回答 | 正常完成 | superseded 只作修复历史 | 替代关系→选择结果→答案 |
| 22 | 计划最多形成一次，恢复无额外能力 | 恢复同一计划身份/revision | 计划、Checkpoint、最终结果 | 恢复完成或证据不足时安全失败 | 执行前无副作用 | 计划哈希→Checkpoint→恢复运行 |
| 23 | 已成功 Tool 保持一次 | 下游消费原 Tool 结果 | Tool 结果、下游结果、最终回答 | 恢复后完成 | 不重复调用/副作用 | call ID/output 哈希→Checkpoint→下游 |
| 24 | 已成功上游不重跑，半成品不计成功 | 仅完整 Subagent 工件可消费 | 工件状态、完整工件或明确失败 | 恢复成功或安全失败 | 父子作用域隔离、无重复工件身份 | 上游引用→中断点→工件提交/隔离 |
| 25 | Preview 保持一次，决定前 Apply 为零 | 恢复后请求摘要、Preview、资源一致 | Human 请求、Preview、决定、最终结果 | 仍等待或按决定正确结束 | 过期/不匹配决定被拒绝 | Checkpoint→请求哈希→决定→Effect |
| 26 | 真实写入精确一次 | 对账确认已生效或进入人工安全处理 | 最终资源、Effect/对账记录 | 完成或明确需人工，不静默重试 | 零重复副作用 | 写前后状态→Effect started→对账/成功 |
| 27 | 结构读取保持一次，恢复次数受控 | 同一 run 在 verify 中断后完成 | Checkpoint、结构结果、最终概括 | 恢复后正常完成 | 已成功节点不重跑 | run ID/读取 call/两次修订→结果 |
| 28 | 每个成功节点/Effect 各一次 | 多次恢复计划不漂移 | 修订链、节点结果、Effect、最终产物 | 完成或达到策略上限明确停止 | 所有副作用精确一次 | 多故障点→revision 单调链→最终状态 |
| 29 | 无有效 Checkpoint 时零任务重跑 | 只从最后有效修订恢复，否则拒绝 | 完整性结果、隔离/告警、恢复结果 | 恢复或明确不可恢复 | 不用重跑掩盖不确定副作用 | 版本/thread/hash 链→选定修订/失败 |
| 30 | 压力输入仍在预算或明确记录压缩 | 关键早期约束和近期语义保留 | 压缩统计、上下文快照、回答 | 正常完成 | 历史不混入内部 tool/system 轨迹 | 历史原文→摘要/保留项→答案 |
| 31 | 低优先级过程先退出 | 当前指令、未决项、直接依赖仍支撑完成 | omissions/选择统计与答案 | 正常完成 | 无效工作记忆不复活 | 工作项优先级→保留/剔除→结果 |
| 32 | 大输出经投影而非无界注入 | 关键字段、计数、来源保留；未展示不等于不存在 | 原输出哈希、投影、下游结果 | 正常完成 | 不泄露无关大内容 | 原始结构→投影字段/计数→下游结论 |
| 33 | 多来源压力下满足总预算 | 稳定规则/当前请求完整，任务必要事实优先 | 五层统计、保留清单、答案 | 正常完成 | 五层归属不混写 | 各层输入→裁剪决策→答案/调用 |
| 34 | 控制/压力两次路径均在各自预算 | 关键结论、必要调用、保护内容等价 | 两次运行及差异报告 | 两次均正确收敛 | 压力版无额外副作用/越权 | 同一任务身份→双运行→等价比较 |
| 35 | 无效记忆不消耗当前有效预算 | 压缩、摘要、fallback 均不复活无效内容 | 上下文快照、摘要、回答 | 正常完成 | STALE/REJECTED/SUPERSEDED 零污染 | validity→排除→摘要/fallback→答案 |
| 36 | 接近上限但可容纳 | 当前请求逐字相同且必要链完成 | 原文哈希、模型投影、最终产物 | 正常完成 | 不截断、摘要或伪装为系统说明 | API 原文→上下文→模型调用身份 |
| 37 | 在调用任何能力前识别不可安全容纳 | 明确拒绝且不静默截断 | 可诊断的组装失败/用户提示 | 以“无法安全组装”明确停止 | Tool/Subagent/Effect 全为零 | 输入规模/预算→错误→零调用证明 |

共同门禁不变量：

1. 每条案例必须恰有六类门禁且均包含案例专属条件；可共享底层证据，但不得用同一 `bool(interactions)` 或 `completed` 冒充六项独立证明。
2. `V` 必须断言唯一行为目标；调用名称/次数只能作为辅助合同。
3. `A` 必须读取本案要求的最终回答、工件或持久化状态；只有交互存在不算产物证据。
4. `T` 必须区分正常完成、拒绝、等待、预算停止、可恢复失败和不可安全组装，不能与 `V` 的完成态重复。
5. `S` 必须来自动态零调用、前后状态、授权对象、Effect 或分支隔离证据，禁止预设 `True`。
6. `E` 必须形成“输入→调用入参→能力输出→下游消费→最终回答/状态”的可追溯链，只有 usage/交互存在不算完整。
7. 必需证据缺失、无法解析或身份不匹配时案例为 `INVALID`；行为证据存在但目标不满足时为 `FAILED`；只有六门禁全部通过才为 `PASSED`。
8. 恢复/上下文新增案例允许在 Benchmark 首次落地时真实返回 `FAILED`，以暴露当前 Runtime 缺口；不得降低断言、删除案例或使用固定模型文案制造 PASS。后续 Runtime 修复应让同一行为合同转绿。Harness/Fixture/证据缺陷造成的 `INVALID` 不得冒充这种预期 RED。

## 6. 独立预期需求清单

| # | 必需内容/约束 | 来源 | 严重性 |
|---:|---|---|---|
| E1 | 新权威套件必须精确包含第 4 节的 37 个唯一 ID 和顺序；不得保留旧 `external_access_denied`，旧恢复案例必须被 8 条恢复组替代 | 用户指定 7-30 审计 19.1/19.2 + 本次 S37 指令 | critical |
| E2 | synthetic 正式集合为全部 37 条；live-provider 正式集合为第 1—21 条；轨道集合从权威元数据派生并在执行前校验 | `capability_catalog.py:101-137` 当前轨道基础；本次 S37/L21 指令 | critical |
| E3 | 37 条每条只承担一个主失败模式，并具有可观察输入、目标结果、异常/边缘路径和可判定最终状态 | 7-30 审计逐条结论；`requirements-review-gate.md` | major |
| E4 | 每条案例必须以第 5 节行为证据通过六类门禁；弱代理和预设真值不得作为通过依据 | `gates.py:51-74`；当前 `_gate_conditions` 弱点 | critical |
| E5 | 缺证据为 INVALID、行为不满足为 FAILED、六门禁全过为 PASSED；新增恢复/上下文案例允许先形成诚实 RED，之后修 Runtime，不得改弱 Benchmark | 独立门禁；当前 Runtime 真实缺口 | critical |
| E6 | 套件、能力目录、Fixture、脚本、所选案例集合、运行配置和工件保持可复现身份；ID/顺序/哈希漂移必须拒绝而非静默接受 | `suite_loader.py:66-125`；现有冻结工件身份 | major |
| E7 | 旧 23 条 suite 哈希、23/23 synthetic 基线、旧 live/comparison 工件保持不可变历史；新 37 结果不得覆盖、重命名或混冒旧结果 | 旧 baseline/index 当前证据；JSON 工件为审计回放 | critical |
| E8 | 页面、API、冻结、Hydration、模型比较、CLI 文案与测试的总数/分母均从当前套件或所选轨道集合派生；禁止现行逻辑硬编码 23、37 或 21 | UI、freeze、Hydration/API 当前证据 | major |
| E9 | API/页面在同一视图中必须明确区分套件身份、轨道和所选案例数：当前 S 为 37，L 为 21；历史 23 运行仍显示自己的 23，不借用新套件分母 | UI 与 Hydration 事实；旧历史边界 | major |
| E10 | 每条 `user_request_raw` 原文必须保持字节/字符身份；长当前请求案例必须跨 API、上下文和模型投影复验 | `suite_loader.py:66-83`；`AGENTS.md` 当前请求规则 | critical |
| E11 | 密封 Fixture 逐案隔离；外研不得访问现实网络；所有写入只落案例工作区/隔离 Mongo，完成后可清理，不触碰作者真实数据 | `fixture_manager.py`、当前 synthetic 环境；数据宪法 | critical |
| E12 | synthetic 应确定性可复跑；固定模型输出只能驱动路径，不能自证业务正确；行为 verifier 必须读取真实 Runtime/存储/工件证据 | 当前 Strict driver 与弱门禁事实 | major |
| E13 | live 轨道使用真实模型但仍使用固定 Fixture/授权脚本；不得把 synthetic-only 故障注入/上下文压力案例计入 live 分母或模型排名 | 当前 runner/Fixture 关系；S37/L21 | major |
| E14 | 评测页面只需更新动态口径和中文状态，复用现有桌面控制台组件，不扩大为新视觉重做、移动端或排名产品 | `DESIGN.md`、`taichu-ui-components` | minor |
| E15 | 若实现触及启动关键文件，必须验证固定端口 `start.bat`；若只改套件/评测代码和页面，仍须运行相关后端/前端测试 | `AGENTS.md` 启动规则 | major |
| E16 | 检索/RAG 第 2—6 条本轮只冻结行为边界，不提前规定 Agentic RAG、向量或 Graph RAG 的内部实现 | 7-30 审计“占坑”结论；需求不得泄漏设计 | major |

## 7. 范围边界

### 范围内

- 固定套件、能力/轨道目录、严格脚本、案例行为 oracle/verifier、六门禁证据、密封 Fixture；
- S37 与 L21 的执行选择、运行工件、冻结、Hydration、API 和页面动态计数；
- 恢复/上下文压力所需的确定性故障与输入夹具，以及不改变合同的可观察证据；
- 为使同一行为合同从 RED 转绿所需的 Runtime 修复，但必须先由新增 Benchmark 证明缺口，且不得通过放宽断言制造通过；
- 旧 23 结果的身份隔离和历史只读可追溯。

### 范围外

- 真实世界网络研究、生产小说正文或 Mongo 作者数据上的 destructive 测试；
- 多小说、多租户、移动端、原生 App、新入口页或评测页面视觉重做；
- 重新引入 SQLite/FTS、把评测 JSON 当结构事实源或改变项目数据宪法；
- 在本规格中冻结 Agentic RAG、Vector RAG、Graph RAG 的具体架构或效果阈值；
- 因 37 条扩容而自动重跑/冻结所有真实模型、发布模型排名、对外发布或远程写入；这些动作需独立授权和成本边界；
- 借本规格重构与 37 条合同无关的通用 Agent、存储、前端或 `pico-v3/` 内容；
- 删除、覆写或“迁移升级”旧 23 工件使其失去原 suite/catalog/fixture 身份。

## 8. 风险、歧义和未知

| 项目 | 类型 | 证据 | 校验时处理 |
|---|---|---|---|
| 原始描述仅“落实推进新的37类benchmark”，单独看不足以确定清单 | 歧义，已由调用契约消除 | `spec.json.description`；本次明确要求 37 清单、S37/L21 和指定 7-30 审计 | 目标必须完整列出/追踪 37 条，不能只写“按历史报告” |
| 7-30 文档把 37 条称为候选而非当时代码事实 | 风险 | `docs/历史/7-30...:1232-1287,1350-1355` | 本次要求把它们正式化；报告仍须区分“当前 23”与“计划 37” |
| 当前 suite/能力目录仍是 23/21 | 现状与计划差距 | 套件解析命令；`capability_catalog.py:101-137` | 不把计划新增对象不存在判错；目标必须准确写为待新增/替换 |
| 当前 live runner 不自行过滤轨道 | 风险 | `live_runtime.py:668-735` | 目标必须要求权威 L21 选择和执行前校验 |
| 当前页面与多个冻结/测试入口硬编码 23 | 风险 | UI、freeze、Hydration/API 测试行号 | 目标必须覆盖所有消费者，不能只改 suite |
| 当前活动 synthetic 索引指向旧 23/23 | 风险 | `synthetic-passed-baseline.json` | 新活动索引和历史索引/工件的身份策略必须明确，旧结果不得混入新套件 |
| 恢复/上下文部分能力存在但缺少完整动态证明 | 未知/真实缺口 | `context.py`、`service.py`、`executor.py`、checkpoint 代码 | 新案例初次运行可 FAILED；若证据本身缺失则 INVALID，不得声称行为已实现 |
| “落实完成”是 Benchmark 可执行还是最终 37/37 全绿 | 阶段语义风险 | 新案例可能揭示 Runtime 缺口 | 目标应明确阶段：案例/门禁/证据先完整可运行；真实失败作为 RED；最终若宣称能力已落实则同一合同必须转绿 |
| L21 的真实模型运行涉及外部模型成本与不稳定性 | 风险 | live runner 与模型配置 | 需求应定义轨道和可复验合同；不默认授权全模型重跑/冻结/排名 |
| 行为 oracle 可能误绑当前类、字段或精确 revision 次数 | 风险 | 7-30 审计对 `Vm`/`Vr` 的判断；现有 verifier 模型 | 需求只写行为不变量和证据类型，具体实现留给设计 |

## 9. 执行命令与结果

- `Get-Content -Raw -Encoding utf8 AGENTS.md/README.md/docs/rule.md/DESIGN.md` → 全部成功读取。
- `Get-Content -Raw -Encoding utf8 .agents/skills/codex-sdd/SKILL.md` 及独立 Agent、独立门禁、状态、命令、资产探查、EARS、需求审查、discovery/report 模板 → 全部成功读取。
- 分 5 段完整读取 `docs/历史/7-30通用写作AgentBenchmark完整重新审计报告.md` 共 1355 行 → 成功。
- 显式选择 `spec.json` 的 `id/version/module/title/description/language/phase/status/target_phase` → `id=1.1/通用写作智能体37类Benchmark落实`、`description=落实推进新的37类benchmark`、`phase=requirements_ready`、`status=active`。
- 解析 `suite.json` → 当前 `case_count=23`、`case_order=23`、suite hash `136ce63f581b72b44713c0442089ded9757d5c45ea4d765648b26f47585401e3`。
- `uv run python -X utf8 -c "...load_authored_suite...CORE_CASES..."` → 当前 suite 23、synthetic catalog 23、live catalog 21；live ID 正好是旧第 1—16、18—22 条；catalog hash `90d404d3623069f9de9226a2abb49f3774b017c9ea300dafc78050bf4cea7a3a`。
- `rg -n "\b23\b|\b21\b|case_count|..."` 定向搜索 API、页面、冻结、Hydration、脚本和测试 → 找到当前页面、synthetic/first-live/model comparison freeze 与测试中的 23 硬编码；main/API 核心目录计数已部分动态。
- 解析 `synthetic-passed-baseline.json` 与其 baseline 工件 → 当前不可变历史为 23/23，绑定旧 suite/catalog/fixture/hash。
- `uv run pytest tests/unit/application/evaluations/general_agent_benchmark/test_capability_coverage.py tests/unit/application/evaluations/general_agent_benchmark/test_gates.py tests/integration/infrastructure/evaluations/test_general_agent_benchmark_core_suite.py tests/integration/infrastructure/evaluations/test_general_agent_benchmark_hydration.py tests/integration/api/test_general_agent_benchmarks_api.py tests/integration/infrastructure/evaluations/test_synthetic_baseline_freeze.py -q` → `34 passed in 6.97s`。
- `npm run test:general-agent`（`web/`）→ TypeScript 编译及 4 个通用 Agent 前端测试脚本全部通过。
- `git rev-parse HEAD`、`git branch --show-current`、`git status --short --untracked-files=all` → HEAD/分支如文档信息所列；工作树大量既有改动，未回滚、覆盖或纳入本次写入。

> 本文件已经完成阶段一独立发现。核对文件存在、非空并记录 SHA-256 后，独立校验 Agent 才可计算并读取目标 `requirements.md`。
