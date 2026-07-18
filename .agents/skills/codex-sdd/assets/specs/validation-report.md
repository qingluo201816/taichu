# {{TARGET}}独立校验报告

## 文档信息

- 规格：{{VERSION}}/{{MODULE}}
- 模式：requirements / design / implementation
- 校验时间：{{TIMESTAMP}}
- 目标对象：`{{TARGET_PATH}}`
- 目标 SHA-256：`{{TARGET_HASH}}`
- discovery：`{{DISCOVERY_PATH}}`
- discovery SHA-256：`{{DISCOVERY_HASH}}`
- Git/工作树基线：{{BASELINE}}

## 1. 结论摘要

{{SUMMARY}}

## 2. 独立发现范围与方法

- 允许的上游：{{ALLOWED_UPSTREAM}}
- 禁止读取目标阶段遵守情况：{{PHASE_SEPARATION}}
- Graphify 覆盖/降级：{{GRAPHIFY_OR_FALLBACK}}
- 执行命令：{{COMMANDS}}

## 3. 匹配项

| # | 发现/预期 | 目标对应 | 证据 |
|---|---|---|---|
| 1 | {{DISCOVERY}} | {{TARGET_SECTION}} | `{{PATH_LINE_OR_COMMAND}}` |

## 4. 错误项

| # | 目标声明 | 项目现实 | 证据 | 严重性 |
|---|---|---|---|---|
| 1 | {{CLAIM}} | {{REALITY}} | `{{EVIDENCE}}` | critical/major/minor |

## 5. 遗漏项

| # | 必需内容 | 目标缺失 | 证据 | 严重性 |
|---|---|---|---|---|
| 1 | {{EXPECTED}} | {{OMISSION}} | `{{EVIDENCE}}` | critical/major/minor |

## 6. 多余项

| # | 目标内容 | 无依据原因 | 证据 | 严重性 |
|---|---|---|---|---|
| 1 | {{EXTRA}} | {{REASON}} | `{{EVIDENCE}}` | major/minor/info |

## 7. 不可验证或规则冲突

| # | 项目 | 类型 | 证据 | 严重性 |
|---|---|---|---|---|
| 1 | {{ITEM}} | 不可验证/规则冲突/过期证据 | `{{EVIDENCE}}` | critical/major/minor |

## 8. 追踪表

| 需求/任务 | 目标章节/设计元素 | 代码/测试 | 结果 |
|---|---|---|---|
| {{ID}} | {{TARGET_ELEMENT}} | `{{EVIDENCE}}` | PASS/FAIL |

## 9. 测试与机械检查

| 检查/命令 | 退出码 | 结果 | 是否必需 |
|---|---:|---|---|
| `{{CHECK}}` | {{CODE}} | {{RESULT}} | 是/否 |

## 10. 分级问题

### Critical

- {{ISSUE_OR_NONE}}

### Major

- {{ISSUE_OR_NONE}}

### Minor

- {{ISSUE_OR_NONE}}

### Info

- {{ISSUE_OR_NONE}}

## 11. 修正项（FAIL 时）

1. 删除/修正：{{CORRECTION}}
2. 补充：{{CORRECTION}}
3. 重新验证：{{CHECK}}

## 12. 门禁理由

{{GATE_REASON}}

结论：{{PASS_OR_FAIL}}
