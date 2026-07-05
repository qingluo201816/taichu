# 正文知识沉淀 Agent 方案

> 更新日期：2026-07-04
>
> 当前版本：v1.2
>
> 当前状态：v1.2 任务包前最终定稿。
>
> 用途：作为后续生成 Codex 执行任务包的唯一事实输入。
>
> 最新修正：第一版必须实现候选质量闸门和证据聚合，GeneralExtractionNode 只输出 raw mentions，不允许 LLM “出现即建卡”；Prompt 版本固定为 general_extraction_v2、character_expert_v2、entity_expert_v2。
>
> 文档维护规则：后续如有新讨论，继续在本文内追加版本记录和修改章节，不再为每轮讨论新增独立方案文档。

## 目录

1. 更新状态与版本记录
2. 定稿结论
3. 存储决策：JSON 先行，MongoDB 后置
4. 目标与非目标
5. 页面入口与工作台布局
6. 数据层与中间态
7. 抽取范围与处理单元
8. LangGraph 工作流
9. 类型专家节点
10. 运行 JSON 结构
11. API 契约
12. Prompt 契约
13. 专家节点输出 schema
14. 候选判断、匹配与审核
15. 评测与回放
16. 与知识库和写作页的关系
17. 第一版不做的事情
18. Codex 任务包生成边界

## 1. 更新状态与版本记录

### 1.1 当前更新状态

本文已从讨论稿收敛为 v1.2 任务包前最终定稿。后续生成 Codex 任务包时，以本文为唯一方案事实源。

v1.1 修正了 JSON 先行、MongoDB 后置的存储决策。v1.2 在此基础上收紧正文知识沉淀 Agent 的核心链路：第一版必须先抽取 raw mentions，再做 mention 规范化、实体证据聚合和候选质量闸门，最后才进入类型专家节点生成可审核候选。实现时不得回退到“LLM 直接输出知识卡”的旧链路。

### 1.2 版本记录

| 版本 | 日期 | 讨论主题 | 状态 |
|---|---|---|---|
| v0.1 | 2026-07-04 | 正文知识沉淀 Agent 的定位、数据层、智能体工作台入口、评测同步建设 | 已合并 |
| v0.2 | 2026-07-04 | 第一版抽取范围、章节调度单元、JSON 中间态、LangGraph 主图草案 | 已合并 |
| v0.3 | 2026-07-04 | 第一版入口、LLM 调用记录、类型专家节点拆分、候选确认方式、首批抽取类型 | 已合并 |
| v0.4 | 2026-07-04 | 旧独立对话服务清理边界、候选匹配 active 知识卡规则 | 已合并 |
| v0.5 | 2026-07-04 | 智能体工作台布局、JSON 中间态、Prompt 拆分、输出 schema、审核流与接口边界 | 已合并 |
| v0.6 | 2026-07-04 | 第一版 API 契约、运行 JSON 严格结构、候选审核字段、Prompt 草案 | 已合并 |
| v1.0 | 2026-07-04 | 任务包前最终定稿 | 已合并 |
| v1.1 | 2026-07-04 | JSON 先行、MongoDB 后置的存储决策修正 | 已合并 |
| v1.2 | 2026-07-04 | 候选质量闸门、证据聚合、raw mentions 链路、Prompt v2 与冲突收窄规则 | 当前有效版本 |

## 2. 定稿结论

正文知识沉淀 Agent 是太初第一个真实 LLM + LangGraph Agent。

它的定位是：

```text
Markdown 正文 → 候选知识卡 / 更新建议 → 作者审核 → 当前有效知识库
```

当前有效知识库第一版使用现有 JSON 知识库实现；MongoDB 是后续主数据存储目标，不作为第一版前置条件。

正文知识沉淀 Agent 不是写作页 AI，不是 RAG，不是图谱推理，不是一次性全书自动入库工具。

第一版只做当前章节抽取，只抽角色、地点、势力、物品。抽取链路必须先生成 raw mentions，再聚合为 entity_groups，经候选质量闸门过滤后生成可审核候选。抽取结果先写入 JSON 中间态，作者逐条确认后才写入有效知识库。

最重要的产品约束：

```text
不要让 LLM “出现即建卡”。
GeneralExtractionNode 只输出 raw mentions。
专家节点输入必须是 entity_groups，不是单条 mention。
CandidateQualityGateNode 是第一版必做节点，不是后续优化。
```

第一版使用真实 LLM，但不评测文学质量，不评测写作页回答质量。评测重点是结构、链路、候选、节点状态、prompt/response、作者处理结果。

## 3. 存储决策：JSON 先行，MongoDB 后置

