# project_assets 目录说明

> 更新日期：2026-07-04

`project_assets/` 是太初单本小说的本地资产根目录，用于保存正文源数据、知识库源数据、AI 运行产物、索引缓存和临时生成文件。

## 维护规则

- 修改 `project_assets/` 下的目录结构时，必须同步热更新本文件。
- 新增、删除、移动或改变任一目录职责时，必须在同一次变更里更新“目录结构”和“目录职责说明”。
- 正式源数据优先放在 `source/`；可再生成的运行产物放在 `derived/`；缓存、索引、日志和导出物放在 `generated/`。
- 不要把可再生成的缓存或日志当作正式源数据依赖。

## 数据分层

- `source/`：作者和系统长期维护的源数据。这里的数据代表当前小说的事实来源、正文、知识卡和工作区状态。
- `derived/`：由正文、知识库或 Agent 运行派生出的中间态与运行记录。用于回放、审计和调试，不等同于正式知识库。
- `generated/`：可重建的生成物、缓存、索引、导出包和临时日志。通常不应承载唯一事实。

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
│   ├── knowledge/                               # 第一版结构化知识库源数据
│   │   ├── character/                           # 角色知识卡
│   │   ├── event/                               # 事件知识卡
│   │   ├── faction/                             # 势力知识卡
│   │   ├── item/                                # 物品知识卡
│   │   ├── location/                            # 地点知识卡
│   │   ├── realm/                               # 境界知识卡
│   │   ├── rule/                                # 规则设定知识卡
│   │   └── technique/                           # 功法知识卡
│   ├── workspace/                               # 工作区状态、收件箱、AI 卡片和待处理事实
│   ├── plots/                                   # 剧情资料根目录
│   │   ├── arcs/                                # 剧情弧线资料
│   │   └── outlines/                            # 大纲资料
│   ├── characters/                              # 旧角色资料占位目录，当前知识卡以 knowledge/character 为准
│   ├── factions/                                # 旧势力资料占位目录，当前知识卡以 knowledge/faction 为准
│   ├── inspirations/                            # 灵感资料占位目录
│   ├── locations/                               # 旧地点资料占位目录，当前知识卡以 knowledge/location 为准
│   ├── techniques/                              # 旧功法资料占位目录，当前知识卡以 knowledge/technique 为准
│   ├── templates/                               # 模板资料占位目录
│   ├── timeline/                                # 时间线资料占位目录
│   └── worldbuilding/                           # 世界观资料占位目录
├── derived/                                     # 派生数据和 Agent 运行记录
│   └── agent_runs/                              # Agent 运行快照根目录
│       └── knowledge_extraction/                # 正文知识沉淀 Agent 的运行记录和候选审核项
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

`source/` 是正式源数据层。只要数据需要长期保留、被视为当前小说事实、或需要人工审阅维护，就应优先放在这里。

- 正文源文件位于 `source/manuscripts/chapters/`。
- 章节清单位于 `source/manuscripts/manifest.json`。
- 大纲数据位于 `source/manuscripts/outline.json`。
- 正式知识卡位于 `source/knowledge/{类型}/`。
- 收件箱、AI 卡片、偏好设置和工作区状态位于 `source/workspace/`。

### source/knowledge

`source/knowledge/` 是当前结构化知识库的正式源目录。每张正式知识卡是一个独立 JSON 文件，按类型分目录保存。

知识卡状态通过 `status` 表达生命周期：

- `active`：有效知识卡，会参与后续检索和 Agent 匹配。
- `draft`：草稿。
- `deprecated`：已弃用，相当于软删除；文件保留，但不应作为有效知识使用，也不应出现在前端普通列表、筛选结果、搜索结果或默认视图中。

### derived

`derived/` 是派生数据层。这里保存 Agent 运行快照、LLM 调用记录、中间态和候选审核项，用于审计与回放。

正文知识沉淀 Agent 的候选卡不单独落到 `source/knowledge/`，而是保存在运行 JSON 的 `review_items[*].suggested_card` 中。只有用户确认后，才会写入 `source/knowledge/{类型}/` 成为正式知识卡。

候选项状态通过 `candidate_status` 表达：

- `pending`：待处理；保留在待处理队列中，本身就表示可以稍后再处理。
- `confirmed`：已确认。
- `rejected`：已废弃，保留在运行记录中用于审计。

### generated

`generated/` 是可重建生成物层。这里可以保存缓存、索引、导出文件、临时日志和本地数据库文件。

该目录下的数据原则上不应成为唯一事实来源。若生成物丢失，系统应能从 `source/` 和必要的运行流程重新生成。
