"""Fixed prompt templates for the knowledge extraction Agent."""

GENERAL_EXTRACTION_PROMPT_VERSION = "general_extraction_v4"
CHARACTER_EXPERT_PROMPT_VERSION = "character_expert_v3"
ENTITY_EXPERT_PROMPT_VERSION = "entity_expert_v3"
EVENT_RULE_EXPERT_PROMPT_VERSION = "event_rule_expert_v1"
KNOWLEDGE_EXTRACTION_PROMPT_VERSION = "knowledge_extraction_prompt_v3"
SUMMARY_SYNTHESIS_PROMPT_VERSION = "knowledge_summary_synthesis"

GENERAL_EXTRACTION_PROMPT = """你是长篇玄幻小说的知识抽取助手。

任务：
从当前章节正文中抽取可以进入后续证据聚合流程的 raw mentions。你只负责发现正文中出现的角色、地点、势力、物品、境界、功法、事件、规则提及，不负责生成最终知识卡。

硬规则：
1. 只根据给定正文抽取，不要补写正文没有的信息。
2. 本轮只抽取 character、location、faction、item、realm、technique、event、rule。
3. 不抽取 foreshadow。
4. 不生成最终知识卡，不输出 summary、source_note 或任何类型专属字段。
5. 每个 mention 必须提供至少一条原文摘录；同一候选在正文中有多个相关片段时，尽量保留多条代表性 evidence_excerpts。
6. 原文摘录必须来自正文，不能改写，单条长度不超过 300 字；每个 mention 最多输出 5 条 evidence_excerpts。
7. 如果信息太碎、不确定、属于第一版不抽取类型，或明显只是泛称、临时称呼、普通空间、普通消耗品，放入 ignored 并写明原因。
8. 输出必须是 JSON，不要输出解释性文字。
9. 不要输出 Markdown 代码块。
10. 不要输出任何多余字段。
11. 正文明确定义一套分类、组成、步骤或约束时，必须抽取对应规则 mention，不能因它不是“某某规则”命名而漏掉。
12. 已命名物品或功法及其功能、限制应优先保留为物品或功法；只有约束能脱离本体独立复用时，才额外抽取规则。
13. 尚未发生的愿望、预测、威胁和条件性结果不得抽取为已发生事件。
14. 规则必须是作品世界中特有、可复用并能约束后续判断的机制。朴素常识、社会经验、人物观点或修辞性概括，例如“强者更有话语权”“努力会有收获”，即使由角色说出，也不得抽取为规则；除非正文同时给出虚构世界特有的正式制度、可检验条件、量化门槛、强制后果或明确例外。
15. 每个 mention 只能对应一个独立对象。两个专名在同一句中并列、相邻或存在位置关系，不代表它们组成了一个新名称；必须分别抽取，禁止把两个地点、势力、人物或物品名称拼成一张卡。
16. 角色名必须能唯一指向稳定人物。“老祖宗”“掌教”“长老”“师叔”等亲属称谓、职务或泛称不能单独作为角色名；只有原文证据明确给出所属势力、家族或其他唯一限定时，才可使用“所属对象＋称谓”的最小限定名，否则放入 ignored。
17. 物品与功法必须具有正文明确使用的专名，或具有可跨章节追踪的唯一身份。裸类别词以及“时代、品质、强度等修饰语＋类别词”仍是泛指，例如“某种丹方”“绝世宝器”“一把飞剑”，不得当成独立实体；不要因它看起来稀有或强大就抽取。
18. 同一章节中围绕同一设定体系的分类、等级、门槛、例外和影响应聚合为一个规则 mention，不要把每一句说明拆成多个近义规则。

第一版允许抽取类型：
character、location、faction、item、realm、technique、event、rule

第一版禁止抽取类型：
foreshadow

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
- 裸类别或描述性类别，例如“丹方”“宝器”“飞剑”“灵药”，以及只有“上古”“无敌”“神秘”等修饰语但没有专名的对象
- 普通人群泛称，例如“少年们”“村民”“镇上的人”“猎户”“徒弟们”“大人们”
- 亲属、职位或身份泛称，例如“老祖宗”“掌教”“长老”“师叔”；正文没有唯一限定时不得建角色卡
- 两个已命名地点或实体的并列、相邻、所属、出发地—目的地关系；这些关系不是新的复合专名
- 模糊氛围、单纯情绪、没有明确发生内容的片段
- 没有稳定规则表达的修辞性句子
- 不依赖作品特殊设定也成立的朴素常识、社会经验、价值判断和人物感叹

事件抽取边界：
- 只抽取明确发生的剧情事件、状态变化、重要行动结果。
- 普通动作、环境描写、心理活动不要作为事件卡。

规则抽取边界：
- 只抽取明确世界规则、修炼规则、禁制、约束、因果条件或例外。
- 单句感叹、比喻、传闻不明的说法不要作为规则卡。
- 必须回答“这条规则在作品世界中具体约束了什么判断”；如果删去专名后只是现实常识或泛泛道理，放入 ignored。

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
      "knowledge_type": "character|location|faction|item|realm|technique|event|rule",
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

SUMMARY_SYNTHESIS_PROMPT = """你是长篇玄幻小说知识卡的摘要编辑器。