### 3.1 当前决策

第一版不先上 MongoDB。

原因：当前仓库已经有结构化知识卡模型和 JSON 知识库路径，且正文知识沉淀 Agent 的第一版重点是打通抽取、审核、写入和评测闭环。先引入 MongoDB 会增加部署、初始化、迁移、测试和调试成本，反而拖慢第一个 Agent 的成型。

第一版采用：

```text
正文 Markdown：继续存 Markdown
Agent 中间态：project_assets/derived/agent_runs/knowledge_extraction/*.json
有效知识库：当前 JSON 知识卡存储
未来主数据：MongoDB
```

### 3.2 必须抽象存储接口

虽然第一版不接 MongoDB，但 Codex 实现时必须避免把 Agent 直接写死到 JSON 文件细节。

需要抽象一个知识库读写边界，例如：

```text
KnowledgeRepository / StructuredKnowledgeRepository
  list_active_cards(type?: string)
  get_card(card_id)
  create_active_card(card)
  patch_active_card(card_id, updates)
  search_active_identity(type, name, aliases)
```

第一版实现：JSONKnowledgeRepository。

后续实现：MongoKnowledgeRepository。

Agent、API、前端都依赖抽象服务，不直接依赖 MongoDB 或 JSON 文件路径。

### 3.3 第一版 active 匹配来源

候选匹配已有知识卡时，只匹配当前 JSON 知识库中的 active 卡。

draft 和 deprecated 后续也默认不参与候选匹配。

### 3.4 什么时候上 MongoDB

MongoDB 建议在下一版或后续主数据阶段引入，而不是卡住第一版 Agent。

触发条件：

```text
知识卡数量明显增多
需要复杂筛选、分页、组合查询
候选中间态需要长期保留和复杂检索
写作页频繁结构化查询 active 卡
需要多 Agent 并发写入或更强事务边界
```

在这些条件出现之前，JSON 实现足够支持第一版验证。

## 4. 目标与非目标

### 4.1 第一版目标

第一版目标是做出一个可用、可追溯、可评测的正文知识沉淀闭环：

```text
选择当前章节
读取 Markdown 正文
运行 LangGraph
调用真实 LLM
生成候选角色 / 地点 / 势力 / 物品
写入 JSON 中间态
展示运行状态、候选项、LLM 调用记录和评测指标
作者逐条确认、编辑后确认、废弃或稍后处理
确认后写入当前 JSON 有效知识库
写作页后续可以通过知识库服务查询有效知识卡
```

### 4.2 第一版非目标

第一版不做：

```text
先上 MongoDB
写作页入口跳转
当前卷抽取
全书抽取
批量确认
候选置信度
匹配 draft 知识卡
匹配 deprecated 知识卡
复用 /api/agents/chat
RAG
向量库
ES
Neo4j
GraphRAG
事件卡抽取
规则卡抽取
境界卡抽取
功法卡抽取
伏笔卡抽取
复杂 LangGraph interrupt / resume
自动写入有效知识库
复杂曲线评测
流式运行状态
后台队列
```

## 5. 页面入口与工作台布局

新的智能体工作台路由为：

```text
/agent-workbench
```

旧 `/chat` 独立对话页面和旧 `/api/agents/chat` 已清理，不复用。

主导航中的“智能体工作台”入口等真实工作台页面壳子完成后再恢复。

第一版工作台布局：

```text
智能体工作台
  左侧：Agent 列表
    - 正文知识沉淀 Agent
    - 未来其他 Agent，占位或禁用
    - 最近运行列表

  中间：当前 Agent 工作区
    - 运行任务
    - 待处理候选
    - 运行详情
    - 评测指标

  右侧：详情区
    - 当前运行摘要
    - 当前候选详情
    - 当前 LLM 调用详情
    - 错误信息
```

四个固定 Tab：

```text
运行任务
待处理候选
运行详情
评测指标
```

## 6. 数据层与中间态

### 6.1 数据分层

```text
Markdown 正文
  ↓
JSON 中间态：待确认候选卡、更新建议、冲突项、运行记录
  ↓
当前 JSON 有效知识库：作者确认后的角色卡、地点卡、势力卡、物品卡等结构化知识
  ↓
未来 MongoDB 主数据
  ↓
未来：Qdrant 向量层、ES 全文索引、Neo4j / 事件层 / GraphRAG
```

### 6.2 中间态目录

第一版 JSON 中间态目录：

```text
project_assets/derived/agent_runs/knowledge_extraction/
```

中间态属于派生运行产物，不属于作者确认主数据。候选内容不能放进 `project_assets/source/knowledge/`。

