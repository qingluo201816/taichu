# 通用写作智能体 37 类 Benchmark 落实实现报告

## 文档信息

- 规格：`1.1/通用写作智能体37类Benchmark落实`
- 实现范围：任务 1.1—11.4
- Git/工作树基线：共享脏工作树，无独立提交；本规格以 Suite 哈希、Runtime 代码快照哈希、活动冻结工件及 `tasks-status.json` 为可复现基线，不把无关用户改动归入本实现
- 完成时间：2026-07-31

## 1. 完成任务

| 任务组 | 需求 | 结果 | 状态证据 |
|---|---|---|---|
| 1—2 | 1、2、7、10、14 | 建立 Suite@2、37 条正式清单、typed assertion/Oracle、六类门禁与负例 | `tasks-status.json`；后端聚焦回归 |
| 3—4 | 3、4、5、6、11 | 接通 CapabilityResult、父生命周期、Fixture 隔离、协作与持久化案例 | 逐案 Synthetic 结果与资源后态证据 |
| 5—6 | 7、8 | 接通四类运行记忆和八类恢复故障注入 | 恢复/记忆专项测试与完整套件 |
| 7 | 9 | 接通八类上下文压力和 AssemblyTrace | 压力 Harness、行为结果、长请求与安全拒绝测试 |
| 8 | 12 | 建立当前 37、历史 37、历史 23 的不可变冻结与 Hydration | 活动目录和 Hydration `available` |
| 9 | 13 | API 严格选择、中文详情、前端动态 37/21/23 | API 集成测试、前端专项测试、固定端口页面验收 |
| 10 | 14 | 清理旧活动案例、弱 Gate、当前 23 常量和旧评测入口 | banned-ID、源码扫描、历史只读回归 |
| 11 | 全部 | 后端/前端回归、启动、固定端口、冻结和文档联动 | 471 passed；测试/Lint/Build；`start.bat`；37/37 工件 |

## 2. 实际改动

| 区域 | 新增/修改/删除 | 职责与行为 | 关联任务 |
|---|---|---|---|
| `tests/fixtures/evaluations/general_writing_agent_benchmark/` | 新增/修改 | 37 条权威 Suite、ClaimCatalog、密封 Fixture、恢复与压力计划 | 1—7 |
| `src/taichu/application/evaluations/general_agent_benchmark/` | 新增 | 模型、加载器、选择器、观察、Oracle、Gate、生命周期、工件与查询服务 | 1—10 |
| `src/taichu/infrastructure/evaluations/general_agent_benchmark/` | 新增 | 生产 Runtime 组合、隔离环境、恢复/压力 Harness、冻结与 Hydration | 3—10 |
| `src/taichu/application/general_agent/` | 修改 | 通用故障点、能力结果复用、恢复、上下文证据和父生命周期边界 | 3—7 |
| `src/taichu/api/routes/general_agent_benchmarks.py` 等 | 新增/修改 | Suite/Run/Case/Evidence/Artifact API 与严格 422 选择错误 | 9 |
| `web/src/components/agent-task-monitor/general-agent-evaluation-shell.tsx` 等 | 修改/新增 | 当前 37、Live 21、历史 23/37 的中文动态显示和历史隔离 | 9—10 |
| `scripts/run_general_agent_synthetic_baseline.py` 等 | 新增 | 双隔离稳定运行、Synthetic 冻结、Live 资格与模型比较入口 | 8、11 |
| 旧 `general_agent_evaluations` 后端/前端/Fixture | 删除 | 移除被 Suite@2 替代的旧活动评测实现 | 10 |
| `docs/历史/7-31通用写作智能体37类Benchmark落实报告.md` | 新增 | 保存实现、身份、验证和限制的历史快照 | 11 |
| `README.md`、已讨论功能决策 | 修改 | 更新当前入口与 37 条决策口径 | 11 |

## 3. TDD 证据

