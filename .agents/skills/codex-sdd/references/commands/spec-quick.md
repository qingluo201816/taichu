# `run`：自动规格编排

## 使命

在一个调用中连续执行高质量规格流程。默认目标为 `tasks_ready`，不因阶段转换暂停；若用户明确包含实现，则继续到 `completed`。本操作保留标准流程的资产探查、草稿门禁、设计评审和独立校验，不以“快速”为由跳过质量步骤。

## 参数

```text
$codex-sdd run <版本号> <大需求模块名称> <原始需求描述> [--impl] [--sequential]
```

- `--impl`：明确授权业务实现与实现验证。
- `--sequential`：任务不标记 `(P)`。
- 未带 `--impl`：目标阶段为 `tasks_ready`。
- 规格已存在：转为恢复模式，保留原始 `target_phase`；若本次扩大到实现，需用户明确 `--impl`。

## 启动

1. 读取 `SKILL.md`、两份编排规范和状态契约。
2. 读取根 `AGENTS.md`、`README.md` 及当前任务所需项目规则。
3. 解析规格标识，拒绝缺失版本号或模块名。
4. 新规格调用 `spec-init`；已有规格调用 `show` 与 `validate`。
5. 将阶段清单落入 `spec.json.target_phase` 和 `progress.log`，不使用会话内待办作为恢复事实。
6. 从第一个未满足证据的阶段开始。

## 自动阶段循环

### Step 1：初始化

执行 `commands/spec-init.md`。收尾必须有合法状态与初始化产物。

### Step 2：需求

执行 `commands/spec-requirements.md`：

- 现有资产探查；
- EARS 需求生成；
- 需求草稿门禁；
- 独立需求发现与 PASS/FAIL；
- FAIL 最多两轮自动修复。

### Step 3：差距分析

对当前存量代码库默认执行 `commands/validate-gap.md`。只有明确为无集成点的纯绿地规格时才可跳过，并在 `progress.log` 记录理由。

### Step 4：设计

执行 `commands/spec-design.md`：

- 发现分级；
- `research.md`；
- 设计综合；
- 设计草稿门禁；
- GO/NO-GO 质量评审；
- 独立设计发现与 PASS/FAIL；
- FAIL 最多两轮自动修复。

### Step 5：任务

执行 `commands/spec-tasks.md`：

- 全量需求与设计覆盖；
- 边界、依赖、可观察完成；
- 并行安全分析或顺序模式；
- 任务计划门禁；
- 状态与任务索引同步。

### Step 6：实现（仅授权时）

执行 `commands/spec-impl.md`：

- 逐任务 RED/GREEN/REFACTOR/VERIFY；
- 状态持久化；
- 旧实现清理；
- 实现报告；
- 独立实现验证；
- FAIL 返回最小责任范围修复。

## 自动推进规则

每阶段结束后：

1. 检查专属收尾清单。
2. 检查产物存在、非空、无模板占位符。
3. 检查需要的对象哈希与独立 PASS 报告。
4. 通过状态脚本登记。
5. 运行 `state.py validate`。
6. 立即执行下一已授权阶段。

不得展示“继续/修改/跳过/终止”的例行选择菜单。跳过必需门禁也不是自动模式的含义。

## 暂停条件

只在以下情况暂停：

- 会改变范围的真实歧义或规则冲突；
- 只有用户能提供的必需输入缺失；
- 两轮自动修复后仍 FAIL；
- 下一步超出 `target_phase` 或需要未授权实现/外部写入/破坏性操作；
- 与本任务重叠的用户改动无法安全合并。

暂停前写入阻塞状态、当前阶段、失败证据和精确恢复入口。

## 错误恢复

- 阶段执行失败：不推进 phase，保留已生成证据。
- 状态索引漂移：执行 `repair-index` 后重新 `validate`。
- 校验对象变化：使旧 PASS 失效并重跑独立校验。
- 会话重启：使用 `resume`，不重做已验证且哈希有效的阶段。
- 子 Agent只返回摘要：视为该 Step 未完成。

