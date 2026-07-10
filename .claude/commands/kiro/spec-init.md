# /kiro:spec-init

## 用途

初始化 `.kiro/specs/{版本号}/{功能名}/` 规格目录。

## 输入

- 版本号。
- 功能名。
- 来源 PRD。
- 功能点列表。

## 执行要求

1. 读取 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `3.1 spec-init`。
2. 创建规格目录。
3. 生成 `spec.json`。
4. `language` 设置为 `zh-CN`。
5. 不写入工号、工时、多人分配、Confluence 或 Graphify 字段。

## 输出

中文摘要：

- 规格路径。
- 功能点数量。
- 当前阶段。
- 下一步建议。
