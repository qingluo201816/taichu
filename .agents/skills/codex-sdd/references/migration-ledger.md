# Codex SDD 逐项迁移台账

## 1. 台账目的

本台账用于证明原始参考包中的每一个非空文件都有明确、可审计的 Codex 去向。迁移不是把多个严格文件压缩成一段概述，而是保留原有职责、步骤、输入输出、门禁、禁止项和模板结构，再对运行机制与太初项目事实做必要适配。

完整性口径：

- 原始参考文件共 57 个。
- 其中 56 个包含有效内容：10 个 Agent、12 个命令、2 个编排规范、15 个规则、17 个模板。
- `taichu/README.txt` 为空文件，不承载规则；按“旧 SDD 文件统一删除且不留运行残留”的决策删除，不迁移为空占位文件。
- 56 个非空文件均在下列清单中有一对一落点；新增的状态契约、发现报告、验证报告和实现报告不计入原始文件数量。

## 1.1 保真度口径

迁移不再用文件存在和行数冒充保真度，采用三层检查：

1. **直接内容覆盖（43 项）**：可直接保留或只需平台替换的文件，逐行规范化后检查原始约束覆盖率。
   默认门禁为 90%；设计模板因表格、代码块和太初专属章节重排，门禁为 80%。
2. **结构化适配覆盖（13 项）**：对旧技术栈、旧状态机制、工号、审批、图谱或路径事实冲突的文件，
   逐节检查原职责、流程、失败分支和输出是否有明确的新落点；同时要求有效字符量不少于原件的 50%，
   物理行数不少于原件的 65%，防止用少量命中标题冒充完整改写。
3. **注册定义同步（10 项）**：每个 `.codex/agents/*.toml` 的 `developer_instructions`
   必须与对应 `references/agents/*.md` 完整一致，不允许再压成几句摘要。

13 项结构化适配包括：两份编排规范、资产探查、前端探索、差距分析、独立校验、项目事实维护，
以及前端设计、状态 JSON、需求初始化、需求、研究和任务模板。

格式门禁另外要求 Markdown 标题/换行/围栏有效、普通文本不会因单换行折叠成长段，
Markdown、Agent TOML、JSON 与 YAML 不含工具截断占位符或字面量换行，并且物理行不超过 120 字符。

## 2. Agent 定义：10 / 10

### `taichu/agents/spec-design.txt`

- 原始参考：`taichu/agents/spec-design.txt`
- 完整规则落点：`references/agents/spec-design.md`
- Codex 注册入口：`.codex/agents/codex-sdd-design.toml`
- 适配状态：保留设计发现、研究、综合、追踪和输出约束；改用 Codex 子 Agent 与 `.sdd/`。

### `taichu/agents/spec-impl.txt`

- 原始参考：`taichu/agents/spec-impl.txt`
- 完整规则落点：`references/agents/spec-impl.md`
- Codex 注册入口：`.codex/agents/codex-sdd-impl.toml`
- 适配状态：保留测试驱动实现、任务状态、旧实现清理和验证证据；适配太初启动门禁。

### `taichu/agents/spec-independent-validator.txt`

- 原始参考：`taichu/agents/spec-independent-validator.txt`
- 完整规则落点：`references/agents/spec-independent-validator.md`
- Codex 注册入口：`.codex/agents/codex-sdd-validator.toml`
- 适配状态：完整展开独立上下文、先发现后读取、哈希、证据、分级问题和 PASS/FAIL；
  删除不存在的个人图谱服务依赖。

### `taichu/agents/spec-requirements.txt`

- 原始参考：`taichu/agents/spec-requirements.txt`
- 完整规则落点：`references/agents/spec-requirements.md`
- Codex 注册入口：`.codex/agents/codex-sdd-requirements.toml`
- 适配状态：保留 EARS、项目发现、评审、自修复和需求追踪要求。

### `taichu/agents/spec-tasks.txt`

- 原始参考：`taichu/agents/spec-tasks.txt`
- 完整规则落点：`references/agents/spec-tasks.md`
- Codex 注册入口：`.codex/agents/codex-sdd-tasks.toml`
- 适配状态：保留设计到任务的完整覆盖、依赖、并行边界和验收门禁；删除工时估算。

