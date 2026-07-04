# 正文知识沉淀 Agent 方案 v0.3：第一版入口与节点拆分

> 更新日期：2026-07-04

## 1. 版本记录

| 版本 | 讨论主题 | 状态 |
|---|---|---|
| v0.1 | 正文知识沉淀 Agent 的定位、数据层、智能体工作台入口、评测同步建设 | 已沉淀 |
| v0.2 | 第一版抽取范围、章节调度单元、JSON 中间态、LangGraph 主图草案 | 已沉淀 |
| v0.3 | 第一版入口、LLM 调用记录、类型专家节点拆分、候选确认方式、首批抽取类型 | 当前版本 |

若本文与 v0.1、v0.2 的旧表述冲突，以本文为准。

## 2. 本轮确认结论

本轮确认：第一版正文知识沉淀 Agent 只在智能体工作台中选择章节启动，不从写作页当前章节入口跳转。

本轮确认：每次 LLM 调用必须保存完整 prompt 和 response，用于后续评测、回放、调试和效果对比。

本轮确认：第一版采用“通用抽取器 + 三个类型专家节点”的折中结构。

三个类型专家节点为：

```text
角色专家节点：人物状态与关系
实体专家节点：世界中存在的对象
事件规则专家节点：剧情变化、因果、限制、伏笔
```

本轮确认：候选项第一版不需要置信度字段。

本轮确认：第一版候选确认只支持逐条确认，不做批量确认。

本轮确认：第一版先只抽取角色、地点、势力、物品。先把基本盘调好，再逐步加入事件、规则、境界、功法、伏笔等类型。

## 3. 对第一版范围的最终收敛

第一版目标不是一次性覆盖所有知识类型，而是先把一个真实 Agent 的闭环做稳：

```text
选择当前章节
  ↓
读取 Markdown 正文
  ↓
真实 LLM 抽取候选
  ↓
类型专家填表
  ↓
写入 JSON 中间态
  ↓
作者逐条审核
  ↓
确认后写入 MongoDB 有效知识库
  ↓
写作页可以参考有效知识卡
```

第一版只开放当前章节抽取。

第二版再做多章节批量处理。

不从写作页入口跳转，是为了避免写作页复杂化。正文知识沉淀 Agent 是后台式、批处理式任务，不是写作时即时返回的轻量 AI 面板能力。入口放在智能体工作台更符合它的任务性质。

## 4. 为什么第一版只抽角色、地点、势力、物品

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

所以第一版先把角色、地点、势力、物品抽稳，再往里加功能更安全。

## 5. 类型专家节点设计

第一版采用三个专家节点，但不是每个专家都在第一版全部启用。

### 5.1 角色专家节点

职责：处理人物状态与关系。

第一版启用。

输入：通用抽取器发现的人物候选、相关原文摘录、章节信息。

输出：角色卡草稿或角色卡更新建议。

第一版字段重点：

```text
name
summary
role_type
identity
relationship_summary
death_chapter_id
current_realm_text
first_seen_chapter_id
last_seen_chapter_id
source_refs
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

### 5.2 实体专家节点

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

它负责把候选实体填成地点卡、势力卡、物品卡草稿，或生成对已有卡的更新建议。

### 5.3 事件规则专家节点

职责：处理剧情变化、因果、限制、伏笔。

第一版先设计接口，但默认不启用抽取。

后续逐步开启：

```text
事件卡
规则卡
伏笔卡
```

第一版不启用它，是为了避免第一个 Agent 过早进入剧情理解、因果判断和长期上下文推理，导致调试难度过高。

## 6. 第一版 LangGraph 主图

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
MatchExistingKnowledgeNode
  与 MongoDB 已确认知识卡做名称、别名和摘要级匹配

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

第一版可以采用更稳的做法：LangGraph 运行完成后写入 JSON 中间态；前端智能体工作台读取中间态，作者逐条审核；确认后调用普通 API 写入 MongoDB。

后续再升级为真正的 LangGraph interrupt / resume。

## 7. LangGraph State 建议

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

## 8. 候选项不设置置信度

第一版不使用 confidence / high / medium / low。

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
是否命中已有卡
冲突说明
作者处理状态
```

后续如果需要排序，可以先用规则排序，不用 LLM 置信度。例如：有来源、无冲突、schema 通过、命中已有卡等。

## 9. 作者审核方式

第一版只允许逐条确认。

支持动作：

```text
确认入库
编辑后确认
合并到已有卡
废弃
稍后处理
```

第一版不做批量确认。

原因：这个 Agent 会直接影响 MongoDB 有效知识库，而有效知识库后续会被写作页参考。批量确认会放大错误写入风险。

## 10. 评测与仪表盘第一版要求

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

后续再做曲线和趋势，例如通过率、废弃率、平均每章候选数、不同 prompt 版本表现对比。

## 11. 与写作页的关系

确认后的知识卡只要状态为有效，就立即进入写作页可参考知识库。

即使非必填字段缺失，也可以被写作页结构化查询使用。

这意味着后续正文知识沉淀 Agent 再次运行时，可能不是创建新卡，而是对已有知识卡生成补充建议：

```text
补充摘要
补充来源引用
更新最近出现章节
补充当前境界文本
补充物品当前持有人
提示与已有字段冲突
```

这类更新建议也进入待处理候选，由作者逐条确认。

## 12. 当前不做的事情

第一版不做：

```text
写作页入口跳转
当前卷抽取
全书抽取
批量确认
候选置信度
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
```

## 13. 当前推荐总方案

正文知识沉淀 Agent 第一版应收敛为：

```text
智能体工作台内启动
只选当前章节
真实 LLM 参与抽取
通用抽取器 + 角色专家节点 + 实体专家节点
事件规则专家节点只设计接口，第一版不启用
只抽角色、地点、势力、物品
保存完整 prompt 和 response
输出 JSON 中间态
作者逐条确认
确认后写入 MongoDB 有效知识库
评测和节点状态同步建设
```

这是最适合当前阶段的路线：既能真正用上 LangGraph 和真实 LLM，又不会一次性进入全书抽取、多类型抽取、RAG、图谱和复杂批处理。

## 14. 下一轮讨论建议

下一轮建议继续讨论：

1. 智能体工作台页面第一版具体布局。
2. JSON 中间态目录结构和字段结构。
3. 当前章节抽取的 prompt 结构。
4. 角色专家节点和实体专家节点的输出 schema。
5. 运行记录和 LLM 调用记录是否放同一个 JSON 文件。
6. 作者审核卡片的最小交互。
7. 第一版如何判断“候选新卡 / 候选更新 / 候选冲突”。
