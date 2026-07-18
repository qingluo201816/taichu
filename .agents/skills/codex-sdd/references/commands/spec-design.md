# `spec-design`：技术设计生成、评审与独立门禁

## 使命

把已经独立校验通过的需求转化为与太初当前架构一致、边界明确、契约完整、可追踪且可实施的技术设计。

## 参数

```text
$codex-sdd spec-design <版本号>/<大需求模块名称>
```

内部模式为 `generate`、`merge` 或 `repair`。

## 前置门禁

1. `requirements.md` 存在。
2. 最近需求独立报告为 `结论：PASS`。
3. 报告记录的需求哈希与当前 `requirements.md` 一致。
4. `spec.json.phase` 至少为 `requirements_validated`。
5. `state.py validate` 通过。
6. 任一条件失败均返回需求阶段，不允许自动“批准需求”。

## 必须读取

- 根 `AGENTS.md`、`README.md`；
- 已校验 `requirements.md` 及其 PASS 报告；
- `gap-analysis.md`（存在时）；
- `references/agents/spec-design.md`；
- `references/rules/asset-discovery.md`；
- `references/rules/design-discovery-full.md`；
- `references/rules/design-discovery-light.md`；
- `references/rules/design-synthesis.md`；
- `references/rules/design-principles.md`；
- `references/rules/design-review-gate.md`；
- `assets/specs/research.md`；
- `assets/specs/design.md`；
- 涉及 UI 时额外读取根 `DESIGN.md`、`taichu-ui-components` Skill、前端探索规则与前端设计模板。

## 发现分级

- 完整发现：新边界、复杂集成、架构变更、安全/性能关键、未知依赖。
- 轻量发现：在现有明确模式内扩展，重点确认集成点和兼容性。
- 最小发现：真正局部且无新边界的简单改动；仍须验证现有模式和影响面。
- 不确定时升级到更完整的发现。

外部依赖、现行库版本、标准或 API 如可能变化，必须查官方一手资料并在 `research.md` 记录来源。

## 子 Agent 调用

角色：`codex_sdd_design`。

```text
operation: spec-design
spec_id: <id>
spec_dir: <dir>
mode: generate | merge | repair
discovery: full | light | minimal
input_artifacts:
  - requirements.md
  - independent-validation-report-requirements.md
  - gap-analysis.md（存在时）
expected_outputs:
  - research.md（需要发现时）
  - design.md
forbidden_writes:
  - spec.json
  - .sdd/state.json
  - tasks-status.json
  - requirements.md
  - tasks.md
  - 业务代码
```

设计角色完成调查、综合、草稿门禁后才写正式 `design.md`。

## 质量评审与独立校验

1. 主 Agent检查边界承诺、允许依赖、文件结构规划、组件契约、数据/状态、错误、迁移、测试和数字需求追踪。
2. 调用 `codex_sdd_design_reviewer`：
   - 最多三个关键问题；
   - 输出 GO/NO-GO；
   - NO-GO 自动退回设计修复。
3. GO 后登记 `design_ready`。
4. 创建全新 `codex_sdd_validator`，执行 `mode=design`：
   - 阶段一可读已校验需求，但不得读 `design.md`；
   - discovery 落盘后才读目标；
   - 报告含目标哈希与精确 PASS/FAIL。
5. FAIL 退回设计角色定向修复，最多两轮。
6. PASS 由状态脚本登记 `design_validated` 并运行 `state.py validate`。

## 严格约束

- 设计关注架构、边界和契约，不写完整实现代码。
- 设计中引用的现有文件、接口、字段和依赖必须有真实证据。
- 计划新增内容必须明确标为“新增”，不得伪装成现有事实。
- Graphify 仅作可选派生证据；图谱不覆盖目标时使用 `rg`、源码、测试和配置。
- 涉及 `web/` 时只面向 Next.js + shadcn/ui + Tailwind 的桌面网页，并使用中文用户文案。
- 不引入移动端、Vue、旧组件库或与 `DESIGN.md` 冲突的视觉规则。
- 默认自动推进，不等待人工批准。

## 成功输出

```text
执行状态：成功
发现级别：full | light | minimal
研究记录：.../research.md
设计文件：.../design.md
设计评审：GO
独立校验：PASS
对象 SHA-256：...
```
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 保留设计生成、研究分级、上下文加载和状态收尾；批准字段改为独立需求 PASS，设计完成后增加 GO/NO-GO 与独立设计 PASS。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 为规格创建完整的技术设计文档 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <功能名称> [-y] | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
技术设计生成器
解析参数
功能名称: $1
自动批准标志: $2（可选，"-y"）
验证
检查需求是否已完成:

验证 .sdd/specs/$1/ 存在
验证 .sdd/specs/$1/requirements.md 存在
如果验证失败，提示用户先完成需求阶段。

调用子 Agent
将设计生成委托给 spec-design-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="spec-design-agent",
  description="生成技术设计并更新研究日志",
  prompt="""
Feature: $1
Spec directory: .sdd/specs/$1/
Auto-approve: {true if $2 == "-y", else false}

File patterns to read:
- .sdd/specs/$1/*.{json,md}
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料
- .agents/skills/codex-sdd/references/rules/design-*.md
- .agents/skills/codex-sdd/assets/specs/design.md
- .agents/skills/codex-sdd/assets/specs/research.md

Discovery: auto-detect based on requirements
Mode: {generate or merge based on design.md existence}
Language: respect spec.json language for design.md/research.md outputs
"""
)
显示结果
向用户展示子 Agent 的摘要，然后提供下一步指导:

下一阶段: 任务生成
如果设计已批准:

查看生成的设计文档 .sdd/specs/$1/design.md
可选: 运行 $codex-sdd validate-design $1 进行交互式质量评审
然后运行 $codex-sdd spec-tasks $1 -y 生成实现任务
如果需要修改:

提供反馈并重新运行 $codex-sdd spec-design $1
现有设计将作为参考（合并模式）
注意: 进入任务生成阶段前必须完成设计审批。
~~~
