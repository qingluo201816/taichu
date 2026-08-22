# 独立校验报告

规格：`1.1/通用写作智能体评测体系重构`  
模式：`design`  
校验时间：`2026-07-27T05:01:42.1069848Z`  
目标对象：`.sdd/specs/1.1/通用写作智能体评测体系重构/design.md`  
目标 SHA-256：`0c3e7645e1a827878de1cababc1484c8230aa8993fd366786f62779a7462aa2b`  
discovery：`.sdd/specs/1.1/通用写作智能体评测体系重构/validation-discovery-design.md`，SHA-256 `3934d4b55be7744a6e37b636e521e487210851ac49cb3001540ac1a1503d3167`  
Git/工作树基线：`HEAD 82bab37a5514f8a6f4d632872010293a910c2bec`；工作树原本非干净，规格目录在 Git 状态中为未跟踪。本轮只写 discovery 与本报告，未修改目标、需求、源码、测试、配置、状态或其他用户改动。

## 结论摘要

设计对固定 suite、23 个业务案例、29 个生产能力、隔离 Runtime、严格脚本、类型化产物、六硬门禁、工作记忆专项、生命周期、桌面工作台、DeepSeek 首轮和破坏式清理给出了广泛且大体可实施的结构。机械索引覆盖了需求中的全部 325 个数字验收标准，目标哈希在阶段二前和报告写入前均与用户指定值一致。

门禁仍不通过。设计一方面把既有 Runtime 审计字段、生命周期与写入流程列为边界外，另一方面又要求修改 `LLMRequest`、`InvocationContext/InvocationTraceRecord`、Orchestrator、Subagent runner 和 RightCode gateway 的调用身份及写入语义，直接违反需求 11.10，并与设计自身边界承诺冲突。另有一个重要缺口：不可变套件/首轮工件与事后创建、更新、关闭的 Inbox 问题双向链接之间没有定义可执行的版本化一致性协议。

问题计数：Critical `1`，Major `1`，Minor `1`，Info `1`。

## 独立发现范围与方法

阶段一严格未读取、搜索或接收 `design.md`、`research.md`、`design-review-report.md` 的任何内容。先读取根/局部规则、SDD 独立校验协议、状态契约、已校验需求及其当前 PASS 报告、差距分析、当前源码、测试、配置、依赖、启动脚本、前端 `DESIGN.md`、组件准入规则和 `docs/rule.md`，再将独立发现写入 discovery。文件系统证据显示 discovery 于 `2026-07-27T04:53:24Z` 创建且最后写入，`2026-07-27T04:54:24Z` 完成非空和哈希门禁；discovery 页首手工记录的 `05:50:00Z` 是时间录入笔误，未据此证明阶段顺序，阶段顺序以文件时间、门禁命令输出和对象哈希为准。

阶段二开始前计算：

- `design.md`：`0c3e7645e1a827878de1cababc1484c8230aa8993fd366786f62779a7462aa2b`
- `research.md`：`7c0d3b8e9d5678e019f300afc77f3a81da4aaf390ce36f7c71cb5c55f728bce9`
- discovery：`3934d4b55be7744a6e37b636e521e487210851ac49cb3001540ac1a1503d3167`

随后全文读取 `research.md` 与 `design.md`，把设计同 15 组 325 条需求、独立发现和当前源码逐项对比。Graphify 按项目规则禁用，本轮未调用 Graphify，也未把现有图谱产物作为证据。

## 匹配项