| 任务组 | RED | GREEN | REFACTOR | VERIFY |
|---|---|---|---|---|
| Suite/Oracle/Gate | 缺 37 清单、typed 观察和真实逐案断言的测试先失败 | 增加严格模型、Oracle 和 Gate | 删除弱代理与默认通过 | 正反例和完整 37 |
| 能力结果/恢复 | 中断后重复调用、损坏 Checkpoint、父清理等负例先失败 | 增加 CapabilityResult、Fault Hook、恢复决定 | 生产 Hook 与 case ID 解耦 | 八恢复案例与并发/损坏测试 |
| 上下文 | 长历史、工作记忆、大结果、无效记忆等压力负例先失败 | 增加 Pressure Harness 和 AssemblyTrace | 统一载体投影和安全拒绝 | 八压力案例 |
| API/UI | 37/21/23、非法选择、partial/invalid 显示测试先失败 | 增加详情、严格选择和动态显示 | 删除当前 23 默认值和内部 ID | API 集成、前端专项、浏览器 |
| 冻结 | partial、缺 Gate、身份漂移、双运行漂移先失败 | 增加 @2 冻结目录与原子指针 | 历史 @1/@2 独立 Hydration | 正式双运行 37/37 |

实现期间第 36 条暴露“名称为长当前请求、真实输入却是短句”的 RED 缺口。最终由权威 Suite 显式声明确定性展开合同，加载后原文为 20,038 字符，并新增长度、空白、关键事实和行为完成测试。

## 4. 需求与设计追踪

| 需求范围 | 设计组件/契约 | 实现位置 | 测试证据 |
|---|---|---|---|
| 1—2 | Suite@2、严格 Union、选择与六 Gate | `suite_loader.py`、`selection.py`、`oracles.py`、`gates.py` | Suite/selector/oracle/gate 单元与集成测试 |
| 3—6 | CapabilityResult、隔离、协作、持久化、记忆、恢复 | `executor.py`、`synthetic_environment.py`、`synthetic_recovery_harness.py` | 1—29 案例与 Runtime 回归 |
| 7—9 | 证据闭环、上下文压力、安全拒绝 | `observations.py`、`pressure.py`、`pressure_harness.py` | 30—37 案例与压力测试 |
| 10—12 | 六门禁语义、冻结身份与历史 | `suite_artifact_builder.py`、`synthetic_baseline.py`、`artifact_hydration.py` | Gate 负例、冻结、Hydration |
| 13—14 | API/UI、中文、清理、历史兼容 | API schemas/routes/services、Web client/view/shell | API 集成、前端专项、源码扫描、固定端口 |

完整数字需求映射保存在 `requirements.md`、`design.md` 和 `tasks.md`，测试名称按任务编号与合同语义组织。

## 5. 旧实现清理

- 删除旧 `general_agent_evaluations` API、Schema、Repository、服务和前端类型/视图入口。
- 删除旧 `general_writing_assistant_core` Fixture 和旧生产评测 JSON。
- 活动 Suite 不含 `external_access_denied` 和旧 `runtime_checkpoint_recovery`；加载器保留 banned-ID 拒绝测试。
- 删除 Synthetic/Live 中 `security_ok=True`、交互存在即产物、空证据、统一完成态和普通案例默认机制通过路径。
- 删除活动代码、API、冻结器和前端中的当前 23/23 常量；23 只存在于历史只读适配与历史工件。
- 保留共享工作树中与本规格无关的用户改动，不执行 reset/checkout。
- 仓库根仍可见若干本次调试生成的未跟踪 `.pytest-tmp-*`/`.tmp-*` 目录；已尝试按验证后的精确工作区路径清理，但执行环境阻止递归删除。它们不在运行、构建、索引、冻结或文档入口中，不属于交付物。

## 6. 与设计的偏差

| 偏差 | 原因 | 影响 | 是否需要回到设计 |
|---|---|---|---|
| 第 36 条用紧凑声明在加载时确定性展开长请求 | 避免在 Suite JSON 重复保存 20,000 字符，同时保证 Runtime 使用同一真实原文 | Suite 内容哈希包含展开指令；加载后请求、快照和 Oracle 身份一致 | 否 |
| 首次最终冻结被第 28 条一次规范化漂移阻断 | 双运行门禁按设计失败关闭；随后独立复现和完整重跑稳定 | 未切换错误活动指针；最终工件来自稳定双运行 | 否 |

## 7. 自动验证

