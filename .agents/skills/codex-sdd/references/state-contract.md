# 状态与产物契约

## 目录

```text
.sdd/
├── state.json
└── specs/
    └── {版本号}/
        └── {大需求模块名称}/
            ├── spec.json
            ├── progress.log
            ├── requirements.md
            ├── research.md                         # 设计调查需要时生成
            ├── gap-analysis.md                     # 存量系统差距明显时生成
            ├── design.md
            ├── design-review-report.md
            ├── tasks.md
            ├── tasks-status.json
            ├── implementation-report.md
            ├── validation-discovery-requirements.md
            ├── validation-discovery-design.md
            ├── independent-validation-report-requirements.md
            ├── independent-validation-report-design.md
            └── verification-report.md
```

目录按需创建，不使用 `.gitkeep`。`state.json` 是活动规格索引，`spec.json` 是单个规格的恢复事实源，
`tasks-status.json` 是实现任务状态，`progress.log` 是只追加的 JSON Lines 审计记录。
它们共同替代仅存在于会话内的任务追踪。

活动索引的完整路径是 `.sdd/state.json`。需求、设计和实现门禁均记录对象哈希；目标对象发生任何变化后，旧 PASS 自动失效。

## `spec.json`

脚本维护以下字段：

- `schema`：机器兼容标识，不表示业务开发版本。
- `id`：`{版本号}/{大需求模块名称}`。
- `version`、`module`、`title`、`description`、`language`。
- `phase`：当前已达到的最后有效阶段。
- `status`：`active`、`blocked` 或 `completed`。
- `target_phase`：本次编排目标，可在恢复时继续。
- `artifacts`：已登记产物及相对规格目录的路径，包括需求、研究、差距、设计、设计评审、任务、实现与校验证据。
- `validations`：需求、设计、实现的最近结论、轮次、discovery、目标产物哈希和报告哈希；通过后任一对象变化都会使门禁失效。
- `blocker`：阻塞说明；非阻塞时为 `null`。
- `created_at`、`updated_at`。

禁止手工伪造阶段。所有状态变更通过 `scripts/state.py` 完成。

## 阶段门禁

| 阶段 | 必须存在的证据 |
|---|---|
| `initialized` | `spec.json`、初始 `requirements.md`、`progress.log` |
| `requirements_ready` | 完整 `requirements.md` |
| `requirements_validated` | 需求独立校验报告且结论 `PASS` |
| `design_ready` | `design.md`、含精确 `决策：GO` 的 `design-review-report.md`，必要调查已落入 `research.md` |
| `design_validated` | 设计独立校验报告且结论 `PASS` |
| `tasks_ready` | `tasks.md`、`tasks-status.json` |
| `implementing` | 至少一个任务已进入 `in_progress` 或 `completed` |
| `implementation_ready` | 所有纳入范围任务已完成，存在 `implementation-report.md` |
| `completed` | 实现验证报告且结论 `PASS` |

## 状态脚本

在仓库根目录运行：

```powershell
uv run python .agents/skills/codex-sdd/scripts/state.py init `
  --version 1.0 --module 示例模块 --description "需求原文" `
  --target-phase tasks_ready
uv run python .agents/skills/codex-sdd/scripts/state.py show --spec 1.0/示例模块
uv run python .agents/skills/codex-sdd/scripts/state.py advance `
  --spec 1.0/示例模块 --to requirements_ready `
  --artifact requirements=requirements.md
uv run python .agents/skills/codex-sdd/scripts/state.py validation `
  --spec 1.0/示例模块 --mode requirements --status pass `
  --report independent-validation-report-requirements.md
uv run python .agents/skills/codex-sdd/scripts/state.py advance `
  --spec 1.0/示例模块 --to design_ready `
  --artifact design=design.md `
  --artifact design_review=design-review-report.md
uv run python .agents/skills/codex-sdd/scripts/state.py task-set --spec 1.0/示例模块 --task-id 1.1 --status completed
uv run python .agents/skills/codex-sdd/scripts/state.py validate --spec 1.0/示例模块
uv run python .agents/skills/codex-sdd/scripts/state.py repair-index --active-spec 1.0/示例模块
```

脚本支持 `--root <路径>`，仅用于在另一个明确工作区或临时验证目录中运行。

`spec.json` 与 `.sdd/state.json` 分别原子写入，不宣称跨文件事务。
进程若恰好在两次写入之间中断，`validate` 会报告索引漂移；
使用 `repair-index` 可从全部 `spec.json` 重建工作区索引。
`progress.log` 是审计记录，不覆盖 `spec.json` 的状态事实。