### 6.3 文件粒度与命名

第一版采用“每次运行一个 JSON 文件”。

文件命名：

```text
extract_run_<日期时间>_<短ID>.json
```

示例：

```text
extract_run_20260704_153022_a1b2c3.json
```

同一章节允许多次运行，每次运行都保留独立 run 文件，用于评测、回放和 prompt 对比。

## 7. 抽取范围与处理单元

第一版只开放当前章节抽取。

章节是调度、溯源、状态记录和增量重跑的基本单元。

LLM 实际处理单元可以是整章，也可以是章内场景片段。

处理规则：

```text
章节较短：整章作为 LLM 输入
章节较长：按场景片段或段落窗口切分
片段抽取后：章内合并候选
多章节版本：再做批次汇总、批次内去重和失败章节重试
```

版本节奏：

```text
V1：当前章节抽取
V2：自定义章节范围，例如 1～5 章
V3：当前卷抽取
V4：全书抽取
```

## 8. LangGraph 工作流

第一版主图围绕当前章节抽取设计：

```text
Start
  ↓
LoadChapterNode
  读取当前章节 Markdown、chapter_id、display_title、content_hash

  ↓
SegmentChapterNode
  判断章节长度；短章节整章处理，长章节切成场景片段

  ↓
GeneralExtractionNode（LLM）
  只抽取 raw mentions 和 ignored，不输出最终知识卡

  ↓
MentionNormalizeNode
  规范 mention 字段、裁剪 evidence_excerpt、过滤明显无效 JSON 项

  ↓
EntityAggregationNode
  将同名、别名、同指代、同语义 mentions 聚合为 entity_groups

  ↓
CandidateQualityGateNode
  基于 v1.2 质量闸门过滤临时称呼、泛称、普通空间和普通消耗品

  ↓
TypeDispatchNode
  将通过质量闸门的 entity_groups 分发给角色专家节点或实体专家节点

  ↓
CharacterExpertNode（LLM）
  基于角色 entity_groups 和多条 evidence_excerpts 生成角色卡草稿或更新建议

  ↓
EntityExpertNode（LLM）
  基于地点、势力、物品 entity_groups 和多条 evidence_excerpts 生成实体类知识卡草稿或更新建议

  ↓
NormalizeAndValidateNode
  规范字段、枚举、空值、chapter_id、来源摘录，并做 schema 校验

  ↓
RunInternalConflictCheckNode
  先检查本轮内部重复和冲突

  ↓
MatchExistingKnowledgeNode
  只与 active 知识卡做名称、别名和摘要级匹配

  ↓
BuildReviewItemsNode
  生成候选新卡、候选更新、候选冲突、建议忽略

  ↓
WriteIntermediateJsonNode
  写入 JSON 中间态，包括完整 prompt / response 记录

  ↓
End
```

第一版 HumanReview 不放进 LangGraph interrupt 流程。LangGraph 运行完成后写入 JSON 中间态，前端读取候选，作者逐条审核，确认后调用普通 API 写入有效知识库。

v1.2 必须实现的节点顺序是：

```text
Start
→ LoadChapterNode
→ SegmentChapterNode
→ GeneralExtractionNode（LLM）
→ MentionNormalizeNode
→ EntityAggregationNode
→ CandidateQualityGateNode
→ TypeDispatchNode
→ CharacterExpertNode（LLM）
→ EntityExpertNode（LLM）
→ NormalizeAndValidateNode
→ RunInternalConflictCheckNode
→ MatchExistingKnowledgeNode
→ BuildReviewItemsNode
→ WriteIntermediateJsonNode
→ End
```

`MergeChapterCandidatesNode` 属于 v1.1 旧链路，v1.2 不再使用。它的职责拆分为 `MentionNormalizeNode`、`EntityAggregationNode` 和 `CandidateQualityGateNode`。

每个 `entity_group` 必须保存：

```text
entity_group_id
canonical_name
knowledge_type
raw_names
mention_count
evidence_excerpts
quality_decision
quality_reason
```

## 9. 类型专家节点

第一版采用三个专家节点，但只有两个启用。

角色专家节点：第一版启用，输入为角色 `entity_groups`，处理人物状态与关系。

实体专家节点：第一版启用，输入为地点、势力、物品 `entity_groups`，只处理地点、势力、物品。

事件规则专家节点：第一版只设计接口，默认不启用。

角色字段重点：

```text
name
aliases
summary
importance
role_type
identity
relationship_summary
death_chapter_id
current_realm_text
first_seen_chapter_id
last_seen_chapter_id
source_origin
source_note
evidence_excerpt
evidence_excerpts
```

