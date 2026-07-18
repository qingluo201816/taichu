# Codex SDD 命令调用规范

## 适用范围

本规范适用于 `$codex-sdd` Skill 的全部操作，以及任何需要复用 Codex SDD 阶段能力的项目级 Skill。
命令定义、Agent 职责、规则、模板、状态与产物必须经过同一条可审计路径；主 Agent 不得用临时提示替代。

## 一、不可绕过的原则

1. **禁止模拟命令效果**：不得绕过命令定义、Agent 定义、阶段规则或模板，凭当前上下文自行拼出 `requirements.md`、`design.md`、`tasks.md` 或校验报告。
2. **禁止压缩关键约束**：自定义 Agent 的 TOML 必须包含本角色的关键门禁、读写边界、失败条件和返回契约；详细规则同时保留在本 Skill 的一对一参考文件中。
3. **禁止跳过阶段门禁**：文件存在不等于阶段完成。状态推进必须满足 [状态契约](../state-contract.md) 的证据条件。
4. **禁止生成后自我判定通过**：需求、设计和实现的最终 PASS/FAIL 必须由独立校验角色给出。
5. **禁止依赖聊天记忆恢复**：状态、目标阶段、任务进度、校验轮次、对象哈希和阻塞原因必须落盘到 `.sdd/`。
6. **禁止旧载体回流**：不创建第二套命令目录、Agent 目录、项目记忆目录或规格目录。
   项目级 Skill 只在 `.agents/skills/`；自定义 Agent 只在 `.codex/agents/`；规格只在 `.sdd/specs/`。
7. **主 Agent 保持全局控制**：子 Agent 只负责被委派的单阶段产物；主 Agent 负责目标、状态、依赖、修复循环、自动推进和最终报告。
8. **先读后写**：任何阶段先加载项目规则、命令定义、Agent 定义、所需上游产物和对应规则；完成调查或校验后才能写目标文件。
9. **不静默降级**：模板或规则缺失、状态不一致、对象哈希过期、目标文件无法读取时必须停止该阶段并报告，不能用临时内联模板掩盖框架损坏。

## 二、Codex 机制映射

### 命令发现

- Codex 等效载体：Skill 名称与子操作路由。
- 本项目实现：`.agents/skills/codex-sdd/SKILL.md` + `references/commands/*.md`。

### Agent 注册

- Codex 等效载体：项目自定义 Agent TOML。
- 本项目实现：`.codex/agents/*.toml`。

### 工具声明

- Codex 等效载体：当前会话工具 + Agent 内允许/禁止行为。
- 本项目实现：TOML 的 `developer_instructions` 与 Agent 参考文件。

### 子 Agent 调用

- Codex 等效载体：Codex 原生自定义角色/子 Agent。
- 本项目实现：主 Agent 按映射选择角色；不可用时由独立原生子 Agent 读取对应 TOML。

### 内存任务树

- Codex 等效载体：磁盘状态机与审计日志。
- 本项目实现：`.sdd/state.json`、规格 `spec.json`、`tasks-status.json`、`progress.log`。

### 斜杠命令串联

- Codex 等效载体：Skill 内部子操作。
- 本项目实现：`$codex-sdd <operation> ...`。

当前客户端已验证的 Agent 注册字段只有 `name`、`description` 和 `developer_instructions`。不得为追求表面一致而加入未经当前客户端验证的 `tools`、颜色或模型字段。

## 三、规格标识与目录

- 规格标识：`{版本号}/{大需求模块名称}`。
- 个人项目不含工号；不得生成空占位工号。
- 目录：`.sdd/specs/{版本号}/{大需求模块名称}/`。
- 版本号与模块名由用户输入或当前任务中明确给出；不得仅凭描述静默发明版本号。
- 模块名应使用用户给出的中文名称；仅在 Windows 路径非法、空值、保留名、尾随空格/句点或包含 `..` 时拒绝。
- 同名规格存在时不得自动追加编号形成另一份规格；读取状态后执行恢复、定向重跑或要求用户明确新名称。

## 四、操作与角色映射

### `spec-init`

- 执行者：主 Agent + 状态脚本。
- 命令定义：`commands/spec-init.md`；无子 Agent。
- 主要产物：`spec.json`、初始 `requirements.md`、`progress.log`。

### `spec-requirements`

- 执行者：`codex_sdd_requirements`。
- 命令/Agent：`commands/spec-requirements.md`、`agents/spec-requirements.md`。
- 主要产物：`requirements.md`。

### `validate-gap`

