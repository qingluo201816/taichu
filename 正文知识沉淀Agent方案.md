# 正文知识沉淀 Agent 方案

> 更新日期：2026-07-04
>
> 当前版本：v0.5
>
> 当前状态：讨论稿，作为正文知识沉淀 Agent 的唯一有效方案文档。
>
> 最新讨论主题：智能体工作台布局、JSON 中间态、Prompt 拆分、输出 schema、审核流与接口边界。
>
> 文档维护规则：后续继续在本文内更新版本记录和章节内容，不再为每轮讨论新增独立方案文档。

## 目录

1. 更新状态与版本记录
2. 文档目的
3. 当前核心结论
4. 本轮已确认决策
5. 数据层与中间态
6. 为什么第一版不做 RAG
7. 智能体工作台页面定位
8. 抽取范围与处理单元
9. 第一版抽取类型
10. LangGraph 第一版主图
11. 类型专家节点设计
12. LangGraph State 与 LLM 调用记录
13. Prompt 结构
14. 专家节点输出 schema
15. 哪些节点需要 LLM
16. 候选项、匹配规则与作者审核
17. 评测与仪表盘
18. 与写作页的关系
19. 增量更新与后续批量任务
20. 接口边界与旧独立对话服务清理
21. 当前不做的事情
22. 当前推荐总方案
23. 下一轮讨论建议

## 1. 更新状态与版本记录

### 1.1 当前更新状态

本文已合并此前所有正文知识沉淀 Agent 讨论内容。后续只维护这一份文档。

已合并内容包括：

```text
正文知识沉淀 Agent 的定位
数据层与 JSON 中间态
智能体工作台入口
评测同步建设
章节调度单元与 LLM 实际输入单元的区别
第一版当前章节抽取范围
通用抽取器 + 类型专家节点
首批只抽角色、地点、势力、物品
完整 prompt / response 保存
逐条确认，不做批量确认
候选匹配只匹配 active 知识卡
旧独立对话服务不作为正文知识沉淀 Agent 接口
智能体工作台第一版布局
JSON 中间态目录和单文件结构
通用抽取 prompt、角色专家 prompt、实体专家 prompt 的拆分
角色专家和实体专家输出贴近 StructuredKnowledgeCard 顶层字段
```

### 1.2 版本记录

| 版本 | 日期 | 讨论主题 | 状态 |
|---|---|---|---|
| v0.1 | 2026-07-04 | 正文知识沉淀 Agent 的定位、数据层、智能体工作台入口、评测同步建设 | 已合并 |
| v0.2 | 2026-07-04 | 第一版抽取范围、章节调度单元、JSON 中间态、LangGraph 主图草案 | 已合并 |
| v0.3 | 2026-07-04 | 第一版入口、LLM 调用记录、类型专家节点拆分、候选确认方式、首批抽取类型 | 已合并 |
| v0.4 | 2026-07-04 | 旧独立对话服务清理边界、候选匹配 active 知识卡规则 | 已合并 |
| v0.5 | 2026-07-04 | 智能体工作台布局、JSON 中间态、Prompt 拆分、输出 schema、审核流与接口边界 | 当前有效版本 |

### 1.3 当前有效决策摘要

```text
只讨论第一个真实 Agent：正文知识沉淀 Agent。
入口放在智能体工作台。
旧 /chat 独立对话页面和旧 /api/agents/chat 已清理，不作为本 Agent 接口。
新的智能体工作台路由推荐 /agent-workbench。
主导航入口等真实工作台页面壳子完成后再恢复。
第一版只在智能体工作台选择当前章节启动。
第一版只抽角色、地点、势力、物品。
第一版中间态先用外部 JSON 文件。
每次运行一个 JSON 文件，放在 project_assets/derived/agent_runs/knowledge_extraction/。
确认后的有效知识卡进入 MongoDB 主数据。
确认后的有效知识卡立即可被写作页结构化查询使用。
每次 LLM 调用必须保存完整 prompt 和 response，并允许前端展开查看。
候选匹配现有知识卡时，只匹配 active 知识卡。
draft 和 deprecated 后续也默认不参与候选匹配。
第一版不做 RAG、不做向量库、不做 ES、不做图谱、不做 GraphRAG。
评测和节点状态从第一版同步建设，先用表格和状态标签，不做曲线。
```

## 2. 文档目的

