# `validate-impl`：独立实现验证

## 使命

以独立上下文对照需求、设计、任务、实际代码差异和测试结果验证实现，给出可审计的 PASS/FAIL。

## 参数

```text
$codex-sdd validate-impl [<版本号>/<大需求模块名称>] [任务编号列表]
```

未指定规格时仅使用合法 `active_spec`，不得从聊天历史猜测另一个规格。

## 前置门禁

- `requirements.md`、`design.md`、`tasks.md`、`tasks-status.json`、`implementation-report.md` 存在。
- 需求与设计独立 PASS 报告哈希有效。
- 当前阶段为 `implementation_ready`。
- `state.py validate` 通过。
- 验证角色与实现角色上下文隔离。

## 必须读取

- 根 `AGENTS.md`、相关局部规则和启动约束；
- 全部规格产物与报告；
- 当前 `git status`、相关 diff、目标源码与测试；
- `references/agents/validate-impl.md`；
- `references/rules/independent-validation-gate.md` 的实现部分；
- 项目真实测试与启动配置。

## 子 Agent 调用

角色：`codex_sdd_impl_validator`。

```text
operation: validate-impl
mode: implementation
spec_id: <id>
spec_dir: <dir>
target_tasks: <ids | all completed>
expected_outputs:
  - verification-report.md
forbidden_writes:
  - 业务代码
  - 测试代码
  - requirements.md
  - design.md
  - tasks.md
  - tasks-status.json
  - spec.json
  - .sdd/state.json
```

## 强制验证维度

1. 任务状态：计划任务、状态文件和实际变更一致。
2. 需求追踪：每个范围内数字需求 ID 有代码和测试证据。
3. 设计对齐：边界、依赖方向、接口、数据模型和文件规划一致；偏差有明确理由。
4. 测试证据：运行任务测试、受影响回归和必要完整套件；记录命令、退出码和关键结果。
5. 旧实现清理：被替代函数、入口、状态、字段、依赖、配置、测试和文档无残留。
6. 项目约束：数据宪法、单小说边界、中文可见文案、软删除展示规则等未回归。
7. 启动约束：关键文件变化时验证 `start.bat`；前后端效果按固定端口验证。
8. 工作树范围：无关用户改动未被归入本实现。
9. 手动验收：报告包含可复现步骤和实际结果。

## 报告要求

`verification-report.md` 必须包含：

- 规格、验证时间、验证范围；
- 实现对象哈希或可复现 diff 基线；
- 测试命令与原始结果摘要；
- 需求/任务/设计追踪表；
- Critical/Major/Minor 问题；
- 清理与启动验证；
- 限制和未运行项；
- 精确一行 `结论：PASS` 或 `结论：FAIL`；
- 门禁理由。

存在测试失败、必需测试未运行、核心需求缺失、关键设计偏离、旧实现残留、启动约束破坏或证据不可复现时必须 FAIL。

## 主 Agent处理

- PASS：用 `state.py validation --mode implementation --status pass` 登记，验证哈希后推进 `completed`。
- FAIL：按最小责任范围退回实现、设计或需求；修复后创建新的独立验证上下文。
- 不允许验证角色直接修复。
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 保留任务、测试和需求对照；扩展为实际 diff、旧实现清理、启动约束和实现报告的独立 PASS/FAIL。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 针对需求、设计和任务验证实现 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task | 映射到当前工具面与命令禁止项 |
| `argument-hint` | [功能名称] [任务编号] | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
实现验证
解析参数
功能名称: $1（可选）
任务编号: $2（可选）
自动检测逻辑
在调用子 Agent 前执行检测:

如果没有参数（$1 为空）:

从对话历史中解析 $codex-sdd spec-impl <feature> [tasks] 模式
或扫描 .sdd/specs/*/tasks.md 查找 [x] 复选框
将检测到的功能和任务传递给子 Agent
如果只有功能（$1 存在，$2 为空）:

读取 .sdd/specs/$1/tasks.md 并找到所有 [x] 复选框
将功能和检测到的任务传递给子 Agent
如果两者都提供（$1 和 $2 都存在）:

直接传递给子 Agent，无需检测
调用子 Agent
将验证委托给 validate-impl-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="validate-impl-agent",
  description="验证实现",
  prompt="""
Feature: {$1 or auto-detected}
Target tasks: {$2 or auto-detected}
Mode: {auto-detect, feature-all, or explicit}

File patterns to read:
- .sdd/specs/{规格标识}/*.{json,md}
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料

Validation scope: {based on detection results}
"""
)
显示结果
向用户展示子 Agent 的摘要，然后提供下一步指导:

下一步指导
如果是 GO 决策:

实现已验证并准备就绪
继续部署或进入下一个功能
如果是 NO-GO 决策:

解决列出的关键问题
重新运行 $codex-sdd spec-impl <feature> [tasks] 进行修复
用 $codex-sdd validate-impl [feature] [tasks] 重新验证
注意: 推荐在实现后进行验证，以确保规格一致性和质量。
~~~