### `taichu/agents/steering-custom.txt`

- 原始参考：`taichu/agents/steering-custom.txt`
- 完整规则落点：`references/agents/steering-custom.md`
- Codex 注册入口：`.codex/agents/codex-sdd-context-custom.toml`
- 适配状态：改为审计和补充现有项目上下文，不建立第二套事实源。

### `taichu/agents/steering.txt`

- 原始参考：`taichu/agents/steering.txt`
- 完整规则落点：`references/agents/steering.md`
- Codex 注册入口：`.codex/agents/codex-sdd-context-sync.toml`
- 适配状态：改为同步 README、AGENTS、DESIGN 等现有权威文件。

### `taichu/agents/validate-design.txt`

- 原始参考：`taichu/agents/validate-design.txt`
- 完整规则落点：`references/agents/validate-design.md`
- Codex 注册入口：`.codex/agents/codex-sdd-design-reviewer.toml`
- 适配状态：保留设计质量审查与 GO / NO-GO 门禁，独立验证仍由独立校验 Agent 承担。

### `taichu/agents/validate-gap.txt`

- 原始参考：`taichu/agents/validate-gap.txt`
- 完整规则落点：`references/agents/validate-gap.md`
- Codex 注册入口：`.codex/agents/codex-sdd-gap-validator.toml`
- 适配状态：保留需求与现状差距、依赖、风险、未知项和证据要求。

### `taichu/agents/validate-impl.txt`

- 原始参考：`taichu/agents/validate-impl.txt`
- 完整规则落点：`references/agents/validate-impl.md`
- Codex 注册入口：`.codex/agents/codex-sdd-impl-validator.toml`
- 适配状态：保留实现差异、测试、清理、启动和验收证据检查。


Agent 的 Markdown 文件是完整规则正文；10 个 TOML 的 `developer_instructions` 均直接内嵌对应 Markdown 全文。
保真度审计逐字核对二者，任一处不同都会失败，防止注册入口被脱离上下文调用时降级。

## 3. 命令规范：12 / 12

### `taichu/commands/spec-init.txt`

- 原始参考：`taichu/commands/spec-init.txt`
- Codex 命令规范：`references/commands/spec-init.md`
- `$codex-sdd` 操作：`spec-init`
- 适配状态：规格标识改为 `{版本号}/{大需求模块名称}`，个人项目不使用工号。

### `taichu/commands/spec-requirements.txt`

- 原始参考：`taichu/commands/spec-requirements.txt`
- Codex 命令规范：`references/commands/spec-requirements.md`
- `$codex-sdd` 操作：`spec-requirements`
- 适配状态：保留发现、EARS、评审、自修复、独立验证和状态推进。

### `taichu/commands/validate-gap.txt`

- 原始参考：`taichu/commands/validate-gap.txt`
- Codex 命令规范：`references/commands/validate-gap.md`
- `$codex-sdd` 操作：`validate-gap`
- 适配状态：保留差距分析的输入、输出、证据和失败语义。

### `taichu/commands/spec-design.txt`

- 原始参考：`taichu/commands/spec-design.txt`
- Codex 命令规范：`references/commands/spec-design.md`
- `$codex-sdd` 操作：`spec-design`
- 适配状态：保留研究、设计、普通审查、独立审查和门禁；前端与 Graphify 规则按当前项目改写。

### `taichu/commands/validate-design.txt`

- 原始参考：`taichu/commands/validate-design.txt`
- Codex 命令规范：`references/commands/validate-design.md`
- `$codex-sdd` 操作：`validate-design`
- 适配状态：保留设计审查报告与 GO / NO-GO 决策。

### `taichu/commands/spec-tasks.txt`

- 原始参考：`taichu/commands/spec-tasks.txt`
- Codex 命令规范：`references/commands/spec-tasks.md`
- `$codex-sdd` 操作：`spec-tasks`
- 适配状态：保留追踪、依赖、并行与任务状态初始化；删除工时估算。

### `taichu/commands/spec-impl.txt`

- 原始参考：`taichu/commands/spec-impl.txt`
- Codex 命令规范：`references/commands/spec-impl.md`
- `$codex-sdd` 操作：`spec-impl`
- 适配状态：保留实现、测试、清理、启动验证、普通验证与独立验证。