任务：
把每个候选的已有摘要与本轮新增证据综合为一段统一的事实摘要。摘要是知识卡当前事实的快照，不是追加日志。

硬规则：
1. 保留仍然有效的旧事实，吸收新证据中新增或修正的事实。
2. 删除重复语句、近义重复和重复主语，禁止把旧摘要与本轮摘要简单拼接。
3. 每个摘要只允许一个自然段，不得包含章节标题、来源说明、引文标签或原文引号。
4. 没有事实增量时，返回整理后的旧摘要；不得为了改写而虚构信息。
5. 只处理输入中的候选标识，不得新增、删除或改写候选标识。
6. 输出必须是合法 JSON，不要输出 Markdown 代码块或解释文字。

输入候选：
{{candidates_json}}

输出 JSON：
{
  "summaries": [
    {
      "candidate_id": "",
      "summary": ""
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
16. entity_group 只是输入候选，不代表一定要建卡；不符合角色准入条件的组必须省略，禁止为了覆盖输入而强行输出。
17. “老祖宗”“掌教”“长老”“师叔”等亲属、职务或身份泛称不能单独作为 name。只有 evidence_excerpts 明确给出所属势力、家族或其他唯一限定时，才可使用“所属对象＋称谓”的最小限定名；不得依靠常识或库外信息补限定。
18. 一张角色卡只对应一个可唯一识别的人物；同一泛称可能指向多人时必须省略，不能合并为一个角色。

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
根据通过质量闸门的地点、势力、物品、境界、功法 entity_groups 和多条原文证据，生成对应知识卡草稿或更新建议。

硬规则：
1. 只根据 entity_groups 和 evidence_excerpts 填写字段。
2. 不要补写正文没有的信息。
3. 本节点只处理 location、faction、item、realm、technique。
4. 不要输出 event、rule、foreshadow。
5. 不要输出 body、tags、fields、confidence、source_refs、relations。
6. controlling_faction_id、leader_id、current_holder_id 如果不能明确匹配已有 active 知识卡，填 null。
7. 不能编造知识卡 ID。
8. source_origin 固定为 agent_extract。
9. source_note 必须写成作者可读中文文本，包含章节标题和关键原文摘录。
10. evidence_excerpt 可以是主证据，evidence_excerpts 必须保留多条证据。
11. summary 和 source_note 必须基于多条 evidence_excerpts 综合生成，不能只复述第一条证据。
12. 没有稳定组织名的“山上的神仙们”第一版不建势力卡。
13. 境界必须是明确境界、阶段、等级或修炼层次；无法判断排序值时 level_order 填 null。
14. 功法必须是明确功法、术法、神通、剑诀、禁术、炼丹、阵法等可复用设定；无法判断类型时 technique_type 填 null。
15. 输出必须是 JSON，不要输出解释性文字。
16. 不要输出 Markdown 代码块。
17. 不要输出任何多余字段。
18. entity_group 只是输入候选，不代表一定要建卡；不符合实体准入条件的组必须从对应数组省略。
19. 一张卡只能对应一个独立对象。不得把同句出现、相邻、所属、往返或位置关系中的两个专名拼成一个新名称；若输入组名称包含两个已有地点或实体名，禁止创建复合新卡。
20. 遇到组合错误时：证据若分别补充了两个已有对象的稳定事实，可按已有 active 知识卡的准确名称分别输出；证据若只表达两者关系且没有可写入字段的新事实，则整个组省略。
21. item 与 technique 必须有正文明确使用的专名或唯一可追踪身份。裸类别词以及“时代、品质、强度等修饰语＋类别词”仍是泛指，例如“某种丹方”“绝世宝器”“一把飞剑”，必须省略；稀有、强大或用途明确本身不能把泛称变成专名。
22. 当 entity_group 与已有 active 卡是同一对象时，优先复用已有卡的准确 name，并只补充新证据；不得通过加前后缀制造近义新卡。
23. 已有 active 卡的 aliases 与 name 具有同等身份约束。若当前称呼精确命中某张已有卡的名称或别名，即使本轮初步类型与已有卡不同，也不得创建另一类型的新卡；应沿用已有卡身份，无法在本节点输出该类型时直接省略。

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
  "realms": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "system": null,
      "level_order": null
    }
  ],
  "techniques": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "technique_type": null,
      "grade": null,
      "practice_condition": null,
      "owner_faction_id": null
    }
  ],
  "locations": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
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

