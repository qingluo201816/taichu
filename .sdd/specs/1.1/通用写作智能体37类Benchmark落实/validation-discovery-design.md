# 设计独立发现

## 文档信息

- 规格：`1.1/通用写作智能体37类Benchmark落实`
- 模式：`design`
- 发现时间（UTC）：`2026-07-30T14:56:53.2211834Z`
- 阶段一目标读取：禁止且未读取、未搜索、未摘要、未计算 `design.md` 哈希；亦未读取旧 design discovery、旧 design validation report 或 `research.md`
- 允许上游：`spec.json` 允许字段、哈希有效且结论为 PASS 的 `requirements.md` 与需求独立报告、根项目规则、当前源码/测试/配置/启动入口
- Git/工作树基线：分支 `master`，HEAD `82bab37a5514f8a6f4d632872010293a910c2bec`；工作树已有 112 个 tracked 变更和大量测试临时产物/未跟踪文件。本轮只允许覆盖本 discovery 与后续独立 design 报告，不把既有改动视为本轮产出。
- Graphify：根规则禁用；未读取或使用 `graphify-out/`、`GRAPH_REPORT.md` 或任何图谱查询结果。

## 1. 上游有效性

| 对象 | 当前 SHA-256 | 状态证据 | 结论 |
|---|---|---|---|
| `requirements.md` | `b3f7dbf57cf7cdc00c75427c030ef3e5244354e6923c5f773326b60aafa18a5a` | `spec.json.validations.requirements.target_sha256` 与实算一致 | 有效 |
| `validation-discovery-requirements.md` | `24ec88d046691882f4f6888db317d841e37d1614ddc6b0230041bccb4f8f8a24` | `spec.json`、需求 PASS 报告与实算一致 | 有效 |
| `independent-validation-report-requirements.md` | `b7e1a78c1377f8be83e23239f58dbd857030cc3b843d0f899bf9a19806e9355c` | 末行精确 `结论：PASS`，目标/discovery 哈希均匹配 | 有效 |

`spec.json` 当前为 `phase=design_ready`、`status=active`，原始描述为“落实推进新的37类benchmark”。本轮只校验设计实现就绪性，不验证 37 条是否已经实现。

## 2. 独立调查范围

本轮按上级任务要求只聚焦三项既定设计修复：

1. 37 条清单的外部先验锚必须能阻止“篡改清单后重算 suite 自哈希”的替换，同时不能形成第二运行目录。
2. Benchmark 夹具销毁与生产父生命周期清理必须职责分离，不能引入全局七仓储 Deletion Manifest、`WORKSPACE` scope 或启动时广域恢复。
3. 第 37 条必须先成为生产 Runtime 的真实不可恢复失败，再由 Benchmark 做窄语义映射；其他普通 `FAILED` 不得被美化为 `safe_failure`。

其余 37 条场景、六门禁、恢复/上下文/页面动态计数只检查设计是否保持需求追踪，不展开为实现验证或大范围回归。

## 3. 项目规则与上游约束

| 事实/约束 | 证据 | 对设计的预期 |
|---|---|---|
| 活动套件必须精确锁定 37 个 ID、中文名、顺序和 S37/L21 轨道，套件身份变化不能冒充旧结果 | `requirements.md:175-189` | 加载前须有不受被加载 `suite.json` 自身控制的最小批准合同；自哈希只证明内容自洽，不能证明内容获批 |
| 运行目录必须来自活动 Suite，能力目录只能从 Suite 与生产能力快照派生 | `requirements.md:171-189,205-207`；`AGENTS.md`“能力目录与运行实例解耦” | 批准合同只在 loader 校验使用；选择、runner、API/UI 和工件继续消费已验证 Suite，不得再读第二份案例目录 |
| 合成案例须逐案密封隔离，异常退出也要证明作者数据及其他案例未变 | `requirements.md:385-397` | 夹具控制器只销毁自己创建并验证归属的案例副本；必须有 `try/finally`、路径归属、Mongo 隔离库和哨兵/快照后态证明 |
| 需求没有授权重做生产 Runtime 全仓储删除协议或新增启动恢复流程 | `requirements.md:81-110,379-397,439-455` | 只补 CapabilityResult 随父 conversation/run 生命周期清理；不得扩为七仓储事务、工作区删除 scope 或全局启动扫描 |
| 第 37 条要求任何能力调用和副作用前拒绝，并保存无法安全组装原因 | `requirements.md:345-351,367-377,498-499` | 生产 Runtime 应持久化 `FAILED + resumable=false + unsafe_context`；Benchmark 只翻译该精确事实为 `safe_failure/unsafe_context/stop` |
| 正确安全失败按案例终态判定，但失败或无效门禁不得被覆盖 | `requirements.md:120,373-377,407-419` | 不能把所有 `FAILED` 统一映射为 `safe_failure`；第 29 条仍由其 Checkpoint 专属证据窄映射 |
| 修改 `src/taichu/main.py` 必须验证 `start.bat` 固定端口启动 | `AGENTS.md`“启动脚本” | 若删除启动恢复/wiring 触及 `main.py`，实现任务必须包含 `start.bat` 与 `127.0.0.1:8000` 验收 |

