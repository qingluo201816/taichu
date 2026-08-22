# 独立设计发现

规格：`1.1/通用写作智能体评测体系重构`
模式：`design`
发现时间（UTC）：`2026-07-27T06:29:24Z`
Git 基线：`82bab37a5514f8a6f4d632872010293a910c2bec`；工作树在校验前已有大量用户改动与未跟踪文件，本轮只写本规格目录内允许的 discovery 与独立校验报告。

## 阶段边界与方法

- 本文件落盘前未读取、搜索、摘要或接收 `design.md`、`research.md`、`design-review-report.md`、旧设计校验报告的任何内容。
- 允许上游包括：根与局部规则、`spec.json` 元数据/原始描述/状态、已锁定并独立 PASS 的 `requirements.md` 及其 discovery/PASS 报告、`gap-analysis.md`、源码、测试、配置、依赖和启动脚本。
- Graphify 依据根 `AGENTS.md` 的暂停规则禁用；未读取或使用任何 Graphify 派生物。
- 主要机械检查：`rg --files`、`rg -n`、PowerShell `Get-Content`/`Get-FileHash`、直接源码阅读、`.venv\Scripts\python.exe -m pytest`。

## 上游对象与哈希

| 对象 | SHA-256 | 结论 |
|---|---|---|
| `spec.json` | `cdb45bc1bdf5e9799b9be07707ffa683611dc7539566fb2abf34f6204524ab71` | 元数据与原始描述可读 |
| `requirements.md` | `b5b65cf351b58c6ff72bfc6f76f1d9c3b10470ebc01875670571957fe14a1cf2` | 与锁定哈希一致 |
| `validation-discovery-requirements.md` | `1fec9a39dc15199b242ae095ce157c24ff60f5e397431ac377a529148f6bca82` | 已读取 |
| `independent-validation-report-requirements.md` | `5a963c09cf5266874e77b70c274ba7a07890960f7bbb379410d17120d3a5212f` | 结论 PASS |
| `gap-analysis.md` | `b347d8ef29dde59e7e0383243a9799a88b378a79caf9da3340f7568517661034` | 仅作允许上游，不替代源码 |

## 独立发现的真实现状

### 1. 能力目录与旧评测边界

- `src/taichu/infrastructure/plugins/discovery.py` 与 `tests/unit/infrastructure/test_plugin_discovery.py` 的生产发现集合为 17 个 Tool、12 个 Subagent。
- `src/taichu/application/evaluations/capability_profiles.py` 的 `CAPABILITY_PROFILES` 为 29 项；`tests/unit/application/evaluations/test_capability_profiles.py` 机械断言其与生产发现集合完全相等。
- 当前旧固定集 `tests/fixtures/evaluations/general_agent/manifest.json` 只有 8 个 case；“23 case”是本规格待建并须机械验收的目标，不是现状事实。
- 旧实现集中于 `src/taichu/application/evaluations/general_agent/`、对应 contract/repository/schema/route、旧 fixture、前端 API/types/view/shell/test 与 `project_assets/generated/agent_evaluations/general_eval/`。旧模型 `GeneralAgentEvaluationDimension` 只有五维加权总分，`GeneralAgentEvaluationRecord` 只描述对既有运行的事后评测，无法表达脚本步骤、硬门禁、尝试、证据包和可比性。

### 2. Runtime 审计与隔离执行

- `src/taichu/application/general_agent/runtime.py` 的 `GeneralAgentRuntimeService.start` 创建并返回带 `run_id` 的运行，不包含评测关联字段。
- 运行审计由独立 Protocol/仓储承载：`GeneralAgentRunRepository`、`InvocationTraceReader`、`GeneralAgentContextSnapshotRepository`、`LLMCallReplayRepository`、`LLMUsageRepository`、`GeneralAgentEffectRepository` 以及 LangGraph checkpoint saver。
- 现有链路已经具备 `conversation_id`、`run_id`、`thread_id`、`node_id`、`plan_revision`、`attempt_id`、`effect_id`、`call_id`、`parent_call_id`、`context_snapshot_id` 等稳定标识。设计不得向这些 Runtime 审计记录、模型或写入生命周期增加评测字段。
- 评测应自行持久化 `suite/run/case/attempt -> runtime_run_id` 关联，只通过窄只读 Protocol/适配器获取审计；内存事件中心只能辅助观察，不能作为耐久关联事实源。
- 为避免污染作者唯一小说上下文，评测必须复用同一 Runtime 业务逻辑但使用隔离组合根、密封 fixture 的逐 case 干净副本及评测专用存储/记忆/checkpoint/审计依赖，不能调用会写入活动工作区的生产组合。