| # | 设计范围 | 匹配结论 | 证据 |
|---|---|---|---|
| 1 | 新旧边界 | 正确选择“新评测核心 + 现有能力窄适配”，明确删除旧五维根模型、服务、仓储、API、fixture、测试和活动结果，不设计兼容 reader/mapper/回退 | `design.md:12-57`、`:142-221`、`:463-489`、`:1751-1786`；旧事实见 `src/taichu/application/evaluations/general_agent/models.py:95-163`、`service.py:53-128` |
| 2 | 固定合同与能力覆盖 | 明确 17 Tool + 12 Subagent 生产快照、23 个业务案例、30 条调用期望覆盖 29 个唯一能力；`allowed`、manifest、注册成功不计覆盖 | `design.md:514-524`、`:545-619`、`:621-725`、`:909`；当前目录见 `tests/unit/infrastructure/test_plugin_discovery.py:32-87` |
| 3 | 隔离与事实安全 | 每 case 独立临时 assets root、独立 `taichu_eval_<32hex>` 数据库、专属 CapabilityContext/registry/Runtime，密封源不直接挂载；活动事实使用不可达凭据与前后指纹双重证明 | `design.md:727-755`、`:1273-1337`；当前注入缝见 `src/taichu/infrastructure/knowledge/mongo_repository.py:35-65`、`tests/unit/application/general_agent/test_runtime.py:1141-1182` |
| 4 | 严格 synthetic | 单一全局有序 model/tool/subagent/human/task 流，Tool/Subagent 执行真实 handler，六类稳定错误，所有退出路径 mandatory `finalize()`，重复结果规范化漂移失败 | `design.md:264`、`:579-619`、`:1297-1313` |
| 5 | 判定与失败 | 五类类型化预期产物、静态 verifier registry、六硬门禁交集、案例/套件/机制分层结论、主要与全部失败类别并存，指标不覆盖硬失败 | `design.md:757-919`、`:1339-1394` |
| 6 | 只读证据 | 设计了八个窄单源 facade、聚合 reader、精确 ID/hash 关联、availability 和最小 bundle，禁止完整仓储注入、mtime 和时间邻近回填 | `design.md:921-996`、`:1463-1477` |
| 7 | 工作记忆 | 准确识别 `SUPERSEDED` 修复投影和复用防复活缺口，规划 Orchestrator/Executor 双门禁、统一 current/repair 投影、四案例和七项专项硬门禁 | `design.md:1105-1140`；当前缺口见 `src/taichu/application/services/agent_memory_service.py:236-301`、`orchestrator.py:259-293`、`executor.py:190-227` |
| 8 | 生命周期与工件 | 预检在状态机外；幂等、租约、CAS、取消、unfinished 新 run 恢复、终态保护、原子工件和可重建索引均有明确路径 | `design.md:998-1047`、`:1396-1461` |
| 9 | 首轮与比较 | synthetic/核心/机制前置、DeepSeek V4 Pro 首轮、失败分类、非系统类别不写 Inbox、逐模型 probe/实际身份/fallback/replay/usage/cost/error 准入均被覆盖 | `design.md:1142-1172`、`:1518-1530` |
| 10 | 前端与清理 | 保留 route/nav/AppShell，中文桌面三栏、结论优先级、按需详情、固定端口、旧契约零残留和 `start.bat` 联动均有设计与测试门禁 | `design.md:1585-1716`、`:1788-1849` |

## 错误项

### E-01：设计改变了需求明确要求保持不变的 Runtime 审计字段与写入流程

分类：规则冲突、事实边界冲突  
严重性：Critical

- 上游需求 11.10 明确要求“保持现有 Runtime 审计记录的字段、生命周期和写入流程不因评测读取而改变”，见 `requirements.md:644`。
- 设计也把 Runtime 原始 run/invocation/context/replay/checkpoint/effect/usage 的字段和写入列为边界之外，见 `design.md:82-89`，并声明不拥有调用审计，见 `design.md:14-16`。
- 但文件规划要求：
  - 给 `LLMRequest` 新增 caller-generated `call_id`，见 `design.md:425`；
  - 给 `InvocationContext/InvocationTraceRecord` 新增 `context_snapshot_id`，见 `design.md:426`；
  - 改 Orchestrator、Subagent runner、Executor、RightCode/adapter 的 call ID 创建、透传、响应、replay 和 usage 写入语义，见 `design.md:428-439`、`:526`、`:963-970`。
