# `project-context`：项目事实源审计与同步

## 适配定位

太初已有根 `AGENTS.md`、`README.md`、`DESIGN.md`、各目录 `rule.md` 和最新项目资料。这些文件是项目事实源，不再生成一套平行的项目记忆目录。

本命令保留参考框架“初始化/同步项目记忆”的严格职责，但将其适配为：

- 审计现有事实源与代码是否漂移；
- 确定每条事实的权威归属；
- 仅在用户明确调用时，增量更新对应权威文件；
- 同步资料入口时遵守 README 仓库地图规则。

## 参数

```text
$codex-sdd project-context [--audit-only]
```

默认仅在用户明确要求同步时写文件；`--audit-only` 绝对只读。

## 必须读取

- 根 `AGENTS.md`、`README.md`、`DESIGN.md`；
- `docs/rule.md`、`.agents/skills/rule.md`；
- 相关目录的局部 `AGENTS.md`/规则；
- `references/agents/steering.md`；
- `references/rules/steering-principles.md`；
- `assets/project-context/product.md`、`tech.md`、`structure.md`（只作审计结构，不作事实模板）；
- 代码、配置、测试和启动脚本。

## 子 Agent 调用

角色：`codex_sdd_context_sync`。

## 审计维度

1. 产品定位与功能边界。
2. 技术栈、包管理、Python/Node 版本和启动命令。
3. 架构层次、依赖方向、插件协议与存储边界。
4. 数据事实源与已废弃技术。
5. 前端框架、设计规则、交付端和固定端口。
6. 仓库地图与资料入口。
7. 项目规则与真实代码/配置之间的漂移。
8. 敏感信息、环境值和本地路径是否被误写入通用规则。

## 更新原则

- 先报告漂移和建议归属。
- 增量修改，不覆盖用户定制内容。
- 只记录稳定模式和决策，不列出每个文件或依赖。
- 事实属于哪个权威文件就更新哪个文件，不生成副本。
- 修改 `docs/`、项目 Skill 或前端规则前读取对应强制规则。
- 不把 `.sdd/` 运行状态写入项目事实源。
- 不记录密钥、密码、令牌、数据库 URL 或个人敏感数据。

## 输出

```text
执行状态：成功
模式：audit-only | sync
已检查事实源：...
代码漂移：...
已更新：...
未更新建议：...
冲突：...
```
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 不生成 product/tech/structure 第二套事实源；改为审计 README、AGENTS、DESIGN 与项目资料。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 管理 当前项目权威资料 作为持久化项目知识 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task, Glob | 映射到当前工具面与命令禁止项 |

### 原协议正文（顺序保留）

~~~text
Codex SDD Steering 管理
模式检测
在调用子 Agent 前执行检测:

检查 当前项目权威资料 状态:

引导模式: 为空或缺少核心文件（product.md, tech.md, structure.md）
同步模式: 所有核心文件都存在
使用 Glob 检查现有的 steering 文件。

调用子 Agent
将 steering 管理委托给 steering-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="steering-agent",
  description="管理 steering 文件",
  prompt="""
Mode: {bootstrap or sync based on detection}

File patterns to read:
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料 (if sync mode)
- .sdd/settings/templates/steering/*.md
- .agents/skills/codex-sdd/references/rules/steering-principles.md

JIT Strategy: Fetch codebase files when needed, not upfront
"""
)
显示结果
向用户展示子 Agent 的摘要:

引导模式:
生成的 steering 文件: product.md, tech.md, structure.md
查看并批准作为事实来源
同步模式:
更新的 steering 文件
代码漂移警告
自定义 steering 的建议
说明
所有 AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料 作为项目记忆加载
模板和原则是外部的，可自定义
关注模式，而非目录
"黄金法则": 遵循模式的新代码不应需要更新 steering
避免记录 agent 特定的工具目录（如 .cursor/, .gemini/, .codex/）
.sdd/settings/ 内容不应记录在 steering 文件中（设置是元数据，不是项目知识）
可以轻引用 .sdd/specs/ 和 当前项目权威资料；避免其他 .sdd/ 目录
~~~