实体字段按当前 schema 输出地点、势力、物品对应字段。

专家节点必须基于多条 `evidence_excerpts` 生成 `summary` 和 `source_note`，不能只复述第一条证据。专家节点输出应贴近 `StructuredKnowledgeCard` 顶层字段，不输出 `fields` 对象，不输出 `body`、`tags`、`fields`、`confidence`、`source_refs`、`relations`。

## 10. 运行 JSON 结构

### 10.1 顶层结构

```json
{
  "run_id": "extract_run_20260704_153022_a1b2c3",
  "agent_name": "knowledge_extraction",
  "agent_version": "v0.1",
  "schema_version": "knowledge_fields_v2",
  "prompt_version": "knowledge_extraction_prompt_v2",
  "model_name": "gpt-xxx",
  "status": "completed",
  "scope": {
    "scope_type": "chapter",
    "chapter_id": "chapter_0012",
    "chapter_title": "第12章 xxx",
    "content_hash": "sha256..."
  },
  "started_at": "2026-07-04T15:30:22+09:00",
  "finished_at": "2026-07-04T15:30:58+09:00",
  "nodes": [],
  "llm_calls": [],
  "raw_mentions": [],
  "entity_groups": [],
  "raw_candidates": [],
  "typed_candidates": [],
  "review_items": [],
  "ignored": [],
  "metrics": {},
  "errors": []
}
```

v1.2 顶层必须包含：

```text
run_id
agent_name
agent_version
schema_version
prompt_version
model_name
status
scope
nodes
llm_calls
raw_mentions
entity_groups
raw_candidates
typed_candidates
review_items
metrics
errors
```

`ignored` 用于评测与回放展示通用抽取阶段主动忽略的文本及原因，可以作为顶层字段保存，也可以由 `raw_mentions` 同级的通用抽取解析结果派生展示；第一版实现建议顶层保存，方便前端直接回放。

run status：

```text
pending
running
completed
failed
```

第一版运行接口同步执行，不做 streaming，不做后台队列。

### 10.2 node 结构

```json
{
  "node_name": "GeneralExtractionNode",
  "status": "success",
  "started_at": "2026-07-04T15:30:25+09:00",
  "finished_at": "2026-07-04T15:30:34+09:00",
  "duration_ms": 9000,
  "input_summary": "第12章正文，约4200字",
  "output_summary": "抽出人物3个、地点1个、物品2个",
  "error": null
}
```

node status：

```text
pending
running
success
failed
skipped
```

### 10.3 llm_calls 结构

```json
{
  "call_id": "llm_call_001",
  "node_name": "GeneralExtractionNode",
  "model_name": "gpt-xxx",
  "prompt_version": "general_extraction_v2",
  "input_prompt": "完整 prompt 文本",
  "raw_response": "完整 response 文本",
  "parsed_output": {},
  "started_at": "2026-07-04T15:30:25+09:00",
  "finished_at": "2026-07-04T15:30:34+09:00",
  "duration_ms": 9000,
  "error": null
}
```

### 10.4 raw_mentions 结构

```json
{
  "mention_id": "mention_001",
  "name": "秦浩轩",
  "knowledge_type": "character",
  "description": "正文中出现的角色描述",
  "evidence_excerpts": ["原文摘录"],
  "reason": "抽取理由",
  "segment_index": 1
}
```

### 10.5 entity_groups 结构

```json
{
  "entity_group_id": "entity_group_001",
  "canonical_name": "秦浩轩",
  "knowledge_type": "character",
  "raw_names": ["秦浩轩", "秦小仙苗"],
  "mention_count": 2,
  "evidence_excerpts": ["原文摘录 1", "原文摘录 2"],
  "quality_decision": "accepted",
  "quality_reason": "稳定专名，且有独立行为链。"
}
```

### 10.6 review_items 结构

```json
{
  "review_item_id": "review_item_001",
  "run_id": "extract_run_20260704_153022_a1b2c3",
  "candidate_action": "create_card",
  "knowledge_type": "character",
  "candidate_status": "pending",
  "display_title": "秦浩轩",
  "suggested_card": {},
  "target_card_id": null,
  "matched_card_name": null,
  "match_reason": "",
  "source_excerpt": "原文摘录，不超过300字",
  "schema_validation": {
    "passed": true,
    "errors": []
  },
  "internal_conflicts": [],
  "external_conflicts": [],
  "suggested_action_label": "建议创建新角色卡",
  "author_action": null,
  "created_knowledge_card_id": null,
  "updated_knowledge_card_id": null,
  "created_at": "2026-07-04T15:30:58+09:00",
  "updated_at": "2026-07-04T15:30:58+09:00"
}
```

