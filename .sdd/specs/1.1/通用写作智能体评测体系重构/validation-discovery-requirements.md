# 需求独立发现

## 文档信息

- 规格：`1.1/通用写作智能体评测体系重构`
- 模式：`requirements`
- 发现时间：`2026-07-26T17:14:37.668Z`
- 阶段一目标读取：禁止且未读取
- 允许上游：`spec.json.description` 的原始描述与安全元数据、根 `AGENTS.md`、`README.md`、当前源码/测试/配置、`pico-v3` 当前参考实现
- 禁止上游遵守：未读取 `requirements.md`、任何既有 requirements discovery/report、`design.md`、`research.md`、`gap-analysis.md` 或其摘要
- Git/工作树基线：`HEAD 82bab37a5514f8a6f4d632872010293a910c2bec`；工作树存在大量与本轮并行的已修改/未跟踪文件，本轮不修改、不回滚、不纳入结论，只把当前源码视为事实

## 1. 调查范围

本轮只形成会影响 critical/major 门禁的 15 组预期，围绕六个聚合边界收敛：生产能力全覆盖、严格脚本交互、工作记忆四态与复用污染、Inbox 持久化闭环、多模型可比准入、破坏式旧实现清理。原始描述中的固定 benchmark、隔离执行、确定性 baseline、多条件通过、失败解释、运行工件聚合、分机制实验和页面入口也纳入预期。未调查非关键视觉细节，未把 Pico 的具体内部类名当成太初必须照搬的设计。

## 2. 项目规则与事实

