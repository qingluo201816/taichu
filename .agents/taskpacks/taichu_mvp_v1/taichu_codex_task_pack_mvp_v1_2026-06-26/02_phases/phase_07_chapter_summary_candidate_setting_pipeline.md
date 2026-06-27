# Phase 7：Chapter Summary / Candidate Setting Pipeline

## 1. 阶段目标

实现章节整理草稿和候选设定管线，但不自动污染知识库。

## 2. 本阶段要实现

- 新增“整理本章”工作流。
- 生成 ChapterSummary draft。
- 提取 key_events、character_changes、new_setting_candidates、foreshadow_candidates、next_chapter_hooks。
- 候选设定可转 PendingFact。
- 摘要可编辑确认/忽略。
- 整理结果以章节整理卡展示。

## 3. 本阶段不要实现

- 不要后台自动全书摘要。
- 不要批量自动写 Knowledge。
- 不要复杂时间线。
- 不要自动改角色卡状态。

## 4. 涉及模块

- `application/services/chapter_summary_service.py`
- `application/workflows/summary`
- `api/routes/chapters.py 或 summaries.py`
- `web/src/components/ai-card/summary`

## 5. 涉及数据对象

- ChapterSummary
- PendingFact
- CharacterStateCandidate
- ForeshadowCandidate
- SourceRef

## 6. AI 工作流

输入当前章节 Markdown、已有 confirmed knowledge、检索证据；输出 ChapterSummary draft + candidates；作者确认后才沉淀。

## 7. 验收标准

- 章节整理结果是 draft。
- 候选设定进入 PendingFact。
- 确认摘要不写 Knowledge。
- 角色状态变化只是候选。
- 未确认候选不进入 fact_scope。

## 8. 测试要求

- 空章节测试
- 超长章节分段测试
- 重复候选测试
- 摘要确认/忽略测试
- 候选防污染测试

## 9. 主要风险

- 摘要噪音多。
- 角色变化误判。
- 用户确认成本过高。

## 10. 给 Codex 的任务拆解建议

- 实现 summary schema。
- 实现 prompt/workflow。
- 实现 summary repository JSONL。
- 实现整理卡 UI。
- 实现候选转 PendingFact。
- 补防污染测试。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
