---
name: prd-design-generator
description: 技术设计文档生成工具，适用于 cc-sdd 需求规格确认后，为 .kiro 规格生成 design.md 并按需执行设计评审。
---

# PRD Design Generator

## 定位

为 `.kiro/specs/{版本号}/{功能名}/` 下的规格生成 `design.md`，并可按用户选择执行设计评审。

## 输入

- 规格名称：`{版本号}/{功能名}`。
- 支持通配符，例如 `V1.0/*`。

## 输入校验

1. 规格名称非空。
2. `.kiro/specs/` 下存在匹配目录。
3. 每个匹配目录都有 `spec.json`。
4. `spec.json` 的 `stage` 为 `requirements`、`design`、`tasks`、`implementing` 或 `completed`。
5. `requirements.md` 存在且非空。
6. 匹配多个目录时，先展示清单并等待用户确认。

## 设计生成

参照 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `spec-design` 模板生成 `design.md`。

设计文档必须覆盖：

- 当前太初架构落点：`api`、`application`、`domain`、`infrastructure`、`web` 中涉及的目录。
- 依赖方向，尤其是 `domain` 不得依赖 Agent、LangGraph、LLM、MCP 或具体存储。
- 数据模型、接口契约、状态流转和验证策略。
- 前端变更必须引用 `TAICHU_DESIGN.md` 和 `.agents/skills/taichu-ui-components/SKILL.md`。
- 启动关键文件若被影响，必须列出 `start.bat` 验证要求。

生成后更新 `spec.json` 的 `stage` 与 `approvals.design`。

## 设计评审

设计生成后询问用户是否执行设计评审。

评审重点：

- 是否覆盖全部需求。
- 是否符合太初单本小说边界。
- 是否维护分层依赖。
- 是否避免僵尸依赖、孤儿配置和旧实现残留。
- 是否给出可运行验证命令。

## 后续提示

设计确认后，引导使用 `prd-spec-impl` 生成任务并实施。

## 异常处理

| 场景 | 处理 |
|---|---|
| 规格不存在 | 提示先执行 `prd-to-ccsdd` |
| 需求未生成 | 提示先完成 `spec-requirements` |
| `spec.json` 状态不足 | 停止并展示当前状态 |
| 匹配多个规格 | 展示清单，等待确认后批量执行 |
