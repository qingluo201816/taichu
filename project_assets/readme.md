# project_assets 目录说明

> 更新日期：2026-07-13

`project_assets/` 是太初单本小说的本地资产根目录，用于保存正文 Markdown、工作区中间态、AI/Agent 运行记录、评测审计和临时生成文件。MongoDB `taichu.knowledge_cards` 是唯一结构事实源，`project_assets/` 下的 JSON/JSONL 不承担兼容事实源职责。

## 本机实际部署位置

- 本说明文件：`C:\Users\wyh\Desktop\Taichu\project_assets\readme.md`。
- 项目资产根目录：`C:\Users\wyh\Desktop\Taichu\project_assets`，由 `PROJECT_ASSETS_DIR` 指定，仍保留在项目目录中。
- MongoDB 数据目录：`E:\Taichu\MongoDB\data\db`，由 `MONGODB_DATA_DIR` 指定。
- MongoDB 日志目录：`E:\Taichu\MongoDB\log`，由 `MONGODB_LOG_DIR` 指定。
- 原小说导入资料：`E:\Taichu\导入资料\太初原小说`，只作为外部导入材料，不属于 `project_assets/`。
- 旧知识 JSON 迁移备份：`E:\Taichu\迁移备份\知识库-20260711-151915`，包含全部 88 张旧卡和 `migration-manifest.json`，不属于运行时数据目录。
- MongoDB 数据和日志不属于 `project_assets/` 目录树；当前开发机把它们放到 E 盘，避免数据库文件占用项目所在磁盘。更换开发机时，应同步更新当前用户环境变量与项目根目录 `.env`，不得仅修改本说明。

旧知识迁移已完成 `apply` 和 `finalize`：58 张有效卡作为 `lifecycle=confirmed` 写入 MongoDB，30 张已弃用重复卡仅保留在 E 盘备份，`source/knowledge/` 已完成对账并删除。存储骨架和业务代码不得重新创建该目录。

## 维护规则

- 修改 `project_assets/` 下的目录结构时，必须同步热更新本文件。
- 新增、删除、移动或改变任一目录职责时，必须在同一次变更里更新“目录结构”和“目录职责说明”。
- 文本事实源优先放在 `source/`；结构事实源归属 MongoDB；可再生成的运行产物放在 `derived/`；缓存、索引、日志和导出物放在 `generated/`。
- 不要把可再生成的缓存或日志当作正式源数据依赖。
- 不创建或保留 `.gitkeep`；目录由存储实现按需创建。
- 评测基准和测试夹具放在 `tests/fixtures/evaluations/`，不得作为 `project_assets/` 的额外顶层目录。

## 数据宪法

- Markdown 是唯一文本事实源，正文与需要保留作者原始表达的长文本必须以 Markdown 为准。
- MongoDB 是唯一结构事实源，作者确认后的角色、地点、势力、物品、事件、规则等结构化事实只以 MongoDB 中 `lifecycle=confirmed` 的记录为准。
- 未来若增加 vector、Elasticsearch、graph 或缓存，它们都只能是可重建派生层。
- SQLite/FTS 已废弃，不属于当前数据目录或后续架构决策。
- AI 不得直接写入 MongoDB，必须先生成 JSON 中间态并通过 schema、来源、冲突和生命周期校验。
- 所有非事实数据必须显式标记 `lifecycle`，取值只能是 `draft`、`confirmed`、`rejected`。

## 数据分层

- `source/`：作者和系统长期维护的本地文本源与工作区状态。正文 Markdown 是文本事实；workspace JSONL 是非事实中间态。
- MongoDB：唯一结构事实源。它不属于 `project_assets/` 目录树，角色、地点、势力、物品、事件、规则等确认事实只存于 `knowledge_cards`。
- `derived/`：AI、Agent 和评测产生的 JSON 中间态、运行快照与审计记录，不等同于正式知识库。
- `generated/`：按需产生的运行日志、导出临时物和可重建缓存，不得承载唯一事实。

## 目录结构

```text
project_assets/
├── source/                                      # 单本小说的正式源数据根目录
│   ├── metadata.yaml                            # 小说级元数据
│   ├── manuscripts/                             # 正文章节、目录清单和大纲源数据
│   │   ├── manifest.json                        # 章节树和卷章元信息
│   │   ├── outline.json                         # 大纲结构数据
│   │   ├── chapters/                            # 当前有效正文稿目录
│   │   │   ├── volume_001_第一卷/               # 第一卷章节正文
│   │   │   ├── volume_002_第二卷/               # 第二卷章节正文
│   │   │   ├── volume_003_第三卷/               # 第三卷章节正文
│   │   │   └── volume_004_第四卷/               # 第四卷章节正文
│   │   └── deleted_chapters/                    # 被删除章节的归档区
│   │       └── volume_004_第四卷/               # 第四卷删除章节归档
│   └── workspace/                               # 工作区状态、收件箱、待处理事实和写作 AI 运行记录
├── derived/                                     # 派生数据和 Agent 运行记录
│   ├── agent_runs/                              # Agent 运行快照根目录
│   │   └── knowledge_extraction/                # 正文知识沉淀 Agent 的运行记录和候选审核项
│   ├── llm_usage/                               # 跨任务模型调用遥测，按需创建 calls.jsonl
│   ├── retrieval/                               # 统一知识召回技术观测，按需创建 calls.jsonl
│   └── agent_evaluations/                       # Agent 效果评估输入快照、结果与审计记录
│       └── knowledge_extraction/                # 知识沉淀评估报告及裁判校准报告
└── generated/                                   # 按需创建的临时生成物根目录
    └── temp/                                    # 前后端运行日志等临时输出
```