### 3. 四态工作记忆与复用门禁

- `src/taichu/domain/models/agent_memory.py` 的 `AgentMemoryValidity` 包含 `ACTIVE`、`STALE`、`REJECTED`、`SUPERSEDED`。
- 依赖传播中 `BASIS`、`REVIEW_TARGET` 会传播失效，`REPAIR_SOURCE` 不传播；`AgentMemoryService.list_invalidated` 默认只取 `REJECTED`、`STALE`，遗漏了 `SUPERSEDED` 的修复投影。
- `src/taichu/application/general_agent/context.py` 会刷新失效、仅选择 active 记忆，并对 node summary 生产者有效性做过滤，再生成摘要/指纹/上下文快照。
- orchestrator/executor 的 `reuse_from_node_id` 当前只校验成功节点和能力一致，没有校验生产者记忆仍为 `ACTIVE`。
- 设计必须把缺口修复落在生产应用层：完整四态修复投影、统一生产者有效性查询、编排与执行复用双门禁，并以来源指纹、两类传播/不传播、替代、并行隔离、node summary/digest/context snapshot/reuse 组成专门硬门禁；不能只在评测替身中绕过。

### 4. Inbox 确定性闭环

- `src/taichu/domain/models/mvp.py` 的 `MVPInboxIssue` 当前无机器修订号、评测链接和操作意图。
- `src/taichu/presentation/api/routes/mvp.py` 只有列表、创建、PATCH，无按 ID 精确读取。
- `MVPInboxService.create_issue` 接受外部 ID 但未确保唯一/幂等；PATCH 在存储锁外读取，再整体重写。
- `ProjectAssetStorageBackend` 只有单实例线程锁和临时文件原子替换，未给读改写事务或 CAS，仍可能丢失更新。
- 设计需要评测侧耐久 `IssueOperationIntent`，包含确定性 intent/issue ID、期望 revision、完整目标状态、双向链接和状态；Inbox issue 增加机器一致性 revision/结构化评测链接，同时严格保留八字段中文 content 格式。
- 写路径必须提供同一锁域内的原子读改写、CAS 冲突语义、幂等创建、精确按 ID 读取、单协调者租约、写后读回，以及处理超时不确定性的启动/按需 reconciler；追加与 PATCH 均须达到双向链接收敛。

### 5. 模型、实跑与可比性

- `.env.example` 和 `src/taichu/config.py` 的默认模型为 `deepseek-v4-pro`。
- `LLMGatewayContract` 只有完成、流式和列模型；具体 `RightCodeLLMGateway` 另有 `probe_model`。应用设计应定义窄的目录/探测/只读证据 Protocol，不能依赖具体网关。
- replay/usage 已记录模型、provider、fallback、upstream、状态、tokens、cost kind/error；成本可能不可用。
- DeepSeek 首轮完整真跑只能在合成与核心门禁通过后开始；每轮必须冻结 fixture、脚本、能力快照、模型身份和预算。探测/回放/fallback/成本证据不全应标为“不具可比性”，不能降格为能力失败或参与排名。

### 6. Pico 参照与反例

- Pico 的可取原则包括固定 benchmark 校验、fixture 内容哈希、每任务全新副本、独立运行目录、多条件通过、失败分类和 artifact 聚合。
- 不得照搬的缺陷包括按 fixture 名硬编码 artifact 路径、verifier 内执行被测 subprocess，以及 HarnessBench 依赖 latest/mtime 寻址。太初脚本、执行和验证必须分离，所有证据通过稳定 ID/manifest 显式索引。

