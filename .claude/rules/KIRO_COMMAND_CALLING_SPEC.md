# Kiro 命令调用规范

## 定位

本文件定义太初项目内的 cc-sdd 规格驱动流程。这里的 Kiro 命令是 Codex 可执行的文档化调用模板，不要求存在外部 Kiro CLI。

## 目录约定

```text
.kiro/specs/{版本号}/{功能名}/
├── spec.json
├── requirements.md
├── design.md
└── tasks.md
```

`spec.json` 使用 UTF-8 JSON，建议结构：

```json
{
  "name": "功能名",
  "version": "V1.0",
  "stage": "initialized",
  "language": "zh-CN",
  "source_prd": "prd-docs/example.md",
  "feature_points": [],
  "approvals": {
    "requirements": {"completed": false},
    "design": {"completed": false},
    "tasks": {"completed": false},
    "implementation": {"completed": false}
  },
  "verification": []
}
```

阶段枚举：

- `initialized`
- `requirements`
- `design`
- `tasks`
- `implementing`
- `completed`

## 3.1 spec-init

输入：

- 版本号。
- 功能名。
- 来源 PRD。
- 该规格包含的功能点。

动作：

1. 创建 `.kiro/specs/{版本号}/{功能名}/`。
2. 写入 `spec.json`。
3. 初始化空的 `requirements.md`、`design.md`、`tasks.md`，或保留不存在状态并在后续阶段创建。

要求：

- `language` 固定为 `zh-CN`。
- 功能名使用中文业务名称；目录名允许中文。
- 不能引入工号、多人分配、工时表或企业认证字段。

## 3.2 spec-requirements

输入：

- `spec.json`。
- 来源功能点。
- PRD 摘要。

动作：

1. 生成 `requirements.md`。
2. 每条需求关联功能点序号。
3. 使用 EARS 风格描述。
4. 更新 `spec.json.stage` 为 `requirements`。
5. 更新 `approvals.requirements.completed`。

EARS 固定短语保留英文，例如：

```markdown
### 需求 1：知识卡软删除不出现在普通列表

来源功能点：1.1-1

#### 验收标准

1. When 用户删除一张知识卡, the system shall 将该知识卡标记为已删除。
2. When 用户查看普通知识卡列表, the system shall 排除已删除知识卡。
```

## 3.3 gap-analysis

输入：

- `requirements.md`。
- 当前代码库。

动作：

1. 使用 `rg` 和文件读取定位相关实现。
2. 输出需求与现状差距。
3. 标记新增、修改、删除和测试缺口。

不得使用 Graphify、Confluence 或企业内部系统。

## 3.4 spec-design

输入：

- 已审批需求。
- 当前架构规则。

动作：

1. 生成 `design.md`。
2. 描述模块落点、数据结构、接口契约、状态流转和验证策略。
3. 更新 `spec.json.stage` 为 `design`。
4. 更新 `approvals.design.completed`。

太初强制项：

- `domain` 不依赖 Agent、LangGraph、LLM、MCP 或具体存储。
- 存储、检索等跨层契约优先使用 `typing.Protocol`。
- 新增 Agent 按插件目录实现，不改已有发现逻辑。
- 前端遵循 `TAICHU_DESIGN.md`。
- 启动关键文件变更必须列出 `start.bat` 验证。

## 3.5 validate-design

设计评审检查：

- 是否覆盖全部需求。
- 是否符合单本小说边界。
- 是否保持分层依赖。
- 是否避免旧实现残留。
- 是否给出可执行验证命令。

评审结论必须为中文，并列出阻塞问题、非阻塞风险和建议修正。

## 3.6 spec-tasks

输入：

- `requirements.md`。
- `design.md`。

动作：

1. 生成 `tasks.md`。
2. 更新 `spec.json.stage` 为 `tasks`。
3. 更新 `approvals.tasks.completed`。

格式：

```markdown
# 实现计划

- [ ] 1. 任务标题
  - 需求来源：需求 1
  - 边界范围：只修改 ...
  - 验证：运行 ...
```

任务必须包含测试或验证项，不得只写实现动作。

## 3.7 spec-impl

输入：

- 已确认的 `tasks.md`。

动作：

1. RED：补失败测试或明确可复现验收。
2. GREEN：实现最小可用改动。
3. REFACTOR：必要整理。
4. VERIFY：运行相关验证。
5. 更新 `spec.json.stage` 为 `completed`。
6. 更新 `approvals.implementation.completed`。
7. 记录验证命令和结果。

实现时不得回滚用户已有改动，不得扩大范围，不得引入无关依赖。
