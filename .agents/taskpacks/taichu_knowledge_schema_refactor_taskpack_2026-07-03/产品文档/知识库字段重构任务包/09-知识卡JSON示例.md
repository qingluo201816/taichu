# 知识卡 JSON 示例

更新日期：2026-07-03

以下示例用于说明目标结构。实际 ID 和时间由系统生成。

## 1. 角色卡示例

```json
{
  "id": "character_qin_haoxuan",
  "type": "character",
  "name": "秦浩轩",
  "aliases": ["浩轩"],
  "summary": "一个出身普通但牵动主线命运的核心角色。",
  "body": "这里记录不适合结构化字段承载的补充说明。",
  "tags": [],
  "importance": "core",
  "status": "draft",
  "confidence": "explicit",
  "source_origin": "manual",
  "source_note": "作者手动添加：用于后续主角线测试。",
  "fields": {
    "role_type": "protagonist",
    "identity": "普通出身的少年。",
    "personality": "沉稳、谨慎，但关键时刻敢赌。",
    "motivation": "寻找自身命运变化的原因。",
    "appearance": "外貌暂未定。",
    "relationship_summary": "与主要人物关系待补充。",
    "death_chapter_id": null,
    "current_realm_text": "未定",
    "first_seen_chapter_id": "chapter_0001",
    "last_seen_chapter_id": "chapter_0001",
    "state_records": [
      {
        "time_point": "开篇",
        "chapter_id": "chapter_0001",
        "realm_text": "未定",
        "location_text": "村中",
        "life_status": "存活",
        "camp": "无明确阵营",
        "items_text": "无",
        "note": "初始状态。"
      }
    ]
  },
  "created_at": "2026-07-03T00:00:00+09:00",
  "updated_at": "2026-07-03T00:00:00+09:00"
}
```

## 2. 境界卡示例

```json
{
  "id": "realm_qi_refining_1",
  "type": "realm",
  "name": "练气一层",
  "aliases": [],
  "summary": "练气体系的初始层级。",
  "body": "特殊能力和限制可写在这里，不拆更多字段。",
  "tags": [],
  "importance": "normal",
  "status": "draft",
  "confidence": "explicit",
  "source_origin": "manual",
  "source_note": "作者手动添加的境界体系草稿。",
  "fields": {
    "system": "练气体系",
    "level_order": 11
  },
  "created_at": "2026-07-03T00:00:00+09:00",
  "updated_at": "2026-07-03T00:00:00+09:00"
}
```

## 3. 功法卡示例

```json
{
  "id": "technique_basic_sword_art",
  "type": "technique",
  "name": "基础剑诀",
  "aliases": [],
  "summary": "入门级剑道术法。",
  "body": "具体招式可后续补充。",
  "tags": [],
  "importance": "normal",
  "status": "draft",
  "confidence": "explicit",
  "source_origin": "manual",
  "source_note": "作者手动添加，用于功法字段测试。",
  "fields": {
    "technique_type": "sword_art",
    "grade": "入门",
    "practice_condition": "需要基本灵力感知。",
    "owner_faction_id": null
  },
  "created_at": "2026-07-03T00:00:00+09:00",
  "updated_at": "2026-07-03T00:00:00+09:00"
}
```

## 4. 事件卡示例

```json
{
  "id": "event_first_encounter",
  "type": "event",
  "name": "初遇异象",
  "aliases": [],
  "summary": "主角第一次接触影响命运的异象。",
  "body": "事件细节可后续补充。",
  "tags": [],
  "importance": "major",
  "status": "draft",
  "confidence": "explicit",
  "source_origin": "manual",
  "source_note": "作者手动添加，用于事件卡测试。",
  "fields": {
    "chapter_id": "chapter_0001",
    "description": "主角在开篇章节中首次接触未知异象，后续可能改变修行路径。"
  },
  "created_at": "2026-07-03T00:00:00+09:00",
  "updated_at": "2026-07-03T00:00:00+09:00"
}
```