candidate_action：

```text
create_card
update_card
conflict
ignore
```

candidate_status：

```text
pending
confirmed
rejected
deferred
```

knowledge_type 第一版：

```text
character
location
faction
item
```

## 11. API 契约

第一版新增独立接口前缀：

```text
/api/agent-workbench/knowledge-extraction
```

第一版接口只做运行、详情、候选审核三类。metrics、nodes、llm_calls 包含在 run detail 中，不单独拆 metrics/logs API。

### 11.1 创建运行

```text
POST /api/agent-workbench/knowledge-extraction/runs
```

请求：

```json
{
  "chapter_id": "chapter_0012",
  "model_name": null,
  "force": false
}
```

响应：

```json
{
  "run": {
    "run_id": "extract_run_20260704_153022_a1b2c3",
    "agent_name": "knowledge_extraction",
    "status": "completed",
    "chapter_id": "chapter_0012",
    "chapter_title": "第12章 xxx",
    "candidate_count": 8,
    "pending_count": 8,
    "confirmed_count": 0,
    "rejected_count": 0,
    "started_at": "2026-07-04T15:30:22+09:00",
    "finished_at": "2026-07-04T15:30:58+09:00"
  }
}
```

### 11.2 运行列表

```text
GET /api/agent-workbench/knowledge-extraction/runs?page=1&page_size=20&status=all
```

### 11.3 运行详情

```text
GET /api/agent-workbench/knowledge-extraction/runs/{run_id}
```

### 11.4 候选列表

```text
GET /api/agent-workbench/knowledge-extraction/runs/{run_id}/candidates?status=pending&action=all
```

### 11.5 确认候选

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/confirm
```

create_card：把 suggested_card 写成 active 知识卡。

update_card：只补充已有 active 卡的空字段，或追加 source_note；不覆盖已有非空字段。

conflict：不允许直接 confirm，必须 edit-confirm。

ignore：不允许 confirm。

### 11.6 编辑后确认

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/edit-confirm
```

请求：

```json
{
  "card_updates": {
    "name": "秦浩轩",
    "summary": "作者编辑后的摘要"
  },
  "target_card_id": null
}
```

### 11.7 废弃候选

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/reject
```

### 11.8 稍后处理

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/defer
```

## 12. Prompt 契约

Prompt 分三类：

```text
通用抽取 prompt
角色专家 prompt
实体专家 prompt
```

Agent prompt 应从知识卡 schema registry 读取字段说明，而不是手写死字段。

至少注入：

```text
field_key
label
field_type
options
required_when_active
ai_usage
```

Prompt 版本必须固定为：

```text
general_extraction_v2
character_expert_v2
entity_expert_v2
```

任务包中必须完整给出 prompt，不允许执行时自行设计 prompt。可以把本文 prompt 落成 prompt builder，但不能自行改变抽取范围、禁用字段、输出 JSON 结构或质量闸门规则。

### 12.1 通用抽取 prompt 草案

```text
你是长篇玄幻小说的知识抽取助手。

任务：
从当前章节正文中抽取可以进入后续证据聚合流程的 raw mentions。你只负责发现正文中出现的角色、地点、势力、物品提及，不负责生成最终知识卡。

硬规则：
1. 只根据给定正文抽取，不要补写正文没有的信息。
2. 第一版只抽取 character、location、faction、item。
3. 不抽取 event、rule、realm、technique、foreshadow。
4. 不生成最终知识卡，不输出 summary、importance、source_note 或任何类型专属字段。
5. 每个 mention 必须提供至少一条原文摘录。
6. 原文摘录必须来自正文，不能改写，单条长度不超过 300 字。
7. 如果信息太碎、不确定、属于第一版不抽取类型，或明显只是泛称、临时称呼、普通空间、普通消耗品，放入 ignored 并写明原因。
8. 输出必须是 JSON，不要输出解释性文字。
9. 不要输出 Markdown 代码块。
10. 不要输出任何多余字段。

第一版允许抽取类型：
character、location、faction、item

第一版禁止抽取类型：
event、rule、realm、technique、foreshadow

优先忽略：
- 临时描述性称呼，例如“另一生面孔”“小山羊胡子”“穿青衫的人”“一个少年”
- 相对指代，例如“另一人”“其中一个”“那人”“他们”“众人”
- 泛称，例如“少年们”“村民”“大人们”“徒弟们”
- 单句功能性台词、无姓名、无后续作用的路人
- 只有外貌特征、没有稳定身份或专名的对象
- 普通功能空间，例如“酒家”“药铺门口”“小店铺”“内院”“小镇广场”
- 泛称地点，例如“山里”“镇上”“北街”“家中”
- 单次环境描写，例如“小山谷”“普通树林”“路边”“广场”
- 普通消耗品、普通银两、普通衣物、普通器具
- 普通人群泛称，例如“少年们”“村民”“镇上的人”“猎户”“徒弟们”“大人们”

输入：
章节 ID：{{chapter_id}}
章节标题：{{chapter_title}}
章节正文：
{{chapter_text}}

允许抽取类型：
{{allowed_types}}

输出 JSON：
{
  "mentions": [
    {
      "name": "",
      "knowledge_type": "character|location|faction|item",
      "description": "",
      "evidence_excerpts": [""],
      "reason": ""
    }
  ],
  "ignored": [
    {
      "text": "",
      "reason": ""
    }
  ]
}
```