本文只讨论太初的第一个真实 Agent：**正文知识沉淀 Agent**。

它的目标不是写作页续写，不是 RAG 问答，也不是图谱推理，而是把 Markdown 正文中的有效信息抽取成可审核的知识库草稿或更新建议，最终由作者确认后进入结构化知识库主数据。

本文是讨论稿，用于反复迭代方案，不是最终实现任务包。

## 3. 当前核心结论

正文知识沉淀 Agent 是太初第一个真正适合 LangGraph 的 Agent。

原因是它不是单轮问答，而是一个长流程任务：读取正文、切分或整理章节输入、调用真实 LLM 抽取、类型归类、字段填充、匹配已有知识卡、生成草稿或补丁、校验、冲突检测、人工确认、写入知识库。

推荐定位：

```text
正文知识沉淀 Agent = 正文 → 候选知识卡 / 更新建议 → 人工确认 → MongoDB 有效知识库
```

不推荐叫“自动写知识库 Agent”，因为它听起来像 LLM 可以绕过作者确认直接污染事实源。

第一版重点是做成一个可控、可追溯、可评测的真实 Agent，而不是追求一次性全书自动入库。

## 4. 本轮已确认决策

第一版正文知识沉淀 Agent 只在智能体工作台中选择章节启动，不从写作页当前章节入口跳转。

新的智能体工作台推荐使用 `/agent-workbench` 路由，和旧 `/chat` 完全切开。

主导航中的“智能体工作台”入口等真实工作台页面壳子完成后再恢复，不在空页面阶段提前暴露。

每次 LLM 调用必须保存完整 prompt 和 response，用于后续评测、回放、调试和效果对比。

第一版采用“通用抽取器 + 三个类型专家节点”的折中结构。

三个类型专家节点为：

```text
角色专家节点：人物状态与关系
实体专家节点：世界中存在的对象
事件规则专家节点：剧情变化、因果、限制、伏笔
```

候选项第一版不需要置信度字段。

候选确认第一版只支持逐条确认，不做批量确认。

第一版先只抽取角色、地点、势力、物品。先把基本盘调好，再逐步加入事件、规则、境界、功法、伏笔等类型。

候选匹配现有知识卡时，只匹配 active 知识卡。draft 和 deprecated 后续也默认不参与候选匹配。

候选更新不允许自动覆盖已有非空字段。空字段补充可以在作者确认后写入；已有非空字段不一致时进入候选冲突或编辑后确认。

旧 `/api/agents/chat` 是旧独立对话服务，会生成 AIResultCard，不作为正文知识沉淀 Agent 接口。正文知识沉淀 Agent 使用独立接口前缀。

## 5. 数据层与中间态

当前推荐分层：

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

知识卡有效主数据存 MongoDB，用于结构化查询和写作页知识参考。

抽取 Agent 生成的候选内容先放在中间态。第一版使用外部 JSON 文件承载中间态，便于调试、回放、删除和人工审核。

中间态不是有效知识库。它可以校验宽松，可以包含不确定字段，可以保存候选文本和节点过程，但不能被写作页当作已确认知识使用。

### 5.1 中间态目录

第一版 JSON 中间态目录：

```text
project_assets/derived/agent_runs/knowledge_extraction/
```

该目录属于派生运行产物，不属于作者确认主数据。候选内容不能放进 `project_assets/source/knowledge/`，避免污染知识库主数据。

### 5.2 JSON 文件粒度与命名

第一版采用“每次运行一个 JSON 文件”。

文件命名：

```text
extract_run_<日期时间>_<短ID>.json
```

示例：

```text
extract_run_20260704_153022_a1b2c3.json
```

使用日期时间是为了便于按运行顺序排查，短 ID 用于避免冲突。不能只用章节 ID 命名，因为同一章会多次运行，需要保留历史记录用于评测和回放。

### 5.3 单文件结构

第一版 run JSON 文件同时保存运行记录、节点状态、LLM 调用、候选项和指标。

推荐结构：

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

节点记录示例：

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

LLM 调用记录示例：

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

## 6. 为什么第一版不做 RAG

正文知识沉淀 Agent 的输入就是正文。它不需要先检索再增强。

RAG 的典型场景是：用户问一个问题，系统先从知识库或正文里检索材料，再交给 LLM 整理回答。

正文知识沉淀 Agent 的场景是：系统读取当前章节正文，从正文中抽取结构化事实。

