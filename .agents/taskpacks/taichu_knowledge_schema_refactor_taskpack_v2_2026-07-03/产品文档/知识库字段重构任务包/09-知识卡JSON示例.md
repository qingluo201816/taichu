更新日期：2026-07-03


# 知识卡 JSON 示例

## 角色 character

```json
{
  "id": "character_qinhaoxuan",
  "type": "character",
  "name": "秦浩轩",
  "aliases": ["浩轩"],
  "summary": "主角，太初教弟子。",
  "importance": "core",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动创建，用于开发测试。",
  "role_type": "protagonist",
  "identity": "太初教弟子",
  "relationship_summary": "与太初教相关人物存在主线关系。",
  "death_chapter_id": null,
  "current_realm_text": "",
  "first_seen_chapter_id": null,
  "last_seen_chapter_id": null,
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 境界 realm

```json
{
  "id": "realm_lianqi_1",
  "type": "realm",
  "name": "练气一层",
  "aliases": [],
  "summary": "练气体系的初始小境界。",
  "importance": "normal",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动添加的境界示例。",
  "system": "练气体系",
  "level_order": 11,
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 功法 technique

```json
{
  "id": "technique_basic_qi",
  "type": "technique",
  "name": "基础吐纳法",
  "aliases": [],
  "summary": "入门修行法门。",
  "importance": "normal",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动添加的功法示例。",
  "technique_type": "cultivation_method",
  "grade": "入门",
  "practice_condition": "需具备基础灵根或对应资质。",
  "owner_faction_id": null,
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 地点 location

```json
{
  "id": "location_taichu_mountain",
  "type": "location",
  "name": "太初山",
  "aliases": [],
  "summary": "太初教所在之地。",
  "importance": "major",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动添加的地点示例。",
  "controlling_faction_id": null,
  "first_seen_chapter_id": null,
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 势力 faction

```json
{
  "id": "faction_taichu",
  "type": "faction",
  "name": "太初教",
  "aliases": [],
  "summary": "重要宗门势力。",
  "importance": "major",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动添加的势力示例。",
  "faction_type": "sect",
  "leader_id": null,
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 物品 item

```json
{
  "id": "item_test_sword",
  "type": "item",
  "name": "试剑",
  "aliases": [],
  "summary": "测试用法器。",
  "importance": "normal",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动添加的物品示例。",
  "item_type": "magic_treasure",
  "grade": "普通",
  "current_holder_id": null,
  "first_seen_chapter_id": null,
  "last_seen_chapter_id": null,
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 规则 rule

```json
{
  "id": "rule_realm_order",
  "type": "rule",
  "name": "境界压制规则",
  "aliases": [],
  "summary": "通常情况下，高境界对低境界存在明显压制。",
  "importance": "major",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动添加的规则示例。",
  "exceptions": "特殊法宝、禁术、地利或剧情伏线可能造成例外。",
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 事件 event

```json
{
  "id": "event_opening_incident",
  "type": "event",
  "name": "开篇事件",
  "aliases": [],
  "summary": "对主角状态造成变化的关键事件。",
  "importance": "major",
  "status": "draft",
  "source_origin": "manual",
  "source_note": "作者手动添加的事件示例。",
  "chapter_id": null,
  "description": "事件内容与影响的简要描述。",
  "created_at": "2026-07-03T00:00:00Z",
  "updated_at": "2026-07-03T00:00:00Z"
}
```

## 禁止示例

下面是错误示例，不能出现在新知识卡中：

```json
{
  "id": "wrong_character",
  "type": "character",
  "name": "错误示例",
  "body": "不要保留",
  "tags": ["不要保留"],
  "confidence": "不要保留",
  "source_refs": [],
  "fields": {
    "personality": "不要保留",
    "motivation": "不要保留",
    "appearance": "不要保留"
  }
}
```
