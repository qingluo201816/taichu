# `spec-init`：规格初始化

## 使命

只创建一个可恢复、无歧义的规格容器，不提前生成正式需求、设计或任务。

## 参数

```text
$codex-sdd spec-init <版本号> <大需求模块名称> <原始需求描述>
```

必需输入：

- `version`：用户明确给出的版本号。
- `module`：大需求模块名称；个人项目不含工号。
- `description`：保留用户原始表达，不做摘要替换。
- `target_phase`：由调用操作决定；单独初始化为 `initialized`，`run` 默认为 `tasks_ready`，含实现时为 `completed`。

规格标识固定为 `{版本号}/{大需求模块名称}`。

## 前置读取

1. 根目录 `AGENTS.md` 与 `README.md`。
2. `references/state-contract.md`。
3. `assets/specs/init.json`。
4. `assets/specs/requirements-init.md`。
5. 当前 `.sdd/state.json`（存在时）和目标规格目录（存在时）。

## 执行步骤

1. 校验版本号和模块名：
   - 非空；
   - 不含 Windows 非法字符或保留名；
   - 不含 `..`；
   - 不以空格或句点结尾；
   - 规格标识恰为两段。
2. 检查 `.sdd/specs/{version}/{module}/`：
   - 不存在：创建新规格；
   - 已存在且 `spec.json` 合法：不得追加数字后缀，转为恢复/状态检查；
   - 已存在但状态损坏：停止并报告，不覆盖。
3. 执行：
   ```powershell
   uv run python .agents/skills/codex-sdd/scripts/state.py init `
     --version "<version>" `
     --module "<module>" `
     --description "<description>" `
     --target-phase "<target_phase>"
   ```
4. 核对生成：
   - `spec.json`；
   - 仅含原始描述和后续占位说明的 `requirements.md`；
   - `progress.log`；
   - `.sdd/state.json` 活动规格索引。
5. 执行 `state.py validate --spec "<version>/<module>"`。
6. 单独调用 `spec-init` 时结束；由 `run` 调用时立即进入需求阶段。

## 严格约束

- 不从描述中自行发明版本号。
- 不生成工号或空工号目录。
- 不把中文模块名静默改成英文 slug。
- 不自动创建 `module-2` 之类的新规格掩盖冲突。
- 不在本阶段生成正式 EARS 需求、设计、任务或业务代码。
- 不手工编辑 `spec.json`、`.sdd/state.json` 或 `progress.log`。
- 不创建空目录占位文件。

## 成功输出

```text
执行状态：成功
规格标识：<version>/<module>
规格目录：.sdd/specs/<version>/<module>/
目标阶段：...
已创建：spec.json、requirements.md、progress.log
状态验证：PASS
```

## 失败处理

- 参数缺失：指出缺失字段；不得猜测。
- 目录冲突：展示现有规格状态，建议 `resume` 或由用户明确新模块名。
- 模板或脚本缺失：视为框架损坏并停止。
- 状态验证失败：保留现场，报告具体不一致，不进入下一阶段。
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 功能名生成改为用户提供的 {版本号}/{大需求模块名称}，不使用工号、kebab-case 自动命名或冲突后缀。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 初始化新规格，包含详细的项目描述 | 保留为角色用途与注册描述 |
| `allowed-tools` | Bash, Read, Write, Glob | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <项目描述> | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
规格初始化
<background_information>

使命: 通过为新规格创建目录结构和元数据，初始化规格驱动开发的第一阶段
成功标准:
从项目描述生成合适的功能名称
创建无冲突的唯一规格结构
提供清晰的下一阶段路径（需求生成） </background_information>
## 核心任务 从项目描述 ($ARGUMENTS) 生成唯一的功能名称并初始化规格结构。
执行步骤
检查唯一性: 验证 .sdd/specs/ 中是否存在命名冲突（如有则追加数字后缀）
创建目录: .sdd/specs/[功能名称]/
使用模板初始化文件:
读取 .agents/skills/codex-sdd/assets/specs/init.json
读取 .agents/skills/codex-sdd/assets/specs/requirements-init.md
替换占位符:
{{FEATURE_NAME}} → 生成的功能名称
{{TIMESTAMP}} → 当前 ISO 8601 时间戳
{{PROJECT_DESCRIPTION}} → $ARGUMENTS
将 spec.json 和 requirements.md 写入规格目录
重要约束
此阶段不要生成需求/设计/任务
遵循逐阶段开发原则
保持严格的阶段分离
此阶段仅执行初始化
工具使用指南
使用 Glob 检查现有规格目录以确保名称唯一性
使用 Read 获取模板: init.json 和 requirements-init.md
使用 Write 在占位符替换后创建 spec.json 和 requirements.md
在任何文件写入操作前执行验证
输出描述
使用 spec.json 中指定的语言提供输出，结构如下:

生成的功能名称: 功能名称 格式，附 1-2 句理由说明
项目摘要: 简要总结（1 句话）
创建的文件: 带完整路径的项目列表
下一步: 显示 $codex-sdd spec-requirements <功能名称> 的命令块
说明: 解释为什么只执行了初始化（2-3 句话说明阶段分离）
格式要求:

使用 Markdown 标题 (##, ###)
命令用代码块包裹
保持总输出简洁（250 字以内）
使用清晰、专业的语言，遵循 spec.json.language
安全与回退
模糊的功能名称: 如果功能名称生成不明确，提出 2-3 个选项并请用户选择
模板缺失: 如果 .agents/skills/codex-sdd/assets/specs/ 中不存在模板文件，报告错误并指出具体缺失的文件路径，建议检查仓库设置
目录冲突: 如果功能名称已存在，追加数字后缀（如 feature-name-2）并通知用户已自动解决冲突
写入失败: 报告错误并指出具体路径，建议检查权限或磁盘空间
~~~