| 事实/约束 | 证据 | 对目标的预期 |
|---|---|---|
| 本规格是对现有通用写作智能体评测的完全替换，不保留旧兼容 | `spec.json.description` 原文；`AGENTS.md`“技术栈变更必须联动清理”“旧实现清理规则” | 需求必须把旧代码、接口、状态、字段、前端、测试、当前资料和僵尸入口的删除列为可机械验收硬门禁 |
| 通用智能体能力目录与单次运行 DAG 分离，Runtime 只能使用已注册真实能力 | `AGENTS.md`“能力目录与运行实例解耦”；`tests/unit/application/evaluations/test_capability_profiles.py:13-25` | 评测覆盖必须从生产发现结果生成机器快照并检测目录漂移，不能维护另一份人工清单 |
| 当前生产能力 Profile 共 29 个并与 Tool/子 Agent 动态发现集合相等 | `tests/unit/application/evaluations/test_capability_profiles.py:13-25`；`src/taichu/application/evaluations/capability_profiles.py:32-53` | 每个生产能力至少有一个结构合格、可执行的案例；少一个、重复、孤儿或目录漂移都必须阻断运行 |
| 当前通用评测集只有 8 类代表案例，并非 29 个生产能力的全覆盖 benchmark | `tests/fixtures/evaluations/general_writing_assistant_core/manifest.json:8-292`；`tests/integration/api/test_general_agent_evaluations_api.py:44-72` | 新需求不能把“有 Profile”或“有代表场景”误当成全覆盖，应规定逐能力覆盖矩阵和预检失败证据 |
| 当前测试桩按任务名从列表 `pop(0)`，未声明请求匹配、乱序、耗尽和剩余步骤统一失败契约 | `tests/unit/application/general_agent/test_runtime.py:111-143` | strict scripted interaction 必须严格顺序消费并同时验证期望请求；意外、乱序、耗尽、运行结束仍有剩余步骤均失败，且同步/异步或不同调用入口采用同一规范化结果 |
| 五层上下文和对话隔离已有真实实现，复用快照也有一致性校验 | `src/taichu/application/general_agent/context.py:53-81,187-229,297-316`；`tests/unit/application/general_agent/test_memory_context.py:80-127,398-468` | 评测需覆盖工作记忆四种运行态与复用污染，既验证应复用，也验证跨 case、跨 conversation、过期/失效或前一模型运行不得污染 |
| DeepSeek 是当前唯一默认模型，网关支持实际身份、探测与官方 fallback 记录 | `tests/unit/infrastructure/llm/test_identity_runtime.py:17-20`；`tests/unit/infrastructure/llm/test_rightcode_gateway.py:339-430`；`src/taichu/application/contracts/llm.py:144-180` | benchmark 首轮必须先跑 DeepSeek；多模型比较必须记录实际 provider/model/upstream/fallback/探测证据，不能仅以请求别名分组 |
| 当前模型契约已归一化 usage/cost，但成本可能 `unavailable` | `src/taichu/application/contracts/llm.py:17,113-124`；`tests/unit/infrastructure/llm/test_rightcode_gateway.py:112-139,700-729` | 可比排名必须有固定环境、预算和证据完整性准入；fallback、身份不明、探测失败、成本/用量缺证或环境污染的运行必须排除排名并解释原因 |
| Inbox 问题记录已有规范格式、持久化、列表和读回入口，但当前问题模型未含评测运行双向关联 | `AGENTS.md`“系统问题记录口令”；`src/taichu/application/services/mvp_inbox_service.py:25-28,146-220,288`；`src/taichu/domain/models/mvp_inbox.py:69-75`；`tests/integration/api/test_mvp_first_api.py:231-379` | 评测确定失败必须创建规范问题并读回；格式拒绝或未持久化必须阻断；问题可回到评测运行，评测运行也可列出问题，关联缺失不得宣称闭环 |
| 旧通用评测仍有独立后端服务、路由、8-case 数据集、前端 API/类型/页面与测试 | `src/taichu/main.py:453-528`；`src/taichu/api/routes/general_agent_evaluations.py:1-140`；`web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx:47-250`；`tests/integration/api/test_general_agent_evaluations_api.py:1-102` | 新体系替换完成后这些旧实现不得作为兼容路径残留；任务入口中的页面位置保留，但内容和契约应由新体系接管 |
| Pico 固定 benchmark 使用锁定 schema、全新 fixture 副本、全新 run 目录和可复现元数据 | `pico-v3/pico/evaluation/evaluator.py:19-36,171-241,380-476`；`pico-v3/tests/test_evaluator.py:16-130` | 太初需求必须规定冻结输入、校验和/快照、隔离运行目录、固定时区/locale/解码/预算等环境证据和漂移阻断 |
| Pico 的单例通过是多条件合取，并持久化失败类别和工件 | `pico-v3/pico/evaluation/evaluator.py:491-541,554-564`；`pico-v3/tests/test_evaluator.py:82-130,190-226` | 通过不能仅由总分或回答文本决定；必需验证、预算、工件、正常停止、能力契约和安全门禁任一失败都应使 case/运行失败 |
| Pico 能聚合运行工件并做记忆、上下文、安全、多 provider 等分机制实验 | `pico-v3/pico/evaluation/run_evidence.py:15-111`；`pico-v3/pico/evaluation/metrics.py:67-109,308-621,809-970` | 结果必须保存可回放工件、失败解释和机制实验分组；机制实验不得与生产多模型排名混淆 |
| 前端仅交付桌面网页，入口继续位于任务监控的“通用写作智能体评测” | `AGENTS.md`“前端”“桌面布局边界”；`web/src/components/agent-task-monitor/task-monitor-overview.tsx:164-211`；`web/src/components/agent-task-monitor/general-agent-monitor-nav.tsx:27-29` | 需求只覆盖桌面页面，并保留现有入口与中文可见文案；不扩展移动端或独立 App |

## 3. 代码、测试与配置发现

