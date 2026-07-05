"""Fixed prompt templates for the knowledge extraction Agent."""

GENERAL_EXTRACTION_PROMPT_VERSION = "general_extraction_v2"
CHARACTER_EXPERT_PROMPT_VERSION = "character_expert_v2"
ENTITY_EXPERT_PROMPT_VERSION = "entity_expert_v2"
KNOWLEDGE_EXTRACTION_PROMPT_VERSION = "knowledge_extraction_prompt_v2"

GENERAL_EXTRACTION_PROMPT = """你是长篇玄幻小说的知识抽取助手。

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
"""

CHARACTER_EXPERT_PROMPT = """你是长篇玄幻小说的角色知识卡整理助手。

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
"""

ENTITY_EXPERT_PROMPT = """你是长篇玄幻小说的实体知识卡整理助手。

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
"""