## 4. 当前源码、测试与配置发现

### 4.1 Suite 批准合同与单一运行目录

| 对象 | 现状 | 证据 | 设计影响 |
|---|---|---|---|
| loader 内 37 条先验 | `suite_loader.py` 当前以 `_EXPECTED_CASES` 锁定 37 个 ID/中文名，并以位置规则锁定 synthetic 全 37、live 前 21 | `src/taichu/application/evaluations/general_agent_benchmark/suite_loader.py:32-83,473-505` | 可收敛为计划新增的 `ApprovedSuiteContract`；必须显式包含 `(id, 中文名, 顺序, tracks)`，且仅供 loader 校验 |
| Suite 自哈希 | loader 先重算 `content_hash`，再做 `_EXPECTED_CASES` 外部校验 | `suite_loader.py:622-650` | 自哈希不能替代批准合同；负例必须篡改 ID/中文名/顺序/轨道并重算自哈希，仍在执行前失败 |
| 运行期能力目录 | `DerivedCapabilityCatalog` 从已加载 Suite 的 `required_invocations` 与生产能力快照确定性派生 | `capability_catalog.py:49-60,126-219` | 这是派生覆盖视图，不是第二案例目录；设计不得让 `ApprovedSuiteContract` 被 selection/runner/API/UI 直接消费 |
| 当前测试 | 集成测试复制了一份 `_EXPECTED_CASES` 并检查 37/S37/L21，但现有片段未形成“篡改后重算 Suite 自哈希仍拒绝”的完整参数化门禁 | `tests/integration/infrastructure/evaluations/test_general_agent_benchmark_suite_v2.py:28-66,69-140` | 需要 loader 级参数化负例；测试期望应从批准合同或单一测试夹具导出，避免第三份漂移清单 |
| `ApprovedSuiteContract` | 当前源码/测试精确搜索零结果 | `rg -n 'ApprovedSuiteContract' src/taichu tests/...` → 0 | 必须在设计中明确标为“新增”，不得称为现有类型 |

### 4.2 删除与夹具隔离边界

| 对象 | 现状 | 证据 | 设计影响 |
|---|---|---|---|
| CapabilityResult owner | 结果以 `conversation_id + run_id` 双层 owner 归属，仓储已有 `delete_run(owner)` | `application/contracts/general_agent_capability_results.py:57-62,195-223` | 只需接入既有父 run/conversation 删除路径，防止孤儿结果；不需要新全局删除状态机 |
| CapabilityResult 物理路径 | 仓储路径为 `<root>/<conversation>/<run>`，删除只移除该 owner 根并有 containment 检查 | `infrastructure/general_agent_runs/capability_result_repository.py:57-87,185-197,333-370` | 设计应复用这一最小边界，并给出 run/conversation 级幂等清理测试 |
| 全局七仓储 Deletion Manifest | 当前工作树存在计划外合同，把 CapabilityResult、Effect、Checkpoint、Context、Replay、Event、Memory 固定成七仓储矩阵 | `application/contracts/general_agent_deletion.py:1-6,31-65,171-226` | 与本规格授权不相称；设计必须明确删除该合同、仓储、导出、注入、测试及所有引用，而非留下“暂不使用”的僵尸代码 |
| Runtime 广域删除/启动恢复 | 当前工作树把七仓储清理注入 Runtime，并提供 `recover_incomplete_deletions()` | `application/general_agent/service.py:114-180,460-559,661-690,987-1012` | 恢复到既有父删除语义，只追加 CapabilityResult 清理；不得保留 Manifest 驱动的启动恢复 |
| 生产启动 wiring | 当前工作树创建并注入 deletion repository，启动时先恢复删除清单，并挂到 `application.state` | `src/taichu/main.py:152-159,313-325,525-542,603-605,640-645` | 全部移除；因触及 `main.py`，实现必须执行启动门禁 |
| FixtureIsolationController | 控制器已能证明 sealed source、创建唯一工作区、记录 owned 路径并阻止越界写 | `fixture_manager.py:50-150` | 这是逐案例销毁的正确所有者，应保留并扩展为 controller 自己的密封销毁 |
| Fixture 清理越界耦合 | 当前工作树要求生产会话级完成态删除清单后才物理删除案例工作区 | `fixture_manager.py:152-220`；`synthetic_environment.py:666-675` | 必须移除与生产 Deletion Manifest 的依赖；案例 `finally` 中由 controller 校验 handle、隔离 Mongo 名称、哨兵/快照和外部作者事实未变后销毁 |
| `WORKSPACE` 删除 scope | 当前目标源码精确搜索未发现该 scope | `rg -n 'WORKSPACE|workspace_scope|scope_type.*workspace' ...` → 0 | 设计不得新增；工作区只是 `FixtureIsolationController` 的内部 owned handle，不进入生产删除协议 |

