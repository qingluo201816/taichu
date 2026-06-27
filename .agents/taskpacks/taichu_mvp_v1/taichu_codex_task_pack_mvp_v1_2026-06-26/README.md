# 太初 MVP v1 Codex 任务包

> 生成日期：2026-06-26  
> 用途：交给 Codex / Coding Agent 执行太初 MVP v1 的阶段化开发。  
> 任务包性质：开发态资料，不参与太初产品运行。建议放入仓库 `.agents/taskpacks/taichu_mvp_v1/`。

## 0. 一句话目标

太初 MVP v1 要验证：作者在当前章节编辑器内，能完成“写正文 → 选区 AI → AI 卡片 → 插入正文 / 保存灵感 / 生成待确认设定 → 作者确认入库 → 后续检索带来源依据”的闭环。

## 1. Codex 使用方式

每次只执行一个 Phase，不要一次性执行全部 Phase。执行前必须阅读：

1. `00_context/product_baseline.md`
2. `00_context/non_negotiable_decisions.md`
3. `01_architecture/target_architecture.md`
4. `01_architecture/data_contract.md`
5. 当前要执行的 `02_phases/phase_xx_*.md`
6. `03_execution/codex_rules.md`
7. `03_execution/evidence_return_template.md`

执行时必须遵守：

- 不重新争论已经定死的架构决策。
- 不跨 Phase 偷做后续功能。
- 不把 MVP 写成多小说平台、协作 SaaS、发布平台或纯 Agent 展示。
- 不让 AI 输出绕过 AIResultCard、PendingFact、KnowledgeCard 状态机。
- 不让 SQLite 保存唯一用户资产。
- 不让非事实内容进入默认 `fact_scope`。
- 每次返回必须提供证据：修改文件、关键 diff、测试命令、测试结果、未完成项、风险。

## 2. 三个已定死的架构决策

1. SQLite：MVP v1 只做 `project_assets/generated/` 下的可重建投影。用户资产主记录放 `project_assets/source/` 的 Markdown / JSON / JSONL。
2. Selection AI：MVP v1 是编辑器应用工作流，由 `SelectionAIService` 承载；不是 AgentRegistry 里的产品 Agent。
3. SourceRef：MVP v1 做段落级/字段级证据定位；选区保留段内字符偏移；不做全文稳定锚点、token 级坐标、CRDT anchor。

## 3. Phase 总览

| Phase | 名称 | 核心产物 |
|---:|---|---|
| 0 | Product Contract / Data Contract Lockdown | 数据模型、状态机、事实范围规则、契约测试 |
| 1 | Project Asset Skeleton / Corpus Importer | `project_assets/source/generated` 骨架、章节 manifest、导入器 |
| 2 | Editor Shell / Markdown Persistence | 编辑器页面、章节导航、Markdown 保存、自动保存、选区捕获 |
| 3 | Selection AI / AI Result Card | 三类选区 AI、AIResultCard、插入/保存/丢弃/重试 |
| 4 | Creative Inbox / Lightweight Kanban | 灵感、待确认设定、AI 收藏、章节问题轻量收件箱 |
| 5 | Minimal Knowledge Base | KnowledgeCard、CharacterCard、PendingFact 确认入库 |
| 6 | Hybrid Retrieval / Evidence Answer | exact + FTS + vector-lite、证据卡、fact_scope 防污染 |
| 7 | Chapter Summary / Candidate Setting Pipeline | 章节整理卡、摘要草稿、设定/角色变化/伏笔候选 |
| 8 | Basic Agent Chat / Export / MVP Integration | 基础深度对话、导出、索引重建、端到端验收 |

## 4. 什么时候停止

当当前 Phase 的验收标准满足，且测试通过，就停止。不要继续做下一 Phase。若发现当前仓库结构和任务包假设冲突，先返回冲突报告，不要擅自重构全仓库。
