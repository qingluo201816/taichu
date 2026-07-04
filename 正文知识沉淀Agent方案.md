# 正文知识沉淀 Agent 方案

> 更新日期：2026-07-04
>
> 当前版本：v1.0
>
> 当前状态：任务包前最终定稿。
>
> 用途：作为后续生成 Codex 执行任务包的唯一事实输入。
>
> 文档维护规则：后续如有新讨论，继续在本文内追加版本记录和修改章节，不再为每轮讨论新增独立方案文档。

## 目录

1. 更新状态与版本记录
2. 定稿结论
3. 目标与非目标
4. 页面入口与工作台布局
5. 数据层与中间态
6. 抽取范围与处理单元
7. LangGraph 工作流
8. 类型专家节点
9. 运行 JSON 结构
10. API 契约
11. Prompt 契约
12. 专家节点输出 schema
13. 候选判断、匹配与审核
14. 评测与回放
15. 与知识库和写作页的关系
16. 第一版不做的事情
17. Codex 任务包生成边界

## 1. 更新状态与版本记录

### 1.1 当前更新状态

本文已从讨论稿收敛为任务包前最终定稿。后续生成 Codex 任务包时，以本文为准。

### 1.2 版本记录

| 版本 | 日期 | 讨论主题 | 状态 |
|---|---|---|---|
| v0.1 | 2026-07-04 | 正文知识沉淀 Agent 的定位、数据层、智能体工作台入口、评测同步建设 | 已合并 |
| v0.2 | 2026-07-04 | 第一版抽取范围、章节调度单元、JSON 中间态、LangGraph 主图草案 | 已合并 |
| v0.3 | 2026-07-04 | 第一版入口、LLM 调用记录、类型专家节点拆分、候选确认方式、首批抽取类型 | 已合并 |
| v0.4 | 2026-07-04 | 旧独立对话服务清理边界、候选匹配 active 知识卡规则 | 已合并 |
| v0.5 | 2026-07-04 | 智能体工作台布局、JSON 中间态、Prompt 拆分、输出 schema、审核流与接口边界 | 已合并 |
| v0.6 | 2026-07-04 | 第一版 API 契约、运行 JSON 严格结构、候选审核字段、Prompt 草案 | 已合并 |
| v1.0 | 2026-07-04 | 任务包前最终定稿 | 当前有效版本 |

## 2. 定稿结论

正文知识沉淀 Agent 是太初第一个真实 LLM + LangGraph Agent。

它的定位是：

```text
Markdown 正文 → 候选知识卡 / 更新建议 → 作者审核 → MongoDB 有效知识库
```

它不是写作页 AI，不是 RAG，不是图谱推理，不是一次性全书自动入库工具。

第一版只做当前章节抽取，只抽角色、地点、势力、物品。抽取结果先写入 JSON 中间态，作者逐条确认后才写入 MongoDB 有效知识库。

第一版使用真实 LLM，但不评测文学质量，不评测写作页回答质量。评测重点是结构、链路、候选、节点状态、prompt/response、作者处理结果。

## 3. 目标与非目标

### 3.1 第一版目标

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
确认后写入 MongoDB 有效知识库
写作页后续可以查询有效知识卡
```

### 3.2 第一版非目标

第一版不做：

```text
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

## 4. 页面入口与工作台布局

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

运行任务：选择当前章节，启动抽取，查看最近一次运行摘要。

待处理候选：展示候选新卡、候选更新、候选冲突、建议忽略，支持逐条审核。

运行详情：展示节点状态、LLM 调用记录、错误信息、完整 prompt / response。

评测指标：展示候选数量、schema 校验、作者处理结果、节点耗时、LLM 调用次数。

## 5. 数据层与中间态

### 5.1 数据分层

```text
Markdown 正文
  ↓
JSON 中间态：待确认候选卡、更新建议、冲突项、运行记录
  ↓
MongoDB 主数据：作者确认后的角色卡、地点卡、势力卡、物品卡等结构化知识
  ↓
未来：Qdrant 向量层、ES 全文索引、Neo4j / 事件层 / GraphRAG
```

正文继续存 Markdown。

MongoDB 只保存作者确认后的有效知识卡。

