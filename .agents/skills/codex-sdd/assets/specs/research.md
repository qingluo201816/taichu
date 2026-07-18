# 研究与设计决策

## 1. 文档信息

- 规格：{{VERSION}}/{{MODULE}}
- 发现级别：完整 / 轻量 / 最小
- 调查时间：{{TIMESTAMP}}
- 目标：捕获影响架构、契约、边界、迁移和验证的证据与权衡。

## 2. 需求与约束摘要

| 需求 ID | 技术约束 | 非功能约束 | 关键未知 |
|---|---|---|---|
| {{ID}} | {{TECH_CONSTRAINT}} | {{NFR}} | {{UNKNOWN}} |

## 3. 当前项目事实

### 3.1 权威资料

| 资料 | 状态 | 关键事实 | 影响 |
|---|---|---|---|
| `AGENTS.md` | 当前规则 | {{FACT}} | {{IMPACT}} |
| {{PATH}} | 当前/临时/历史 | {{FACT}} | {{IMPACT}} |

### 3.2 代码与测试

| 资产 | 现有/新增候选 | 证据 | 可复用/约束 |
|---|---|---|---|
| {{ASSET}} | {{STATUS}} | `path:line` | {{IMPACT}} |

### 3.3 Graphify

- 图谱路径：{{GRAPH_PATH}}
- 扫描根：{{GRAPH_ROOT}}
- 是否覆盖目标：{{COVERAGE}}
- 查询：`graphify query/path/explain ...`
- 返回的 `source_location`：{{SOURCE_LOCATIONS}}
- 源码复核：{{SOURCE_CHECK}}
- 不可用/不覆盖时的 `rg` 降级：{{FALLBACK}}

不得记录个人项目不存在的图谱服务或旧脚本。

## 4. 前端架构分析（涉及 UI 时）

按 `frontend-exploration-rules.md` 填写：

1. 页面与导航清单。
2. 组件职责树。
3. 组件复用与准入决策。
4. API/后端端点/类型映射。
5. 状态所有权与交互表。
6. 视觉和中文文案约束。
7. 变更文件规划。
8. 测试与固定端口验收。
9. 风险与恢复。
10. Graphify 覆盖/降级。

无 UI 变更时写“本规格无 UI 变更”。

## 5. 外部依赖与技术研究

每个主题使用：

### {{TOPIC}}

- 背景：{{CONTEXT}}
- 一手来源：{{OFFICIAL_SOURCE}}
- 版本/日期：{{VERSION_OR_DATE}}
- 发现：{{FINDING}}
- 约束：{{CONSTRAINT}}
- 对设计影响：{{IMPACT}}
- 仍需验证：{{FOLLOW_UP}}

社区讨论只作问题线索，不作契约证据。

## 6. 架构候选

| 选项 | 边界与工作方式 | 优势 | 风险/限制 | 与当前架构契合 |
|---|---|---|---|---|
| {{OPTION}} | {{DESCRIPTION}} | {{PROS}} | {{RISKS}} | {{FIT}} |

## 7. 设计综合

### 7.1 泛化

- 可泛化的底层能力：{{GENERALIZATION}}
- 保持当前实现范围的方式：{{SCOPE_GUARD}}

### 7.2 构建 vs 采用

- 候选成熟能力：{{EXISTING_SOLUTION}}
- 维护/兼容/许可核对：{{CHECK}}
- 采用或自建结论：{{DECISION}}
- 拒绝其他方案理由：{{REASON}}

### 7.3 简化

- 删除的投机组件/抽象：{{REMOVED}}
- 最小内聚设计：{{MINIMAL_DESIGN}}

## 8. 设计决策

### 决策：{{TITLE}}

- 背景：{{CONTEXT}}
- 替代方案：{{ALTERNATIVES}}
- 选择：{{DECISION}}
- 理由：{{RATIONALE}}
- 权衡：{{TRADE_OFF}}
- 需求：{{REQUIREMENT_IDS}}
- 后续验证：{{VERIFICATION}}

## 9. 风险与缓解

| 风险 | 严重性 | 触发条件 | 缓解 | 验证 |
|---|---|---|---|---|
| {{RISK}} | 高/中/低 | {{TRIGGER}} | {{MITIGATION}} | {{CHECK}} |

## 10. 参考文献

- {{TITLE}} — {{URL_OR_PATH}} — {{RELEVANCE}}
