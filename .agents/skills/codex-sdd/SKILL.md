---
name: codex-sdd
description: >-
  Codex 规格驱动开发编排工具。用于新功能或较大变更的规格初始化、EARS 需求、差距分析、技术设计、
  设计评审、任务拆分、TDD 实现与独立校验；支持 spec-init、spec-requirements、validate-gap、
  spec-design、validate-design、spec-tasks、spec-impl、validate-impl、run、status、resume 和
  project-context，并通过 .sdd/ 在上下文压缩或会话重启后恢复。
---

# Codex SDD

## 目标

在不压缩阶段规则的前提下，把规格流程迁移为 Codex 可发现、可委派、可恢复、可独立校验的项目级工作流。

运行事实位于 `.sdd/`。项目事实始终以当前代码、根 `AGENTS.md`、`README.md`、`DESIGN.md`、局部规则和明确标为当前的资料为准。

## 调用

```text
$codex-sdd spec-init <版本号> <大需求模块名称> <原始需求描述>
$codex-sdd spec-requirements <版本号>/<大需求模块名称>
$codex-sdd validate-gap <版本号>/<大需求模块名称>
$codex-sdd spec-design <版本号>/<大需求模块名称>
$codex-sdd validate-design <版本号>/<大需求模块名称>
$codex-sdd spec-tasks <版本号>/<大需求模块名称> [--sequential]
$codex-sdd spec-impl <版本号>/<大需求模块名称> [任务编号]
$codex-sdd validate-impl [<版本号>/<大需求模块名称>] [任务编号]
$codex-sdd run <版本号> <大需求模块名称> <原始需求描述> [--impl] [--sequential]
$codex-sdd status [<版本号>/<大需求模块名称>]
$codex-sdd resume [<版本号>/<大需求模块名称>]
$codex-sdd project-context [--audit-only]
$codex-sdd project-context-custom <主题> [--audit-only]
```

规格标识固定为 `{版本号}/{大需求模块名称}`。个人项目不含工号。不得静默发明版本号、追加冲突后缀或把中文模块名改成英文 slug。

## 每次运行先读

1. 根 `AGENTS.md`、`README.md` 和本次目标适用的局部强制规则。
2. [命令调用规范](references/orchestration/command-calling-spec.md)。
3. [Skill 编排规范](references/orchestration/skill-orchestrator-pattern.md)。
4. [状态与产物契约](references/state-contract.md)。
5. 本次操作对应的 `references/commands/<operation>.md`。
6. 被委派角色对应的 `references/agents/<role>.md`。
7. 命令明确列出的每一份规则与模板。

不得用旧的摘要参考文件替代一对一规则。框架资源映射与适配依据见 [迁移账本](references/migration-ledger.md)。

## 操作路由

### `spec-init`

- 命令：[spec-init](references/commands/spec-init.md)；执行者：主 Agent。
- 必读：状态契约、`assets/specs/init.json`、`requirements-init.md`。

### `spec-requirements`

- 命令：[spec-requirements](references/commands/spec-requirements.md)；Agent：`codex_sdd_requirements`。
- 必读：资产探查、EARS、需求门禁、需求模板。

### `validate-gap`

- 命令：[validate-gap](references/commands/validate-gap.md)；Agent：`codex_sdd_gap_validator`。
- 必读：差距分析、资产探查。

### `spec-design`

- 命令：[spec-design](references/commands/spec-design.md)；Agent：`codex_sdd_design`。
- 必读：发现、综合、设计原则、设计门禁、研究/设计模板。

### `validate-design`

- 命令：[validate-design](references/commands/validate-design.md)；Agent：`codex_sdd_design_reviewer`。
- 必读：设计评审与设计门禁。

### `spec-tasks`

- 命令：[spec-tasks](references/commands/spec-tasks.md)；Agent：`codex_sdd_tasks`。
- 必读：任务生成、并行分析、任务模板。

### `spec-impl`

- 命令：[spec-impl](references/commands/spec-impl.md)；Agent：`codex_sdd_impl`。
- 必读：TDD 实现职责、任务规则、实现报告模板。

### `validate-impl`

- 命令：[validate-impl](references/commands/validate-impl.md)；Agent：`codex_sdd_impl_validator`。
- 必读：独立门禁、验证报告模板。

### 独立需求/设计门禁

- 由命令内部调用 `codex_sdd_validator`。
- 必读：独立 Agent、独立门禁、discovery/报告模板。

### `run`

- 命令：[自动编排](references/commands/spec-quick.md)；按阶段选择 Agent。
- 不跳过任何标准门禁。

### `status` / `resume`

- 命令：[状态与恢复](references/commands/spec-status.md)；执行者：主 Agent。
- 必读：状态契约。

### `project-context`

- 命令：[项目事实审计](references/commands/steering.md)；Agent：`codex_sdd_context_sync`。
- 必读：项目事实维护原则。

### `project-context-custom`

- 命令：[专门事实](references/commands/steering-custom.md)；Agent：`codex_sdd_context_custom`。
- 必读：项目事实维护原则与对应结构模板。

## 完整规则目录

### Agent 定义

