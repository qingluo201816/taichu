# /kiro:spec-impl

## 用途

根据用户确认的 `tasks.md` 执行 TDD 实现和验证。

## 输入

- `tasks.md`
- `requirements.md`
- `design.md`
- `spec.json`

## 执行要求

1. 读取 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `3.7 spec-impl`。
2. 先确认用户已批准任务清单。
3. 按 RED、GREEN、REFACTOR、VERIFY 执行。
4. 不回滚用户已有改动。
5. 不扩大任务范围。
6. 验证通过后更新 `spec.json.stage` 为 `completed`。

## 输出

中文实现报告：

- 完成任务。
- 新增文件。
- 修改文件。
- 验证命令和结果。
- 未完成项或风险。
