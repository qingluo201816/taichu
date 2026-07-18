# `validate-gap`：现状与实现差距分析

## 使命

在需求与设计之间，以真实代码、测试、配置和当前项目资料为证据，说明现有能力、缺口、约束、可选方案和需要继续研究的风险。

## 参数

```text
$codex-sdd validate-gap <版本号>/<大需求模块名称>
```

## 前置门禁

- `requirements.md` 存在且需求独立校验 PASS、哈希有效。
- `state.py validate` 通过。
- 需求未通过时停止，不用差距分析替代需求修复。

## 必须读取

- 根 `AGENTS.md`、`README.md` 与相关当前资料；
- 已校验 `requirements.md`；
- `references/agents/validate-gap.md`；
- `references/rules/gap-analysis.md`；
- `references/rules/asset-discovery.md`；
- 相关源码、测试、配置和依赖清单。

## 子 Agent 调用

角色：`codex_sdd_gap_validator`。

```text
operation: validate-gap
spec_id: <id>
spec_dir: <dir>
input_artifacts:
  - requirements.md
expected_outputs:
  - gap-analysis.md
forbidden_writes:
  - requirements.md
  - design.md
  - tasks.md
  - spec.json
  - .sdd/state.json
  - 业务代码
```

## 输出必须包含

1. 调查范围与证据清单。
2. 需求到现有资产映射。
3. 可复用能力、缺失能力、未知项和架构约束。
4. 扩展现有组件、新建组件、混合方案中实际可行的选项。
5. 每个选项的边界、集成点、清理影响、验证关注点和风险。
6. 建议设计阶段继续调查的事项。
7. 复杂度按影响面、依赖、未知项、数据迁移和验证成本定性分级；不得给出人工天数、工时、排期或人员估算。

## Graphify 使用

- 若 `graphify-out/graph.json` 存在且扫描根覆盖目标，使用 Graphify 当前 `query/path/explain` 接口。
- 必须引用图谱返回的 `source_location`，并用源码抽样复核关键结论。
- 图谱不覆盖目标、过期或不可用时，直接使用 `rg`、`rg --files`、源码、测试和配置。
- Graphify 是派生索引，不能凌驾于源码与当前项目事实。

## 收尾

- 主 Agent核对 `gap-analysis.md` 非空、方案和证据完整。
- 用状态脚本登记 `gap_analysis=gap-analysis.md`，但差距分析不单独改变主 phase。
- 自动流程立即进入设计，不请求批准。

## 失败处理

- 代码库信息有限：明确“需新增开发”与未知项，不虚构现有资产。
- 外部依赖不确定：标为设计研究项并查官方一手资料。
- 发现需求冲突：停止设计，返回需求修复。
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 保留现状调查、多方案、风险和研究需求；删除工作量、人员和周期估算。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 分析需求与现有代码库之间的实现差距 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <功能名称> | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
实现差距验证
解析参数
功能名称: $1
验证
检查需求是否已完成:

验证 .sdd/specs/$1/ 存在
验证 .sdd/specs/$1/requirements.md 存在
如果验证失败，提示用户先完成需求阶段。

调用子 Agent
将差距分析委托给 validate-gap-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="validate-gap-agent",
  description="分析实现差距",
  prompt="""
Feature: $1
Spec directory: .sdd/specs/$1/

File patterns to read:
- .sdd/specs/$1/spec.json
- .sdd/specs/$1/requirements.md
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料
- .agents/skills/codex-sdd/references/rules/gap-analysis.md
"""
)
显示结果
向用户展示子 Agent 的摘要，然后提供下一步指导:

下一阶段: 设计生成
如果差距分析完成:

查看差距分析洞察
运行 $codex-sdd spec-design $1 创建技术设计文档
或运行 $codex-sdd spec-design $1 -y 自动批准需求并直接继续
注意: 差距分析是可选的，但对于棕地项目推荐执行，以为设计决策提供信息。
~~~