- 执行者：`codex_sdd_gap_validator`。
- 命令/Agent：`commands/validate-gap.md`、`agents/validate-gap.md`。
- 主要产物：`gap-analysis.md`。

### `spec-design`

- 执行者：`codex_sdd_design`。
- 命令/Agent：`commands/spec-design.md`、`agents/spec-design.md`。
- 主要产物：`research.md`、`design.md`。

### `validate-design`

- 执行者：`codex_sdd_design_reviewer`。
- 命令/Agent：`commands/validate-design.md`、`agents/validate-design.md`。
- 主要产物：`design-review-report.md`。

### `spec-tasks`

- 执行者：`codex_sdd_tasks`。
- 命令/Agent：`commands/spec-tasks.md`、`agents/spec-tasks.md`。
- 主要产物：`tasks.md`。

### `spec-impl`

- 执行者：`codex_sdd_impl`。
- 命令/Agent：`commands/spec-impl.md`、`agents/spec-impl.md`。
- 主要产物：代码、测试、`implementation-report.md`。

### `validate-impl`

- 执行者：`codex_sdd_impl_validator`。
- 命令/Agent：`commands/validate-impl.md`、`agents/validate-impl.md`。
- 主要产物：`verification-report.md`。

### `validate-independent`

- 执行者：`codex_sdd_validator`。
- Agent 定义：`agents/spec-independent-validator.md`；由各阶段内部门禁调用。
- 主要产物：discovery + 独立校验报告。

### `run`

- 执行者：主 Agent 编排；命令定义：`commands/spec-quick.md`。
- 主要结果：默认推进到 `tasks_ready`。

### `status` / `resume`

- 执行者：主 Agent + 状态脚本；命令定义：`commands/spec-status.md`。
- 主要结果：只读状态报告，或从第一个未完成阶段恢复到原 `target_phase`。

### `project-context`

- 执行者：`codex_sdd_context_sync`。
- 命令/Agent：`commands/steering.md`、`agents/steering.md`。
- 主要结果：对现有事实源的审计/定向同步。

### `project-context-custom`

- 执行者：`codex_sdd_context_custom`。
- 命令/Agent：`commands/steering-custom.md`、`agents/steering-custom.md`。
- 主要结果：对现有权威文档的专门主题补充。

## 五、统一委派协议

每次委派都必须在任务中明确以下字段，不能让子 Agent 自行猜测：

```text
operation: <操作名>
spec_id: <版本号>/<大需求模块名称>
spec_dir: .sdd/specs/<版本号>/<大需求模块名称>/
mode: <generate|merge|repair|requirements|design|implementation>
target_phase: <状态契约中的目标阶段>
input_artifacts:
  - <允许读取的上游产物>
expected_outputs:
  - <本步骤必须生成或更新的文件>
forbidden_writes:
  - spec.json
  - .sdd/state.json
  - tasks-status.json（实现角色按主 Agent 指定的状态脚本操作除外）
  - <其他阶段产物或业务代码>
```

子 Agent 开始前必须：

1. 读取根目录 `AGENTS.md`，再读取当前目录树中适用的更近层级规则。
2. 读取对应 `references/agents/<name>.md` 与 `references/commands/<operation>.md`。
3. 读取命令明确列出的规则和模板，不得自行挑选一个摘要文件替代。
4. 核对 `spec.json` 的当前阶段、目标阶段、上游产物和有效独立校验，不得跳过状态门禁。
5. 先确认允许写入范围；子 Agent 不得直接推进阶段、改全局索引或覆盖其他角色的产物。

## 六、阶段调用要求

### 6.1 `spec-init`

- 由主 Agent 读取 `commands/spec-init.md`，调用 `state.py init`，不创建子 Agent。
- 必填参数是版本号、大需求模块名称、原始需求描述和目标阶段；个人项目规格标识不加入工号层级。
- 初始化前检查同一规格标识是否已存在：不存在则创建，已存在则按恢复协议读取，不重复覆盖已有产物。
- 目录固定为 `.sdd/specs/{版本号}/{大需求模块名称}/`；初始状态、时间戳和日志由状态脚本原子写入。
- 返回规格标识、绝对规格目录、当前阶段、目标阶段和下一步，不把“目录已创建”误报为需求已完成。

### 6.2 `spec-requirements`

- 使用 `codex_sdd_requirements`，输入完整原始需求、规格目录、当前项目规则和允许读取的事实源。
- 必须加载 `spec-requirements.md`、`asset-discovery.md`、`ears-format.md`、
  `requirements-review-gate.md` 与需求模板，不能只依赖角色简介。
