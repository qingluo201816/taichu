# `validate-design`：设计质量评审

## 使命

以最多三个最重要问题评估设计是否具备实现就绪性，给出有证据的 GO/NO-GO；该评审不替代独立设计 PASS/FAIL 校验。

## 参数

```text
$codex-sdd validate-design <版本号>/<大需求模块名称>
```

## 前置门禁

- 已校验 `requirements.md` 存在。
- `design.md` 存在。
- `state.py validate` 通过。
- 设计尚未登记 `design_ready` 也可评审，但不得因此降低标准。

## 必须读取

- 根 `AGENTS.md` 和相关强制项目规则；
- `requirements.md`、`design.md`、`research.md`（存在时）；
- `references/agents/validate-design.md`；
- `references/rules/design-review.md`；
- `references/rules/design-review-gate.md`；
- 涉及 UI 时读取根 `DESIGN.md` 与前端规则。

## 子 Agent 调用

角色：`codex_sdd_design_reviewer`。

```text
operation: validate-design
spec_id: <id>
spec_dir: <dir>
expected_outputs:
  - design-review-report.md
forbidden_writes:
  - requirements.md
  - design.md
  - research.md
  - spec.json
  - 业务代码
```

## 评审流程

1. 机械检查：需求 ID 覆盖、边界章节、文件规划、组件对应、占位符、依赖方向。
2. 判断检查：架构对齐、职责所有权、契约充分性、数据一致性、错误与恢复、迁移与验证、复杂度是否成比例。
3. 识别最多三个关键问题：
   - 关注点；
   - 影响；
   - 可执行建议；
   - 数字需求 ID；
   - `design.md` 章节或代码事实证据。
4. 认可 1–2 个有证据的设计优点。
5. 给出 `决策：GO` 或 `决策：NO-GO` 及理由。

## 自动流程处理

- GO：主 Agent继续独立设计校验。
- NO-GO：主 Agent把问题交回设计角色定向修复，然后重新评审。
- 不向用户展示例行“是否继续”菜单。
- 只有两轮仍 NO-GO 或发现真实需求歧义时暂停。

## 严格约束

- 评审只做质量门禁，不直接修改设计。
- 不把偏好或追求完美当成阻塞。
- 核心边界冲突、需求缺失、虚构接口、不可执行契约或不成比例复杂度必须 NO-GO。
- 输出保存到规格目录，保留评审证据。
---

## 原参考完整协议（保真迁移）

> 本节按原文件顺序保留角色、使命、成功标准、步骤、约束、输出与失败处理；只替换运行平台、路径和太初已确认冲突。
> 上方 Codex/太初规则是适配覆盖层；本节中若仍出现技术栈示例或交互示例，只取其约束意图，不得覆盖根 `AGENTS.md` 与上方写入边界。

### 本文件的明确适配

- 保留设计质量评审步骤和最多三个关键问题；审批操作改为 GO/NO-GO 报告，不替代独立设计 PASS。
- 原工具清单不直接映射为 TOML `tools` 字段；当前 Codex 客户端工具面由父会话提供，角色权限由允许/禁止行为和写入边界收紧。
- 规格路径统一为 `.sdd/specs/{版本号}/{大需求模块名称}/`，状态更新统一通过 `state.py`。

### 原注册元数据与 Codex 映射

| 原字段 | 原值 | Codex 映射 |
|---|---|---|
| `description` | 交互式技术设计质量评审与验证 | 保留为角色用途与注册描述 |
| `allowed-tools` | Read, Task | 映射到当前工具面与命令禁止项 |
| `argument-hint` | <功能名称> | 映射到 `$codex-sdd` 调用契约 |

### 原协议正文（顺序保留）

~~~text
技术设计验证
解析参数
功能名称: $1
验证
检查设计是否已完成:

验证 .sdd/specs/$1/ 存在
验证 .sdd/specs/$1/design.md 存在
如果验证失败，提示用户先完成设计阶段。

调用子 Agent
将设计验证委托给 validate-design-agent:

使用 Task 工具调用子 Agent，传入文件路径模式:

Task(
  subagent_type="validate-design-agent",
  description="交互式设计评审",
  prompt="""
Feature: $1
Spec directory: .sdd/specs/$1/

File patterns to read:
- .sdd/specs/$1/spec.json
- .sdd/specs/$1/requirements.md
- .sdd/specs/$1/design.md
- AGENTS.md、README.md、DESIGN.md 与适用的当前项目资料
- .agents/skills/codex-sdd/references/rules/design-review.md
"""
)
显示结果
向用户展示子 Agent 的摘要，然后提供下一步指导:

下一阶段: 任务生成
如果设计通过验证（GO 决策）:

查看反馈并根据需要应用更改
运行 $codex-sdd spec-tasks $1 生成实现任务
或运行 $codex-sdd spec-tasks $1 -y 自动批准并直接继续
如果设计需要修改（NO-GO 决策）:

解决识别出的关键问题
用改进重新运行 $codex-sdd spec-design $1
用 $codex-sdd validate-design $1 重新验证
注意: 设计验证是推荐但可选的。质量评审有助于尽早发现问题。
~~~