- 当前源码证明这不是“只读 adapter”：`LLMRequest` 当前没有 `call_id`（`src/taichu/application/contracts/llm.py:65-81`）；`InvocationTraceRecord` 当前没有 `context_snapshot_id`（`src/taichu/application/invocations/models.py:97-126`）；Orchestrator 另建 `call_<uuid>`（`src/taichu/application/general_agent/orchestrator.py:465-506`），RightCode 另建 `llm-call-<uuid>`（`src/taichu/infrastructure/llm/rightcode.py:166`、`:293`）。

当前事实确实显示 trace 与 replay/usage 的 LLM call identity 无法精确 join，但这说明需求 7.12 的精确关联目标与需求 11.10 的不改审计约束之间存在必须由上游澄清的冲突。设计不能一边宣称只读复用，一边把变更审计合同作为默认实现路径。

影响：该变更触及所有正常 Runtime/LLM 调用，而不只是评测；会改变现有审计 Schema、调用标识生成和写入流程，可能影响历史读取、运行监控、其他评测域和相邻测试。核心证据链在当前设计约束下不可合法实现。

## 遗漏项

### M-01：不可变评测工件与事后 Inbox 双向链接之间缺少版本化一致性协议

分类：遗漏、不可实施边界  
严重性：Major

- 设计规定 `CaseResultRow` 引用不可变 attempt artifact，`SuiteArtifact` 为终态不可变聚合，completed run 必须有终态 artifact，见 `design.md:998-1045`。
- DeepSeek 首轮保存不可变 first-run suite artifact，见 `design.md:1144-1152`；所有终态 artifact 和首轮工件不得原地覆盖，见 `design.md:1459`。
- 系统问题却只能在真实 suite 结束、失败分类后创建，并会在修复后 PATCH 关闭；每次创建、更新、关闭还要读回 revision/status/content/links，见 `design.md:1154-1168`。
- 同时设计要求 `SuiteArtifact/SuiteRun/FirstLiveIteration/FailureRecord` 都保存相同 `issue_id` 与 link hash，见 `design.md:1156`，但没有定义：
  - issue 创建前不可变 suite/case artifact 如何预留或提交反向链接；
  - issue 从 `todo` 更新为 `processed`、正文和 revision 改变后，`MVPInboxIssueLink.content_sha256` 如何不使已冻结反向链接过期；
  - `iterations/.../issue-links.json` 是事实源、版本化 sidecar 还是缓存，以及它如何被 SuiteArtifact/SuiteRun/FailureRecord 不可变引用；
  - 跨 Inbox CAS 与评测 artifact CAS 的失败补偿、幂等重放和恢复顺序。

影响：需求 15.29—15.32 的双向稳定关联、写后读回和关联对称门禁无法按当前合同实现；实现者只能选择修改冻结工件、留下陈旧 hash，或另造未定义的可变旁路。

## 多余项

未发现会单独扩大产品范围的 critical/major 多余设计。新增 Inbox GET-by-ID、revision/typed links 和原子 CAS 虽超出旧接口现状，但有需求 15.9—15.11、15.26—15.32 的直接依据。

## 不可验证或规则冲突

### N-01：前端共享组件和组件准入计划前后矛盾

分类：不可验证、局部规则冲突  
严重性：Minor

- 设计明确要求调用侧给 `CompactPagination` 传 `border-t-0`，不修改共享组件默认样式，见 `design.md:1624-1626`；当前组件确实接受 `className` 且默认包含 `border-t`，见 `web/src/components/ui/compact-pagination.tsx:9-48`。
- 但前端“重写”文件清单又包含 `web/src/components/ui/compact-pagination.tsx`，见 `design.md:1702-1714`，与“不修改共享组件”冲突。
- 同一节声明未核实存在的 Dialog/Sheet/Skeleton 不作为实现前提，见 `design.md:1624`，后续状态和可访问性却直接要求 Skeleton、Dialog、Sheet，见 `design.md:1659`、`:1698`；取消确认和实验二次确认也未指定使用已准入组件或原生边界。