JSON 中间态保存未确认候选、运行记录、节点状态、LLM 调用记录、评测指标和错误信息。

### 5.2 中间态目录

第一版 JSON 中间态目录：

```text
project_assets/derived/agent_runs/knowledge_extraction/
```

该目录属于派生运行产物，不属于作者确认主数据。候选内容不能放进 `project_assets/source/knowledge/`。

### 5.3 文件粒度与命名

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

## 6. 抽取范围与处理单元

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

## 7. LangGraph 工作流

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
  抽取候选人物、地点、势力、物品，以及必要的原文摘录

  ↓
MergeChapterCandidatesNode
  合并章内多个片段的候选，去掉明显重复

  ↓
TypeDispatchNode
  分发给角色专家节点或实体专家节点

  ↓
CharacterExpertNode（LLM）
  处理人物状态与关系，生成角色卡草稿或更新建议

  ↓
EntityExpertNode（LLM）
  处理地点、势力、物品，生成实体类知识卡草稿或更新建议

  ↓
NormalizeAndValidateNode
  规范字段、枚举、空值、chapter_id、来源摘录，并做 schema 校验

  ↓
RunInternalConflictCheckNode
  先检查本轮内部重复和冲突

  ↓
MatchExistingKnowledgeNode
  只与 MongoDB 中 active 知识卡做名称、别名和摘要级匹配

  ↓
BuildReviewItemsNode
  生成候选新卡、候选更新、候选冲突、建议忽略

  ↓
WriteIntermediateJsonNode
  写入 JSON 中间态，包括完整 prompt / response 记录

  ↓
End
```

第一版 HumanReview 不放进 LangGraph interrupt 流程。LangGraph 运行完成后写入 JSON 中间态，前端读取候选，作者逐条审核，确认后调用普通 API 写入 MongoDB。

后续再升级为 LangGraph interrupt / resume。

## 8. 类型专家节点

第一版采用三个专家节点，但只有两个启用。

### 8.1 角色专家节点

职责：处理人物状态与关系。

第一版启用。

字段重点：

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
```

第一版不抽：

```text
personality
motivation
appearance
relations
current_goal
secret
known_secrets
```

### 8.2 实体专家节点

职责：处理世界中存在的对象。

第一版启用。

第一版只处理：

```text
地点
势力
物品
```

后续可扩展到：

```text
功法
境界
```

### 8.3 事件规则专家节点

职责：处理剧情变化、因果、限制、伏笔。

第一版只设计接口，默认不启用。

后续开启：

```text
事件卡
规则卡
伏笔卡
```

## 9. 运行 JSON 结构

### 9.1 顶层结构

```json
{
  "run_id": "extract_run_20260704_153022_a1b2c3",
  "agent_name": "knowledge_extraction",
  "agent_version": "v0.1",
  "schema_version": "knowledge_fields_v2",
  "prompt_version": "knowledge_extraction_prompt_v1",
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
  "raw_candidates": [],
  "typed_candidates": [],
  "review_items": [],
  "metrics": {},
  "errors": []
}
```

run status：

```text
pending
running
completed
failed
```

第一版运行接口同步执行，不做 streaming，不做后台队列。状态字段仍保留，方便前端展示和后续升级异步任务。

### 9.2 node 结构

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

### 9.3 llm_calls 结构

```json
{
  "call_id": "llm_call_001",
  "node_name": "GeneralExtractionNode",
  "model_name": "gpt-xxx",
  "prompt_version": "general_extraction_v1",
  "input_prompt": "完整 prompt 文本",
  "raw_response": "完整 response 文本",
  "parsed_output": {},
  "started_at": "2026-07-04T15:30:25+09:00",
  "finished_at": "2026-07-04T15:30:34+09:00",
  "duration_ms": 9000,
  "error": null
}
```

### 9.4 review_items 结构

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

## 10. API 契约

第一版新增独立接口前缀：

```text
/api/agent-workbench/knowledge-extraction
```

第一版接口只做运行、详情、候选审核三类。metrics、nodes、llm_calls 包含在 run detail 中，不单独拆 metrics/logs API。

### 10.1 创建运行

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

### 10.2 运行列表