| 命令 | 退出码 | 结果摘要 | 覆盖范围 |
|---|---:|---|---|
| 后端 Benchmark 聚焦与相邻回归 | 0 | 471 passed | 37 合同、负例、Runtime、API、Hydration |
| `npm run test:general-agent` | 0 | 四组专项测试通过 | 显示、监控、记忆追踪、评测客户端 |
| `npm run lint` | 0 | 无错误 | Web 全量 ESLint |
| `npm run build` | 0 | 20 个静态页面构建成功 | Next.js 严格类型与生产构建 |
| `uv run python scripts/run_general_agent_synthetic_baseline.py` | 0 | 37/37 冻结 | 双隔离稳定性、六 Gate、证据和身份 |
| `state.py validate` | 0 | 状态与磁盘产物一致 | SDD 状态 |

## 8. 启动与页面验证

- 是否触发 `start.bat` 联动：是，生产组合根 `src/taichu/main.py` 有修改。
- 启动验证：根目录 `start.bat` 非交互执行两次均成功。
- 前端固定端口：`http://localhost:3000` — 当前 37/37、37 条中文详情、历史 23 自身内容均已浏览器验证。
- 后端固定端口：`http://127.0.0.1:8000` — 当前 37 条活动基线、历史基线、非法选择 422/零副作用及第 37 条真实安全失败证据已验证。

## 9. 手动验收

1. 打开 `/task-monitor/general-agent/evaluation`，首屏应显示当前 `37/37 Benchmark 全部通过`。
2. 点击“查看评测明细”，固定基准应为 37 例，当前运行案例为中文名称、摘要和通过状态。
3. 切换到第 1 次历史评测，应显示其自身 23 条及历史中文摘要，不出现当前恢复/上下文案例。
4. 通过 API 提交 Live 轨道的第 36 条，应返回 422，运行总数不变。

## 10. 冻结身份与限制

- Suite：`145c40a5b69ca64385dab0ffaa015b23669475d10d71f5590417687511b8e508`
- Runtime 代码快照：`2507e854157f7a39a6046483dc902d71d96403490e3dd558c5184a4d60fd647f`
- 活动工件：`runs/synthetic_baseline_28a233df10c59e1e488637b3d9483805.json`
- 活动工件内容哈希：`812a83059d2c044866128a7bbac577fb4d329c9c32c25b7219259d2a968388f3`
- 工件清单哈希：`9447faa1db35510cc699a855010fde0945871286c15beacbb9e6bd5a3fe7cd2e`
- 活动结果：37 passed、0 failed、0 invalid、0 unfinished
- Hydration：当前 37、历史 37、历史 23，状态 `available`，问题为空
- Live Provider：只有前 21 条具备资格；本实现未宣称一次真实模型运行已经 21/21。
- 第 2—6 条仍是检索/RAG 占坑合同。

> 本报告不作最终 PASS 判定；最终结论由独立实现验证报告给出。

## 11. 首轮独立验证 FAIL 的闭环

首轮独立实现验证指出两个 Major：第 37 条没有穿过生产 Runtime 的真实安全失败路径，且缺少独立浏览器验收。闭环后：

- 生产 Runtime 在上下文无法安全组装时于规划前失败，保存结构化 `unsafe_context` 证据，状态为失败、不可恢复；
- Synthetic 仅在生产运行同时满足无计划、零节点、零交互、零 CapabilityResult、零 Effect 时映射为合同层 `safe_failure`；
- 冻结工件的第 37 条包含 `runtime_failure`，显示层只有在该证据完整时才接受零规范化动作；
- 合同哈希改为直接规范化模型，消除集合转 JSON 后的跨进程顺序漂移；
- 恢复规范化不再把具体 Checkpoint 修订号当作稳定结果，仍在底层证据保留真实修订号；
- 运行列表按活动/创建新鲜度展示，不再被哈希尾缀排序误导；
- 连续两次正式冻结复用同一活动工件，`start.bat` 固定端口启动成功；
- 浏览器已独立验证当前 37/37 首屏、第 37 条三层证据和历史 23 条视图；
- 前端专项测试、ESLint、生产构建均通过；最终后端聚焦回归为 471 passed。
