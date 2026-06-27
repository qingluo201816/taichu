# Phase 8：Basic Agent Chat / Export / MVP Integration

## 1. 阶段目标

整合编辑器、卡片、收件箱、知识库、检索、导出，完成真实写作闭环验证。

## 2. 本阶段要实现

- 实现基础 Agent Chat 页面。
- Agent Chat 可选择当前章节/confirmed facts 上下文。
- Agent 输出也可转 AIResultCard。
- 实现导出 Markdown、Knowledge JSON、workspace JSONL、metadata。
- 实现 generated 删除重建入口。
- 跑完整 E2E 验收。
- 收敛首页导航，突出 editor。

## 3. 本阶段不要实现

- 不要多 Agent 可视化。
- 不要模型看板主功能。
- 不要地图/时间线。
- 不要发布/协作。

## 4. 涉及模块

- `application/agents/chat`
- `application/services/export_service.py`
- `application/services/index_service.py`
- `api/routes/agents.py`
- `api/routes/export.py`
- `web/src/app/chat`
- `web/src/app/settings 或 export入口`

## 5. 涉及数据对象

- AgentConversation
- AIResultCard
- ExportBundle
- IndexBuildJob
- SourceRef

## 6. AI 工作流

Agent Chat 是独立深度对话，可调用 retrieval；输出必须标来源或推测；不得绕过卡片/PendingFact/Knowledge 状态机。

## 7. 验收标准

- 完整跑通 13 步 MVP 验收。
- 导出文件可读。
- 删除 generated 后重建检索。
- Agent Chat 不引用待确认事实。
- 首页主入口是 editor。

## 8. 测试要求

- E2E 完整闭环测试
- 导出测试
- 重建测试
- Agent 防污染测试
- 真实/Mock LLM 冒烟测试

## 9. 主要风险

- 集成暴露前面契约漏洞。
- 导出不完整导致数据锁死。

## 10. 给 Codex 的任务拆解建议

- 改造/复用 chat agent。
- 实现 export service。
- 实现 rebuild endpoint。
- 实现 E2E fixture。
- 整理首页导航。
- 输出最终 MVP 验收报告。

## 11. 停止条件

- 本阶段验收标准满足后立即停止。
- 如果必须跨到下一 Phase 才能完成当前功能，先返回冲突报告。
- 如果发现需要违反不可变架构决策，立即停止。
