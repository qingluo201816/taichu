---
name: prd-to-ccsdd
description: 功能点转 cc-sdd 规格工具，适用于从功能点清单生成 .kiro 规格目录，并推进 spec-init 与 spec-requirements 阶段。
---

# PRD to cc-sdd

## 定位

从 `out/{版本号}/功能点清单.md` 提取功能点，为每个大需求模块创建 `.kiro/specs/{版本号}/{功能名}/`，并生成需求文档。

## 输入

- 功能点清单路径：`out/{版本号}/功能点清单.md`。
- 或由 `prd-spec-develop` 传入的规格名称列表。

## 输入校验

1. 功能点清单存在，或规格名称列表非空。
2. 功能点清单中必须包含功能点条目。
3. 规格名称不得与已有目录冲突；同名时先询问用户是否复用、改名或停止。

## 禁止行为

- 禁止模拟 Kiro 命令效果后直接宣称命令已执行。
- 禁止跳过名称唯一性检查。
- 禁止生成英文用户文档；`requirements.md`、`design.md`、`tasks.md` 主体必须是简体中文。
- 禁止引入多小说、多租户或 `project_id` 设计。

## 执行流程

### 1. 读取功能点清单

提取：

- 版本号。
- PRD 文件名。
- 大需求模块。
- 功能点序号、名称、所属模块、需求描述、前置条件、预期结果、依赖、代码影响。

### 2. 规格初始化

每个 PRD 一级需求模块对应一个规格目录：

```text
.kiro/specs/{版本号}/{功能名}/
├── spec.json
├── requirements.md
├── design.md
└── tasks.md
```

参照 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `spec-init` 模板生成 `spec.json`。`spec.json` 必须包含：

- `name`
- `version`
- `stage`
- `language`，值为 `zh-CN`
- `source_prd`
- `feature_points`
- `approvals`

### 3. 人工审核初始化结果

展示规格目录、规格名称和来源功能点摘要，等待用户确认。

用户可选择：

- 全部推进到需求生成。
- 选择部分规格推进。
- 暂停。

### 4. 需求文档生成

仅处理用户选中的规格。参照 `.claude/rules/KIRO_COMMAND_CALLING_SPEC.md` 的 `spec-requirements` 模板生成 `requirements.md`。

要求：

- 使用简体中文。
- EARS 固定短语 `When`、`If`、`While`、`Where`、`the system shall` 保持英文。
- 每条需求必须能追溯到功能点。
- 更新 `spec.json` 的 `stage` 与 `approvals.requirements`。

### 5. 需求审批与 Gap 分析

展示 `requirements.md` 摘要并等待用户审批。审批通过后，询问是否执行 Gap 分析，对比需求与当前代码库差距。

Gap 分析必须使用 `rg`、文件读取和现有项目规则，不使用知识图谱或外部企业系统。

## 异常处理

| 场景 | 处理 |
|---|---|
| 功能点清单不存在 | 提示先运行 `prd-plan-analyze` |
| 功能点清单为空 | 停止并提示用户确认清单 |
| 规格名冲突 | 展示冲突目录，等待用户决策 |
| 需求生成失败 | 展示错误，等待用户重试、跳过或终止 |