### `taichu/commands/validate-impl.txt`

- 原始参考：`taichu/commands/validate-impl.txt`
- Codex 命令规范：`references/commands/validate-impl.md`
- `$codex-sdd` 操作：`validate-impl`
- 适配状态：保留实现验证和失败修复回路。

### `taichu/commands/spec-quick.txt`

- 原始参考：`taichu/commands/spec-quick.txt`
- Codex 命令规范：`references/commands/spec-quick.md`
- `$codex-sdd` 操作：`run`
- 适配状态：从逐步审批改为默认自动串行推进；只在真正阻塞时停下。

### `taichu/commands/spec-status.txt`

- 原始参考：`taichu/commands/spec-status.txt`
- Codex 命令规范：`references/commands/spec-status.md`
- `$codex-sdd` 操作：`status`、`resume`
- 适配状态：用 `.sdd/` 落盘状态替代会话内任务记忆，支持上下文压缩和会话恢复。

### `taichu/commands/steering.txt`

- 原始参考：`taichu/commands/steering.txt`
- Codex 命令规范：`references/commands/steering.md`
- `$codex-sdd` 操作：`project-context`
- 适配状态：同步现有权威文档，不生成并行 steering 目录。

### `taichu/commands/steering-custom.txt`

- 原始参考：`taichu/commands/steering-custom.txt`
- Codex 命令规范：`references/commands/steering-custom.md`
- `$codex-sdd` 操作：`project-context-custom`
- 适配状态：按需审计专题上下文，模板只作为问题清单。


Codex 客户端不依赖目录自动生成斜杠命令；统一通过项目 Skill `$codex-sdd <操作>` 路由，并由 `.codex/agents/*.toml` 注册可调用角色。

## 4. 编排规范：2 / 2

### `taichu/orchestration-rules/KIRO_COMMAND_CALLING_SPEC.txt`

- 原始参考：`taichu/orchestration-rules/KIRO_COMMAND_CALLING_SPEC.txt`
- 新落点：`references/orchestration/command-calling-spec.md`
- 适配状态：保留命令调用契约、输入输出和错误语义；替换为 `$codex-sdd`、自定义 Agent、磁盘状态与默认自动推进。

### `taichu/orchestration-rules/SKILL_ORCHESTRATOR_PATTERN.txt`

- 原始参考：`taichu/orchestration-rules/SKILL_ORCHESTRATOR_PATTERN.txt`
- 新落点：`references/orchestration/skill-orchestrator-pattern.md`
- 适配状态：实现缺失的 Skill 编排器，覆盖 init → requirements → design → tasks → impl、恢复、修复回路与禁止模拟执行。


## 5. 规则文件：15 / 15

### `taichu/rules/asset-discovery.txt`

- 原始参考：`taichu/rules/asset-discovery.txt`
- 新落点：`references/rules/asset-discovery.md`
- 适配状态：按当前太初仓库、Graphify 覆盖边界和 `rg` 回退路径重写。

### `taichu/rules/design-discovery-full.txt`

- 原始参考：`taichu/rules/design-discovery-full.txt`
- 新落点：`references/rules/design-discovery-full.md`
- 适配状态：保留完整研究流程，外部技术事实要求优先使用官方一手资料。

### `taichu/rules/design-discovery-light.txt`

- 原始参考：`taichu/rules/design-discovery-light.txt`
- 新落点：`references/rules/design-discovery-light.md`
- 适配状态：保留轻量发现边界和升级条件。

### `taichu/rules/design-principles.txt`

- 原始参考：`taichu/rules/design-principles.txt`
- 新落点：`references/rules/design-principles.md`
- 适配状态：保留设计原则、边界、契约、可验证性和现有系统对齐要求。

### `taichu/rules/design-review-gate.txt`

- 原始参考：`taichu/rules/design-review-gate.txt`
- 新落点：`references/rules/design-review-gate.md`
- 适配状态：保留设计阶段门禁与不可跳过条件。

### `taichu/rules/design-review.txt`

- 原始参考：`taichu/rules/design-review.txt`
- 新落点：`references/rules/design-review.md`
- 适配状态：保留完整设计审查维度和问题分级。

### `taichu/rules/design-synthesis.txt`