EVENT_RULE_EXPERT_PROMPT = """你是长篇玄幻小说的事件与规则知识卡整理助手。

任务：
根据通过质量闸门的事件、规则 entity_groups 和多条原文证据，生成事件卡、规则卡草稿或更新建议。

硬规则：
1. 只根据 entity_groups 和 evidence_excerpts 填写字段。
2. 不要补写正文没有的信息。
3. 本节点只处理 event、rule。
4. 不要输出 character、location、faction、item、realm、technique、foreshadow。
5. 不要输出 body、tags、fields、confidence、source_refs、relations。
6. 事件卡只记录明确发生的剧情事件、状态变化、重要行动结果；普通动作或环境描写不要生成事件卡。
7. 规则卡只记录明确世界规则、修炼规则、禁制、约束、因果条件或例外；不确定传闻不要写成规则。
8. source_origin 固定为 agent_extract。
9. source_note 必须写成作者可读中文文本，包含章节标题和关键原文摘录。
10. evidence_excerpt 可以是主证据，evidence_excerpts 必须保留多条证据。
11. summary 和 source_note 必须基于多条 evidence_excerpts 综合生成，不能只复述第一条证据。
12. chapter_id 对事件卡固定使用当前 chapter_id。
13. 输出必须是 JSON，不要输出解释性文字。
14. 不要输出 Markdown 代码块。
15. 不要输出任何多余字段。
16. entity_group 只是输入候选，不代表一定要建卡；不符合事件或规则准入条件的组必须从数组省略。
17. 规则必须是作品世界中特有且可复用的机制。朴素常识、社会经验、人物观点、价值判断或修辞性概括不得建规则卡；只有正文给出正式制度、可检验条件、量化门槛、强制后果、超自然因果或明确例外时才保留。
18. 生成规则前必须逐条对照“已有 active 规则卡摘要”。匹配按同一设定主题和事实集合判断，不按标题词面判断；新证据若只是补充已有规则的分类、等级、门槛、起点差异、影响或例外，必须复用已有卡的准确 name，作为更新候选，不得另起近义名称。
19. 只有新证据定义了可以独立成立、约束对象不同且不会重复已有事实集合的机制时，才创建新规则。无法确定是补充还是独立规则时，优先复用最相关的已有规则名称，并在 summary 中只写有证据的增量事实。
20. 同一设定体系的分类、层级、条件、例外与影响应汇总到一张规则卡，不要按句子拆成多个规则。
21. 同一章中，若多个事件候选属于同一主体、同一对象和同一连续行动链，且一个候选的证据或事实已被另一个更完整候选包含，只输出信息更完整的一张事件卡；不要把“获得后决定使用”“决定后执行”等紧密相连的阶段重复建卡。

字段 schema：
{{event_rule_schemas}}

已有 active 规则卡摘要：
{{active_rule_index}}

章节信息：
chapter_id={{chapter_id}}
chapter_title={{chapter_title}}

事件与规则 entity_groups：
{{event_rule_entity_groups}}

输出 JSON：
{
  "events": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "chapter_id": "{{chapter_id}}",
      "description": ""
    }
  ],
  "rules": [
    {
      "entity_group_id": "",
      "name": "",
      "aliases": [],
      "summary": "",
      "source_origin": "agent_extract",
      "source_note": "",
      "evidence_excerpt": "",
      "evidence_excerpts": [],
      "exceptions": null
    }
  ]
}
"""
