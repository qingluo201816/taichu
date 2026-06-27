# Phase 6：Hybrid Retrieval / Evidence Answer

## 1. 阶段目标

实现可溯源检索：exact + FTS + vector-lite，默认只读 fact_scope，回答/证据必须带 SourceRef。

## 2. 本阶段要实现

- 实现 EntityAlias exact 检索。
- 实现 SQLite FTS projection。
- 实现中文短实体处理策略。
- 实现 EmbeddingChunk projection 和 vector-lite。
- 实现 HybridRetrievalService。
- 实现 RetrievalHit 统一返回。
- 实现证据卡 UI。
- 实现 rebuild generated/index API/命令。
- fact_scope 默认只索引章节和 confirmed knowledge。

## 3. 本阶段不要实现

- 不要接独立向量数据库。
- 不要做复杂 reranker。
- 不要做全自动冲突检查。
- 不要跨小说检索。

## 4. 涉及模块

- `application/services/retrieval_service.py`
- `application/contracts/retrieval.py`
- `infrastructure/retrieval`
- `infrastructure/indexing`
- `api/routes/retrieval.py`
- `web/src/components/ai-card/evidence`

## 5. 涉及数据对象

- RetrievalQuery
- RetrievalHit
- EmbeddingChunk
- EntityAlias
- SourceRef
- IndexScope

## 6. AI 工作流

AI 可调用 retrieval 获取证据；无证据时回答必须标推测。

## 7. 验收标准

- 确认 Knowledge 能被检索并显示来源。
- PendingFact/IdeaCard/未采纳 AI 卡不能被 fact_scope 检索。
- 2-4 字短名能通过 exact/alias 查到。
- 删除 generated 后可重建。
- RetrievalHit 均带 SourceRef。

## 8. 测试要求

- 短名检索测试
- 别名测试
- 同名实体测试
- fact_scope 防污染测试
- generated 删除重建测试
- SourceRef stale 测试

## 9. 主要风险

- 中文 FTS 漏召回。
- SourceRef 定位不准。
- vector-lite 质量有限。

## 10. 给 Codex 的任务拆解建议

- 设计 SQLite projection schema。
- 实现 indexer。
- 实现 exact/fts/vector/hybrid。
- 实现 rebuild。
- 实现证据卡。
- 补检索测试。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