```text
GET /api/agent-workbench/knowledge-extraction/runs?page=1&page_size=20&status=all
```

响应：

```json
{
  "runs": [],
  "page": 1,
  "page_size": 20,
  "total": 0
}
```

### 10.3 运行详情

```text
GET /api/agent-workbench/knowledge-extraction/runs/{run_id}
```

响应：

```json
{
  "run": {
    "run_id": "extract_run_20260704_153022_a1b2c3",
    "agent_name": "knowledge_extraction",
    "agent_version": "v0.1",
    "schema_version": "knowledge_fields_v2",
    "prompt_version": "knowledge_extraction_prompt_v1",
    "model_name": "gpt-xxx",
    "status": "completed",
    "scope": {},
    "nodes": [],
    "llm_calls": [],
    "review_items": [],
    "metrics": {},
    "errors": []
  }
}
```

### 10.4 候选列表

```text
GET /api/agent-workbench/knowledge-extraction/runs/{run_id}/candidates?status=pending&action=all
```

响应：

```json
{
  "items": [],
  "run_id": "extract_run_20260704_153022_a1b2c3",
  "total": 0
}
```

### 10.5 确认候选

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/confirm
```

请求：

```json
{}
```

行为：

```text
create_card：把 suggested_card 写成 active 知识卡。
update_card：只补充已有 active 卡的空字段，或追加 source_note；不覆盖已有非空字段。
conflict：不允许直接 confirm，必须 edit-confirm。
ignore：不允许 confirm。
```

响应：

```json
{
  "item": {},
  "knowledge_card": {},
  "message": "已确认入库"
}
```

### 10.6 编辑后确认

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

响应：

```json
{
  "item": {},
  "knowledge_card": {},
  "message": "已编辑并确认"
}
```

### 10.7 废弃候选

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/reject
```

请求：

```json
{
  "reason": "不是知识库需要沉淀的内容"
}
```

响应：

```json
{
  "item": {},
  "message": "已废弃候选"
}
```

### 10.8 稍后处理

```text
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/defer
```

请求：

```json
{}
```

响应：

```json
{
  "item": {},
  "message": "已标记稍后处理"
}
```

## 11. Prompt 契约

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

### 11.1 通用抽取 prompt 草案

```text
你是长篇玄幻小说的知识抽取助手。

任务：
从当前章节正文中抽取可以沉淀为知识库候选的角色、地点、势力、物品。

硬规则：
1. 只根据给定正文抽取，不要补写正文没有的信息。
2. 第一版只抽取 character、location、faction、item。
3. 不抽取 event、rule、realm、technique、foreshadow。
4. 不抽取性格、动机、外貌、秘密、当前目标。
5. 每个候选必须提供原文摘录。
6. 原文摘录必须来自正文，不能改写，长度不超过 300 字。
7. 如果信息太碎、不确定或不属于第一版类型，放入 ignored。
8. 输出必须是 JSON，不要输出解释性文字。

输入：
章节 ID：{{chapter_id}}
章节标题：{{chapter_title}}
章节正文：
{{chapter_text}}

允许抽取类型：
{{allowed_types}}

输出 JSON：
{
  "characters": [],
  "locations": [],
  "factions": [],
  "items": [],
  "ignored": []
}
```

### 11.2 角色专家 prompt 草案

```text
你是长篇玄幻小说的角色知识卡整理助手。

任务：
根据通用抽取器给出的人物候选和原文摘录，生成角色卡草稿或角色卡更新建议。

硬规则：
1. 只根据候选和原文摘录填写字段。
2. 不要补写正文没有的信息。
3. 不要输出 personality、motivation、appearance、relations、current_goal、secret、known_secrets。
4. role_type 只能从 schema options 中选择，无法判断时填 null。
5. death_chapter_id 只有正文明确确认死亡时才填写，否则填 null。
6. current_realm_text 只有正文出现境界或修为信息时才填写，否则填 null。
7. first_seen_chapter_id 和 last_seen_chapter_id 第一版都可以使用当前 chapter_id。
8. source_origin 固定为 agent_extract。
9. source_note 必须写成作者可读文本，包含章节标题和原文摘录。
10. 输出必须是 JSON，不要输出解释性文字。

字段 schema：
{{character_schema}}

章节信息：
chapter_id={{chapter_id}}
chapter_title={{chapter_title}}

人物候选：
{{character_candidates}}

输出 JSON：
{
  "knowledge_type": "character",
  "cards": []
}
```

