# cc-sdd 初始化与需求规则

## 目录和状态

每个规格使用以下目录：

```text
.kiro/specs/{版本号}/{功能名}/
├── spec.json
├── requirements.md
├── design.md
└── tasks.md
```

`spec.json` 使用 UTF-8 JSON，阶段只能是：

- `initialized`
- `requirements`
- `design`
- `tasks`
- `implementing`
- `completed`

至少保存 `name`、`version`、`stage`、`language`、`source_prd`、`feature_points`、`approvals` 和 `verification`。`language` 固定为 `zh-CN`。

## 初始化

1. 检查规格名称唯一性。
2. 创建 `.kiro/specs/{版本号}/{功能名}/`。
3. 写入 `spec.json`，阶段为 `initialized`。
4. 后续阶段需要时再创建 Markdown 文件，不为维持空目录创建 `.gitkeep`。

不得加入工号、人员分配、工时表、企业认证或多租户字段。

## 需求生成

1. 读取来源功能点和 PRD 摘要。
2. 生成中文 `requirements.md`。
3. 每条需求关联来源功能点。
4. 按 `ears-format.md` 编写可验证验收标准。
5. 更新 `spec.json.stage` 为 `requirements`。
6. 仅在用户审批后设置 `approvals.requirements.completed=true`。

## Gap 分析

使用 `rg` 和文件读取对比需求与当前代码，标记新增、修改、删除和测试缺口。不得依赖 Graphify、Confluence 或其他企业内部系统。