该问题不阻塞后端核心架构，但会导致任务拆分时无法判断共享组件是否允许修改、确认交互使用哪个已准入组件以及相应测试归属。

## 需求/设计/任务追踪表

| 需求组 | 机械覆盖 | 语义结果 | 关键设计落点 | 问题 |
|---|---:|---|---|---|
| 1 固定基准与能力覆盖 | 25/25 | 匹配 | 7.1—7.3、8.1—8.4 | 无 |
| 2 身份与复现 | 16/16 | 匹配 | 7.1、8.2、11.3 | 无 |
| 3 密封夹具与隔离 | 17/17 | 匹配 | 7.4、9.1—9.4 | 无 |
| 4 确定性基线 | 15/15 | 匹配 | 7.2、7.7、9.2、10.1 | 无 |
| 5 多条件硬门禁 | 27/27 | 匹配 | 7.5—7.8、10.3 | 无 |
| 6 失败解释 | 17/17 | 匹配 | 7.7—7.8、10.1、13.7 | 无 |
| 7 工件与证据 | 23/23 | 部分冲突 | 7.9—7.10、11.3—11.4 | E-01 |
| 8 分轨与机制 | 31/31 | 匹配 | 7.8、7.11、10.4 | 无 |
| 9 生命周期 | 9/9 | 匹配 | 11.1—11.3、12.2 | 无 |
| 10 桌面工作台 | 34/34 | 基本匹配 | 13.1—13.10 | N-01 |
| 11 相邻与数据边界 | 15/15 | 冲突 | 4.2—4.3、7.9、11.4 | E-01 |
| 12 破坏式清理 | 21/21 | 匹配 | 6、15、16.4 | 无 |
| 13 类型化产物 | 15/15 | 匹配 | 7.6—7.7、10.2 | 无 |
| 14 工作记忆专项 | 20/20 | 匹配 | 7.12、16.1—16.2 | 无 |
| 15 首轮闭环与比较 | 40/40 | 有重要遗漏 | 7.13、12.1—12.4、13.5—13.7 | M-01 |

机械索引总计：需求 `325`、唯一需求 `325`；设计 17.1 索引 `325`、唯一索引 `325`；缺失 `0`、多余 `0`、重复 `0`。机械覆盖不覆盖语义冲突，不能据此放行 E-01 或 M-01。

## 测试与机械检查

| 检查 | 命令/方法 | 结果 |
|---|---|---|
| 上游需求对象 | `Get-FileHash -Algorithm SHA256 requirements.md`，并核对 `spec.json.validations.requirements` 与需求独立报告 | `b5b65cf351b58c6ff72bfc6f76f1d9c3b10470ebc01875670571957fe14a1cf2`，当前 PASS 报告/对象/discovery 哈希登记一致 |
| discovery 门禁 | `Get-Item`、`Measure-Object -Line`、`Get-FileHash` | 35834 bytes、173 个非空统计行、SHA-256 `3934d4...d3167` |
| 目标前置哈希 | 阶段二前 `Get-FileHash design.md` | 与用户指定 `0c3e7645...aa2b` 完全一致 |
| 全文读取 | UTF-8 分段读取 `research.md` 与 `design.md` | `research.md` 442 物理行；`design.md` 1974 物理行；均读至 EOF |
| 325 ID 机械追踪 | PowerShell 从 requirements 行首提取 ID，并从 design 17.1 提取显式 ID 后比较集合/重复 | 325 对 325；missing 0、extra 0、duplicates 0 |
| 生产能力现状 | 读取 `test_plugin_discovery.py`，并运行 `uv run --no-sync pytest tests/unit/infrastructure/test_plugin_discovery.py tests/unit/application/general_agent/test_memory_context.py -q` | 20 passed，0.98s；确认 17 Tool、12 Subagent 与当前记忆基础行为 |
| 首次测试启动 | `uv run pytest ... -q` | 未进入 pytest：`uv` 同步可编辑入口时因正在运行的 `.venv/Scripts/taichu.exe` 文件锁失败；随后用 `--no-sync` 在现有环境成功运行，未停止或干扰服务 |
| 审计身份现状 | `rg -n` 与源码读取 `LLMRequest`、`InvocationTraceRecord`、Orchestrator、RightCode | 证实 trace 与 gateway 当前各自生成不同 call ID，设计变更不是只读 adapter |
| UI 组件事实 | 读取 `CompactPagination` | 支持 `className` 调用侧覆盖；设计无需修改共享文件即可去掉本页顶边 |
| Graphify | 项目规则检查 | 禁用；未调用、未读取旧图谱事实 |
| 报告前目标哈希 | `Get-FileHash design.md` | `0c3e7645e1a827878de1cababc1484c8230aa8993fd366786f62779a7462aa2b`，未变化 |