### 4.3 第 37 条生产终态与窄映射

| 对象 | 现状 | 证据 | 设计影响 |
|---|---|---|---|
| 不安全上下文异常 | `ContextAssemblyError` 已携带稳定 `reason_code=unsafe_context`、预算和受保护内容哈希 | `application/general_agent/context.py:713-731,734-780` | 生产 Runtime 应直接消费该异常，不能让 Benchmark 自己制造生产终态 |
| 生产 Run 模型 | `GeneralAgentRun` 有 `status` 与 `resumable`，当前没有可机器判定的终止原因字段；`FAILED` 是通用状态 | `application/general_agent/models.py:20-33,620-667` | 设计必须定义一个明确且持久化的生产终止原因合同（字段名、类型、默认/迁移、写入点、API/快照影响） |
| 通用异常处理 | 当前 broad catch 把所有异常写成 `FAILED` 且 `resumable=True` | `application/general_agent/service.py:1304-1314` | 在 broad catch 之前增加 `ContextAssemblyError` 专属分支：`FAILED`、`resumable=false`、原因 `unsafe_context`，并保留零能力/零 Effect 证据 |
| Benchmark 自造 safe failure | 当前 pressure artifact 从异常直接构造 `safe_failure/unsafe_context/stop`，SyntheticEnvironment 再覆盖终态 | `application/evaluations/general_agent_benchmark/pressure.py:1512-1608`；`infrastructure/evaluations/general_agent_benchmark/synthetic_environment.py:432-442` | 设计应改为观察已持久化的生产 Run 三元组并窄翻译，不能绕过生产状态 |
| Benchmark 通用 FAILED 映射 | 默认 terminal 观察会让普通 FAILED 保持 `failed`；第 29 条已有 Checkpoint 专属条件覆盖 | `synthetic_environment.py:417-431,1073-1130` | 保留第 29 条专属映射；新增第 37 条映射必须要求精确 `FAILED + false + unsafe_context`，其他 FAILED 继续是 `failed` |
| 当前 Suite 第 37 条合同 | `context_unsafe_compression_refusal` 为 synthetic-only，期望 `safe_failure / false / stop / unsafe_context` 且六门禁齐全 | 解析 `tests/fixtures/evaluations/general_writing_agent_benchmark/suite.json` → `case_count=37`、第 37 条上述终态 | 设计需给出生产态→Benchmark 态映射表和反向负例 |
| 当前测试缺口 | 压力测试验证 artifact 的 safe failure，但没有证明 production Runtime 持久 Run 已形成该三元组 | `tests/unit/application/evaluations/general_agent_benchmark/test_context_pressure.py:1654-1667` | 必须新增生产 Runtime 测试、observer 映射测试和“其他 FAILED 不映射”负例 |

## 5. 独立预期设计清单