所以第一版的重点是：

```text
读取正文 → 抽取候选知识 → 生成草稿 / 更新建议 → 人工确认
```

不是：

```text
用户提问 → 检索 → 增强 → 回答
```

Qdrant、ES、Neo4j、GraphRAG 都是未来层。现在只需要把来源说明、章节 ID、知识卡 ID、运行记录、候选项这些字段设计好，为未来扩展留接口。

## 7. 智能体工作台页面定位

正文知识沉淀 Agent 放在“智能体工作台”页面里，不新增主导航页面。

新的智能体工作台推荐路由：

```text
/agent-workbench
```

旧 `/chat` 已清理，不复用旧路由。

主导航中的“智能体工作台”入口等真实工作台页面壳子完成后再恢复。

### 7.1 页面布局

第一版采用“左侧 Agent 列表 + 中间四个 Tab + 右侧详情”的布局。

推荐页面结构：

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

### 7.2 四个固定 Tab

第一版固定四个 Tab：

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

不建议新开“评测主页面”。评测是 Agent 运行的一部分，第一版放在智能体工作台内部更清楚。未来如果 Agent 很多、评测复杂，再考虑单独的全局评测中心。

## 8. 抽取范围与处理单元

原表述“底层都是按章节这个小单元抽取”需要修正。

更准确的说法是：

```text
章节是调度、溯源、状态记录和增量重跑的基本单元。
LLM 实际处理单元可以是整章，也可以是章内场景片段。
```

系统层面按章节管理任务，但模型层面不一定每次把整章全部塞给 LLM。

如果章节较短，可以整章抽取。

如果章节较长，应在章节内部按场景片段或段落窗口切分，再做章内汇总。

推荐结构：

```text
任务范围：当前章 / 多章 / 当前卷 / 全书
  ↓
调度单元：章节
  ↓
LLM 输入单元：整章或章内片段
  ↓
章内汇总：合并本章候选
  ↓
批次汇总：多章任务再做批次内去重和合并
```

第一版只开放当前章节抽取。

第二版再做多章节批量处理。

推荐版本节奏：

```text
V1：当前章节抽取
V2：自定义章节范围，例如 1～5 章
V3：当前卷抽取
V4：全书抽取
```

不从写作页入口跳转，是为了避免写作页复杂化。正文知识沉淀 Agent 是后台式、批处理式任务，不是写作时即时返回的轻量 AI 面板能力。

## 9. 第一版抽取类型

第一版先只抽取：

```text
角色
地点
势力
物品
```

角色、地点、势力、物品是玄幻小说知识库的基本盘。

它们有几个优势：

```text
实体边界相对清楚
来源引用容易定位
字段契约相对稳定
作者审核成本较低
对写作页后续参考价值高
```

事件、规则、境界、功法、伏笔虽然重要，但第一版不优先开启，原因如下：

```text
事件容易和章节摘要混淆
规则容易抽成推测
境界需要排序和体系判断
功法容易和术法、神通、物品混淆
伏笔需要长期上下文，单章抽取不稳定
```

## 10. LangGraph 第一版主图

第一版主图围绕“当前章节抽取”设计。

推荐主图：

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

第一版 HumanReview 不必强行放进 LangGraph 的 interrupt 流程里。

第一版采用更稳的做法：LangGraph 运行完成后写入 JSON 中间态；前端智能体工作台读取中间态，作者逐条审核；确认后调用普通 API 写入 MongoDB。

后续再升级为真正的 LangGraph interrupt / resume。

## 11. 类型专家节点设计

第一版采用三个专家节点，但不是每个专家都在第一版全部启用。

### 11.1 角色专家节点

职责：处理人物状态与关系。

第一版启用。

输入：通用抽取器发现的人物候选、相关原文摘录、章节信息。

输出：角色卡草稿或角色卡更新建议。

第一版字段重点：

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

### 11.2 实体专家节点

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

实体专家节点不负责事件因果，也不负责复杂时间线推理。

它负责把候选实体填成地点卡、势力卡、物品卡草稿，或生成对已有 active 卡的更新建议。

### 11.3 事件规则专家节点

职责：处理剧情变化、因果、限制、伏笔。

第一版先设计接口，但默认不启用抽取。

后续逐步开启：

```text
事件卡
规则卡
伏笔卡
```

