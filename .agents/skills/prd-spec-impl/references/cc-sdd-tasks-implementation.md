# cc-sdd 任务与实现规则

## 任务生成

读取已审批的 `requirements.md` 和 `design.md`，生成中文 `tasks.md`：

```markdown
# 实现计划

- [ ] 1. 任务标题
  - 需求来源：需求 1
  - 边界范围：只修改……
  - 验证：运行……
```

每项任务必须可独立执行和验证。生成后将 `spec.json.stage` 更新为 `tasks`；只有用户审批后才能设置 `approvals.tasks.completed=true`。

## 实现

用户确认任务后按以下顺序执行：

1. RED：补失败测试或明确可复现验收。
2. GREEN：实现最小可用改动。
3. REFACTOR：只做必要整理。
4. VERIFY：运行影响范围内的验证。

实现期间不得回滚用户已有改动、扩大范围或引入无关依赖。验证通过后更新 `spec.json.stage=completed`、`approvals.implementation.completed=true`，并记录验证命令与结果。