### 11.3 实体专家 prompt 草案

```text
你是长篇玄幻小说的实体知识卡整理助手。

任务：
根据通用抽取器给出的地点、势力、物品候选和原文摘录，生成地点卡、势力卡、物品卡草稿或更新建议。

硬规则：
1. 只根据候选和原文摘录填写字段。
2. 不要补写正文没有的信息。
3. 第一版只处理 location、faction、item。
4. controlling_faction_id、leader_id、current_holder_id 如果不能明确匹配已有 active 知识卡，填 null。
5. 不能编造知识卡 ID。
6. source_origin 固定为 agent_extract。
7. source_note 必须写成作者可读文本，包含章节标题和原文摘录。
8. 输出必须是 JSON，不要输出解释性文字。

字段 schema：
{{entity_schemas}}

已有 active 知识卡摘要：
{{active_knowledge_index}}

章节信息：
chapter_id={{chapter_id}}
chapter_title={{chapter_title}}

实体候选：
{{entity_candidates}}

输出 JSON：
{
  "locations": [],
  "factions": [],
  "items": []
}
```

## 12. 专家节点输出 schema

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

## 13. 候选判断、匹配与审核

第一步：本轮内部检测。

```text
同一 run 内，先按 name + aliases 规范化比较。
如果同名同类型，合并候选。
如果同名但类型不同，进入本轮冲突。
如果别名互相包含，标记疑似重复。
```

第二步：和 MongoDB 已有 active 知识卡比对。

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

候选冲突：命中已有 active 卡，但候选字段和已有字段不一致，并且不能安全自动覆盖。

建议忽略：候选信息太碎、没有足够来源摘录、或者不属于第一版抽取类型。

作者审核第一版只允许逐条确认，支持：

```text
确认入库
编辑后确认
废弃
稍后处理
```

候选更新不允许自动覆盖已有非空字段。空字段补充可以在作者确认后写入。已有非空字段与候选字段不一致时，进入候选冲突或编辑后确认。

## 14. 评测与回放

第一版评测不做复杂曲线，以表格、状态标签、运行详情为主。

必须有：

```text
运行列表
节点状态表
LLM 调用记录
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

## 15. 与知识库和写作页的关系

确认后的知识卡只要状态为有效，就立即进入写作页可参考知识库。

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

## 16. 当前不做的事情

第一版不做：

```text
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

## 17. Codex 任务包生成边界

下一步应生成 Codex 执行任务包。

任务包应以本文为唯一方案输入，并以真实仓库当前代码为实现锚点。

任务包阶段建议：

```text
阶段 0：Preflight
  读取必读文档、检查仓库状态、确认旧 /chat 和 /api/agents/chat 已清理。

阶段 1：后端模型与 JSON 中间态
  新增 run / node / llm_call / review_item 的模型和读写服务。

阶段 2：LangGraph 主图骨架
  实现 LoadChapterNode、SegmentChapterNode、GeneralExtractionNode、CharacterExpertNode、EntityExpertNode、NormalizeAndValidateNode、RunInternalConflictCheckNode、MatchExistingKnowledgeNode、BuildReviewItemsNode、WriteIntermediateJsonNode。

阶段 3：API 契约
  实现 /api/agent-workbench/knowledge-extraction 前缀下的运行、详情、候选审核接口。

阶段 4：前端智能体工作台
  新增 /agent-workbench 页面，恢复导航入口，实现左侧 Agent 列表、中间四个 Tab、右侧详情。

阶段 5：评测与回放展示
  展示 nodes、llm_calls、review_items、metrics，支持展开完整 prompt / response。

阶段 6：端到端验收与清理
  跑通当前章节抽取 → JSON 中间态 → 候选审核 → MongoDB active 知识卡 → 写作页可查。
```

每个阶段完成后必须停下来返回证据，不自动进入下一阶段。

阶段 commit 应发生在阶段完成、测试通过、返回证据并由用户确认之后，不能在停机点前自动提交。