## 关键目录职责

### source

`source/` 是本地文本源数据和工作区资产层。正文 Markdown 是唯一文本事实源；结构化事实只存于 MongoDB。

- 正文源文件位于 `source/manuscripts/chapters/`。
- 章节清单位于 `source/manuscripts/manifest.json`。
- 大纲数据位于 `source/manuscripts/outline.json`。
- 收件箱、偏好设置、工作区状态、待处理事实和写作 AI 运行记录位于 `source/workspace/`。
- 写作页 9 个 AI 按钮的真实模型调用轨迹保存在 `source/workspace/writing_ai_runs.jsonl`，用于历史查看、提示词审计和回放，不直接写入正式知识库。
- `source/knowledge/` 已退出运行时结构并在迁移 `finalize` 时删除；`ensure_skeleton()` 不会重建它。

### 旧知识 JSON 迁移结果

旧知识卡不再保存在 `project_assets/` 中作为运行数据。迁移备份固定在：

`E:\Taichu\迁移备份\知识库-20260711-151915`

- 全部 88 张旧 JSON 均已复制并通过迁移清单记录 SHA-256。
- 58 张原 `active` 卡已转换并导入为 MongoDB `lifecycle=confirmed`。
- 30 张原 `deprecated` 重复卡未导入，只存在于备份和迁移清单。
- `finalize` 对账已通过，`project_assets/source/knowledge/` 已删除；后端无 JSON 双写、读取回退或目录重建逻辑。

MongoDB 知识卡统一使用 `lifecycle=draft|confirmed|rejected`；默认列表、事实查询和 AI 有效上下文只读取 `confirmed`。

### derived

`derived/` 是派生数据层。这里保存 Agent 运行快照、LLM 调用记录、评测 JSON 中间态和候选审核项，用于审计与回放；`source/workspace/` 中的 Inbox 与 AI JSONL 也只属于工作区中间态。

跨任务模型调用遥测追加保存在 `derived/llm_usage/calls.jsonl`。每行只包含模型快照、任务来源、Token、费用、耗时、状态、上游请求 ID 和脱敏错误，不保存密钥、鉴权头、完整 Prompt 或模型原文；该目录属于可重建运行遥测，不是正文或结构化知识事实源。

统一知识召回技术观测追加保存在 `derived/retrieval/calls.jsonl`。每行保存召回关联 ID、调用方、模式、策略、过滤范围、候选数、命中数、排名、耗时和脱敏错误；查询与辅助上下文只保存长度和 SHA-256，不重复保存正文或用户完整输入。该记录用于跨消费者排查召回链路，但不替代写作区、知识沉淀 Workflow 或通用 Agent Runtime 各自的业务日志、状态机与评测记录。

知识沉淀效果评估保存在 `derived/agent_evaluations/knowledge_extraction/`。每次评估独立冻结评测集、实际候选、正文、评分参数和模型身份，并保存确定性结果与裁判调用审计；裁判校准报告位于其 `calibration_reports/` 子目录。评估报告和校准报告都是非事实派生数据，通过 `lifecycle` 区分草稿、已确认和已废弃状态，不得反向成为正文或结构化知识事实源。

正文知识沉淀 Agent 的候选卡不单独落到 `source/knowledge/`，而是保存在运行 JSON 的 `review_items[*].suggested_card` 中。只有用户确认并通过 JSON 中间态校验后，才允许由应用层服务写入 MongoDB 成为结构事实。

现有运行记录中的候选处理状态通过 `candidate_status` 表达；非事实数据仍须用 `lifecycle` 表达事实生命周期：

- `pending`：待处理；保留在待处理队列中，本身就表示可以稍后再处理。
- `confirmed`：已确认。
- `rejected`：已废弃，保留在运行记录中用于审计。

### generated

`generated/` 是按需创建的临时生成物层。当前主要保存前后端运行日志；未来新增的导出临时物或缓存必须可删除、可重建。

该目录下的数据不得成为唯一事实来源。若生成物丢失，系统应能从 Markdown 文本事实源、MongoDB 结构事实源和必要的运行流程重新生成。
