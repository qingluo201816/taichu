# 独立校验报告

规格：`1.1/通用写作智能体37类Benchmark落实`

模式：`design`

校验时间：`2026-07-30T15:04:14Z`

目标对象：`.sdd/specs/1.1/通用写作智能体37类Benchmark落实/design.md`

目标 SHA-256：`9f017598ade1a761ca89d5582f29890373956f98b8a5b0fdb941ddda9ac3db30`

discovery：`.sdd/specs/1.1/通用写作智能体37类Benchmark落实/validation-discovery-design.md`

discovery SHA-256：`015038b68d8a26cc27629ae9dad0695064d9a273026de02ed3bbd5bbd51d1bbe`

research：`.sdd/specs/1.1/通用写作智能体37类Benchmark落实/research.md`

research SHA-256：`b57b3d4a72c814dd18ea093732357d64b127c9683b6ca27a26280f827ba154`

Git/工作树基线：分支 `master`，HEAD `82bab37a5514f8a6f4d632872010293a910c2bec`；校验开始时工作树非干净，存在 112 个 tracked 变更及大量未跟踪运行/临时产物。当前全局删除扩展属于工作树既有未校验内容，不作为本报告的设计事实或通过证据。本独立校验只写入 discovery 与本报告。

## 结论摘要

目标设计已覆盖独立发现形成的实现约束，尤其完整落实本轮三个定向修复：

1. `ApprovedSuiteContract` 被限定为 `suite_loader.py` 内、仅供 loader 使用的最小先验锚，精确锁定 37 个 ID、中文名、顺序与轨道；即使攻击者同步重算 suite 自身哈希，篡改仍会在任何 workspace、provider 或案例执行前被拒绝。完整运行合同仍只属于 `suite.json`，未形成第二个运行目录。
2. 设计已排除七仓储全局删除清单、跨仓储删除状态机、额外 `WORKSPACE` scope、永久删除审计和应用启动恢复，只保留 CapabilityResult 随既有 conversation/run 父生命周期按 owner 清理，以及 `FixtureIsolationController` 对逐案密封工作区的受信销毁。
3. 第 37 案明确以生产 `GeneralAgentRunStatus.FAILED`、`resumable=false` 和 `ContextAssemblyError(reason_code=unsafe_context)` 终止；仅该“规划前、零 Tool/Subagent/CapabilityResult/Effect”的组合可窄映射为 Benchmark `safe_failure/unsafe_context/stop`，其他生产 `FAILED` 均不得映射为 `safe_failure`。

未发现 critical、major、事实错误、规则冲突、虚构现有对象或阻塞实现的不可验证合同。设计具备进入任务拆分的条件。

## 独立发现范围与方法

阶段一严格未读取 `design.md`、`research.md` 或既有设计校验报告。先读取根与适用项目规则、独立校验门禁、状态契约、命令定义、`spec.json` 允许字段、已独立通过的 `requirements.md` 及其 PASS 报告，再直接核查当前源码、测试、配置和启动约束；发现结果先写入并校验非空，之后才进入阶段二。

阶段一覆盖：

- Suite loader、37 条规范清单、轨道校验及现有测试；
- CapabilityResult owner、持久化、父生命周期和工作区清理边界；
- 当前工作树中的全局删除清单、七仓储协议、启动恢复扩展；
- ContextAssembler、`ContextAssemblyError`、生产 Run 状态及 Benchmark pressure/terminal 投影；
- fixture 隔离、API、前端动态计数、不可变工件与固定端口约束。

项目规则明确禁用 Graphify，本轮未读取或使用 `graphify-out/`，全部事实来自当前源码、测试、配置与 `rg`。

阶段二完整读取并对比 `design.md` 与 `research.md`。目标在阶段二开始前和报告写入前的 SHA-256 均为 `9f017598ade1a761ca89d5582f29890373956f98b8a5b0fdb941ddda9ac3db30`，对象未发生变化。

## 匹配项

