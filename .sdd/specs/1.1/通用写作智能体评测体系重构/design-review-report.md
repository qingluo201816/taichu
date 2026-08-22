# 设计质量评审报告

## 文档信息

- 规格：`1.1/通用写作智能体评测体系重构`
- 评审模式：修订后正式实现就绪评审
- requirements SHA-256：`b5b65cf351b58c6ff72bfc6f76f1d9c3b10470ebc01875670571957fe14a1cf2`
- gap-analysis SHA-256：`b347d8ef29dde59e7e0383243a9799a88b378a79caf9da3340f7568517661034`
- research SHA-256：`8658b8a9012b006f997613b6e1b83af1ded3dd52a151b0c08e387211afb4e950`
- design SHA-256：`9577940d2804fea554afce67e62b4b9149b7df3182eac0f3a38a58accfaa73d4`
- 上游需求独立校验：`PASS`
- Graphify：禁用；未调用 Graphify。一次直接源码宽搜索误命中禁用缓存路径，相关输出已丢弃，事实检查随后使用排除 `graphify-out` 的源码搜索重做。

## 评审摘要

当前设计已把上一轮独立 FAIL 的 Runtime 审计越界、冻结工件与 Inbox 一致性缺口、前端组件准入矛盾全部改成可实施且可机械验收的合同。后续审计提出的 observer 故障隔离、源内 hash/状态矩阵、确定性 revision 重放、legacy revision 0、页码分页、纯 Node 测试、request ID、防倒退、comparison 恢复和极光边界也均有物理归属、失败语义与测试门禁。

机械核验得到 325/325 数字需求追踪、23 个固定业务 case，以及当前生产发现的 17 Tool + 12 Subagent = 29 个唯一能力。未发现关键架构偏差、不可实施契约或会阻断任务拆分的问题。

## 机械检查

| 检查 | 结果 | 证据 |
|---|---|---|
| 对象锁定 | 通过 | research/design SHA 与本轮指定值完全一致 |
| 状态一致性 | 通过 | `state.py validate` 返回 `ok=true`，无 errors/warnings |
| 数字需求追踪 | 通过 | requirements 325 个唯一 ID；design 17.1 索引 325 个，缺失 0、多余 0 |
| 边界承诺 | 通过 | design 4.1—4.4 四部分均非空 |
| 文件与组件归属 | 通过 | design 6.1—6.4 列出新增、修改、删除、保留对象；13.2 将前端逻辑组件逐一映射到物理文件 |
| 模板占位符 | 通过 | 未发现 `TBD`、模板变量或待补充段落；`todo` 仅为 Inbox 合法状态值 |
| 依赖方向 | 通过 | application Protocol、infrastructure adapter、API/Web 单向依赖明确；禁止完整可写仓储进入 reader |
| 固定案例与能力 | 通过 | case 表 23 项；直接运行当前插件发现得到 17 Tool、12 Subagent、29 个唯一能力 |
| 前端准入 | 通过 | 只复用现有 AppShell、导航、Button、Checkbox、CompactPagination、lucide 和原生元素；无新增依赖 |

## 重点复核

### 1. Runtime 审计零修改与评测 observer

结论：实现就绪，上一轮 E-01 已消除。

- design 4.2、6.2 明确禁止修改 `LLMRequest`、`InvocationContext/InvocationTraceRecord`、Subagent runner、RightCode gateway/adapter 及其 ID、字段和写入语义；Orchestrator/Executor 仅允许需求 14 的 producer reuse 修复。
- design 5.1、5.4、7.1 将 wrapper 仅装入评测隔离组合根。底层 gateway/trace/replay/usage 调用先且只执行一次，observer/scope/repository 故障只令 evaluation correlation invalid，不替换底层返回、原异常、重试或写入次数；CaseExecutor `finally` 固化取消、缺 trace 和 pending exchange。
- 四行状态矩阵分别定义 live/synthetic 的 returned/raised。它明确允许 gateway completed 后应用层 JSON/Pydantic/schema 校验导致 trace failed，其他非法映射 fail closed。
- 每个 observation 只按自身 locator 和原生算法复读；evaluation、trace、replay request hash 不要求跨源相等。Token 预算遍历 available correlation records，live 按唯一 usage locator/gateway call ID 读取，synthetic 使用 fixed usage observation，不泛化为任意 LLM call ID，也不把缺失 Token 当 0。
- 当前源码存在所需注入缝：Orchestrator/Subagent 通过 LLM gateway 与 trace repository 端口工作，RightCode 通过注入的 usage/replay repository 写入；无需修改共享审计模型。

可追溯性：需求 7.12、11.1—11.15、15.33—15.40。  
设计证据：4.2—4.3、5.1—5.4、6.2、7.1、7.5、7.9、16.1—16.4。

### 2. 冻结 subject、Inbox 事务与 legacy 数据

结论：实现就绪，上一轮 M-01 已消除。

