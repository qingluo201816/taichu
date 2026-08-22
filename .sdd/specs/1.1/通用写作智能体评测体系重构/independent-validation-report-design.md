# 独立校验报告

规格：`1.1/通用写作智能体评测体系重构`
模式：`design`
校验时间：`2026-07-27T06:29:37Z`
目标对象：

- `.sdd/specs/1.1/通用写作智能体评测体系重构/design.md`
- `.sdd/specs/1.1/通用写作智能体评测体系重构/research.md`
- `.sdd/specs/1.1/通用写作智能体评测体系重构/design-review-report.md`

目标 SHA-256：

- `design.md`：`9577940d2804fea554afce67e62b4b9149b7df3182eac0f3a38a58accfaa73d4`
- `research.md`：`8658b8a9012b006f997613b6e1b83af1ded3dd52a151b0c08e387211afb4e950`
- `design-review-report.md`：`abeffc0b9dd57fa6365ea97397079ad87484b21563a159b8752249e21ae177ba`

discovery：`.sdd/specs/1.1/通用写作智能体评测体系重构/validation-discovery-design.md`
discovery SHA-256：`0bd0f000dd24531c2c66484ef10f608650c4197ffd7bba7238c76f9d71df8ef6`
Git/工作树基线：`82bab37a5514f8a6f4d632872010293a910c2bec`；校验开始前工作树已有大量用户改动和未跟踪文件。本轮未修改目标文档、业务代码、测试、状态或其他工作区内容，只写允许的 discovery 与本报告。

## 结论摘要

当前设计与独立发现、已独立 PASS 的 325 条 EARS 需求、项目不可变规则和真实源码边界一致。设计给出了 23 个稳定业务 case，并以真实 invocation 反向覆盖现有 17 Tool 与 12 Subagent；Runtime 审计零修改、四态工作记忆生产修复、密封隔离执行、Inbox 确定性事务与多模型可比性均有明确所有权、接口、失败语义、恢复协议和测试门禁。

本轮未发现 critical、major、事实错误、规则冲突、虚构现有对象或不可实施调用链。设计对象在阶段二前后 SHA-256 一致，结论为 PASS。

## 独立发现范围与方法

阶段一在未读取、搜索或接收 `design.md`、`research.md`、正式设计评审和旧设计校验内容的前提下完成。独立检查范围包括：

- 根 `AGENTS.md`、`DESIGN.md`、`README.md`、`docs/rule.md`、`project_assets/readme.md`、启动脚本和 SDD 独立校验规则；
- 已锁定且独立 PASS 的 `requirements.md`、需求 discovery/PASS 报告和允许上游 `gap-analysis.md`；
- 生产能力发现、29 项能力 profile、旧评测模型/服务/API/fixture/前端；
- Runtime run、invocation、context snapshot、replay、usage、checkpoint、effect 与 memory 的真实模型、Protocol、仓储和测试；
- Inbox domain/service/API/storage/前端调用链；
- LLM catalog、probe、fallback、replay、usage/cost 证据；
- Pico 可取机制与不可复制的硬编码、subprocess 和 newest/mtime 反例；
- 前端现有组件、测试脚本、桌面规则和固定端口启动约束。

阶段一发现已先写入并核对非空，之后才计算目标初始哈希并完整读取 research、design 和正式评审报告。Graphify 按项目暂停规则禁用，未调用且未使用派生图谱。

## 匹配项