- 原始参考：`taichu/rules/design-synthesis.txt`
- 新落点：`references/rules/design-synthesis.md`
- 适配状态：保留研究证据到设计决策的综合规则。

### `taichu/rules/ears-format.txt`

- 原始参考：`taichu/rules/ears-format.txt`
- 新落点：`references/rules/ears-format.md`
- 适配状态：保留 EARS 句式、编号、验收和禁止模糊措辞。

### `taichu/rules/frontend-exploration-rules.txt`

- 原始参考：`taichu/rules/frontend-exploration-rules.txt`
- 新落点：`references/rules/frontend-exploration-rules.md`
- 适配状态：原内容事实失真，保留探索结构并改为当前 Next.js、React、shadcn/ui、Tailwind 与桌面端约束。

### `taichu/rules/gap-analysis.txt`

- 原始参考：`taichu/rules/gap-analysis.txt`
- 新落点：`references/rules/gap-analysis.md`
- 适配状态：保留差距分析结构；去除工时、人员和周期估算。

### `taichu/rules/independent-validation-gate.txt`

- 原始参考：`taichu/rules/independent-validation-gate.txt`
- 新落点：`references/rules/independent-validation-gate.md`
- 适配状态：完整强化两阶段隔离、对象哈希、证据、结论格式和写入边界。

### `taichu/rules/requirements-review-gate.txt`

- 原始参考：`taichu/rules/requirements-review-gate.txt`
- 新落点：`references/rules/requirements-review-gate.md`
- 适配状态：保留需求门禁，并明确 EARS 的 `The system shall` 主句。

### `taichu/rules/steering-principles.txt`

- 原始参考：`taichu/rules/steering-principles.txt`
- 新落点：`references/rules/steering-principles.md`
- 适配状态：适配为现有权威文件审计，不创建重复项目记忆。

### `taichu/rules/tasks-generation.txt`

- 原始参考：`taichu/rules/tasks-generation.txt`
- 新落点：`references/rules/tasks-generation.md`
- 适配状态：保留任务拆分、追踪、依赖和验收；改为按可验证结果拆分，不估工时。

### `taichu/rules/tasks-parallel-analysis.txt`

- 原始参考：`taichu/rules/tasks-parallel-analysis.txt`
- 新落点：`references/rules/tasks-parallel-analysis.md`
- 适配状态：保留并行安全、文件所有权和依赖判定。


## 6. 模板：17 / 17

### `taichu/templates/specs/init.json`

- 原始参考：`taichu/templates/specs/init.json`
- 新落点：`assets/specs/init.json`
- 适配状态：改为 `.sdd` 状态契约和无工号规格标识。

### `taichu/templates/specs/requirements-init.txt`

- 原始参考：`taichu/templates/specs/requirements-init.txt`
- 新落点：`assets/specs/requirements-init.md`
- 适配状态：保留初始需求占位结构。

### `taichu/templates/specs/requirements.txt`

- 原始参考：`taichu/templates/specs/requirements.txt`
- 新落点：`assets/specs/requirements.md`
- 适配状态：扩展为中文规格正文、EARS、追踪和非功能约束模板。

### `taichu/templates/specs/research.txt`

- 原始参考：`taichu/templates/specs/research.txt`
- 新落点：`assets/specs/research.md`
- 适配状态：保留研究日志、来源、未知项与决策证据。

### `taichu/templates/specs/design.txt`

- 原始参考：`taichu/templates/specs/design.txt`
- 新落点：`assets/specs/design.md`
- 适配状态：保留完整设计章节；Graphify 与前端章节按当前项目适配。

### `taichu/templates/specs/frontend-design-section.txt`

- 原始参考：`taichu/templates/specs/frontend-design-section.txt`
- 新落点：`assets/specs/frontend-design-section.md`
- 适配状态：原事实失真，结构保留，内容改为当前太初桌面 Web 约束。

### `taichu/templates/specs/tasks.txt`

- 原始参考：`taichu/templates/specs/tasks.txt`
- 新落点：`assets/specs/tasks.md`
- 适配状态：保留追踪、依赖、并行、验收和状态字段，删除工时。

### `taichu/templates/steering/product.txt`

