# `spec-impl`：测试驱动实现

## 使命

在用户已授权的实现范围内，按已校验规格与任务执行测试驱动实现，保留无关工作树改动，清理被替代的旧实现，并留下可独立复验的证据。

## 参数

```text
$codex-sdd spec-impl <版本号>/<大需求模块名称> [任务编号列表]
```

任务编号可为单个 `1.1` 或逗号分隔列表；不提供时执行所有尚未完成且属于本次授权范围的任务。

## 授权与前置门禁

1. 用户原始请求明确包含“实现/开发/修复”，或显式使用 `--impl`。
2. `spec.json.phase` 至少为 `tasks_ready`。
3. `requirements.md`、`design.md`、`tasks.md` 和两份文档独立 PASS 报告存在且哈希有效。
4. `tasks-status.json` 与 `tasks.md` ID 一致。
5. 当前工作树已检查；与任务重叠的未知改动需先解决。
6. `state.py validate` 通过。

未获实现授权时停止在 `tasks_ready`，不得以自动模式扩大范围。

## 必须读取

- 根 `AGENTS.md`、`README.md` 和适用的局部规则；
- 当前 `git status` 与目标文件差异；
- `requirements.md`、`design.md`、`tasks.md`、`tasks-status.json`；
- 两份文档独立 PASS 报告；
- `references/agents/spec-impl.md`；
- `references/rules/tasks-generation.md`；
- 涉及前端时读取根 `DESIGN.md` 和 `taichu-ui-components` Skill；
- 涉及 `docs/` 或项目 Skill 时读取对应 `rule.md`。

## 任务选择

1. 从状态文件读取已完成任务，核对代码和证据后跳过。
2. 显式任务列表只执行指定任务及其未完成前置依赖。
3. 无任务列表时按依赖顺序执行所有待办。
4. `(P)` 只表示计划上可并行；实际执行前重新检查文件和共享状态冲突。
5. 每个任务开始前用状态脚本标记 `in_progress`。

## 子 Agent 调用

角色：`codex_sdd_impl`。

```text
operation: spec-impl
spec_id: <id>
spec_dir: <dir>
target_tasks: <ids | all pending>
tdd_mode: strict
input_artifacts:
  - requirements.md
  - design.md
  - tasks.md
  - tasks-status.json
expected_outputs:
  - 业务代码与测试
  - implementation-report.md
forbidden_actions:
  - 回滚或覆盖无关用户改动
  - 提交、推送、发布
  - 删除重要业务数据
  - 自行判定最终 PASS
```

## 每个任务的强制循环

### RED

- 先写或确定一个能暴露缺失行为的失败验证。
- 运行最窄测试并确认失败原因与目标行为一致。
- 若现有代码已满足行为，记录证据并补足缺失回归测试，不伪造失败。

### GREEN

- 编写使当前验证通过的最小完整实现。
- 不引入当前任务不需要的抽象、兼容层或未来占位。
- 遵守 design.md 的边界、依赖方向和契约。

### REFACTOR

- 消除重复、澄清职责、保持类型安全。
- 新实现替代旧实现时，同步删除旧函数、接口、状态、字段、入口、依赖、配置、测试和文档说明。
- 重构后重新运行最窄测试。

### VERIFY

- 运行任务测试、受影响回归和必要静态检查。
- 修改启动关键文件时按 `AGENTS.md` 验证 `start.bat` 与固定端口约束。
- 涉及 UI 时按桌面浏览器固定端口进行实际页面验证。
- 通过后才用状态脚本标记任务完成。

## 需求追踪

- 追踪依据是 `tasks.md` 的数字需求 ID。
- 在测试名称/说明、任务状态和 `implementation-report.md` 中记录映射。
- 除非项目既有语言规范要求，不强迫所有业务类、接口和方法加入框架特定的 `@Requirement` 注释。
- 禁止为了追踪把文档性版本号或开发阶段写入业务代码。

## 阶段完成

所有纳入范围任务完成后：

1. 检查 `tasks.md` 与 `tasks-status.json` 一致。
2. 生成 `implementation-report.md`，包括：
   - 实际变更；
   - 任务/需求映射；
   - RED/GREEN/REFACTOR/VERIFY 证据；
   - 测试命令与结果；
   - 清理的旧实现；
   - 设计偏差及理由；
   - 手动验收；
   - 未解决问题。
3. 推进到 `implementation_ready`。
4. 创建独立实现验证角色，不得由实现角色自验通过。
5. 验证 PASS 后才推进 `completed`；FAIL 返回最小责任范围修复。

## 严格约束

- 不提交、不推送、不创建 PR，除非用户另行明确要求。
- 不用删除测试、放宽断言或吞掉异常制造通过。
- 不把未运行的测试写成通过。
- 不破坏 `start.bat`。
- 不修改规格来迁就错误实现；发现规格错误时返回相应上游阶段。
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 保留任务选择、TDD、状态与错误恢复；实现授权由用户请求或 --impl 明确给出，状态只能通过 state.py 更新。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 使用 TDD 方法论执行规格任务 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <功能名称> [任务编号] | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
实现任务执行器
解析参数
功能名称: $1
任务编号: $2（可选）
格式: "1.1"（单个任务）或 "1,2,3"（多个任务）
如果未提供: 执行所有待处理任务
验证
检查任务是否已生成:

验证 .sdd/specs/$1/ 存在
验证 .sdd/specs/$1/tasks.md 存在
如果验证失败，提示用户先完成任务生成。

任务选择逻辑
从 $2 解析任务编号（在调用子 Agent 前在 Slash Command 中执行）:

如果提供了 $2: 解析任务编号（如 "1.1", "1,2,3"）
否则: 读取 .sdd/specs/$1/tasks.md 并找到所有未勾选的任务（- [ ]）
调用子 Agent
将 TDD 实现委托给 spec-tdd-impl-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="spec-tdd-impl-agent",
  description="执行 TDD 实现",
  prompt="""
Feature: $1
Spec directory: .sdd/specs/$1/
Target tasks: {parsed task numbers or "all pending"}

File patterns to read:
- .sdd/specs/$1/*.{json,md}
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料

TDD Mode: strict (test-first)
"""
)
显示结果
向用户展示子 Agent 的摘要，然后提供下一步指导:

任务执行
执行特定任务:

$codex-sdd spec-impl $1 1.1 - 单个任务
$codex-sdd spec-impl $1 1,2,3 - 多个任务
执行所有待处理任务:

$codex-sdd spec-impl $1 - 所有未勾选的任务
开始实现前:

重要: 在运行 $codex-sdd spec-impl 前清理对话历史并释放上下文
这适用于开始第一个任务或在任务之间切换
新鲜的上下文确保干净的状态和正确的任务焦点
~~~