## 12. LangGraph State 与 LLM 调用记录

第一版 State 不要过大，但必须支持回放和评测。

建议结构：

```text
run_id
agent_version
schema_version
prompt_version
model_name
scope_type
chapter_id
chapter_title
content_hash
segments
node_statuses
llm_calls
raw_candidates
typed_candidates
review_items
metrics
errors
```

其中 `llm_calls` 必须保存：

```text
call_id
node_name
model_name
prompt_version
input_prompt
raw_response
parsed_output
started_at
finished_at
duration_ms
error
```

保存完整 prompt 和 response 是硬要求，因为后续要做评测、回放、提示词对比和模型对比。

## 13. Prompt 结构

第一版 prompt 拆为三类：

```text
通用抽取 prompt
角色专家 prompt
实体专家 prompt
```

不使用一个大 prompt 全部完成，也不在第一版拆成每种知识类型一个 prompt。

### 13.1 Prompt 字段说明来源

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

这样知识库字段发生调整时，Agent prompt 可以跟着 schema 变化，不需要重复维护字段说明。

### 13.2 通用抽取 prompt

通用抽取 prompt 的职责是“找候选”，不是填最终知识卡。

核心要求：

```text
只根据给定正文抽取，不补写正文没有的信息。
只抽角色、地点、势力、物品。
不抽事件、规则、境界、功法、伏笔。
不抽性格、动机、外貌、秘密、当前目标。
每个候选必须给出原文摘录。
原文摘录必须来自正文，不能改写。
输出必须是 JSON。
```

推荐输出结构：

```json
{
  "characters": [],
  "locations": [],
  "factions": [],
  "items": [],
  "ignored": []
}
```

候选最小字段：

```json
{
  "name": "秦浩轩",
  "evidence_excerpt": "原文摘录",
  "reason": "正文明确出现该人物，并包含身份或行为信息"
}
```

### 13.3 角色专家 prompt

角色专家 prompt 的职责是把人物候选填成角色卡草稿或更新建议。

它必须遵守角色字段契约，不生成禁用字段。

输出贴近 `StructuredKnowledgeCard` 顶层字段，不输出 `fields` 包装对象。

### 13.4 实体专家 prompt

实体专家 prompt 的职责是把地点、势力、物品候选填成对应卡片草稿或更新建议。

引用字段如 `controlling_faction_id`、`leader_id`、`current_holder_id`，如果不能明确匹配已有 active 卡，不要让 LLM 硬填 ID，应留空，保留文本线索到 summary 或 source_note。

## 14. 专家节点输出 schema

专家节点输出应直接贴近当前 `StructuredKnowledgeCard` 的顶层字段，不输出 `fields` 对象，也不输出自然语言让后端二次解析。

### 14.1 角色专家输出示例

```json
{
  "knowledge_type": "character",
  "cards": [
    {
      "name": "秦浩轩",
      "aliases": [],
      "summary": "根据本章正文生成的角色摘要。",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "正文自动提取：第12章《章节标题》。原文摘录：……",
      "role_type": "supporting",
      "identity": "角色身份文本",
      "relationship_summary": "人物关系摘要",
      "death_chapter_id": null,
      "current_realm_text": null,
      "first_seen_chapter_id": "chapter_0012",
      "last_seen_chapter_id": "chapter_0012",
      "evidence_excerpt": "原文摘录"
    }
  ]
}
```

### 14.2 地点输出示例

```json
{
  "knowledge_type": "location",
  "cards": [
    {
      "name": "白鹿城",
      "aliases": [],
      "summary": "根据本章正文生成的地点摘要。",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "正文自动提取：第12章《章节标题》。原文摘录：……",
      "controlling_faction_id": null,
      "first_seen_chapter_id": "chapter_0012",
      "evidence_excerpt": "原文摘录"
    }
  ]
}
```

### 14.3 势力输出示例

```json
{
  "knowledge_type": "faction",
  "cards": [
    {
      "name": "至上仙尊真乙太初教",
      "aliases": [],
      "summary": "根据本章正文生成的势力摘要。",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "正文自动提取：第12章《章节标题》。原文摘录：……",
      "faction_type": "sect",
      "leader_id": null,
      "evidence_excerpt": "原文摘录"
    }
  ]
}
```

### 14.4 物品输出示例