- [需求](references/agents/spec-requirements.md)
- [差距分析](references/agents/validate-gap.md)
- [技术设计](references/agents/spec-design.md)
- [设计评审](references/agents/validate-design.md)
- [任务规划](references/agents/spec-tasks.md)
- [TDD 实现](references/agents/spec-impl.md)
- [实现验证](references/agents/validate-impl.md)
- [独立校验](references/agents/spec-independent-validator.md)
- [项目事实同步](references/agents/steering.md)
- [专门项目事实](references/agents/steering-custom.md)

### 阶段规则

- [现有资产探查](references/rules/asset-discovery.md)
- [EARS](references/rules/ears-format.md)
- [需求审查门禁](references/rules/requirements-review-gate.md)
- [完整设计发现](references/rules/design-discovery-full.md)
- [轻量设计发现](references/rules/design-discovery-light.md)
- [设计综合](references/rules/design-synthesis.md)
- [设计原则](references/rules/design-principles.md)
- [设计草稿门禁](references/rules/design-review-gate.md)
- [设计质量评审](references/rules/design-review.md)
- [差距分析](references/rules/gap-analysis.md)
- [任务生成](references/rules/tasks-generation.md)
- [并行任务分析](references/rules/tasks-parallel-analysis.md)
- [独立校验门禁](references/rules/independent-validation-gate.md)
- [前端探索](references/rules/frontend-exploration-rules.md)
- [项目事实维护](references/rules/steering-principles.md)

### 模板

规格模板在 `assets/specs/`：

- `init.json`
- `requirements-init.md`
- `requirements.md`
- `research.md`
- `design.md`
- `frontend-design-section.md`
- `tasks.md`
- `validation-discovery.md`
- `validation-report.md`
- `design-review-report.md`
- `implementation-report.md`

`assets/project-context/` 的十份文件仅是项目事实审计结构提纲，不是太初当前事实，不得直接复制落盘。

## 自动流程

`run` 默认自动推进到 `tasks_ready`：

```text
初始化
→ 需求生成
→ 独立需求校验
→ 存量差距分析
→ 技术设计
→ 设计质量评审
→ 独立设计校验
→ 任务生成
```

只有用户明确要求实现或带 `--impl` 时继续：

```text
→ TDD 实现
→ 独立实现验证
→ completed
```

阶段之间不弹出例行批准菜单。每一步必须完成产物检查、门禁、状态登记和 `state.py validate` 才可自动推进。

## 暂停边界

只有以下情况暂停：

- 会实质改变范围的歧义/规则冲突无法从项目事实消除；
- 必需信息只有用户能提供；
- 同一独立门禁两轮定向修复仍 FAIL；
- 下一步超出用户授权或需要重要外部/破坏性动作；
- 重叠用户改动无法安全保留；
- 实现没有明确授权。

“进入下一阶段”“建议审阅”“文档已生成”不是暂停理由。

## 独立校验

requirements/design 必须使用新上下文的 `codex_sdd_validator`：

1. 阶段一禁止读取目标任何部分。
2. 从允许上游、规则、代码、测试和配置独立发现。
3. 先写 `validation-discovery-<mode>.md`。
4. 再读目标并输出独立报告。
5. 报告记录目标完整 SHA-256。
6. 报告最后一行精确 `结论：PASS` 或 `结论：FAIL`。
7. discovery 保留。
8. FAIL 退回原生成角色，重新创建独立校验上下文；最多两轮。

生成角色不能给自己最终 PASS。

## 持久化状态

在仓库根运行：

```powershell
uv run python .agents/skills/codex-sdd/scripts/state.py show --spec <规格标识>
uv run python .agents/skills/codex-sdd/scripts/state.py validate --spec <规格标识>
```

所有阶段、目标、产物、校验、对象哈希、阻塞和任务状态以 `.sdd/` 为准。聊天待办不可替代磁盘状态。恢复先 `show`/`validate`，从第一个证据不完整阶段继续。

## Graphify

- 先读取 `.graphify_root`。
- 只有图谱覆盖目标时使用当前 `query/path/explain`。
- 引用 `source_location` 并源码复核。
- 不覆盖、过期或不可用时使用 `rg --files`、`rg -n`、源码和测试。
- 不使用个人项目不存在的代码图谱服务或旧脚本。
- Graphify 是可重建派生索引，不是业务事实源。

## 前端

涉及 `web/` 的创建、修改、评审或设计：

1. 完整读取根 `DESIGN.md`。
2. 使用 `taichu-ui-components` Skill。
3. 执行前端探索规则。
4. 只使用 Next.js + React + shadcn/ui + Tailwind。
5. 只面向桌面浏览器。
6. 用户可见文案中文。
7. 验证固定使用 `localhost:3000` 与 `127.0.0.1:8000`。
8. 不引入移动端、Vue 或失真模板规则。

## 框架修改门禁

任何修改本 Skill、规则、模板、状态脚本或 `.codex/agents/` 后运行：

```powershell
uv run python .agents/skills/codex-sdd/scripts/validate_framework.py
uv run python .agents/skills/codex-sdd/scripts/audit_fidelity.py
uv run python .agents/skills/codex-sdd/scripts/self_test.py
uv run python -X utf8 `
  "$env:USERPROFILE\.codex\skills\.system\skill-creator\scripts\quick_validate.py" `
  .agents/skills/codex-sdd
```

任一失败即框架不完整，不得宣称迁移完成。
