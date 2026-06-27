# 停止条件

## 通用停止条件

出现以下情况必须停止并报告：

1. 当前仓库结构与架构基线严重不一致。
2. 需要引入 project_id / novel_id 才能继续。
3. 需要让 SQLite 保存唯一用户资产才方便实现。
4. 需要让 Selection AI 进入 AgentRegistry 才方便实现。
5. 需要让 PendingFact 或 IdeaCard 进入 fact_scope 才方便实现。
6. 需要前端直接读写 project_assets。
7. 需要 API route 直接读写文件/SQLite/LLM。
8. 本阶段验收需要依赖后续 Phase 大功能。
9. 测试可能污染真实用户数据。
10. 发生无法解释的数据丢失风险。

## Phase 完成后停止

当前 Phase 验收标准满足后必须停止，不要顺手开始下一 Phase。

## 不确定时的处理

先返回“冲突/决策请求”，列出：

- 当前事实
- 任务包要求
- 冲突点
- 推荐方案
- 不推荐方案
- 继续开发的最小前置决策
