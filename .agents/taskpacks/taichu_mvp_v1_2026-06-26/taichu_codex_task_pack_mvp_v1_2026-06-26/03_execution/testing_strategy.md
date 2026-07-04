# 测试策略

## 1. 后端测试

- domain：状态机、SourceRef、fact_scope、identity。
- application：Service 用例、PendingFact 确认、AI 卡片 action、检索 scope。
- infrastructure：Markdown/JSON/JSONL 读写、SQLite projection 重建、FTS、chunker。
- api：请求校验、响应 schema、非法状态、scope 默认值。

## 2. 前端测试

- API client 封装。
- 编辑器加载/保存。
- 章节导航。
- 选区捕获。
- AI 卡片 action。
- 收件箱筛选。
- Knowledge 确认流程。

## 3. E2E 验收

MVP 完整验收流程：

1. 创建/导入 3 章 Markdown。
2. 创建少量 Knowledge JSON。
3. 打开当前章节写作并保存。
4. 使用选区问答。
5. 使用选区设定补充。
6. 使用选区续写 500 字。
7. 插入一条正文候选。
8. 保存一条建议为灵感。
9. 生成一条 PendingFact。
10. 确认 PendingFact 入 Knowledge。
11. 检索该 Knowledge 并显示来源。
12. 验证未确认内容不进入 fact_scope。
13. 导出 Markdown/JSON/JSONL。
14. 删除 generated 后重建索引。

## 4. 数据安全测试

- 保存中断。
- 重复确认 PendingFact。
- generated 删除。
- 测试语料与原创语料隔离。
- SourceRef stale。
- LLM 返回非 JSON。
- LLM 超时。