| # | 独立发现 | 目标设计处理 | 证据 |
|---:|---|---|---|
| 1 | 当前生产目录是 17 Tool + 12 Subagent，旧 suite 只有 8 case；23 case 是待建目标 | 7.1—7.3、8.3—8.4 给出生产快照、23 个稳定 case、30 条调用期望与 29 个唯一能力反向映射；明确 `allowed`/manifest/注册不计覆盖 | `tests/unit/infrastructure/test_plugin_discovery.py`；`tests/unit/application/evaluations/test_capability_profiles.py`；design 7.3 |
| 2 | 评测不得修改 Runtime 审计字段、ID 或写入生命周期 | 4.2、5.1—5.4、7.1、7.9、11.4 将关联归评测侧不可变 correlation ledger，通过隔离 wrapper 原样委托并只读复核原生 locator | `src/taichu/application/general_agent/runtime.py`；invocation/replay/usage/context/checkpoint/effect 模型与 Protocol；design 6.2 明确“不修改”清单 |
| 3 | 评测必须复用真实 Runtime，但不能污染活动 Markdown/Mongo/运行记忆 | 9.1—9.4 设计每 case 独立 assets root、Mongo database/client、完整能力注册、fixture-backed external research、活动事实指纹和严格清理 | `MongoKnowledgeRepository` 可注入数据库；现有临时 Runtime/Mongo 测试；design 9 |
| 4 | 四态记忆已存在，但 repair 投影遗漏 SUPERSEDED，reuse 未验证 producer ACTIVE | 6.2、7.12、16.1—16.2 将生产修复落在 memory service/context/orchestrator/executor/service，包含统一投影、双 proof、复用 provenance 和 anti-resurrection | `AgentMemoryValidity`、`AgentMemoryService.list_invalidated`、orchestrator/executor reuse 源码；design 7.12 |
| 5 | Inbox 缺 revision/typed link/GET-by-ID，读改写无 CAS，超时可产生重复或丢失 | 7.13、11.3、12.1—12.4 设计 deterministic intent/revision、append-only observation、同锁域 CAS、legacy revision 0、读回、租约、reconciler、relation/iteration 两级提交和四方对称门禁 | `MVPInboxIssue`、`MVPInboxService`、`/api/inbox/issues`、`ProjectAssetStorageBackend`；design 7.13 |
| 6 | requested model 不等于实际 provider/model，fallback/replay/usage/cost 缺失会污染比较 | 7.11、7.13、12.1—12.4 设计窄目录/probe、冻结条件、实际身份和不可比硬准入；缺证据不转成能力失败或排名 | LLM catalog、`LLMGatewayContract`、RightCode probe/replay/usage；design 7.11、7.13 |
| 7 | Strict scripted 必须观察真实 handler，执行与 verifier 分离，不得 newest/mtime 寻址 | 7.2、7.7、8、9.2、10.1 定义单一全局有序流、六类稳定错误、mandatory finalize、静态 verifier registry、精确 ID/hash 寻址 | 旧测试私有 scripted gateway；Pico 源码反例；design 7.2、7.7 |
| 8 | 前端需保留既有 route/nav，复用准入组件，无新依赖，只验收桌面 | 6.1—6.2、13.1—13.11 保持 route/Shell 导出，复用 Button/Checkbox/CompactPagination/lucide/原生元素，规定中文高密度、固定端口和浏览器手验 | `DESIGN.md`；现有 page/nav/components/package scripts；design 13 |
| 9 | 新路径验证后必须破坏式删除旧实现，资料与启动联动 | 6.3、15、16.4 给出精确删除/保留清单、原子切换顺序、全仓扫描、README/docs/assets 联动和 `start.bat` 门禁 | 根 `AGENTS.md`、`project_assets/readme.md`、`start.bat`；design 15—16 |

## 错误项

无。

## 遗漏项

无。阶段一“应有设计清单”中的 11 项均有明确设计落点和验收方式。

## 多余项

无。新增对象均明确标为计划新增，且服务于已校验需求；未把计划对象声称为当前现有资产。模型候选只作为 probe 后的建议，不声称当前可用。

## 不可验证或规则冲突

无阻断项。

预算、suite 通过阈值、重复性阈值和真实模型可用性属于实施/运营时必须显式冻结的输入。设计明确禁止隐藏默认值：阈值缺失则预检失败，模型只有 probe 与实际审计证据齐全才可比较，因此这些当前未知项不会造成设计不可验证。

## 需求/设计/任务追踪表

