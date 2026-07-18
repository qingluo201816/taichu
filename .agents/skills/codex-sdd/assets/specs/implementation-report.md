# {{TITLE}}实现报告

## 文档信息

- 规格：{{VERSION}}/{{MODULE}}
- 实现范围：{{TASK_IDS}}
- Git/工作树基线：{{BASELINE}}
- 完成时间：{{TIMESTAMP}}

## 1. 完成任务

| 任务 | 需求 | 结果 | 状态证据 |
|---|---|---|---|
| {{TASK_ID}} | {{REQUIREMENT_IDS}} | {{RESULT}} | {{STATUS_EVIDENCE}} |

## 2. 实际改动

| 文件 | 新增/修改/删除 | 职责与行为 | 关联任务 |
|---|---|---|---|
| `{{PATH}}` | {{CHANGE}} | {{DESCRIPTION}} | {{TASK_ID}} |

## 3. TDD 证据

| 任务 | RED | GREEN | REFACTOR | VERIFY |
|---|---|---|---|---|
| {{TASK_ID}} | 命令、失败原因 | 最小实现与通过 | 清理内容 | 回归命令与结果 |

若行为原已存在，明确记录“已有行为 + 新增回归测试”，不得伪造 RED。

## 4. 需求与设计追踪

| 需求 ID | 设计组件/契约 | 实现位置 | 测试证据 |
|---|---|---|---|
| {{ID}} | {{DESIGN_ELEMENT}} | `{{PATH}}` | `{{TEST}}` |

## 5. 旧实现清理

- 删除的旧函数/接口/状态/字段：{{CLEANUP}}
- 删除的旧入口/组件/文案：{{CLEANUP}}
- 删除的依赖/配置/环境项：{{CLEANUP}}
- 删除或更新的旧测试/文档：{{CLEANUP}}
- 无残留的检索证据：{{COMMAND_AND_RESULT}}

## 6. 与设计的偏差

| 偏差 | 原因 | 影响 | 是否需要回到设计 |
|---|---|---|---|
| {{DEVIATION_OR_NONE}} | {{REASON}} | {{IMPACT}} | 是/否 |

## 7. 自动验证

| 命令 | 退出码 | 结果摘要 | 覆盖范围 |
|---|---:|---|---|
| `{{COMMAND}}` | {{CODE}} | {{RESULT}} | {{SCOPE}} |

未运行项必须列出原因；必需验证未运行时不能声称实现完成。

## 8. 启动与页面验证

- 是否触发 `start.bat` 联动：是/否
- 启动验证：{{RESULT}}
- 前端固定端口：`http://localhost:3000` — {{RESULT}}
- 后端固定端口：`http://127.0.0.1:8000` — {{RESULT}}

## 9. 手动验收

1. {{STEP_AND_EXPECTATION}}
2. {{STEP_AND_EXPECTATION}}

## 10. 未解决问题与限制

- {{ISSUE_OR_NONE}}

> 本报告不作最终 PASS 判定；最终结论由独立实现验证报告给出。
