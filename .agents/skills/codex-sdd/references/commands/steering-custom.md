# `project-context-custom`：专门主题事实补充

## 适配定位

本命令用于补充 API、测试、安全、数据库、错误处理、认证或部署等专门项目规则，但不创建平行的项目记忆目录。输出必须写入现有权威资料中最合适的位置，或在用户同意后创建一个符合项目文档规则的新资料文件。

## 参数

```text
$codex-sdd project-context-custom <主题> [--audit-only]
```

主题缺失且无法从请求确定时必须询问；不能生成一个泛化“最佳实践”文件充数。

## 必须读取

- 根 `AGENTS.md`、`README.md`；
- 相关局部规则和当前实现；
- `references/agents/steering-custom.md`；
- `references/rules/steering-principles.md`；
- 对应 `assets/project-context/<topic>.md` 结构模板；
- 涉及 `docs/` 时读取 `docs/rule.md`；
- 涉及项目 Skill 时读取 `.agents/skills/rule.md`；
- 涉及前端时读取 `DESIGN.md`。

## 子 Agent 调用

角色：`codex_sdd_context_custom`。

## 工作流

1. 明确主题、目标读者和权威归属。
2. 调查真实代码、测试、配置和当前资料。
3. 区分：
   - 已建立且需要记录的项目模式；
   - 资料与代码漂移；
   - 尚未决策的建议；
   - 与现有不可变决策冲突的内容。
4. 选择目标：
   - 现有根规则；
   - 现有目录规则；
   - 现有最新项目文档；
   - 用户同意的新 `docs/` 资料。
5. 仅增量写入，经对应规则检查。
6. 新增、移动或删除资料入口时同步根 `README.md`。
7. 输出证据、修改与未决项。

## 模板使用

`assets/project-context/` 只提供审计提纲。不得把其中通用示例直接当作太初事实；每一条落盘规则必须由现有代码、项目决策或用户明确选择支持。

## 严格约束

- 不生成重复的 product/tech/structure 文件。
- 不写入 `.sdd/` 规格目录。
- 不把通用安全、部署或数据库建议伪装成项目已采用规则。
- 不包含密钥、密码、令牌、内部地址或个人信息。
- 不提供工时或排期。
- `--audit-only` 不修改任何文件。

## 输出

```text
执行状态：成功
主题：...
目标事实源：...
依据：...
已更新：...
仅建议未落盘：...
冲突/待决：...
```
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 不创建平行项目记忆文件；改为审计并按明确授权增量同步当前权威资料。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 为专门的项目上下文创建自定义 steering 文档 | 保留为角色用途与注册描述 |
| `allowed-tools` | Task | 映射到当前工具面与命令禁止项 |

### 原协议正文（顺序保留）

~~~text
Codex SDD 自定义 Steering 创建
交互式工作流
此命令启动与子 Agent 的交互过程:

子 Agent 询问用户领域/主题
子 Agent 检查可用模板
子 Agent 分析代码库中的相关模式
子 Agent 生成自定义 steering 文件
调用子 Agent
将自定义 steering 创建委托给 steering-custom-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="steering-custom-agent",
  description="创建自定义 steering",
  prompt="""
Interactive Mode: Ask user for domain/topic

File patterns to read:
- .sdd/settings/templates/steering-custom/*.md
- .agents/skills/codex-sdd/references/rules/steering-principles.md

JIT Strategy: Analyze codebase for relevant patterns as needed
"""
)
显示结果
向用户展示子 Agent 的摘要:

自定义 steering 文件已创建
使用的模板（如有）
分析的代码库模式
内容概述
可用模板
.sdd/settings/templates/steering-custom/ 中的可用模板:

api-standards.md, testing.md, security.md, database.md
error-handling.md, authentication.md, deployment.md
说明
子 Agent 将与用户交互以了解需求
模板是起点，根据项目定制
所有 steering 文件作为项目记忆加载
避免记录 agent 特定的工具目录（如 .cursor/, .gemini/, .codex/）
.sdd/settings/ 内容不应被记录（它是元数据，不是项目知识）
可以轻引用 .sdd/specs/ 和 当前项目权威资料；避免其他 .sdd/ 目录
~~~
