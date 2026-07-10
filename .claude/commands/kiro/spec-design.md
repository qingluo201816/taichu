# /kiro:spec-design

## 用途

根据已审批需求生成 `design.md`。

## 输入

- `requirements.md`
- `spec.json`
- 当前项目规则和相关代码上下文。

## 执行要求

1. 读取 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `3.4 spec-design`。
2. 读取 `.kiro/settings/rules/design-principles.md`。
3. 涉及前端时读取 `TAICHU_DESIGN.md` 和 `.agents/skills/taichu-ui-components/SKILL.md`。
4. 生成简体中文设计文档。
5. 更新 `spec.json.stage` 为 `design`。

## 输出

中文摘要：

- 受影响模块。
- 关键设计决策。
- 验证命令。
- 风险与待确认项。