| 需求组 | 数量 | 设计主要落点 | 追踪结论 |
|---:|---:|---|---|
| 1 固定套件与生产目录 | 25 | 7.1—7.3、8 | 完整 |
| 2 可复现身份 | 16 | 7.1、8.2、11.3 | 完整 |
| 3 隔离夹具 | 17 | 7.4、9 | 完整 |
| 4 确定性基线 | 15 | 7.2、7.7、10.1 | 完整 |
| 5 判定真值 | 27 | 7.5、7.8、10.3—10.4 | 完整 |
| 6 失败解释 | 17 | 7.8、10.1—10.4 | 完整 |
| 7 证据与工件 | 23 | 7.9—7.10、11.3—11.4 | 完整 |
| 8 分轨、实验与机制 | 31 | 7.11、10.4、12 | 完整 |
| 9 生命周期 | 9 | 11.1—11.3、12.2 | 完整 |
| 10 API 与桌面工作台 | 34 | 12—13 | 完整 |
| 11 相邻边界 | 15 | 4.2—4.3、5、7.9、11.4 | 完整 |
| 12 破坏式清理 | 21 | 6、15—16 | 完整 |
| 13 类型化产物 | 15 | 7.6—7.7、10.2 | 完整 |
| 14 工作记忆专项 | 20 | 7.12、9.2、16.1—16.2 | 完整 |
| 15 首轮闭环与多模型 | 40 | 7.11、7.13、11.3、12—13 | 完整 |

机械比较：requirements 中 325 个唯一数字 ID；design 17.1 中 325 个唯一 ID；缺失 0，多余 0。设计 case 表为 23 个唯一稳定 ID；能力目录相关测试证明当前 17 Tool + 12 Subagent = 29 项。

## 测试与机械检查

| 检查 | 结果 |
|---|---|
| 上游 requirements 锁定 | SHA `b5b65cf351b58c6ff72bfc6f76f1d9c3b10470ebc01875670571957fe14a1cf2`，独立报告 PASS |
| design/research/review 初始与报告前哈希 | 三者分别保持 `957794…73d4`、`8658b8…950`、`abeffc…77ba`，一致 |
| discovery 非空与哈希 | 11167 字节（更新时间前）；最终 SHA `0bd0f0…ef6` |
| 需求 ID 追踪 | 325/325，缺失 0，多余 0 |
| 固定 case | 23 个唯一 ID |
| 当前资产回归 | `.venv\Scripts\python.exe -m pytest -q` 指定能力发现、profile、memory context、RightCode gateway、Inbox API 测试：`51 passed in 20.47s` |
| `uv run` 同组测试 | 未进入 pytest；Windows 报运行中的 `.venv\Scripts\taichu.exe` 被占用（OS error 32）。已用同一虚拟环境 Python 成功执行，不作为产品失败 |
| Graphify | 按项目规则禁用，未调用、未使用缓存事实 |

设计阶段不要求运行尚未实现的新 suite、前端 build 或固定端口验收；design 16 已把它们列为实现完成前的强制门禁。

## 分级问题

### Critical

无。

### Major

无。

### Minor

无。

### Info

- 实施时应严格保持 design 18 的批次顺序，尤其不得在 synthetic、核心机制和 Inbox 对称闭环门禁前启动多模型排名。
- 实现校验应重新计算当时生产能力快照；若不再是 17+12，必须按设计触发预检失败和重新验证，不能沿用本报告的数量事实。

## 修正项（FAIL 时）

不适用。

## 门禁理由

- critical = 0，major = 0，minor = 0；
- 事实错误、规则冲突、虚构现有对象和不可达调用链均为 0；
- 15 组 325 条需求全部追踪；
- 23 个固定业务 case 与 29 项生产能力反向覆盖合同明确；
- Runtime 审计零修改、密封隔离、四态记忆生产修复、Inbox 可恢复一致性、多模型不可比隔离、前端与清理/启动边界均可实施并可机械验收；
- 必要的当前资产测试和机械检查已实际通过；
- 目标对象哈希在校验期间保持一致，证据可复现。

结论：PASS