| # | 独立发现/上游约束 | 设计处理 | 证据 |
|---:|---|---|---|
| 1 | suite 自哈希不能独立证明“仍是批准的 37 条” | 在 loader 内保留最小 `ApprovedSuiteContract`，逐项锁定 ordinal、ID、中文名、轨道 | `design.md:229-283`；当前锚基础见 `suite_loader.py:32-83,473-505,622-650` |
| 2 | 先验锚不得成为第二个活动目录 | Selector、runner、catalog、API、UI、Oracle 只能消费验证后的 Suite；场景和执行合同只在 `suite.json` | `design.md:273-283` |
| 3 | 必须覆盖“篡改后重算 self-hash”而非只测 hash 不一致 | 分别篡改 ID、中文名、顺序、Synthetic/Live 轨道并重算自哈希，仍要求前置拒绝和零执行 | `design.md:884-910` |
| 4 | CapabilityResult 所有权必须是 conversation + run，不能按 run 扫描猜测 | 定义 `CapabilityResultOwner`、稳定路径、per-result record/index 与 owner-aware `delete_run` | `design.md:482-571`；现有边界见 `general_agent_capability_results.py:57-62,195-223`、`capability_result_repository.py:57-87,185-197,333-370` |
| 5 | 本规格不应扩展为七仓储全局删除产品 | 明确排除全局删除协议、删除持久层、跨仓储状态机、永久审计和启动恢复 | `design.md:41-58,573-579,895-901,961` |
| 6 | 只允许父生命周期与逐案密封销毁两条清理边界 | conversation/run 删除入口冻结并验证 owner 后清理 CapabilityResult；case 数据库和 workspace 由 `FixtureIsolationController` 精确销毁 | `design.md:573-579,930-931`；现有 fixture 边界见 `fixture_manager.py:50-150` |
| 7 | 当前工作树全局删除扩展不能冒充已授权设计 | 设计明确将其排除在实现依赖、任务拆分和验收证据之外 | `design.md:48-49,579` |
| 8 | 第 37 案必须先形成真实生产终态，再做 Benchmark 投影 | 生产状态固定为 `FAILED,resumable=false`，原因来自 `ContextAssemblyError(reason_code=unsafe_context)`；Observer 再窄映射 | `design.md:664-668,851-867`；现有异常契约见 `context.py:713-780` |
| 9 | 其他普通失败绝不能借用安全失败语义 | 明确规定其他生产 `FAILED` 保持普通失败，并要求负例测试 | `design.md:668,913-920` |
| 10 | 当前 broad catch、artifact 伪造终态需要由真实 Runtime 证据替换 | 文件规划将 `models.py`、`service.py`、Context、Observer、pressure 与 Gate 纳入同一改造和回归路径 | `design.md:149-170,440-452,581-668`；现状见 `service.py:1304-1314`、`pressure.py:1512-1608`、`synthetic_environment.py:432-442` |
| 11 | 需求必须完整追踪且不能只覆盖三项修复 | 设计给出 102/102 追踪、文件归属、错误、回滚、测试、API/UI 和固定端口验收 | `design.md:963-1083` |
| 12 | 触及 `main.py` 必须验证 `start.bat` 与固定端口 | 明确要求验证 `start.bat`、8000/3000、后端热重载和真实 API/UI | `design.md:949-961` |

## 错误项

无。

## 遗漏项

无。独立 discovery 中关于 suite 先验信任、删除边界收敛、CapabilityResult 父生命周期、第 37 案生产终态、其他 `FAILED` 负例、隔离销毁、启动联动和测试门禁的预期项均有明确映射。

## 多余项

无。设计没有把全局七仓储删除、永久删除审计、启动恢复、未定义 `WORKSPACE` scope、移动端适配、视觉重构、SQLite/FTS 或任务专用生产能力纳入实施范围。

## 不可验证或规则冲突

无。

- 未发现虚构为“现有”的 `ApprovedSuiteContract` 符号；设计明确说明当前职责由 `_EXPECTED_CASES` 承担，可在同文件收敛命名。
- 未把计划新增的 CapabilityResult Protocol、Repository、ClaimCatalog、Oracle 或身份类型冒充现有对象。
- 未违反 Markdown/MongoDB 事实源、JSON 中间态、领域层技术无关、动态 DAG、五层名称、桌面交付、uv、固定端口或 Graphify 禁用规则。

## 需求/设计/任务追踪表

| 上游范围 | 设计落点 | 实施/验证落点 | 状态 |
|---|---|---|---|
| 1.1—1.8 Suite 与轨道 | `design.md:204-322` | loader 先验锚、共享 selector、篡改并重算 hash 负例 | 匹配 |
| 2.1—3.4 typed 合同与检索占坑 | `design.md:323-406` | strict union、ClaimCatalog、Normalizer、observation/oracle | 匹配 |
| 4.1—7.6 案例 1—21 | `design.md:407-452` | 行为矩阵、资源后态、授权与记忆载体证据 | 匹配 |
| 8.1—8.11 恢复 | `design.md:480-629` | CapabilityResult owner/index、Effect、Checkpoint、父生命周期 | 匹配 |
| 9.1—9.10 上下文 | `design.md:630-668` | AssemblyTrace、压力对、unsafe_context 真实终态与窄投影 | 匹配 |
| 10.1—11.7 Gate 与密封隔离 | `design.md:323-406,851-878` | 六 Gate、证据完整性、FixtureIsolationController、哨兵 | 匹配 |
| 12.1—12.8 基线与身份 | `design.md:670-758` | ArtifactIdentity、ComparabilityKey、manifest、Hydration | 匹配 |
| 13.1—13.6 API/UI | `design.md:760-849` | suite detail、真实计数、37 当前与 23 历史 | 匹配 |
| 14.1—14.6 破坏式替换与相邻回归 | `design.md:880-961` | 清理弱路径、生命周期边界、回滚、固定端口 | 匹配 |
| 本轮修复 1 | `design.md:229-283,884-910` | loader-only 37 项批准锚与 tamper+rehash 测试 | 匹配 |
| 本轮修复 2 | `design.md:41-58,573-579,930-931,961` | 仅 CapabilityResult 父清理与 case 密封销毁 | 匹配 |
| 本轮修复 3 | `design.md:664-668,866,919` | 生产 FAILED/non-resumable/unsafe_context 与唯一窄映射 | 匹配 |

