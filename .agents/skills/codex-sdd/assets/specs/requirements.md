# {{TITLE}}需求规格

## 文档信息

- 规格：{{VERSION}}/{{MODULE}}
- 原始需求：{{PROJECT_DESCRIPTION}}
- 语言：zh-CN
- 状态：需求草稿门禁通过，等待/已完成独立校验

## 1. 概述

{{INTRODUCTION}}

说明目标用户/运营者、需要解决的问题、当前背景和预期价值。不写技术实现。

## 2. 现有资产探查

### 2.1 项目事实源

| 资料 | 状态 | 关键事实 | 对本规格影响 |
|---|---|---|---|
| `AGENTS.md` | 当前规则 | {{PROJECT_RULES}} | {{IMPACT}} |
| {{DOC_PATH}} | 当前/临时/历史 | {{DOC_FACT}} | {{IMPACT}} |

### 2.2 后端资产

| 探查项 | 现有/新增/未知 | 发现 | 证据 | 对需求影响 |
|---|---|---|---|---|
| 领域/应用模块 | {{STATUS}} | {{FINDING}} | `path:line` | {{IMPACT}} |
| API/契约 | {{STATUS}} | {{FINDING}} | `path:line` | {{IMPACT}} |
| 数据与生命周期 | {{STATUS}} | {{FINDING}} | `path:line` | {{IMPACT}} |
| 测试/评测 | {{STATUS}} | {{FINDING}} | `path:line` | {{IMPACT}} |
| 启动/配置 | {{STATUS}} | {{FINDING}} | `path:line` | {{IMPACT}} |

### 2.3 前端资产（涉及 UI 时）

| 页面/组件/API | 现有/新增/未知 | 路径 | 可复用能力 | 对需求影响 |
|---|---|---|---|---|
| {{ASSET}} | {{STATUS}} | {{PATH}} | {{REUSE}} | {{IMPACT}} |

### 2.4 Graphify 覆盖

- 图谱存在：是 / 否
- `.graphify_root`：{{GRAPH_ROOT}}
- 是否覆盖目标：是 / 否
- 使用的当前查询：{{QUERIES}}
- 源码复核：{{SOURCE_CHECK}}
- 降级方式：{{FALLBACK}}

Graphify 不是必需事实源；不覆盖目标时使用 `rg`、源码、测试和配置。

## 3. 范围边界

### 3.1 范围内

- {{IN_SCOPE_BEHAVIOR}}

### 3.2 范围外

- {{OUT_OF_SCOPE_BEHAVIOR}}

### 3.3 相邻系统或规格预期

- {{ADJACENT_EXPECTATION}}

### 3.4 约束与假设

| 项目 | 类型 | 内容 | 证据/确认方式 |
|---|---|---|---|
| {{ITEM}} | 已确认约束 / 待确认假设 | {{CONTENT}} | {{EVIDENCE}} |

## 4. 需求列表

### 需求 1：{{REQUIREMENT_AREA_1}}

**目标**：作为 {{ROLE}}，我想要 {{CAPABILITY}}，以便 {{BENEFIT}}。

**验收标准**

1.1 When {{EVENT}}, the {{SYSTEM}} shall {{RESPONSE}}.
1.2 While {{PRECONDITION}}, the {{SYSTEM}} shall {{RESPONSE}}.
1.3 If {{UNEXPECTED_TRIGGER}}, the {{SYSTEM}} shall {{RECOVERY_RESPONSE}}.
1.4 Where {{OPTIONAL_FEATURE_CONDITION}}, the {{SYSTEM}} shall {{OPTIONAL_RESPONSE}}.
1.5 The {{SYSTEM}} shall {{UNIVERSAL_RESPONSE}}.

只保留适用模式；固定 EARS 结构词使用英文，变量内容使用中文。每条只描述一个可观察行为。

### 需求 2：{{REQUIREMENT_AREA_2}}

**目标**：作为 {{ROLE}}，我想要 {{CAPABILITY}}，以便 {{BENEFIT}}。

**验收标准**

2.1 When {{EVENT}}, the {{SYSTEM}} shall {{RESPONSE}}.
2.2 If {{TRIGGER}}, the {{SYSTEM}} shall {{RESPONSE}}.

按实际需求继续编号，不混用字母 ID。

## 5. 异常、边缘与恢复覆盖

| 场景 | 关联需求 | 用户/运营者可观察结果 |
|---|---|---|
| {{ERROR_OR_EDGE}} | {{ID}} | {{OBSERVABLE_RESULT}} |

## 6. 非功能期望

仅写用户或运营者可观察的期望，不写技术选型。

| 类别 | 关联需求 | 可观察期望 | 验证方式 |
|---|---|---|---|
| 性能/可靠性/安全/可用性 | {{ID}} | {{EXPECTATION}} | {{VERIFICATION}} |

## 7. 需求追踪摘要

| 需求 ID | 目标 | 资产/约束依据 | 主要验收范围 |
|---|---|---|---|
| 1.1 | {{SUMMARY}} | {{EVIDENCE}} | {{SCOPE}} |

## 8. 未决问题

只列会实质改变范围且无法从项目事实确定的问题。没有则写“无”。

- {{OPEN_QUESTION}}