- 先完成现有资产探查，再形成草稿；草稿通过机械检查和最多两轮本地审查后才覆盖正式 `requirements.md`。
- 完成后主 Agent 登记 `requirements_ready`，随后立即执行独立需求校验。

### 6.3 `validate-gap`

- 使用 `codex_sdd_gap_validator`。
- 只提供事实、差距、方案与风险，不替代设计决策。
- 不提供人工工时、天数、人员或排期估算；复杂度只按依赖、未知项、影响面和验证成本分级。
- 对存量系统的 `run` 默认执行；仅在确定为纯绿地且无集成点时可记录理由后跳过。

### 6.4 `spec-design`

- 使用 `codex_sdd_design`。
- 必须以已独立校验通过的需求为输入。
- 根据复杂度选择完整、轻量或最小发现；发现记录写入 `research.md`，最终契约写入 `design.md`。
- 写正式设计前执行设计综合和设计草稿门禁。
- 涉及 `web/` 时必须读取根 `DESIGN.md` 与 `taichu-ui-components` Skill；旧前端技术栈或移动端规则不得进入设计。

### 6.5 `validate-design`

- 使用 `codex_sdd_design_reviewer`。
- 这是面向设计质量的 GO/NO-GO 评审，不替代独立 PASS/FAIL 校验。
- 最多列出三个最重要问题，每个问题必须有需求追踪和设计证据。
- 自动流程中 NO-GO 返回设计修复环，不弹出例行审批菜单。

### 6.6 `spec-tasks`

- 使用 `codex_sdd_tasks`。
- 输入必须包含需求与设计两份独立 PASS 报告。
- 任务覆盖全部数字需求 ID、设计组件、契约、集成点、迁移、清理和验证。
- 任务大小按“单一可验证结果”划分，不按人工小时划分。
- 任务计划通过门禁后才写 `tasks.md`；主 Agent 再由状态脚本生成/同步 `tasks-status.json`。

### 6.7 `spec-impl`

- 仅在用户明确要求实现或原目标含实现时使用 `codex_sdd_impl`。
- 先读规格、任务状态和当前工作树；逐项 RED → GREEN → REFACTOR → VERIFY。
- 需求追踪写入测试名称、测试说明、任务状态和实现报告；除非项目既有规范要求，不强迫所有业务类/方法加入框架特定注释。
- 每个任务只有在规定验证通过后才能由状态脚本标记完成。

### 6.8 `validate-impl`

- 使用 `codex_sdd_impl_validator`，不得复用实现角色的上下文作为最终验证。
- 对照需求、设计、任务、实际差异和测试验证；检查旧实现清理、启动约束、固定端口约束和文档联动。
- 只有 `verification-report.md` 明确包含 `结论：PASS` 且对象哈希有效时，主 Agent 才推进 `completed`。

### 6.9 `validate-independent`

- 使用 `codex_sdd_validator`。
- requirements/design 模式严格执行“先发现、落盘、再读目标”；不得让生成者在同一上下文内完成。
- 目标文件读取前必须先写 `validation-discovery-{mode}.md`。
- 报告必须记录目标 SHA-256；目标变化后旧 PASS 自动失效。
- FAIL 返回相应生成角色定向修复；同一门最多两轮自动修复，之后进入真实阻塞。

## 七、默认自动流程

`run` 默认路径：

```text
init
→ requirements
→ independent requirements gate
→ gap analysis（存量系统默认）
→ design
→ design review
→ independent design gate
→ tasks
```

带实现范围时继续：

```text
→ implementation
→ independent implementation validation
→ completed
```

阶段间不弹出“是否继续”审批。只有无法从项目事实消除的作用域歧义、未授权外部写入、重要破坏性操作、校验两轮仍失败或实现未获授权时暂停。

## 八、状态与日志

- 每个有效状态变更都通过 `scripts/state.py`；不得手工改 `spec.json` 或 `.sdd/state.json`。
- `progress.log` 为只追加 JSON Lines，至少记录时间、事件、阶段、状态和结构化详情。
- 每阶段收尾依次检查：产物存在且非空 → 状态证据匹配 → 哈希有效 → `state.py validate` 通过。
- 会话重启或上下文压缩后先执行 `show` 与 `validate`；从磁盘中第一个未完成阶段恢复。
- 索引漂移使用 `repair-index` 修复；不得反向用索引覆盖规格事实。

## 九、禁止的调用方式

