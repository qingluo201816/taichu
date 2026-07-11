# project_assets 目录说明

> 更新日期：2026-07-11

`project_assets/` 是太初单本小说的本地资产根目录，用于保存正文 Markdown、工作区资产、AI 运行产物、过渡 JSON、索引缓存和临时生成文件。结构化事实的目标事实源是 MongoDB，不是 `project_assets/` 下的 JSON 文件。

## 本机实际部署位置

- 本说明文件：`C:\Users\wyh\Desktop\Taichu\project_assets\readme.md`。
- 项目资产根目录：`C:\Users\wyh\Desktop\Taichu\project_assets`，由 `PROJECT_ASSETS_DIR` 指定，仍保留在项目目录中。
- MongoDB 数据目录：`E:\Taichu\MongoDB\data\db`，由 `MONGODB_DATA_DIR` 指定。
- MongoDB 日志目录：`E:\Taichu\MongoDB\log`，由 `MONGODB_LOG_DIR` 指定。
- 原小说导入资料：`E:\Taichu\导入资料\太初原小说`，只作为外部导入材料，不属于 `project_assets/`。
- MongoDB 数据和日志不属于 `project_assets/` 目录树；当前开发机把它们放到 E 盘，避免数据库文件占用项目所在磁盘。更换开发机时，应同步更新当前用户环境变量与项目根目录 `.env`，不得仅修改本说明。

当前代码仍使用 `source/knowledge/` 下的 JSON 兼容仓库；以上 MongoDB 目录是目标结构事实源的本地运行位置，不表示现有 JSON 数据已经迁移或业务代码已经完成 MongoDB 接入。

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
- 所有索引都是可重建派生层，包括 vector、Elasticsearch、graph、SQLite/FTS 和缓存。
- AI 不得直接写入 MongoDB，必须先生成 JSON 中间态并通过 schema、来源、冲突和生命周期校验。
- 所有非事实数据必须显式标记 `lifecycle`，取值只能是 `draft`、`confirmed`、`rejected`。

## 数据分层

- `source/`：作者和系统长期维护的本地源数据。这里保存正文 Markdown、目录清单、大纲、工作区状态和迁移前兼容 JSON。
- MongoDB：结构化事实源。这里不属于 `project_assets/` 目录树，但它是角色、地点、势力、物品、事件、规则等结构事实的目标事实源。
- `derived/`：由正文、结构化知识或 Agent 运行派生出的 JSON 中间态、运行快照与审计记录。不等同于正式知识库。
- `generated/`：可重建的生成物、缓存、索引、导出包和临时日志。不得承载唯一事实。

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
│   ├── knowledge/                               # 迁移前结构化知识 JSON 兼容目录，目标架构不以此作为结构事实源
│   │   ├── character/                           # 角色知识卡
│   │   ├── event/                               # 事件知识卡
│   │   ├── faction/                             # 势力知识卡
│   │   ├── item/                                # 物品知识卡
│   │   ├── location/                            # 地点知识卡
│   │   ├── realm/                               # 境界知识卡
│   │   ├── rule/                                # 规则设定知识卡
│   │   └── technique/                           # 功法知识卡
│   └── workspace/                               # 工作区状态、收件箱、待处理事实和写作 AI 运行记录
├── derived/                                     # 派生数据和 Agent 运行记录
│   ├── agent_runs/                              # Agent 运行快照根目录
│   │   └── knowledge_extraction/                # 正文知识沉淀 Agent 的运行记录和候选审核项
│   ├── llm_usage/                               # 跨任务模型调用遥测，按需创建 calls.jsonl
│   └── agent_evaluations/                       # Agent 效果评估输入快照、结果与审计记录
│       └── knowledge_extraction/                # 知识沉淀评估报告及裁判校准报告
└── generated/                                   # 可重建生成物、缓存、索引和临时文件
    ├── embedding_cache/                         # 嵌入向量计算缓存
    ├── exports/                                 # 导出文件输出目录
    ├── search_index/                            # 搜索索引生成目录
    ├── sqlite/                                  # SQLite 本地生成数据库目录
    ├── temp/                                    # 临时日志和开发运行输出
    └── vector_store/                            # 向量库生成目录
