# {{MODE}}独立发现

## 文档信息

- 规格：{{VERSION}}/{{MODULE}}
- 模式：requirements / design
- 发现时间：{{TIMESTAMP}}
- 阶段一目标读取：禁止且未读取
- 允许上游：{{ALLOWED_UPSTREAM}}
- Git/工作树基线：{{BASELINE}}

## 1. 调查范围

{{SCOPE}}

## 2. 项目规则与事实

| 事实/约束 | 证据 | 对目标的预期 |
|---|---|---|
| {{FACT}} | `{{PATH_LINE}}` | {{EXPECTATION}} |

## 3. 代码、测试与配置发现

| 对象 | 现有/计划候选/未知 | 证据 | 关系/影响 |
|---|---|---|---|
| {{OBJECT}} | {{STATUS}} | `{{EVIDENCE}}` | {{IMPACT}} |

## 4. Graphify

- 扫描根：{{GRAPH_ROOT}}
- 是否覆盖：{{COVERAGE}}
- 查询与 `source_location`：{{QUERY_RESULT}}
- 源码复核：{{SOURCE_CHECK}}
- 降级：{{FALLBACK}}

## 5. 独立预期清单

| # | 必需内容/约束 | 来源 | 严重性 |
|---|---|---|---|
| 1 | {{EXPECTED}} | {{SOURCE}} | critical/major/minor |

## 6. 风险、歧义和未知

| 项目 | 类型 | 证据 | 校验时处理 |
|---|---|---|---|
| {{ITEM}} | 风险/歧义/未知 | {{EVIDENCE}} | {{HANDLING}} |

## 7. 执行命令

- `{{COMMAND}}` → {{RESULT}}

> 本文件落盘后，独立校验 Agent 才可读取目标文档。