### 12.2 角色专家 prompt 草案

```text
你是长篇玄幻小说的角色知识卡整理助手。

任务：
根据通过质量闸门的角色 entity_groups 和多条原文证据，生成角色卡草稿或角色卡更新建议。

硬规则：
1. 只根据 entity_groups 和 evidence_excerpts 填写字段。
2. 不要补写正文没有的信息。
3. 不要输出 personality、motivation、appearance、relations、current_goal、secret、known_secrets。
4. 不要输出 body、tags、fields、confidence、source_refs。
5. role_type 只能从 schema options 中选择，无法判断时填 null。
6. death_chapter_id 只有正文明确确认死亡时才填写，否则填 null。
7. current_realm_text 只有正文出现境界或修为信息时才填写，否则填 null。
8. first_seen_chapter_id 和 last_seen_chapter_id 第一版都可以使用当前 chapter_id。
9. source_origin 固定为 agent_extract。
10. source_note 必须写成作者可读中文文本，包含章节标题和关键原文摘录。
11. evidence_excerpt 可以是主证据，evidence_excerpts 必须保留多条证据。
12. summary 和 source_note 必须基于多条 evidence_excerpts 综合生成，不能只复述第一条证据。
13. 输出必须是 JSON，不要输出解释性文字。
14. 不要输出 Markdown 代码块。
15. 不要输出任何多余字段。

字段 schema：
{{character_schema}}

章节信息：
chapter_id={{chapter_id}}
chapter_title={{chapter_title}}

角色 entity_groups：
{{character_entity_groups}}

输出 JSON：
{
  "knowledge_type": "character",
  "cards": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "role_type": null,
      "identity": null,
      "relationship_summary": null,
      "death_chapter_id": null,
      "current_realm_text": null,
      "first_seen_chapter_id": "{{chapter_id}}",
      "last_seen_chapter_id": "{{chapter_id}}"
    }
  ]
}
```

### 12.3 实体专家 prompt 草案

```text
你是长篇玄幻小说的实体知识卡整理助手。

任务：
根据通过质量闸门的地点、势力、物品 entity_groups 和多条原文证据，生成地点卡、势力卡、物品卡草稿或更新建议。

硬规则：
1. 只根据 entity_groups 和 evidence_excerpts 填写字段。
2. 不要补写正文没有的信息。
3. 第一版只处理 location、faction、item。
4. 不要输出 event、rule、realm、technique、foreshadow。
5. 不要输出 body、tags、fields、confidence、source_refs、relations。
6. controlling_faction_id、leader_id、current_holder_id 如果不能明确匹配已有 active 知识卡，填 null。
7. 不能编造知识卡 ID。
8. source_origin 固定为 agent_extract。
9. source_note 必须写成作者可读中文文本，包含章节标题和关键原文摘录。
10. evidence_excerpt 可以是主证据，evidence_excerpts 必须保留多条证据。
11. summary 和 source_note 必须基于多条 evidence_excerpts 综合生成，不能只复述第一条证据。
12. 没有稳定组织名的“山上的神仙们”第一版不建势力卡。
13. 输出必须是 JSON，不要输出解释性文字。
14. 不要输出 Markdown 代码块。
15. 不要输出任何多余字段。

字段 schema：
{{entity_schemas}}

已有 active 知识卡摘要：
{{active_knowledge_index}}

章节信息：
chapter_id={{chapter_id}}
chapter_title={{chapter_title}}

实体 entity_groups：
{{entity_groups}}

输出 JSON：
{
  "locations": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "controlling_faction_id": null,
      "first_seen_chapter_id": "{{chapter_id}}"
    }
  ],
  "factions": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "faction_type": null,
      "leader_id": null
    }
  ],
  "items": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "item_type": null,
      "grade": null,
      "current_holder_id": null,
      "first_seen_chapter_id": "{{chapter_id}}",
      "last_seen_chapter_id": "{{chapter_id}}"
    }
  ]
}
```

