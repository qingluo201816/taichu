# `spec-tasks`：实现任务生成

## 使命

将已独立校验的需求与设计转换为依赖清晰、边界明确、可恢复、可独立验证的实现任务。

## 参数

```text
$codex-sdd spec-tasks <版本号>/<大需求模块名称> [--sequential]
```

默认分析安全并行性；`--sequential` 完全省略 `(P)`。

## 前置门禁

1. `requirements.md`、`design.md` 均存在。
2. 需求和设计最近独立报告均为 `结论：PASS`。
3. 两份报告的对象哈希与当前目标文件一致。
4. `spec.json.phase` 至少为 `design_validated`。
5. `state.py validate` 通过。

任何门禁失败都返回对应上游阶段，不允许通过修改状态字段绕过。

## 必须读取

- 根 `AGENTS.md`；
- `requirements.md`、`design.md`；
- 两份独立 PASS 报告；
- `references/agents/spec-tasks.md`；
- `references/rules/tasks-generation.md`；
- 非顺序模式下的 `references/rules/tasks-parallel-analysis.md`；
- `assets/specs/tasks.md`；
- `references/state-contract.md`；
- 已有 `tasks.md`（merge/repair 时）。

## 子 Agent 调用

角色：`codex_sdd_tasks`。

```text
operation: spec-tasks
spec_id: <id>
spec_dir: <dir>
mode: generate | merge | repair
sequential: true | false
input_artifacts:
  - requirements.md
  - design.md
  - independent-validation-report-requirements.md
  - independent-validation-report-design.md
expected_outputs:
  - tasks.md
forbidden_writes:
  - spec.json
  - .sdd/state.json
  - tasks-status.json
  - requirements.md
  - design.md
  - 业务代码
```

## 任务计划门禁

写正式文件前必须确认：

- 所有数字需求 ID 至少映射到一个任务。
- 所有设计组件、接口、集成点、运行前提、迁移、旧实现清理和验证关注点均有任务。
- 每个可执行任务只承诺一个内聚、可观察的完成结果。
- 最多两层编号，主任务和子任务不重复。
- 跨边界工作是显式集成任务。
- `(P)` 任务声明非重叠 `_Boundary:`，且无数据、文件或共享状态冲突。
- 非显然依赖使用 `_Depends:`。
- 必需实现或集成验证不得标为可选。
- 不包含人工工时、日期排期、人员分工、审批、部署发布或营销任务。
- 草稿最多两轮本地修复；真正规格空白返回上游。

## 主 Agent 收尾

1. 检查任务 ID 与需求映射。
2. 检查所有可执行任务包含可观察完成条件和验证方式。
3. 调用状态脚本推进到 `tasks_ready` 并登记 `tasks.md`。
4. 让状态脚本创建/同步 `tasks-status.json`；不得手工伪造完成。
5. 运行 `state.py validate`。
6. 若目标只到规格阶段，结束；只有用户原始授权包含实现时才进入 `spec-impl`。

## 严格约束

- 任务描述以能力和结果为主，物理位置、接口与文件来源于 `design.md`，不得凭空发明。
- 任务粒度按“可单独完成并验证的结果”判断，不按 1–3 小时或其他人工时长判断。
- 任务必须为当前范围服务，不为假设未来添加空壳抽象。
- 不把“补文档”“等待审批”当作实现任务；项目强制文档联动可作为对应代码任务的收尾检查。
- 不因自动流程而自动进入未经用户授权的业务实现。

## 成功输出

```text
执行状态：成功
任务文件：.../tasks.md
主任务：N
可执行任务：M
需求覆盖：N/N
并行候选：...
状态：tasks_ready
下一步：已授权实现则自动继续，否则结束
```
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 保留任务生成、覆盖、依赖和并行分析；批准字段改为需求/设计独立 PASS，不输出工时估算。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 为规格生成实现任务清单 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <功能名称> [-y] [--sequential] | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
实现任务生成器
解析参数
功能名称: $1
自动批准标志: $2（可选，"-y"）
顺序模式标志: $3（可选，"--sequential"）
验证
检查设计是否已完成:

验证 .sdd/specs/$1/ 存在
验证 .sdd/specs/$1/design.md 存在
确定 sequential = ($3 == "--sequential")
如果验证失败，提示用户先完成设计阶段。

调用子 Agent
将任务生成委托给 spec-tasks-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="spec-tasks-agent",
  description="生成实现任务",
  prompt="""
Feature: $1
Spec directory: .sdd/specs/$1/
Auto-approve: {true if $2 == "-y", else false}
Sequential mode: {true if sequential else false}

File patterns to read:
- .sdd/specs/$1/*.{json,md}
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料
- .agents/skills/codex-sdd/references/rules/tasks-generation.md
- .agents/skills/codex-sdd/references/rules/tasks-parallel-analysis.md (include only when sequential mode is false)
- .agents/skills/codex-sdd/assets/specs/tasks.md

Mode: {generate or merge based on tasks.md existence}
Instruction highlights:
- Map all requirements to tasks and list requirement IDs only (comma-separated) without extra narration
- Promote single actionable sub-tasks to major tasks and keep container summaries concise
- Apply `(P)` markers only when parallel criteria met (omit in sequential mode)
- Mark optional acceptance-criteria-focused test coverage subtasks with `- [ ]*` only when deferrable post-MVP
"""
)
显示结果
向用户展示子 Agent 的摘要，然后提供下一步指导:

下一阶段: 实现
开始实现前:

重要: 在运行 $codex-sdd spec-impl 前清理对话历史并释放上下文
这适用于开始第一个任务或在任务之间切换
新鲜的上下文确保干净的状态和正确的任务焦点
如果任务计划已生成且需求、设计门禁有效：

执行特定任务: $codex-sdd spec-impl $1 1.1（推荐：每个任务之间清理上下文）
执行多个任务: $codex-sdd spec-impl $1 1.1,1.2（谨慎使用，任务之间清理上下文）
不带参数: $codex-sdd spec-impl $1（执行所有待处理任务 - 不推荐，因为上下文膨胀）
如果需要修改:

提供反馈并重新运行 $codex-sdd spec-tasks $1
现有任务将作为参考（合并模式）
注意: 实现阶段将引导你以适当的上下文和验证执行任务。
~~~