## 完成输出

目标为任务阶段：

```text
执行状态：成功
规格：<id>
阶段：tasks_ready
需求校验：PASS（hash）
设计评审：GO
设计校验：PASS（hash）
任务：N 个可执行任务
实现：未执行（本次未授权）
恢复入口：$codex-sdd resume <id>
```

目标含实现：

```text
执行状态：成功
规格：<id>
阶段：completed
任务：N/N
实现验证：PASS
关键测试：...
手动验收：...
```

## 禁止行为

- 以“快速”为由跳过差距分析、设计评审或独立校验。
- 依赖聊天中的阶段承诺而不更新 `.sdd/`。
- 只执行到文档生成即声称完整流程通过。
- 自动进入未授权业务实现。
- 在阶段间强制用户审批。
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 默认即自动模式，原交互模式只在用户明确要求单步时启用；不再跳过差距分析、设计评审或独立校验。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 快速规格生成，支持交互式或自动模式 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Codex 子 Agent 调用, state.py、spec.json 与 progress.log, Bash, Write, Glob | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <项目描述> [--auto] | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
快速规格生成器
<background_information>

使命: 在单个命令中执行所有规格阶段（init → requirements → design → tasks）
成功标准:
交互模式: 用户在每个阶段通过审批提示控制进度
自动模式: 提供 --auto 标志时，所有阶段无中断执行
所有生成的规格保持与手动工作流相当的质量 </background_information>
## ⚠️ 关键: 自动模式执行规则
如果 $ARGUMENTS 中存在 --auto 标志，你处于自动模式。

在自动模式中:

持续循环执行全部 4 个阶段，不停止
使用 state.py、spec.json 与 progress.log 跟踪进度（4 个任务: init, requirements, design, tasks）
每个阶段完成后更新 state.py、spec.json 与 progress.log 并立即继续
忽略来自第 2-4 阶段的"下一步"消息（它们用于独立使用）
仅在第 4 阶段完成后或发生错误时停止
使用 state.py、spec.json 与 progress.log 跟踪进度:

第 1 阶段完成 = 1/4 任务完成 → 继续第 2 阶段
第 2 阶段完成 = 2/4 任务完成 → 继续第 3 阶段
第 3 阶段完成 = 3/4 任务完成 → 继续第 4 阶段
第 4 阶段完成 = 4/4 任务完成 → 输出摘要并退出
核心任务
按顺序执行 4 个规格阶段。在自动模式下，不停顿执行所有阶段。在交互模式下，在阶段之间提示用户审批。

执行步骤
步骤 1: 解析参数并初始化
解析 $ARGUMENTS:

如果包含 --auto: 自动模式（执行全部 4 个阶段）
否则: 交互模式（每个阶段提示）
提取描述（如有则移除 --auto 标志）
示例:

"User profile with avatar upload --auto" → mode=automatic, description="User profile with avatar upload"
"User profile feature" → mode=interactive, description="User profile feature"
创建 state.py、spec.json 与 progress.log 任务列表:

[
  {"content": "初始化规格", "activeForm": "正在初始化规格", "status": "pending"},
  {"content": "生成需求", "activeForm": "正在生成需求", "status": "pending"},
  {"content": "生成设计", "activeForm": "正在生成设计", "status": "pending"},
  {"content": "生成任务", "activeForm": "正在生成任务", "status": "pending"}
]
显示模式横幅并进入步骤 2。

步骤 2: 执行阶段循环
按顺序执行这 4 个阶段:

第 1 阶段: 初始化规格（直接实现）
更新 state.py、spec.json 与 progress.log: 将任务 1 标记为 in_progress。

核心逻辑:

生成功能名称:

要求使用用户提供的 `{版本号}/{大需求模块名称}`；个人项目不含工号
不得从描述自动生成另一套英文短名或改写规格标识
模块名称应简洁且能表达大需求边界
检查唯一性:

使用 Glob 检查 .sdd/specs/*/
如果规格标识已存在，停止并提示使用 `resume` 或提供新的显式标识，不得自动追加后缀
创建目录:

使用 Bash: mkdir -p .sdd/specs/{版本号}/{大需求模块名称}
从模板初始化文件:

a. 读取模板:

- .agents/skills/codex-sdd/assets/specs/init.json
- .agents/skills/codex-sdd/assets/specs/requirements-init.md
b. 替换占位符:

{{FEATURE_NAME}} → feature-name
{{TIMESTAMP}} → current ISO 8601 timestamp (use `date -u +"%Y-%m-%dT%H:%M:%SZ"`)
{{PROJECT_DESCRIPTION}} → description
c. 使用 Write 工具写入文件:

- .sdd/specs/{版本号}/{大需求模块名称}/spec.json
- .sdd/specs/{版本号}/{大需求模块名称}/requirements.md
更新 state.py、spec.json 与 progress.log: 将任务 1 标记为 completed，任务 2 标记为 in_progress。

输出进度:

✅ 规格已初始化于 .sdd/specs/{版本号}/{大需求模块名称}/
自动模式: 立即继续第 2 阶段。

交互模式: 提示"继续生成需求？(yes/no)"

如果 "no": 停止，显示当前状态
如果 "yes": 继续第 2 阶段
第 2 阶段: 生成需求
任务 2 已从第 1 阶段标记为 in_progress。

执行 Codex 子 Agent 调用:

$codex-sdd spec-requirements {版本号}/{大需求模块名称}
等待完成。子 Agent 将返回"下一步"消息。

重要: 在自动模式中，忽略"下一步"消息。它用于独立使用。

更新 state.py、spec.json 与 progress.log: 将任务 2 标记为 completed，任务 3 标记为 in_progress。

输出进度:

✅ 需求已生成 → 继续生成设计...
自动模式: 任务列表显示 2/4 完成。立即继续第 3 阶段。

交互模式: 提示"继续生成设计？(yes/no)"

如果 "no": 停止，显示当前状态
如果 "yes": 继续第 3 阶段
第 3 阶段: 生成设计
任务 3 已从第 2 阶段标记为 in_progress。

执行 Codex 子 Agent 调用:

$codex-sdd spec-design {版本号}/{大需求模块名称} -y
注意: -y 标志自动批准需求。

等待完成。子 Agent 将返回"下一步"消息。

重要: 在自动模式中，忽略"下一步"消息。

更新 state.py、spec.json 与 progress.log: 将任务 3 标记为 completed，任务 4 标记为 in_progress。

输出进度:

✅ 设计已生成 → 继续生成任务...
自动模式: 任务列表显示 3/4 完成。立即继续第 4 阶段。

交互模式: 提示"继续生成任务？(yes/no)"

如果 "no": 停止，显示当前状态
如果 "yes": 继续第 4 阶段
第 4 阶段: 生成任务
任务 4 已从第 3 阶段标记为 in_progress。

执行 Codex 子 Agent 调用:

$codex-sdd spec-tasks {版本号}/{大需求模块名称} -y
注意: -y 标志自动批准设计。

等待完成。

更新 state.py、spec.json 与 progress.log: 将任务 4 标记为 completed。

全部 4 个任务完成。循环结束。

输出最终完成摘要（见输出描述部分）并退出。

重要约束
第 1 阶段实现说明
功能名称生成应该是确定性的且可读的
在创建目录前始终检查冲突
在读取前验证模板是否存在
使用 ISO 8601 格式的时间戳: YYYY-MM-DDTHH:MM:SSZ
自动模式行为
不要在阶段之间停止
不要等待用户输入
不要受第 2-4 阶段"下一步"消息的影响
在每个阶段后更新 state.py、spec.json 与 progress.log 以保持进度可见性
继续循环直到全部 4 个阶段完成
交互模式行为
在每个阶段后提示用户
等待 "yes/y" 或 "no/n" 响应
如果 "no": 优雅停止，显示已完成的阶段
如果 "yes": 继续下一阶段
错误处理
任何阶段失败都会停止工作流
显示错误和当前状态
建议手动恢复命令
工具使用指南
第 1 阶段工具
Glob: 检查 .sdd/specs/*/ 中已有的功能名称
Bash: 使用 mkdir -p 创建目录，使用 date -u 生成时间戳
Read: 从 .agents/skills/codex-sdd/assets/specs/ 获取模板
Write: 在规格目录中创建 spec.json 和 requirements.md
第 2-4 阶段工具
Codex 子 Agent 调用: 执行 $codex-sdd spec-requirements, $codex-sdd spec-design, $codex-sdd spec-tasks
state.py、spec.json 与 progress.log 使用
初始化 4 个 pending 任务
每个阶段后更新: 当前任务 completed，下一任务 in_progress
在 UI 中提供可视化的进度跟踪
输出描述
模式横幅
交互模式:

🚀 快速规格生成（交互模式）

你将在每个阶段被提示。
✅ 保留差距分析、设计评审和独立校验。
自动模式:

🚀 快速规格生成（自动模式）

所有阶段自动执行，无提示。
✅ 自动模式同样执行全部验证和评审。
中间输出
每个阶段后，显示简要进度:

✅ 规格已初始化于 .sdd/specs/{规格标识}/
✅ 需求已生成 → 继续生成设计...
✅ 设计已生成 → 继续生成任务...
最终完成摘要
使用 spec.json 中指定的语言提供输出:

✅ 快速规格生成完成！

## 生成的文件:
- .sdd/specs/{规格标识}/spec.json
- .sdd/specs/{规格标识}/requirements.md ({X} 个需求)
- .sdd/specs/{规格标识}/design.md ({Y} 个组件, {Z} 个端点)
- .sdd/specs/{规格标识}/tasks.md ({N} 个任务)

⚠️ 快速生成跳过了:
- `$codex-sdd validate-gap` - 差距分析（集成检查）
- `$codex-sdd validate-design` - 设计评审（架构验证）

## 下一步:
1. 查看生成的规格（特别是 design.md）
2. 可选验证:
   - `$codex-sdd validate-gap {规格标识}` - 检查与现有代码库的集成
   - `$codex-sdd validate-design {规格标识}` - 验证架构质量
3. 开始实现: `$codex-sdd spec-impl {规格标识}`

## 注意:
对于复杂功能（集成、安全、API），使用标准工作流:
$codex-sdd spec-init → $codex-sdd spec-requirements → $codex-sdd validate-gap
→ $codex-sdd spec-design → $codex-sdd validate-design → $codex-sdd spec-tasks
安全与回退
参数解析
使用 $ARGUMENTS 解析（不是 $1, $2）
正确处理描述中的空格
示例: "Multi word description --auto" → 正确提取两部分
功能名称生成
校验格式为 `{版本号}/{大需求模块名称}`
拒绝路径穿越、空段和非法路径字符
如果含义有歧义，要求用户明确模块名称
如果存在冲突，停止并提示恢复现有规格或提供新的显式标识
错误场景
模板缺失:

检查 .agents/skills/codex-sdd/assets/specs/ 是否存在
报告具体缺失的文件
退出并显示错误
目录创建失败:

检查权限
报告错误及路径
退出并显示错误
阶段执行失败（第 2-4 阶段）:

停止工作流
显示当前状态和已完成的阶段
建议: "从 $codex-sdd spec-{next-phase} {规格标识} 手动继续"
用户取消（交互模式）:

优雅停止
显示已完成的阶段
建议手动继续
使用指南
使用自动模式（--auto）当:

简单功能（CRUD、基本 UI）
原型 / 概念验证
已知的功能模式
使用交互模式（默认）当:

首次使用 spec-quick
想要查看每个阶段
中等复杂度的功能
使用标准工作流（非 spec-quick）当:

与现有系统的复杂集成
安全关键功能
需要生产就绪的质量
需要差距分析或设计验证
~~~