本阶段不运行尚未实现的新 suite、API、前端构建或固定端口验收；它们属于后续实现门禁，不能用当前旧实现测试冒充。当前失败结论由设计合同冲突和缺失直接触发，不依赖未实现测试。

## 分级问题

### Critical

1. **E-01 Runtime 审计合同越界**：违反需求 11.10 和设计自身边界承诺；若不修改审计链则无法实现设计的精确 LLM identity join，若按设计修改则违反已校验需求，属于核心证据路径不可合法实施。

### Major

1. **M-01 Inbox 双向链接与不可变工件缺少一致性协议**：系统问题的事后创建/更新/关闭无法可靠反向写入已经冻结的 suite/run/failure 工件，15.29—15.32 不具备实现就绪度。

### Minor

1. **N-01 前端文件与组件准入矛盾**：`CompactPagination` 同时被要求不修改和列入重写；未准入的 Skeleton/Dialog/Sheet 又被后续交互直接依赖。

### Info

1. 机械追踪、29 项能力映射、严格脚本、隔离、工作记忆专项、生命周期和清理设计总体质量较高；修正上述门禁问题后可在保留主体结构的前提下重新校验。

## 修正项（FAIL 时）

1. 先解决需求 7.12 与 11.10 的冲突，不能由实现者自行选边：
   - 若 11.10 保持不变，设计必须只使用现有审计字段/写入流程，给出不靠时间、名称或 mtime 的可证明关联方案；当前事实下若做不到，应明确将相关证据标记不可用并调整依赖它的硬门禁，而不是改 Runtime 审计；
   - 若统一 caller-generated LLM call identity 是产品必要条件，应先修订并重新独立校验 requirements，明确允许的审计 Schema、写入兼容、历史读取和相邻回归范围，再更新设计。
2. 为 Inbox 关联定义单一事实源和版本化协议。至少明确：
   - issue ID/关系 ID 何时计算；
   - suite artifact、run manifest、failure record、iteration 与 `issue-links.json` 哪些不可变、哪些可按 revision/CAS 更新；
   - issue 内容/status/revision 变化时 link hash 的稳定定义；
   - Inbox 写成功而评测侧反链写失败、或反向顺序失败时的补偿、重放、读回和恢复；
   - 关闭后怎样在不改写冻结首轮工件的前提下证明双向对称。
3. 统一前端文件规划：从重写清单移除 `compact-pagination.tsx`，或删除“不修改共享组件”的承诺并说明共享回归；对取消确认、实验二次确认、加载占位明确使用已存在/已准入组件或原生实现，并补充对应文件与测试。
4. 修订后重新计算 `design.md` SHA-256，从新的阶段一独立发现或经门禁允许的增量重新校验；旧报告不得用于新哈希。

## 门禁理由

独立设计校验要求 critical=0、major=0、事实错误=0、规则冲突=0，且核心边界可实施。当前对象存在一个直接违反已校验需求的 Critical 规则冲突，以及一个阻断缺陷闭环双向关联的 Major 一致性缺口；因此即使 325 条机械 ID 全覆盖、目标哈希稳定且相关当前测试通过，也不能放行。

结论：FAIL
