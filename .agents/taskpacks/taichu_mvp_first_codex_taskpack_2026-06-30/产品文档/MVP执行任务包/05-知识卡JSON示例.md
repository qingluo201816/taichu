# 05-知识卡JSON示例

> 更新日期：2026-06-30

每张知识卡一个 JSON 文件，按类型分目录保存。内部字段可以英文，前端字段名必须中文。

## 1. 公共字段

```json
{
  "id": "character-qin-yang",
  "type": "character",
  "name": "秦阳",
  "aliases": [],
  "summary": "摘要",
  "body": "正文补充",
  "tags": [],
  "importance": "core",
  "status": "draft",
  "source_refs": [],
  "fields": {},
  "created_at": "2026-06-30T12:00:00+09:00",
  "updated_at": "2026-06-30T12:00:00+09:00"
}
```

状态中文：`draft` 草稿，`active` 有效，`deprecated` 废弃。前端不得直接显示英文状态。

## 2. 来源引用

```json
{
  "source_type": "chapter",
  "source_id": "chapter-001",
  "display_name": "第1章 大田金鳞元神出",
  "excerpt": "秦阳掌心浮现金鳞，残碑随之震动。",
  "note": "首次出现异象。"
}
```

作者说明来源：

```json
{
  "source_type": "author_note",
  "source_id": "author-note-001",
  "display_name": "作者说明：金鳞异象",
  "excerpt": "金鳞异象暂定为元神外显，不等于完整境界。",
  "note": "作者手动说明。"
}
```

## 3. 角色卡

```json
{
  "id": "character-qin-yang",
  "type": "character",
  "name": "秦阳",
  "aliases": ["秦无咎"],
  "summary": "主角，早期出现疑似金鳞元神异象。",
  "body": "秦阳出身低微，但在残碑前引发金鳞异象。",
  "tags": [],
  "importance": "core",
  "status": "draft",
  "source_refs": [
    {
      "source_type": "chapter",
      "source_id": "chapter-001",
      "display_name": "第1章 大田金鳞元神出",
      "excerpt": "秦阳掌心浮现金鳞，残碑随之震动。",
      "note": "角色首次出现异象。"
    }
  ],
  "fields": {
    "identity": "少年修士",
    "faction": "暂无",
    "current_realm": "未定",
    "techniques": ["未定"],
    "items": ["残碑碎片"],
    "relationship_summary": "暂未建立主要关系网。",
    "appearance_chapters": ["chapter-001"],
    "state_records": [
      {
        "time_point": "故事开篇",
        "chapter_id": "chapter-001",
        "realm": "未定",
        "location": "大田村外残碑",
        "life_status": "存活",
        "camp": "未定",
        "note": "引发金鳞异象。"
      }
    ]
  },
  "created_at": "2026-06-30T12:00:00+09:00",
  "updated_at": "2026-06-30T12:00:00+09:00"
}
```

## 4. 境界卡

```json
{
  "id": "realm-ningqi",
  "type": "realm",
  "name": "凝气境",
  "aliases": [],
  "summary": "修行初阶，能感应并引导天地灵气。",
  "body": "凝气境是修行者初步接触灵气的阶段。",
  "tags": [],
  "importance": "major",
  "status": "draft",
  "source_refs": [],
  "fields": {
    "system": "基础修行体系",
    "order": "1",
    "ability_boundary": "可感应灵气，尚不能外放成术。",
    "breakthrough_condition": "完成经脉初步贯通。",
    "typical_manifestation": "呼吸吐纳时出现微弱灵光。",
    "cost_or_limit": "灵气积累不足时容易反噬。"
  },
  "created_at": "2026-06-30T12:00:00+09:00",
  "updated_at": "2026-06-30T12:00:00+09:00"
}
```

## 5. 功法卡

```json
{
  "id": "technique-golden-scale-breath",
  "type": "technique",
  "name": "金鳞吐纳法",
  "aliases": [],
  "summary": "与金鳞异象相关的吐纳法，具体等级未定。",
  "body": "此功法暂为草稿设定，后续需确认来源和规则。",
  "tags": [],
  "importance": "major",
  "status": "draft",
  "source_refs": [],
  "fields": {
    "technique_type": "吐纳法",
    "practice_condition": "需具备金鳞异象或相关体质。",
    "effect": "提升灵气感知。",
    "limit_or_cost": "过度修炼可能引起元神震荡。",
    "related_characters": "秦阳",
    "related_realm": "凝气境",
    "origin": "待定"
  },
  "created_at": "2026-06-30T12:00:00+09:00",
  "updated_at": "2026-06-30T12:00:00+09:00"
}
```

## 6. 其他类型字段建议

地点：所属区域、上级地点、控制势力、地点规则、重要资源、危险程度、出现章节、关联事件。

势力：势力类型、首领、驻地、势力范围、敌友关系、核心规则、重要成员、关联地点。

物品：物品类型、持有者、能力、限制、来源、当前状态、关联事件。

规则：规则内容、适用范围、限制条件、例外情况、关联设定。

事件：发生章节、涉及角色、涉及地点、事件摘要、结果影响。

伏笔：埋设章节、伏笔内容、关联角色或物品、当前状态、预计回收方向。