### 7. API、前端、资料和启动联动

- 既有路由 `/task-monitor/general-agent/evaluation`、导航入口和中文标签应保持；页面入口应继续薄化到 feature shell。
- 可复用前端资产包括 button、checkbox、compact-pagination、card、motion primitives 与现有 `lucide-react`；不得新增依赖或并行组件体系。
- UI 只验收桌面浏览器，遵循 `DESIGN.md` 的午夜极光控制台、高密度、中文、结论先行、少卡片嵌套、少分隔线；排名只有在硬门禁和可比性成立后显示。
- 密封基准 fixture 属于 `tests/fixtures/evaluations/`；派生评测审计属于 `project_assets/generated/agent_evaluations/`，都不能成为 Markdown/MongoDB 主事实源。目录职责变化须同步 `project_assets/readme.md`。
- 若改动 `src/taichu/main.py`、`config.py` 或 `web/package.json` 等启动关键文件，必须验证根 `start.bat`；真实验收固定使用 `127.0.0.1:8000` 与 `localhost:3000`。

## 应有设计清单

1. 冻结契约：能力快照、fixture/script/verifier/hash、精确 23-case 矩阵，并机械证明 17 Tool、12 Subagent 无遗漏、无未知、每 case 有硬门禁。
2. 评测领域/应用边界：suite/run/case/attempt/step、状态机、幂等键、重试/取消/恢复、artifact manifest、失败类别、硬门禁、可比性与聚合。
3. 密封 fixture 与隔离 Runtime 组合根；脚本执行器与 verifier 分离，禁止活动工作区写入与 newest/mtime 寻址。
4. Runtime 审计零修改；评测侧耐久关联、事件观察和只读 audit bundle adapter。
5. 四态记忆生产修复与专门回归门禁。
6. DeepSeek 优先闭环、冻结迭代、模型目录/探测契约、调用链证据和不可比条件。
7. Inbox intent/revision/CAS/409/租约/读回/reconciler/双向链接闭环。
8. 比较门禁、无效运行排除、证据充分后才计算聚合和排名。
9. API/UI 维持既有入口并提供运行、恢复、证据、失败定位和比较视图。
10. 新路径通过后，同一实现内删除全部旧评测代码、依赖、配置、入口、测试、fixture 与派生产物；更新资料地图。
11. 测试分层覆盖 325 条 EARS 的 15 个需求组，并执行后端单元/集成、前端测试/lint/build、固定端口 API/UI 与必要的 `start.bat` 验证。

## 风险与未知项

- 风险：若设计把 23 case 当作已有事实、仅写“覆盖所有能力”而无稳定矩阵及机械校验，实施后无法证明全覆盖。
- 风险：若评测关联写入 Runtime 审计或依赖内存事件，违反零修改边界且恢复后关联会丢失。
- 风险：若 Inbox 只增加字段而无同锁域 CAS、意图日志和 reconciler，超时/并发仍会造成重复或丢失。
- 风险：若只在评测替身中模拟四态记忆修复，生产复用路径缺陷仍存在。
- 未知：23 个 case 的具体稳定 ID 与多能力映射必须由目标设计给出；阶段一不得自行把计划对象伪装成现有代码事实。
- 未知：真实 DeepSeek 运行的可用性、成本和上游模型身份只能在实现后由探测与审计证据确认。

## 测试与机械检查

- `uv run pytest ...`：未进入 pytest；Windows 报 `.venv\Scripts\taichu.exe` 被运行中进程占用（OS error 32）。这是工具同步阶段占用，不是产品测试失败。
- `.venv\Scripts\python.exe -m pytest -q tests/unit/infrastructure/test_plugin_discovery.py tests/unit/application/evaluations/test_capability_profiles.py tests/unit/application/general_agent/test_memory_context.py tests/unit/infrastructure/llm/test_rightcode_gateway.py tests/integration/api/test_mvp_first_api.py`：`51 passed in 20.47s`。
- 以上测试证明当前资产行为，不证明尚未实现的 23-case 体系或 Inbox/记忆修复已经完成。