- design 7.13 只允许 run terminal、suite、first-live、failure 四类不可变 subject；iteration/run manifest、索引和 API view 不能成为 subject，issue 变化不回写冻结工件。
- intent、relation 和 revision 均有排除墙钟/随机值的确定性身份与 create-if-absent 规则；revision snapshot 先写、relation manifest 后 CAS。同路径同 hash 幂等，异 hash 冲突；manifest CAS 前崩溃产生可识别 orphan，reconciler 沿同一路径继续，不增加 revision。
- `IssueCorrelationObservation` 明确定义 append-only 模型、确定性 observation ID、阶段、结果和 observed revisions；repository Protocol 包含 intent/revision/observation、relation CAS、iteration CAS 和 orphan 扫描。
- 外部 Inbox mutation 前先把 pending intent 加入 iteration manifest；全部 relation confirmed 且 symmetry gate 通过后，最终 iteration CAS 才清 pending、写 confirmed refs。每个崩溃窗口都有重放测试，冲突保持 blocked。
- 当前活动 `inbox_issues.jsonl` 直接检查为 16 行，16 行均缺 `revision/links`。设计将它们只读正规化为 `revision=0, links=[]`，首次 expected revision 0 CAS 才原子升级；错误 revision 409 且不写。
- 真实调用点核验显示现有 issue PATCH 生产调用者集中在 `web/src/lib/api/mvp.ts` 与 `inbox-board.tsx`；设计 6.2 同时覆盖 domain model、schema、service、route、storage、这两个 Web 文件以及 domain/API/storage/前端测试，没有遗漏明显调用边。

可追溯性：需求 7.13、9.4、15.9—15.11、15.20—15.22、15.26—15.32。  
设计证据：6.1—6.2、7.13、11.3、12.1—12.4、13.11、16.1—16.3。

### 3. 分页、前端状态恢复与可执行验证

结论：实现就绪，上一轮 N-01 及后续前端审计项已消除。

- API 列表统一采用 `page/page_size` 和 `{items,page,page_size,total,total_pages,index_revision,total_snapshot}`，与现有 `CompactPagination(page,pageSize,total,onPageChange)` 一致。当前组件真实支持上一页、下一页和任意页码跳转。
- `RequestCoordinator` 以 resource key、generation、AbortController 和 `lastAppliedRevision` 同时阻止旧 detail/list 响应倒退；URL 保存 run/case/experiment/comparison 页码及 `comparison`、`iteration`，重载可先 exact detail、再按 iteration 列表恢复比较结果。
- 每个错误 envelope 必带与结构化日志相同的 `request_id`；共享 `ApiError` 保留 status/code/message/details/requestId，Inbox 409 刷新后要求作者确认再重试。
- 现有 `npm run test:general-agent` 经核实确实是 `tsc + node`，并实际执行 `web/tests/general-agent/evaluation-view.test.ts`。设计只让纯 Node 覆盖 parser/reducer/request coordinator/Inbox 数据合同，不虚称 DOM；焦点、ARIA、点击、单次 mutation、409 刷新与 comparison URL 恢复归固定端口浏览器手验。
- 不再依赖 Dialog/Sheet/Skeleton，也不修改共享分页和导航。极光只允许少量背景装饰，不承担状态、交互、文字、边框或功能色语义。

可追溯性：需求 9.1—9.9、10.1—10.34、12.10—12.12。  
设计证据：6.1—6.2、12.2—12.4、13.1—13.11、16.3—16.4；根 `DESIGN.md`。

## 关键问题

关键问题：0。

上述复核项均已形成明确的数据所有权、接口、失败/恢复合同、物理文件计划和可执行验收门禁。剩余风险属于实施期需按既定故障注入、并发 CAS、固定端口浏览器与回归测试验证的正常风险，不构成设计阶段阻断。

## 设计优点

1. 证据关联没有侵入共享 Runtime，而是用隔离 scope、轨道状态矩阵、源内复读和不可变 ledger 解决现有 ID/hash 不同的问题，边界与失败语义清楚。
2. Inbox 闭环将冻结事实、确定性事务身份、append-only observation、relation/iteration 两级 CAS、legacy 演进和 comparison admission 串成一条可崩溃恢复的协议。

## 最终评估

决策：GO

理由：当前 design SHA 对 325 条已校验需求覆盖完整，23/29 基准范围无回归，上一轮三项 FAIL 与后续审计项均已实质解决；实现路径、迁移、失败补偿、前端恢复、验证和启动门禁明确，风险可接受。

下一步：由全新上下文的独立设计校验角色对
`9577940d2804fea554afce67e62b4b9149b7df3182eac0f3a38a58accfaa73d4`
执行正式 PASS/FAIL 校验。本 GO 不替代独立 PASS，也不修改当前状态记录。

## 【Step 收尾检查】

- [x] 直接核对当前 requirements、gap-analysis、research、design 与需求独立 PASS 报告。
- [x] 直接核对 Runtime/RightCode 注入缝、Inbox 16 条 legacy 数据及生产调用点、CompactPagination、Web 测试脚本和现有 UI 资产。
- [x] 完成 325 ID、四边界、文件归属、依赖、占位符、23 case、29 capability、UI 准入机械检查。
- [x] Graphify 禁用；未将误命中的旧缓存输出作为事实，已用排除缓存的源码搜索重做。
- [x] 只覆盖本 `design-review-report.md`，未修改需求、差距、研究、设计、状态或业务代码。
- [x] 最终结论明确为 `决策：GO`，且未冒充独立设计 PASS。