```json
{
  "knowledge_type": "item",
  "cards": [
    {
      "name": "黑骑士",
      "aliases": [],
      "summary": "根据本章正文生成的物品摘要。",
      "importance": "normal",
      "source_origin": "agent_extract",
      "source_note": "正文自动提取：第12章《章节标题》。原文摘录：……",
      "item_type": "other",
      "grade": null,
      "current_holder_id": null,
      "first_seen_chapter_id": "chapter_0012",
      "last_seen_chapter_id": "chapter_0012",
      "evidence_excerpt": "原文摘录"
    }
  ]
}
```

## 15. 哪些节点需要 LLM

第一版必须用 LLM：

```text
GeneralExtractionNode
CharacterExpertNode
EntityExpertNode
```

第一版先不启用但后续可能用 LLM：

```text
EventRuleExpertNode
```

可选用 LLM：

```text
MatchExistingKnowledgeNode 中的模糊同名判断
候选冲突解释
候选更新说明
```

不需要 LLM：

```text
读取 Markdown
计算 content_hash
切分章节
生成 run_id
写 JSON 中间态
字段 schema 校验
枚举合法性检查
来源摘录裁剪
MongoDB 写入
状态流转
匹配范围过滤 active 知识卡
```

原则：

```text
写死更稳定的，不用 LLM。
需要语义理解和归纳的，用 LLM。
成本高但收益不明显的，先不用 LLM。
```

## 16. 候选项、匹配规则与作者审核

第一版候选项不设置 confidence / high / medium / low。

原因：LLM 自报置信度容易产生误导，而且第一版所有候选都必须经过作者逐条确认。与其展示一个不稳定的置信度，不如展示更可验证的信息。

第一版候选项重点展示：

```text
候选类型：新卡 / 更新 / 冲突 / 建议忽略
知识类型：角色 / 地点 / 势力 / 物品
名称
摘要
建议动作
来源章节
原文摘录
schema 校验结果
是否命中已有 active 卡
冲突说明
作者处理状态
```

### 16.1 候选判断顺序

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

第一版只匹配 active 知识卡。

draft 和 deprecated 后续也默认不参与自动匹配。

### 16.2 候选类型判断

候选新卡：同类型下没有命中 active 卡的 name / aliases / 明显同指称。

候选更新：命中已有 active 卡，并且新增字段是空白补充，或是 last_seen_chapter_id / source_note / summary 的补充。

候选冲突：命中已有 active 卡，但候选字段和已有字段不一致，并且不能安全自动覆盖。

建议忽略：候选信息太碎、没有足够来源摘录、或者不属于第一版抽取类型。

### 16.3 作者审核

作者审核第一版只允许逐条确认。

支持动作：

```text
确认入库
编辑后确认
废弃
稍后处理
```

第一版不做批量确认。

原因：这个 Agent 会直接影响 MongoDB 有效知识库，而有效知识库后续会被写作页参考。批量确认会放大错误写入风险。

### 16.4 字段覆盖规则

候选更新不允许自动覆盖已有非空字段。

空字段补充可以在作者确认后写入。

已有非空字段与候选字段不一致时，进入候选冲突或编辑后确认。

## 17. 评测与仪表盘

评测必须和 Agent 同步做，但第一版不做复杂曲线。

第一版以表格、状态标签、运行详情为主。

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

节点级状态：

```text
节点名称
状态：待执行 / 执行中 / 成功 / 失败 / 跳过
开始时间
结束时间
耗时
输入摘要
输出摘要
错误信息
重试次数
```

后续再做曲线和趋势，例如通过率、废弃率、平均每章候选数、不同 prompt 版本表现对比。

LangSmith 可选接入，不作为第一版硬依赖。

产品内必须自建运行记录、节点状态、候选状态、指标面板。LangSmith 可以作为开发调试工具，但不能替代产品内评测和审核记录。

## 18. 与写作页的关系

确认后的知识卡只要状态为有效，就立即进入写作页可参考知识库。

即使非必填字段缺失，也可以被写作页结构化查询使用。

这意味着后续正文知识沉淀 Agent 再次运行时，可能不是创建新卡，而是对已有 active 知识卡生成补充建议：

```text
补充摘要
补充来源说明
更新最近出现章节
补充当前境界文本
补充物品当前持有人
提示与已有字段冲突
```

这类更新建议也进入待处理候选，由作者逐条确认。

