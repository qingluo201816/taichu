# `spec-requirements`：需求生成与独立门禁

## 使命

基于原始描述、项目事实和现有资产生成完整、可测试、无实现泄漏的 EARS 需求，并自动通过独立需求校验后才推进。

## 参数

```text
$codex-sdd spec-requirements <版本号>/<大需求模块名称>
```

支持 `generate`、`merge`、`repair` 三种内部模式。模式由目标文件和校验状态决定，不由子 Agent 自行猜测。

## 前置验证

1. 目标规格目录、`spec.json` 和初始化 `requirements.md` 存在。
2. `spec.json.id` 与参数一致。
3. 当前阶段不早于 `initialized`。
4. 执行 `state.py validate`；失败先修状态。
5. 若已有当前对象哈希对应的需求 PASS 且无修复请求，直接返回“无需重做”。

## 必须读取

- 根 `AGENTS.md`、`README.md`；
- 适用的当前项目资料与真实代码/测试；
- `references/agents/spec-requirements.md`；
- `references/rules/asset-discovery.md`；
- `references/rules/ears-format.md`；
- `references/rules/requirements-review-gate.md`；
- `assets/specs/requirements.md`；
- `references/state-contract.md`；
- 修复模式下的最近独立校验报告。

## 子 Agent 调用

角色：`codex_sdd_requirements`。

必须传入：

```text
+operation: spec-requirements
+spec_id: <id>
+spec_dir: <dir>
+mode: generate | merge | repair
+original_description: spec.json.description
+expected_outputs:
+  - requirements.md
+forbidden_writes:
+  - spec.json
+  - .sdd/state.json
+  - tasks-status.json
+  - design.md
+  - tasks.md
+  - 业务代码
```

生成角色必须先做资产探查，随后形成草稿、运行机械检查和判断审查；只有草稿门禁通过才能写正式 `requirements.md`。

## 主 Agent 收尾

1. 检查需求标题使用数字 ID。
2. 检查每个需求至少一个符合 `ears-format.md` 的验收标准。
3. 检查范围内、范围外、相邻预期、异常与恢复路径。
4. 检查不存在框架/数据库/接口等实现泄漏，除非它们是用户可观察约束。
5. 调用：
   ```powershell
   uv run python .agents/skills/codex-sdd/scripts/state.py advance `
     --spec "<id>" `
     --to requirements_ready `
     --artifact requirements=requirements.md
   ```
6. 创建全新 `codex_sdd_validator` 上下文，执行 `mode=requirements`。
7. 校验 PASS：用 `state.py validation` 登记并进入下一阶段。
8. 校验 FAIL：把报告中的具体问题交回需求角色修复，最多两轮；仍 FAIL 时写阻塞并暂停。
9. 每次状态变更后运行 `state.py validate`。

## 严格约束

- 默认自动推进，不展示“批准需求后继续”的菜单。
- 独立校验不能由需求生成角色执行。
- 不读取旧项目记忆目录；项目事实以当前权威文件和代码为准。
- 不生成工时、排期、工号、多小说、多租户、移动端或已废弃存储方案。
- 不把无法从仓库确认的假设写成已存在事实。
- 需求中的所有对外行为必须可观察、可测试。

## 成功输出

```text
执行状态：成功
规格：<id>
需求文件：.../requirements.md
需求数量：N
验收标准数量：M
独立校验：PASS
对象 SHA-256：...
报告：.../independent-validation-report-requirements.md
```
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 保留需求生成、上下文加载、合并和错误处理；审批提示改为自动独立校验与对象哈希门禁。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 为规格生成完整的需求文档 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <功能名称> | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
需求生成
解析参数
功能名称: $1
验证
检查规格是否已初始化:

验证 .sdd/specs/$1/ 存在
验证 .sdd/specs/$1/spec.json 存在
如果验证失败，提示用户先运行 $codex-sdd spec-init。

调用子 Agent
将需求生成委托给 spec-requirements-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="spec-requirements-agent",
  description="生成 EARS 格式需求",
  prompt="""
Feature: $1
Spec directory: .sdd/specs/$1/

File patterns to read:
- .sdd/specs/$1/spec.json
- .sdd/specs/$1/requirements.md
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料
- .agents/skills/codex-sdd/references/rules/ears-format.md
- .agents/skills/codex-sdd/assets/specs/requirements.md

Mode: generate
"""
)
显示结果
向用户展示子 Agent 的摘要，然后提供下一步指导:

下一阶段: 设计生成
如果需求已批准:

查看生成的需求文档 .sdd/specs/$1/requirements.md
可选的差距分析（针对现有代码库）:
运行 $codex-sdd validate-gap $1 分析与当前代码的实现差距
识别现有组件、集成点和实现策略
对于棕地项目推荐执行；对于绿地项目可跳过
然后运行 $codex-sdd spec-design $1 [-y] 进入设计阶段
如果需要修改:

提供反馈并重新运行 $codex-sdd spec-requirements $1
注意: 进入设计阶段前必须完成审批。
~~~