| 对象 | 现有/计划候选/未知 | 证据 | 关系/影响 |
|---|---|---|---|
| 29 个生产能力 Profile 与发现一致性测试 | 现有 | `src/taichu/application/evaluations/capability_profiles.py:32-53,76-208`；`tests/unit/application/evaluations/test_capability_profiles.py:13-25` | 可作为目录快照来源，但不能替代逐能力合格案例 |
| 8-case 通用写作助手评测集与确定性评分服务 | 现有且待替换 | `src/taichu/application/evaluations/general_agent/models.py:20-163`；`src/taichu/application/evaluations/general_agent/service.py:81-127,131-399` | 旧数据模型只评已有 run，缺少严格脚本、全覆盖、环境准入、Inbox 闭环与多模型排名证据 |
| strict scripted interaction | 计划新增边界 | `tests/unit/application/general_agent/test_runtime.py:111-143`；在限定 `src/`、`tests/` 搜索范围未发现统一生产评测契约 | 必须有正向和五类失败测试：意外、乱序、耗尽、剩余、请求不匹配；并验证规范化响应一致 |
| 工作记忆四态 benchmark | 计划新增边界 | `tests/unit/application/general_agent/test_memory_context.py:80-127,132-223,398-468` | 应复用现有五层上下文和隔离能力，构造空白/有效复用/失效或过期/污染尝试四类状态 |
| DeepSeek 首轮及多模型可比准入 | 计划新增评测约束，底层能力现有 | `tests/unit/infrastructure/llm/test_identity_runtime.py:17-20`；`tests/unit/infrastructure/llm/test_rightcode_gateway.py:339-430,700-729` | 评测编排必须先 DeepSeek，再在固定环境下运行其他真实模型；探测或身份/预算证据不合格不得进入排名 |
| Inbox 评测问题双向关联 | 计划新增边界 | `src/taichu/domain/models/mvp_inbox.py:69-75`；`src/taichu/application/services/mvp_inbox_service.py:146-220` | 需在不破坏规范内容格式的前提下持久化关联，并有问题→运行、运行→问题读回验证 |
| 运行工件聚合与失败解释 | 部分现有、需重构 | 现有 run/trace/replay 可用；Pico 参考为 `pico-v3/pico/evaluation/run_evidence.py:15-111` | 必须把目录快照、输入快照、script 步骤、实际模型身份、用量/成本、运行轨迹、断言、失败类别和关联问题聚合为可审计工件 |
| 旧后端/前端/测试入口 | 现有且必须破坏式清理 | `src/taichu/api/routes/general_agent_evaluations.py:1-140`；`web/src/lib/api/general-agent-evaluation.ts:8-46`；`web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx:47-250`；`web/tests/general-agent/evaluation-view.test.ts:12-64` | 新入口接管后，旧契约、状态、字段、数据集和测试不得残留或继续可调用 |

## 4. Graphify

- 扫描根：未读取
- 是否覆盖：不适用
- 查询与 `source_location`：未执行任何 Graphify 命令
- 源码复核：全部结论直接来自当前源码、测试、配置和 Pico 参考文件
- 降级：使用 `rg`、逐文件读取和测试证据；一次初始文本检索范围过宽命中 `src/graphify-out/cache` 路径，该输出立即弃用且未作为任何事实或证据

## 5. 独立预期清单（15 组）

| # | 必需内容/约束 | 来源 | 严重性 |
|---:|---|---|---|
| 1 | 明确完全替换旧通用智能体评测，同时保留任务入口中的桌面“通用写作智能体评测”位置；不保留旧兼容路径 | `spec.json.description`、`AGENTS.md`、现有入口 | critical |
| 2 | benchmark 的 schema、案例输入、数据快照、校验和与版本/变更规则固定；缺字段、重复 ID、快照或校验和漂移时在执行前失败 | 原始描述；Pico `validate_benchmark` 与 fixture snapshot | critical |
| 3 | 每次 case 使用隔离的临时工作区、运行 ID、存储和清理边界；禁止前例产物、缓存、记忆、Inbox 或模型脚本状态泄漏 | 原始描述；Pico fresh fixture/run；太初五层隔离规则 | critical |
| 4 | 从当前生产 Tool/子 Agent 动态发现结果生成规范化、可哈希的机器目录快照；与 baseline 漂移、重复、孤儿或发现失败时预检阻断 | 29 能力一致性测试；能力目录规则 | critical |
| 5 | 目录快照中的每个生产能力至少被一个 schema 合格且可执行的 benchmark case 覆盖，并追踪到能力专属指标；缺少任一能力即失败 | 当前 29 Profile 与 8-case 差距 | critical |
| 6 | strict scripted interaction 严格按步骤顺序消费并匹配请求关键字段；意外调用、乱序、步骤耗尽、请求不匹配、运行结束仍有剩余步骤全部失败 | 当前 `_ScriptedGateway` 缺口；确定性 baseline 目标 | critical |
| 7 | scripted 输出经通用 LLM 规范化后，不同调用入口对文本、工具调用、usage、cost、实际身份、错误使用一致结果；格式无效必须确定失败而非静默兼容 | 统一 LLM 契约；严格 scripted 目标 | major |
| 8 | 工作记忆以四态机械验收：空白隔离、同会话有效复用、失效/过期不复用、跨 case/会话/模型污染尝试被拒；每态都有可观察选中/排除证据 | 五层记忆规则；现有 memory/context 测试 | critical |
| 9 | DeepSeek 作为默认模型首轮完整执行并形成可审计基线；首轮失败、fallback 或证据不足不得被其他模型结果掩盖 | 当前唯一默认模型；原始多模型目标 | major |
| 10 | 多模型每次运行记录请求身份、实际 provider/model/upstream、探测结果、fallback 链、时间、用量和成本；不得仅按显示名归组 | LLM identity/probe/fallback 现状 | critical |
| 11 | 所有模型使用同一 benchmark 快照、固定 locale/timezone/解码/工具/预算/并发与干净环境；超预算、环境污染、fallback、探测失败或身份/用量/成本缺证的运行标为不可比并排除排名 | Pico reproducibility；太初 usage/cost 契约 | critical |
| 12 | case 与整轮通过均为多条件合取：目标断言、能力契约、script 完整消费、正常停止、预算、安全、必需工件、持久化与环境证据；任一硬条件失败即失败，并输出稳定失败分类和中文解释 | 原始描述；Pico multi-condition pass/failure category | critical |
| 13 | 聚合并可读回目录/数据快照、环境、script、请求/响应、轨迹、工件、断言、费用、失败解释、排行准入与关联问题；缺失关键工件不得完成 | 原始描述；Pico `RunEvidence`/artifact aggregation | major |
| 14 | 分机制实验至少独立表达记忆、上下文、恢复/安全等变量、对照、重复次数和聚合结果；不得把分机制结果混入真实多模型排名或当作生产通过替代 | 原始描述；Pico metrics experiments | major |
| 15 | 确定失败自动进入 Inbox 规范闭环：格式拒绝、写入失败或读回不一致阻断完成；问题与评测运行双向关联；替换后旧代码/API/状态/字段/前端/测试/当前资料及僵尸依赖全部清除 | 根问题记录规则；原始破坏式清理；现有旧入口 | critical |