| # | 必需设计内容 | 来源 | 严重性 |
|---:|---|---|---|
| E1 | 新增 `ApprovedSuiteContract`（名称可保持任务既定名），精确且一次性定义 37 个 `(ID, 中文名, 顺序, tracks)`；它只由 suite loader 调用 | 需求 1.1—1.8；loader 现状 | critical |
| E2 | 明确验证顺序：解析原始 JSON → 校验 suite 自哈希 → Pydantic 结构校验 → 与批准合同逐字段比对 → 夹具/能力身份校验 → 才返回可执行 Suite | 需求 1.2—1.4、11.2 | major |
| E3 | 参数化测试必须覆盖替换 ID、改中文名、换序、改 S/L 轨道，攻击者重算 `content_hash` 后仍拒绝；旧两个 ID/第 38 条也拒绝 | 需求 1.2—1.7、14.1—14.2 | critical |
| E4 | `ApprovedSuiteContract` 不得暴露给 selection、runner、API、UI、工件或派生能力覆盖；运行期唯一目录仍为“通过 loader 的 Suite” | 项目能力目录规则；需求 2.5—2.6 | critical |
| E5 | 删除全局七仓储 Deletion Manifest 的合同、repository、导出、Runtime 注入/执行、启动恢复、`main.py` state wiring 及专属测试，不留僵尸依赖 | 范围边界；旧实现清理规则 | critical |
| E6 | 禁止新增 `WORKSPACE` scope；CapabilityResult 只随其双层 owner 的 run/conversation 父生命周期幂等清理，其他已有仓储保持既有职责 | CapabilityResult owner 合同；需求 11 | critical |
| E7 | `FixtureIsolationController` 独占逐案例工作区销毁：验证 handle/containment、密封源/作者哨兵、隔离 Mongo 名称与 drop、异常 `finally`，且不依赖生产删除清单 | 需求 11.1—11.7 | critical |
| E8 | 生产 Run 增加可机器判定的终止原因合同及兼容规则；`ContextAssemblyError(unsafe_context)` 专属落盘为 `FAILED/resumable=false/reason=unsafe_context` | 需求 9.8、10.5、12.1 | critical |
| E9 | Benchmark translator 只把 E8 的精确三元组映射为 `safe_failure/unsafe_context/stop`；第 29 条保留 Checkpoint 专属映射；其他 FAILED 保持失败 | 需求 9.8、10.5、10.9—10.10 | critical |
| E10 | 证明第 37 条在 planning/Tool/Subagent/Effect 前停止，生产状态、上下文拒绝证据、零调用和六门禁引用形成同一身份链 | 需求 9.8—9.10、第 6 节第 37 行 | major |
| E11 | 文件计划须区分新增/修改/删除，并列出 deletion 合同残留搜索、`ApprovedSuiteContract` 非消费者搜索、FAILED 映射负例和启动门禁 | 独立设计门禁；AGENTS.md | major |
| E12 | 不新增依赖、不改数据库事实源、不引入移动端/视觉重构；UI 只继续消费动态 Suite/Run 计数 | 范围外与项目规则 | major |

## 6. 建议责任边界与依赖方向

```text
suite.json（作者态、带自哈希）
  → suite_loader + ApprovedSuiteContract（唯一批准门）
  → AuthoredSuiteSpec（唯一运行目录）
  → selection / synthetic runner / live runner / API / UI / DerivedCapabilityCatalog

生产 ContextAssembler
  → ContextAssemblyError(reason=unsafe_context)
  → GeneralAgentRuntimeService 专属失败分支
  → 持久 GeneralAgentRun(FAILED, false, unsafe_context)
  → Benchmark terminal translator（精确三元组窄映射）
  → ObservedTerminalState(safe_failure, unsafe_context, false) + recovery_action=stop

CapabilityResult(owner=conversation_id/run_id)
  → 既有父 run/conversation 删除路径追加 delete_run(owner)

FixtureIsolationController
  → 创建/验证/销毁单案例文件工作区与隔离 Mongo
  → 不依赖生产 Deletion Manifest，不进入启动恢复
```

允许依赖方向：

- application loader 可依赖应用层模型和纯值批准合同；
- infrastructure runner 消费已验证 Suite 与 production Runtime；
- benchmark translator 可读取生产 Run 的公开持久契约，但生产 Runtime 不依赖 Benchmark；
- fixture controller 是评测基础设施内部控制面，不向生产 Runtime 注入工作区 scope；
- domain 不依赖 Benchmark、Runtime、LangGraph 或存储技术。

## 7. 必需测试与机械检查候选

