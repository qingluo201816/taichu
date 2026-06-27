# Phase 5：Minimal Knowledge Base

## 1. 阶段目标

实现作者确认后的最小小说记忆 UI 和 JSON 事实源。

## 2. 本阶段要实现

- 新增 /knowledge 页面。
- 实现通用 KnowledgeCard 列表、详情、创建、编辑。
- 实现 CharacterCard 最小视图。
- 实现 PendingFact confirm / confirm-edited / ignore。
- 确认后写入 source/knowledge JSON。
- KnowledgeCard 显示 SourceRef。
- 支持 aliases。

## 3. 本阶段不要实现

- 不要做完整百科字段。
- 不要做复杂角色状态历史。
- 不要做关系图、头像、地图。
- 不要批量自动入库。

## 4. 涉及模块

- `application/services/knowledge_service.py`
- `api/routes/knowledge.py`
- `web/src/app/knowledge`
- `web/src/components/knowledge`
- `domain/rules/identity.py`

## 5. 涉及数据对象

- KnowledgeCard
- CharacterCard
- PendingFact
- EntityAlias
- SourceRef

## 6. AI 工作流

AI 不直接写 Knowledge；只通过 PendingFact confirm 流程。

## 7. 验收标准

- PendingFact 确认后生成/更新 Knowledge JSON。
- 编辑后确认可保留 SourceRef。
- Knowledge 页面不显示未确认 PendingFact 为事实。
- 别名可用于后续 exact 检索。
- 无来源时必须标 author_manual 或拒绝。

## 8. 测试要求

- 确认流程测试
- 重复实体/别名冲突测试
- 无来源规则测试
- JSON 可读测试
- fact_scope 只含 confirmed knowledge 测试

## 9. 主要风险

- 字段过早复杂化导致返工。
- 确认流程太麻烦导致用户不用。

## 10. 给 Codex 的任务拆解建议

- 实现 Knowledge repository。
- 实现 pending confirm service。
- 实现最小 CRUD API。
- 实现前端列表/详情/编辑。
- 补状态和 source_ref 测试。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