## 13. 专家节点输出 schema

专家节点输出应直接贴近当前 `StructuredKnowledgeCard` 的顶层字段，不输出 `fields` 对象，也不输出自然语言让后端二次解析。

角色、地点、势力、物品输出均必须包含：

```text
name
aliases
summary
importance
source_origin
source_note
evidence_excerpt
evidence_excerpts
```

角色额外字段：

```text
role_type
identity
relationship_summary
death_chapter_id
current_realm_text
first_seen_chapter_id
last_seen_chapter_id
```

地点额外字段：

```text
controlling_faction_id
first_seen_chapter_id
```

势力额外字段：

```text
faction_type
leader_id
```

物品额外字段：

```text
item_type
grade
current_holder_id
first_seen_chapter_id
last_seen_chapter_id
```

## 14. 候选判断、匹配与审核

第一步：候选质量闸门。

CandidateQualityGateNode 是第一版必做节点，不是后续优化。它必须过滤：

```text
临时描述性称呼，例如“另一生面孔”“小山羊胡子”“穿青衫的人”“一个少年”
相对指代，例如“另一人”“其中一个”“那人”“他们”“众人”
泛称，例如“少年们”“村民”“大人们”“徒弟们”
单句功能性台词、无姓名、无后续作用的路人
只有外貌特征、没有稳定身份或专名的对象
普通功能空间，例如“酒家”“药铺门口”“小店铺”“内院”“小镇广场”
泛称地点，例如“山里”“镇上”“北街”“家中”
单次环境描写，例如“小山谷”“普通树林”“路边”“广场”
普通消耗品、普通银两、普通衣物、普通器具
普通人群泛称，例如“少年们”“村民”“镇上的人”“猎户”“徒弟们”“大人们”
```

允许进入候选的条件：

角色候选新卡至少满足以下任一条件：

```text
1. 稳定专名，例如“秦浩轩”“张狂”“陈老头”
2. 明确称号或职务，并在本章承担独立行为，例如“镇长”
3. 本章出现次数 >= 2，并且有独立行为链
4. 命中已有 active 角色卡，可作为 update_card
```

地点候选新卡至少满足以下任一条件：

```text
1. 稳定专有地点名，例如“大田镇”“坡子岭”“陈家药铺”
2. 具备可复用空间属性，后续可能作为剧情地点反复引用
3. 命中已有 active 地点卡，可作为 update_card
```

物品候选新卡至少满足以下任一条件：

```text
1. 有明确名称且具备设定价值，例如“黄精”
2. 是珍稀、特殊、可追踪归属或后续可能反复使用的物品
3. 命中已有 active 物品卡，可作为 update_card
```

势力候选新卡必须有稳定组织名称，或明确组织身份，且不是普通人群泛称。没有稳定组织名的“山上的神仙们”第一版不建势力卡。

第二步：本轮内部检测。

```text
同一 run 内，先按 name + aliases 规范化比较。
如果同名同类型，合并候选。
如果同名但类型不同，进入本轮冲突。
如果别名互相包含，标记疑似重复。
```

第三步：和已有 active 知识卡比对。

比对顺序：

```text
1. 同类型 name 完全相同
2. 同类型 aliases 命中
3. name 命中对方 aliases
4. aliases 之间有交集
5. 摘要或 source_note 中出现明显同指称文本
```

候选新卡：同类型下没有命中 active 卡的 name / aliases / 明显同指称。

候选更新：命中已有 active 卡，并且新增字段是空白补充，或是 last_seen_chapter_id / source_note / summary 的补充。

候选冲突：只有互斥事实才进入 conflict。信息更丰富时必须生成 update_card，不得生成 conflict。

冲突判定必须收窄：

```text
同名不是冲突
命中已有 active 卡后，默认先判断 update_card
新增来源说明不是冲突
新增 evidence_excerpt 不是冲突
补充空字段不是冲突
丰富 summary 不是冲突
更新 last_seen_chapter_id 不是冲突
补充 current_realm_text 不是冲突
补充 identity 不是冲突
补充 relationship_summary 不是冲突
同一角色在新章节出现新的行为不是冲突
```

只有以下互斥事实才算 conflict：

```text
同一角色死亡状态互斥：已死亡 vs 仍在行动
同一物品当前持有人互斥：A 持有 vs B 持有，且不能解释为转移
同一地点控制势力互斥：A 控制 vs B 控制，且没有剧情变更说明
同一实体类型互斥：同名对象无法判断是角色还是物品，且证据互斥
同一势力立场或身份互斥：同一组织被明确写成敌对双方，且不是剧情变化
```

