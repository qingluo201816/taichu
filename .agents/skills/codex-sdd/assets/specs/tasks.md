# 实现计划

## 使用规则

- 最多两层：`1`、`1.1`，不使用 `1.1.1`。
- 每个可执行任务只有一个内聚、可观察的结果。
- 每个任务末尾只列数字需求 ID。
- 需求追踪使用 `_Requirements:`，不得用章节名称或自由文本代替数字 ID。
- `(P)` 只用于边界不重叠、无数据/文件/共享状态冲突的任务。
- 并行候选必须同时写 `(P)` 与 `_Boundary:`，否则按顺序任务处理。
- `--sequential` 模式完全省略 `(P)`。
- 需要跨组依赖时写 `_Depends:`。
- `(P)` 任务必须写 `_Boundary:`。
- 涉及前后端协同时可使用 `[BE]` / `[FE]`。
- Graphify 仅在 `.graphify_root` 覆盖任务边界且节点已由源码复核时，可选记录 `_Graphify:`；
  不覆盖时只使用真实组件 `_Boundary:`，不得虚构节点或要求人工维护派生图谱。
- 不使用工时、排期、人员分工或审批任务。

## 格式

- [ ] 1. {{MAJOR_TASK_SUMMARY}}
  - {{MAJOR_SCOPE_OR_OUTCOME}}

- [ ] 1.1 {{SUB_TASK_DESCRIPTION}}
  - {{BEHAVIOR_OR_DELIVERABLE}}
  - {{CONTRACT_OR_BOUNDARY_DETAIL}}
  - {{OBSERVABLE_COMPLETION}}
  - {{VERIFICATION}}
  - _Requirements: {{REQUIREMENT_IDS}}_
  - _Boundary: {{COMPONENT_NAMES}}_
  - _Depends: {{TASK_IDS}}_

- [ ] 1.2 (P) [BE] {{PARALLEL_BACKEND_TASK}}
  - {{DETAIL}}
  - {{OBSERVABLE_COMPLETION}}
  - {{VERIFICATION}}
  - _Requirements: {{REQUIREMENT_IDS}}_
  - _Boundary: {{NON_OVERLAPPING_BACKEND_BOUNDARY}}_

- [ ] 1.3 (P) [FE] {{PARALLEL_FRONTEND_TASK}}
  - {{DETAIL}}
  - {{OBSERVABLE_COMPLETION}}
  - {{VERIFICATION}}
  - _Requirements: {{REQUIREMENT_IDS}}_
  - _Boundary: {{NON_OVERLAPPING_FRONTEND_BOUNDARY}}_

- [ ] 2. 集成与验证

- [ ] 2.1 {{INTEGRATION_TASK}}
  - {{CROSS_BOUNDARY_CONNECTION}}
  - {{ERROR_AND_RECOVERY_CHECK}}
  - {{OBSERVABLE_COMPLETION}}
  - {{REGRESSION_OR_ACCEPTANCE_VERIFICATION}}
  - _Requirements: {{REQUIREMENT_IDS}}_
  - _Depends: 1.1, 1.2, 1.3_

## 可选测试覆盖

仅当某项是可在 MVP 后补充、且不影响核心实现或集成验收的辅助测试时，才使用：

```text
- [ ]* 3.1 {{DEFERRABLE_TEST_TASK}}
  - 直接引用相应验收标准和延期理由
  - _Requirements: {{REQUIREMENT_IDS}}_
```

不得把实现、数据迁移、安全、回归或集成关键验证标为可选。

## 计划收尾必须覆盖

- 需求与设计全部映射；
- TDD/测试；
- 数据迁移与回滚（适用时）；
- 被替代旧实现清理；
- 依赖、配置和文档联动；
- 启动关键文件变化时的 `start.bat` 验证；
- 前端固定端口与桌面浏览器验收；
- 实现报告和独立实现验证。
