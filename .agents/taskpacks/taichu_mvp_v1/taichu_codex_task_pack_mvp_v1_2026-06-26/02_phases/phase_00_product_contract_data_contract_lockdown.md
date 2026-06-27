# Phase 0：Product Contract / Data Contract Lockdown

## 1. 阶段目标

锁定产品边界、数据契约、状态机、fact_scope、防污染规则，避免后续 Code Agent 自由发挥。

## 2. 本阶段要实现

- 新增/整理 domain models：Chapter、ChapterManifest、SourceRef、AIResultCard、PendingFact、KnowledgeCard、IdeaCard、ChapterSummary、RetrievalHit、EmbeddingChunk。
- 新增 domain rules：Card 状态机、PendingFact 状态机、fact_scope 判定、SourceRef validate 接口。
- 新增 application contracts 草案：StorageContract、RetrievalContract、LLMContract、IndexerContract。
- 建立 contract tests，覆盖状态机非法流转、fact_scope 排除非事实、SourceRef 基础校验。
- 更新或新增架构说明，明确 SQLite/SelectionAI/SourceRef 三个硬决策。

## 3. 本阶段不要实现

- 不要做编辑器 UI。
- 不要调用真实 LLM。
- 不要做 SQLite/FTS/vector。
- 不要实现 Agent Chat。
- 不要做知识库复杂页面。

## 4. 涉及模块

- `domain/models`
- `domain/rules`
- `application/contracts`
- `tests/unit/domain`
- `tests/unit/application`

## 5. 涉及数据对象

- Chapter
- ChapterManifest
- SourceRef
- AIResultCard
- PendingFact
- KnowledgeCard
- IdeaCard
- ChapterSummary
- RetrievalHit
- EmbeddingChunk

## 6. AI 工作流

不涉及 AI 调用，只定义 AIResultCard 和 Selection workflow 输入输出契约。

## 7. 验收标准

- 所有核心数据对象可被导入并通过类型/校验测试。
- 非法状态流转会失败。
- fact_scope 默认排除 PendingFact、IdeaCard、AIResultCard。
- SourceRef 不允许指向 generated SQLite。
- 文档明确 SQLite 是 generated projection、Selection AI 是 Service、SourceRef 是段落级。

## 8. 测试要求

- schema 校验测试
- 状态机非法流转测试
- fact_scope 防污染测试
- SourceRef validate 基础测试

## 9. 主要风险

- 模型过度设计导致 Phase 1-3 开发慢。
- 契约太松导致后续卡片/检索各写一套。

## 10. 给 Codex 的任务拆解建议

- 检查现有架构目录。
- 新增 domain 模型文件。
- 新增 rules。
- 新增 contracts。
- 补 contract tests。
- 返回模型字段和状态机证据。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