建议忽略：候选信息太碎、没有足够来源摘录、或者不属于第一版抽取类型。

作者审核第一版只允许逐条确认，支持：

```text
确认入库
编辑后确认
废弃
稍后处理
```

候选更新不允许自动覆盖已有非空字段。空字段补充可以在作者确认后写入。已有非空字段与候选字段不一致时，进入候选冲突或编辑后确认。

## 15. 评测与回放

第一版评测不做复杂曲线，以表格、状态标签、运行详情为主。

必须有：

```text
运行列表
节点状态表
LLM 调用记录
raw_mentions 列表
entity_groups 列表
ignored 列表和原因
候选列表
schema 校验结果
作者处理结果
耗时统计
错误信息
完整 prompt / response 展开查看
```

第一版指标：

```text
本次运行候选总数
角色候选数
地点候选数
势力候选数
物品候选数
候选新卡数
候选更新数
候选冲突数
schema 通过数
schema 失败数
已确认数
已废弃数
待处理数
总耗时
各节点耗时
LLM 调用次数
```

LangSmith 可选，不作为第一版硬依赖。产品内必须自建运行记录、节点状态、候选状态、指标面板。

运行详情必须支持完整 prompt / response 展开查看，并能一键提取本次运行所有 LLM 的输入、输出、原始响应和对应节点信息，按时间逻辑和代码节点逻辑整理，供后续人工或其他模型分析。

## 16. 与知识库和写作页的关系

确认后的知识卡只要状态为 active，就立即进入写作页可参考知识库。

即使非必填字段缺失，也可以被写作页结构化查询使用。

后续正文知识沉淀 Agent 再次运行时，可能不是创建新卡，而是对已有 active 知识卡生成补充建议：

```text
补充摘要
补充来源说明
更新最近出现章节
补充当前境界文本
补充物品当前持有人
提示与已有字段冲突
```

这类更新建议也进入待处理候选，由作者逐条确认。

## 17. 第一版不做的事情

第一版不做：

```text
先上 MongoDB
写作页入口跳转
当前卷抽取
全书抽取
批量确认
候选置信度
匹配 draft 知识卡
匹配 deprecated 知识卡
复用 /api/agents/chat
RAG
向量库
ES
Neo4j
GraphRAG
事件卡抽取
规则卡抽取
境界卡抽取
功法卡抽取
伏笔卡抽取
复杂 LangGraph interrupt / resume
自动写入有效知识库
复杂曲线评测
流式运行状态
后台队列
```

## 18. Codex 任务包生成边界

下一步应生成 Codex 执行任务包。

任务包应以本文为唯一方案输入，并以真实仓库当前代码为实现锚点。

任务包阶段建议：

```text
阶段 0：Preflight
  读取必读文档、检查仓库状态、确认旧 /chat 和 /api/agents/chat 已清理。

阶段 1：后端模型与 JSON 中间态
  新增或校准 run / node / llm_call / raw_mentions / entity_groups / review_item 的模型和 JSON 读写服务。
  新增 KnowledgeRepository 抽象，第一版实现 JSONKnowledgeRepository。

阶段 2：LangGraph v1.2 主图骨架
  实现 LoadChapterNode、SegmentChapterNode、GeneralExtractionNode、MentionNormalizeNode、EntityAggregationNode、CandidateQualityGateNode、TypeDispatchNode、CharacterExpertNode、EntityExpertNode、NormalizeAndValidateNode、RunInternalConflictCheckNode、MatchExistingKnowledgeNode、BuildReviewItemsNode、WriteIntermediateJsonNode。
  移除或替换 v1.1 的 MergeChapterCandidatesNode。

阶段 3：API 契约
  实现 /api/agent-workbench/knowledge-extraction 前缀下的运行、详情、候选审核接口。

阶段 4：前端智能体工作台
  新增 /agent-workbench 页面，恢复导航入口，实现左侧 Agent 列表、中间四个 Tab、右侧详情。

阶段 5：评测与回放展示
  展示 nodes、llm_calls、raw_mentions、entity_groups、review_items、metrics、ignored 列表和原因，支持展开完整 prompt / response。

阶段 6：端到端验收与清理
  跑通当前章节抽取 → JSON 中间态 → 候选审核 → JSON active 知识卡 → 写作页可查。
```

每个阶段完成后必须停下来返回证据并自动检查。阶段 commit 应发生在阶段完成、测试通过、返回证据并由用户确认之后；不得在停机点前自动提交，也不得自动进入下一阶段。
