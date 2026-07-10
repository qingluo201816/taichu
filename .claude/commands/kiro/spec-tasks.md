# /kiro:spec-tasks

## 用途

根据 `requirements.md` 和 `design.md` 生成 `tasks.md`。

## 输入

- `requirements.md`
- `design.md`
- `spec.json`

## 执行要求

1. 读取 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `3.6 spec-tasks`。
2. 读取 `.kiro/settings/rules/tasks-generation.md`。
3. 标题固定为 `# 实现计划`。
4. 使用 `- [ ]` 复选框。
5. 每个任务包含需求来源、边界范围和验证方式。
6. 更新 `spec.json.stage` 为 `tasks`。

## 输出

中文摘要：

- 任务数量。
- 测试与验证任务。
- 需要用户确认后才能实现。