## 6. 风险、歧义和未知

| 项目 | 类型 | 证据 | 校验时处理 |
|---|---|---|---|
| “工作记忆四态”的四个名称在原始 description 未逐字定义 | 歧义 | 输入任务明确要求四态，现有实现有活跃、失效、过期、隔离/复用行为 | 目标需用可观察前置状态和预期结果定义四态；仅写“四态覆盖”视为不可验证 |
| “多模型”没有在原始 description 指定固定候选集合 | 未知 | 当前目录含 GPT、Claude、DeepSeek，DeepSeek 是唯一默认 | 目标可要求运行时从明确的已探测候选清单冻结集合；不得硬编码未经用户确认的永久模型清单，但必须规定 DeepSeek 首轮 |
| 成本可能不可用，是否允许只用 token 预算需明确 | 风险 | `LLMCost.kind` 允许 `unavailable` | 目标必须规定排名准入：成本或用量哪个是必需证据；缺失时排除而非用零值 |
| 并行工作树包含尚未提交的运行时、LLM、Inbox 和前端变更 | 过期风险 | `git status --short --untracked-files=all` | 校验以当前工作树为事实；报告前重算目标哈希，且不把 Git HEAD 当成当前实现全部内容 |
| 评测失败是否全部创建 Inbox 问题可能造成重复/噪声 | 风险 | 根规则规定系统问题写入规范，但未定义评测去重 | 目标需规定确定失败、幂等/去重键、重跑关联和非确定性/基础设施失败的处理，避免重复问题 |

## 7. 执行命令

- `Get-Content ... SKILL.md / command-calling-spec.md / skill-orchestrator-pattern.md / state-contract.md / spec-requirements.md / spec-independent-validator.md / independent-validation-gate.md / asset-discovery.md / ears-format.md / requirements-review-gate.md / discovery/report 模板` → 全部成功读取
- `Get-Content ... AGENTS.md / README.md` → 成功读取当前项目规则与仓库地图
- `ConvertFrom-Json spec.json` 后仅投影安全元数据、原始 `description` 和状态字段 → 成功；未读取任何目标自动摘要字段
- `git rev-parse --verify HEAD` → `82bab37a5514f8a6f4d632872010293a910c2bec`
- `git status --short --untracked-files=all` → 工作树非干净，包含大量并行修改/未跟踪文件
- `rg -n ... src/taichu/application/evaluations ... tests ... pico-v3/...` 与逐文件行号读取 → 确认 29 个生产 Profile、8-case 旧评测、当前脚本桩缺口、五层记忆、Inbox 规范、真实模型身份/fallback 与 Pico benchmark 机制
- Graphify → 未调用

> 本文件已落盘；从此刻起才允许独立校验 Agent 计算并读取目标 `requirements.md`。
