# /kiro:spec-requirements

## 用途

根据已初始化规格生成 `requirements.md`。

## 输入

- `.kiro/specs/{版本号}/{功能名}/spec.json`
- 来源功能点。
- PRD 摘要。

## 执行要求

1. 读取 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `3.2 spec-requirements`。
2. 读取 `.kiro/settings/rules/ears-format.md`。
3. 生成简体中文需求文档。
4. 每条需求标注来源功能点。
5. 更新 `spec.json.stage` 为 `requirements`。

## 输出

中文摘要：

- 需求数量。
- 覆盖的功能点。
- 待用户审批的问题。