- 用 shell 把 `$codex-sdd` 当成操作系统命令执行。
- 主 Agent 在未读命令/Agent/规则的情况下“等价执行”。
- 为方便合并多个角色，导致生成与独立校验共享同一上下文。
- 只在 TOML 写一句“读取参考文件”，但不在 TOML 内保留关键门禁和写入边界。
- 把用户可见的下一步提示误当成必须等待批准。
- 以文件存在、测试“看起来会过”或生成者自评代替状态证据。

## 十、框架完整性门禁

修改本 Skill 后必须运行：

```powershell
uv run python .agents/skills/codex-sdd/scripts/validate_framework.py
uv run python .agents/skills/codex-sdd/scripts/self_test.py
```

前者核对一对一资源、TOML 注册、禁用机制和最低规则密度；后者验证持久化状态、恢复和哈希失效逻辑。任一失败都表示迁移或后续修改不完整。
---

## 原命令调用规范的逐节保真映射

原 `KIRO_COMMAND_CALLING_SPEC` 的命令发现、Agent 调用、参数、返回、日志和禁止项均已迁入上方正式协议。
本节逐项说明运行机制替换，避免旧示例与 Codex 当前事实同时存在。

### 一、核心原则

- 禁止模拟命令效果：保留，见第一章第 1、2、8 项。
- 禁止直接绕过专责 Agent 创建阶段产物：保留，见第五章统一委派协议。
- 禁止跳过模板、名称检查和完整命令流程：保留，见第一章和第六章。
- 统一子 Agent 执行：映射为 `.codex/agents/*.toml` 注册角色，不再使用旧通用类型名称。

### 二、命令与 Agent 映射

原表中的九个阶段均保留：

1. `spec-init`：主 Agent + `state.py`；
2. `spec-requirements`：`codex_sdd_requirements`；
3. `validate-gap`：`codex_sdd_gap_validator`；
4. `spec-design`：`codex_sdd_design`；
5. `validate-design`：`codex_sdd_design_reviewer`；
6. `spec-tasks`：`codex_sdd_tasks`；
7. `spec-impl`：`codex_sdd_impl`；
8. `validate-impl`：`codex_sdd_impl_validator`；
9. `validate-independent`：`codex_sdd_validator`。

对应命令定义、Agent 定义和主要产物已在第四章逐项列出。

### 三、各命令调用模板

原 3.1 至 3.9 节共有的调用结构完整保留为第五章“统一委派协议”：

- `operation`、`spec_id`、`spec_dir`、`mode` 和目标阶段；
- 允许读取的上游产物；
- 必须生成的文件；
- 禁止写入的状态和相邻阶段文件；
- 实际执行状态、产物路径、摘要、问题、验证命令和收尾检查；
- `progress.log` 的结构化阶段事件。

每个命令的专属输入、步骤、输出和失败语义保留在第六章及对应 `references/commands/*.md`。
原规格名称三段式改为 `{版本号}/{大需求模块名称}`，个人项目不保留工号。

### 四、编排 Skill 的共用模板

原 3.10 节要求编排 Skill 复用统一 Agent Prompt、按阶段增量执行并在文档生成后独立校验。
现映射为：

- `SKILL.md` 统一路由；
- 本文件第五章统一委派字段；
- `skill-orchestrator-pattern.md` 的状态恢复、阶段循环和修复循环；
- `.sdd/` 中的阶段、任务、报告与对象哈希；
- requirements/design 生成后立即创建全新独立校验上下文；
- FAIL 默认定向修复并重新校验，不让用户在例行菜单中决定绕过门禁。

### 五、Skill 引用方式

原规范禁止每个 Skill 各自内联一份不同的 Agent Prompt。该约束保留：

- 统一读取本规范、对应命令定义和对应 Agent 定义；
- 自定义 Agent TOML 直接内嵌完整 Agent 协议；
- 不自行缩减文件模式、工具权限、门禁或返回字段；
- 不创建第二套命令命名空间或旧 Agent 目录。

### 六、流程日志规范

原 `progress.log` 的阶段流转要求保留并升级为只追加 JSON Lines：

- 路径：`.sdd/specs/{版本号}/{大需求模块名称}/progress.log`；
- 时间：UTC ISO 8601；
- 每次状态变化只追加一个结构化事件；
- 至少记录事件、阶段、状态和详情；
- 日志只用于审计，不能覆盖 `spec.json` 的状态事实；
- 需求/设计“审批”状态改为独立校验 PASS 与对象哈希。

### 七、用户提示中的命令引用

保留向用户展示 `$codex-sdd <operation>` 的用法，但提示文本不是执行证据。
主 Agent 不能因为输出了下一步命令，就宣称对应阶段已经执行或通过。