- 原始参考：`taichu/templates/steering/product.txt`
- 新落点：`assets/project-context/product.md`
- 适配状态：仅作现有产品规则的审计清单，不取代 README / AGENTS。

### `taichu/templates/steering/structure.txt`

- 原始参考：`taichu/templates/steering/structure.txt`
- 新落点：`assets/project-context/structure.md`
- 适配状态：仅作现有目录事实的审计清单。

### `taichu/templates/steering/tech.txt`

- 原始参考：`taichu/templates/steering/tech.txt`
- 新落点：`assets/project-context/tech.md`
- 适配状态：仅作现有技术事实的审计清单。

### `taichu/templates/steering-custom/api-standards.txt`

- 原始参考：`taichu/templates/steering-custom/api-standards.txt`
- 新落点：`assets/project-context/api-standards.md`
- 适配状态：仅作 API 专题审计清单。

### `taichu/templates/steering-custom/authentication.txt`

- 原始参考：`taichu/templates/steering-custom/authentication.txt`
- 新落点：`assets/project-context/authentication.md`
- 适配状态：仅作认证专题审计清单。

### `taichu/templates/steering-custom/database.txt`

- 原始参考：`taichu/templates/steering-custom/database.txt`
- 新落点：`assets/project-context/database.md`
- 适配状态：仅作数据库专题审计清单。

### `taichu/templates/steering-custom/deployment.txt`

- 原始参考：`taichu/templates/steering-custom/deployment.txt`
- 新落点：`assets/project-context/deployment.md`
- 适配状态：仅作部署专题审计清单。

### `taichu/templates/steering-custom/error-handling.txt`

- 原始参考：`taichu/templates/steering-custom/error-handling.txt`
- 新落点：`assets/project-context/error-handling.md`
- 适配状态：仅作错误处理专题审计清单。

### `taichu/templates/steering-custom/security.txt`

- 原始参考：`taichu/templates/steering-custom/security.txt`
- 新落点：`assets/project-context/security.md`
- 适配状态：仅作安全专题审计清单。

### `taichu/templates/steering-custom/testing.txt`

- 原始参考：`taichu/templates/steering-custom/testing.txt`
- 新落点：`assets/project-context/testing.md`
- 适配状态：仅作测试专题审计清单。


以下文件是 Codex 运行与独立校验所需的新增产物模板，不冒充原始文件的一对一迁移：

- `assets/specs/validation-discovery.md`
- `assets/specs/validation-report.md`
- `assets/specs/design-review-report.md`
- `assets/specs/implementation-report.md`

## 7. 已确认的迁移决策

1. 名称统一为 Codex SDD，调用入口统一为 `$codex-sdd`。
2. 规格目录统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，个人项目不保留工号层级。
3. 默认全自动推进；正常阶段切换不重复审批，只有信息矛盾、缺少不可推断的关键决策、越权写入或连续修复仍失败时才停下。
4. 会话内任务记忆替换为 `.sdd/state.json`、规格内 `spec.json`、`tasks-status.json`、报告文件和对象哈希；`status` 与 `resume` 只以磁盘事实恢复。
5. 原本缺失的自动化 Skill 编排已实现，支持完整阶段、单阶段、状态查询和恢复。
6. Graphify 只在覆盖当前目标路径且索引可用时作为代码发现入口；不覆盖时使用 `rg`、代码、测试和 Git 证据，不虚构图谱结论。
7. 不依赖个人项目不存在的额外图谱服务；任何验证都必须有本地可复查证据。
8. 前端探索规则和设计章节按当前太初的 Next.js、React、shadcn/ui、Tailwind、桌面浏览器与 `DESIGN.md` 重写。
9. 不生成工时、人数、周期或排期估算。
10. README、AGENTS、DESIGN、配置、代码和测试继续作为项目事实源；上下文模板不能建立第二套权威文档。

## 8. 防压缩门禁

`scripts/validate_framework.py` 对上述 56 个落点执行存在性、关键条款、TOML 可解析性、角色数量、
遗留机制词和目录清理检查。`scripts/audit_fidelity.py` 另外执行原始内容覆盖、结构化适配章节与内容量、
Markdown 换行、长行、围栏和 TOML 协议同步检查。

最低规模不是文档质量的替代品。任何内容调整必须同时通过完整性、保真度和状态自测三道门禁。