## 19. 增量更新与后续批量任务

章节修改后，不应该重建全书。

每章需要保存：

```text
chapter_id
content_hash
last_extracted_hash
last_extracted_at
extract_schema_version
prompt_version
model_name
```

如果正文 hash 未变化，跳过抽取。

如果正文 hash 变化，只重跑该章节或包含该章节的任务范围。

已确认知识卡不因正文变化自动删除或覆盖。系统只生成新的候选更新或提示来源可能过期。

当前章节任务第一版可以不做中断恢复。

第二版多章节任务至少需要支持失败章节重试。

第一版最低要求：

```text
单章运行失败时记录错误
允许重新运行当前章节
不需要复杂断点恢复
```

第二版多章节批量处理需要：

```text
每章独立状态
失败章节可重试
成功章节不重复跑
批次级运行记录
批次内候选去重
```

## 20. 接口边界与旧独立对话服务清理

旧 `/api/agents/chat` 是独立对话服务，会生成 AIResultCard，不适合作为正文知识沉淀 Agent 的接口。

正文知识沉淀 Agent 需要 run、node、candidate、review、llm_calls、metrics 等概念，因此需要独立接口。

推荐新增独立前缀：

```text
/api/agent-workbench/knowledge-extraction
```

第一版接口只做运行、详情、候选审核三类，不一次性拆出完整 metrics/logs API。metrics、nodes、llm_calls 可以包含在 run detail 中。

推荐第一版接口：

```text
GET  /api/agent-workbench/knowledge-extraction/runs
POST /api/agent-workbench/knowledge-extraction/runs
GET  /api/agent-workbench/knowledge-extraction/runs/{run_id}
GET  /api/agent-workbench/knowledge-extraction/runs/{run_id}/candidates
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/confirm
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/reject
POST /api/agent-workbench/knowledge-extraction/candidates/{candidate_id}/edit-confirm
```

旧独立对话服务清理后，需要检查：

```text
/api/agents/chat 是否已移除或不再被前端调用
web/src/app/chat/page.tsx 是否已删除
web/src/lib/api/agents.ts 是否只保留 listAgents
web/src/lib/types/agents.ts 是否不再依赖旧 AIResultCard 输出
后端 routes/agents.py 是否只保留通用 /api/agents 列表端点
旧 ChatAgentService 相关服务是否删除或不再注册
AIResultCard 旧 Agent Chat 链路是否没有被正文知识沉淀 Agent 复用
```

## 21. 当前不做的事情

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
```

## 22. 当前推荐总方案

正文知识沉淀 Agent 第一版应收敛为：

```text
智能体工作台内启动
新路由 /agent-workbench
主导航入口等页面壳子完成后恢复
只选当前章节
真实 LLM 参与抽取
通用抽取器 + 角色专家节点 + 实体专家节点
事件规则专家节点只设计接口，第一版不启用
只抽角色、地点、势力、物品
prompt 从 schema registry 读取字段说明
保存完整 prompt 和 response
每次运行一个 JSON 中间态文件
中间态放在 project_assets/derived/agent_runs/knowledge_extraction/
候选匹配只匹配 active 知识卡
作者逐条确认
确认后写入 MongoDB 有效知识库
评测和节点状态同步建设
独立接口，不复用旧 /api/agents/chat
```

这是最适合当前阶段的路线：既能真正用上 LangGraph 和真实 LLM，又不会一次性进入全书抽取、多类型抽取、RAG、图谱和复杂批处理。

关键原则：

```text
LLM 负责理解和建议。
程序负责校验和状态流转。
作者负责最终确认。
MongoDB 只保存确认后的主数据。
JSON 中间态保存未确认候选。
只匹配 active 知识卡。
评测仪表盘和节点状态从第一版同步建设。
```

## 23. 下一轮讨论建议

下一轮建议继续讨论：

1. `POST /api/agent-workbench/knowledge-extraction/runs` 的请求和响应字段。
2. `GET /api/agent-workbench/knowledge-extraction/runs/{run_id}` 的响应结构。
3. 候选确认接口的具体请求字段。
4. JSON 中间态中的 review_items 严格字段。
5. 通用抽取 prompt 的完整草案。
6. 角色专家 prompt 的完整草案。
7. 实体专家 prompt 的完整草案。
8. 第一版智能体工作台页面各 Tab 的空状态、加载态、错误态。