完整逐 ID 追踪由目标文档第 19 节给出，覆盖结果为 102/102；抽查的关键 ID 与独立 discovery 一致。

## 测试与机械检查

| 检查 | 命令/方法 | 结果 |
|---|---|---|
| 上游需求 PASS/hash | 校验需求报告中的目标 hash、discovery hash、唯一末行及 `spec.json` 状态 | 通过；requirements SHA-256 为 `b3f7dbf57cf7cdc00c75427c030ef3e5244354e6923c5f773326b60aafa18a5a` |
| discovery 落盘门禁 | 文件存在、非空并计算 SHA-256 | 通过；19,573 bytes；SHA-256 为 `015038b68d8a26cc27629ae9dad0695064d9a273026de02ed3bbd5bbd51d1bbe` |
| 目标对象稳定性 | 阶段二开始前及报告写入前分别执行 SHA-256 | 通过；两次均为 `9f017598ade1a761ca89d5582f29890373956f98b8a5b0fdb941ddda9ac3db30` |
| 批准锚表机械解析 | 解析 `design.md` 第 229—283 行表格 | 通过；37 行、37 个唯一 ID、ordinal 1—37 连续、S+L=21、S=16 |
| tamper+rehash 合同 | 检索四类篡改、重算自哈希与执行前拒绝描述 | 通过 |
| 删除边界 | 检索全局删除、启动恢复、scope、父生命周期和 FixtureIsolationController 声明 | 通过；全局方案均为禁止项 |
| 第 37 案窄映射 | 检索生产状态、`unsafe_context`、零调用及其他 `FAILED` 负例 | 通过 |
| 需求追踪 | 机械核对设计矩阵和覆盖声明 | 通过；102/102 |
| Graphify | 按根规则跳过 | 符合项目规则 |

本轮是设计校验，不是实现验证；未运行实现级后端、前端或固定端口测试。目标设计已明确把这些测试设为实现门禁，未以“未运行实现测试”冒充实现通过。

主要可复现命令：

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath ".sdd/specs/1.1/通用写作智能体37类Benchmark落实/design.md"
Get-FileHash -Algorithm SHA256 -LiteralPath ".sdd/specs/1.1/通用写作智能体37类Benchmark落实/validation-discovery-design.md"
rg -n "ApprovedSuiteContract|删除清单|启动恢复|WORKSPACE|unsafe_context|safe_failure|FAILED|FixtureIsolationController" ".sdd/specs/1.1/通用写作智能体37类Benchmark落实/design.md"
rg -n "_EXPECTED_CASES|_EXPECTED_TRACK_CASE_IDS|load_authored_suite" src/taichu/application/evaluations/general_agent_benchmark/suite_loader.py
rg -n "ContextAssemblyError|unsafe_context|GeneralAgentRunStatus.FAILED|resumable" src/taichu/application/general_agent
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
```

## 分级问题

### Critical

0。

### Major

0。

### Minor

0。

### Info

1。

- 当前工作树仍含大量既有变更和未跟踪产物，其中包括本规格明确排除的全局删除扩展。它不是目标设计缺陷，也未用于本轮通过证据；后续实现与实现校验必须按实际任务归属隔离 diff，并证明最终实现不依赖该扩展。

## 修正项（FAIL 时）

不适用；本轮未发现需要退回设计角色修正的阻塞项。

## 门禁理由

- Critical、Major、事实错误、规则冲突和虚构现有对象均为零。
- 三项定向修复均形成了文件归属、状态/数据合同、失败语义和可执行负例。
- 102 个已校验需求均被追踪，核心边界、错误恢复、清理、测试、启动和桌面验收完整。
- 目标对象两次 SHA-256 一致，discovery 已先于目标读取落盘并保留，命令与证据可复现。
- Info 项仅提示后续实现 diff 隔离，不影响设计正确性或可实施性。

结论：PASS