| 检查 | 最小断言 |
|---|---|
| loader 批准合同参数化负例 | 篡改 ID/中文名/顺序/轨道并重算 suite 自哈希仍在案例启动前失败 |
| 单一目录静态检查 | 除 loader/其测试外无 `ApprovedSuiteContract` 消费；无第二份运行案例顺序常量 |
| 删除清理静态检查 | `GeneralAgentDeletionManifest`、`JsonGeneralAgentDeletionManifestRepository`、七仓储枚举、`recover_incomplete_deletions`、`WORKSPACE` scope 搜索为零 |
| CapabilityResult 父生命周期 | run 删除只清理目标 owner；conversation 删除清理所属 owners；重复删除幂等；其他 conversation/run 不变 |
| Fixture 销毁 | 正常、案例异常、Mongo drop 异常、路径逃逸、非 owned handle；作者哨兵和其他案例不变 |
| 生产 unsafe_context | 持久 Run 精确为 `FAILED/false/unsafe_context`，没有 Tool/Subagent/Effect/可复用 CapabilityResult |
| translator 正例 | 仅精确三元组映射 `safe_failure/unsafe_context/stop` |
| translator 负例 | `FAILED/true/*`、`FAILED/false/other_reason` 不得映射为 `safe_failure`；第 29 条只走 Checkpoint 专属映射 |
| 第 37 条六门禁 | 预算、校验、产物、停止原因、安全、证据均引用真实生产状态和零调用证据 |
| 启动门禁 | 因修改 `src/taichu/main.py`，运行 `start.bat`，复用固定端口并用 `http://127.0.0.1:8000` 验证新 wiring |

## 8. 风险、歧义与未知

| 项目 | 类型 | 证据 | 校验设计时处理 |
|---|---|---|---|
| 当前工作树已出现大量目标相关未跟踪/修改代码 | 风险 | Git 基线；删除合同、fixture manager 等为未跟踪，service/main 为修改 | 设计必须把它们作为当前现实并给出明确清理文件表，不能因未提交而忽略 |
| 生产 Run 当前缺少稳定终止原因字段 | 设计缺口 | `models.py:620-667` | 设计必须给出字段/类型/迁移/API/序列化契约；仅写“记录原因”不可实施 |
| 第 29 与第 37 都使用 Benchmark `safe_failure` | 映射风险 | Suite 解析结果；`synthetic_environment.py:417-442` | 分别用 Checkpoint 证据和 unsafe_context 三元组窄映射，禁止统一 `FAILED → safe_failure` |
| 删除失败后的夹具清理策略 | 设计选择 | 需求要求异常退出也证明隔离，当前实现遇删除失败保留工作区 | 设计须区分“销毁失败留审计并判 INVALID”与“跨边界继续删除”；不得转成生产启动恢复 |
| `ApprovedSuiteContract` 与测试期望重复 | 漂移风险 | loader/test 当前各有 `_EXPECTED_CASES` | 设计须说明测试如何复用批准合同或生成单一参数表，避免第三运行目录 |
| 外部依赖 | 已知 | 相关实现均使用 stdlib/Pydantic/现有 pytest | 不需要网络检索或新增依赖；不触发 `pyproject.toml` 变更 |

## 9. 执行命令与结果

- `Get-FileHash requirements.md / validation-discovery-requirements.md / independent-validation-report-requirements.md` → 三个哈希与 `spec.json` 及 PASS 报告完全一致。
- 完整读取 `requirements.md`（562 行）与需求 PASS 报告 → 上游有效。
- `rg --files ...general_agent_benchmark...` 与针对性 `rg -n` → 确认 loader、派生能力目录、CapabilityResult、删除 Manifest、fixture controller、ContextAssemblyError、Runtime 终态和 translator 的真实符号与引用。
- `rg -n 'ApprovedSuiteContract|FixtureIsolationController' ...` → `ApprovedSuiteContract` 0 个结果；`FixtureIsolationController` 为现有评测基础设施对象。
- `rg -n 'WORKSPACE|workspace_scope|scope_type.*workspace' ...` → 0 个目标源码结果。
- 解析当前 `suite.json` → 37 条；第 29 条为 `safe_failure/false/checkpoint_invalid/stop`，第 37 条为 `safe_failure/false/unsafe_context/stop`。
- `git rev-parse --abbrev-ref HEAD`、`git rev-parse HEAD`、`git status --porcelain` → `master@82bab37a...`，工作树非干净。

> 本 discovery 已在目标设计首次读取前落盘。后续只能在确认本文件存在且非空后进入 Phase 2。