```

## 关键目录职责

### source

`source/` 是本地文本源数据和工作区资产层。正文 Markdown 是文本事实源；结构化事实的目标事实源是 MongoDB。

- 正文源文件位于 `source/manuscripts/chapters/`。
- 章节清单位于 `source/manuscripts/manifest.json`。
- 大纲数据位于 `source/manuscripts/outline.json`。
- 迁移前兼容知识卡位于 `source/knowledge/{类型}/`；新增架构不得继续把该目录定义为结构事实源。
- 收件箱、偏好设置、工作区状态、待处理事实和写作 AI 运行记录位于 `source/workspace/`。
- 写作页 9 个 AI 按钮的真实模型调用轨迹保存在 `source/workspace/writing_ai_runs.jsonl`，用于历史查看、提示词审计和回放，不直接写入正式知识库。
- 旧版 `source/characters/`、`source/factions/`、`source/locations/`、`source/techniques/`、`source/plots/` 等空占位目录已移除；结构化知识统一查看 `source/knowledge/{类型}/`。

### source/knowledge

`source/knowledge/` 是迁移前结构化知识 JSON 兼容目录。每张知识卡是一个独立 JSON 文件，按类型分目录保存；MongoDB 接入完成后，该目录只能作为迁移材料、导出快照或人工排查材料，不再作为结构事实源扩展。

兼容知识卡当前仍通过 `status` 表达业务状态：

- `active`：有效知识卡，会参与后续检索和 Agent 匹配。
- `draft`：草稿。
- `deprecated`：已弃用，相当于软删除；文件保留，但不应作为有效知识使用，也不应出现在前端普通列表、筛选结果、搜索结果或默认视图中。

新增非事实数据必须使用 `lifecycle` 表达事实生命周期：

- `draft`：草稿或候选。
- `confirmed`：作者确认。
- `rejected`：作者拒绝或废弃。

### derived

`derived/` 是派生数据层。这里保存 Agent 运行快照、LLM 调用记录、JSON 中间态和候选审核项，用于审计与回放。

跨任务模型调用遥测追加保存在 `derived/llm_usage/calls.jsonl`。每行只包含模型快照、任务来源、Token、费用、耗时、状态、上游请求 ID 和脱敏错误，不保存密钥、鉴权头、完整 Prompt 或模型原文；该目录属于可重建运行遥测，不是正文或结构化知识事实源。

知识沉淀效果评估保存在 `derived/agent_evaluations/knowledge_extraction/`。每次评估独立冻结评测集、实际候选、正文、评分参数和模型身份，并保存确定性结果与裁判调用审计；裁判校准报告位于其 `calibration_reports/` 子目录。评估报告和校准报告都是非事实派生数据，通过 `lifecycle` 区分草稿、已确认和已废弃状态，不得反向成为正文或结构化知识事实源。

正文知识沉淀 Agent 的候选卡不单独落到 `source/knowledge/`，而是保存在运行 JSON 的 `review_items[*].suggested_card` 中。只有用户确认并通过 JSON 中间态校验后，才允许由应用层服务写入 MongoDB 成为结构事实。

兼容运行记录中的候选项状态当前通过 `candidate_status` 表达；新增非事实数据必须同时或改用 `lifecycle` 表达事实生命周期：

- `pending`：待处理；保留在待处理队列中，本身就表示可以稍后再处理。
- `confirmed`：已确认。
- `rejected`：已废弃，保留在运行记录中用于审计。

### generated

`generated/` 是可重建生成物层。这里可以保存缓存、索引、导出文件、临时日志和本地数据库文件。

该目录下的数据不得成为唯一事实来源。若生成物丢失，系统应能从 Markdown 文本事实源、MongoDB 结构事实源和必要的运行流程重新生成。
