# 存储与检索方案

## 1. 存储分工

| 内容 | 主记录 | 是否事实 | 是否可删 | 说明 |
|---|---|---:|---:|---|
| 章节正文 | Markdown | 是 | 否 | 正文唯一事实源 |
| 章节 manifest | JSON | 结构源 | 否 | 卷/章顺序与当前章 |
| Knowledge | JSON | 是 | 否 | 作者确认事实 |
| AIResultCard | JSONL | 否 | 否 | 用户创作资产 |
| IdeaCard | JSONL | 否 | 否 | 用户创作资产 |
| PendingFact | JSONL | 否 | 否 | 确认后写 Knowledge |
| ChapterSummary | JSONL | 派生辅助 | 否 | confirmed 也必须回指正文 |
| SQLite | generated db | 否 | 是 | 投影、索引、分页、统计 |
| FTS | SQLite/search_index | 否 | 是 | 可重建 |
| Embedding | generated | 否 | 是 | 可重建 |

## 2. SQLite v1

SQLite 放：

- FTS5 表。
- exact alias 投影。
- embedding chunk 投影。
- AI card / inbox / pending fact 的查询投影。
- word_count、最近编辑、索引状态。

SQLite 不放：

- 唯一章节正文。
- 唯一 Knowledge。
- 唯一 AI 卡片状态。
- 唯一 PendingFact。
- 唯一灵感。

## 3. 检索组合

检索顺序：

1. exact：实体 ID、别名、人名、功法名、法宝名、境界名。
2. FTS：SQLite FTS5，中文可用 trigram 或项目确认的中文分词策略。
3. vector-lite：先轻量实现，可用本地 embedding 表 + 暴力余弦，验证价值。
4. hybrid merge：exact > fts > vector，去重后按 score 与 source 质量排序。

## 4. 中文玄幻短实体注意点

- 2-4 字人名、功法名、法宝名不能只靠向量。
- 必须有 EntityAlias 表/投影。
- 同名角色要靠稳定 ID、source_ref、上下文 disambiguation。
- 别名、称号、宗门简称必须可登记。
- 检索结果必须显示来源摘录。

## 5. 索引重建

重建输入：`project_assets/source/`。

重建输出：`project_assets/generated/`。

删除 `generated/` 后，系统必须能重建：

- SQLite projection
- FTS
- entity alias projection
- embedding chunks
- word count
- search cache

不能要求用户从数据库恢复任何唯一资产。
