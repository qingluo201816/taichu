"""First-version structured knowledge card contracts."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field

from taichu.domain.models.base import DomainModel


class StructuredKnowledgeType(StrEnum):
    """Knowledge card types supported by the first-version knowledge base."""

    CHARACTER = "character"
    REALM = "realm"
    TECHNIQUE = "technique"
    LOCATION = "location"
    FACTION = "faction"
    ITEM = "item"
    RULE = "rule"
    EVENT = "event"


class StructuredKnowledgeLifecycle(StrEnum):
    """Lifecycle states shared by all structured knowledge cards."""

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


class StructuredKnowledgeSourceOrigin(StrEnum):
    """First-version source origin buckets."""

    INBOX_FACT = "inbox_fact"
    AGENT_EXTRACT = "agent_extract"
    MANUAL = "manual"


class KnowledgeSchemaFieldType(StrEnum):
    """Field types used by the backend schema registry."""

    SHORT_TEXT = "short_text"
    LONG_TEXT = "long_text"
    ENUM = "enum"
    NUMBER = "number"
    BOOLEAN = "boolean"
    CHAPTER_REF = "chapter_ref"
    KNOWLEDGE_REF = "knowledge_ref"
    STRING_ARRAY = "string_array"
    RECORD_ARRAY = "record_array"


class KnowledgeFieldOption(DomainModel):
    """One Chinese-labeled option for an enum field."""

    value: str
    label: str


class KnowledgeFieldSchema(DomainModel):
    """One schema registry field definition."""

    field_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    field_type: KnowledgeSchemaFieldType
    required_when_confirmed: bool = False
    options: list[KnowledgeFieldOption] = Field(default_factory=list)
    placeholder: str = ""
    display_group: str = Field(min_length=1)
    list_display: bool = False
    author_editable: bool = True
    ai_usage: str = ""


class KnowledgeTypeSchema(DomainModel):
    """Schema definition for one knowledge card type."""

    type: StructuredKnowledgeType
    label: str = Field(min_length=1)
    fields: list[KnowledgeFieldSchema] = Field(default_factory=list)


class StructuredKnowledgeCard(DomainModel):
    """One structured knowledge card using first-version top-level fields."""

    id: str = Field(min_length=1)
    type: StructuredKnowledgeType
    name: str = ""
    aliases: list[str] = Field(default_factory=list)
    summary: str = ""
    appearance_chapter_count: int | None = Field(default=None, ge=0)
    lifecycle: StructuredKnowledgeLifecycle
    source_origin: StructuredKnowledgeSourceOrigin | None = None
    source_note: str = ""
    role_type: str | None = None
    identity: str | None = None
    relationship_summary: str | None = None
    death_chapter_id: str | None = None
    current_realm_text: str | None = None
    first_seen_chapter_id: str | None = None
    last_seen_chapter_id: str | None = None
    system: str | None = None
    level_order: float | None = None
    technique_type: str | None = None
    grade: str | None = None
    practice_condition: str | None = None
    owner_faction_id: str | None = None
    controlling_faction_id: str | None = None
    faction_type: str | None = None
    leader_id: str | None = None
    item_type: str | None = None
    current_holder_id: str | None = None
    exceptions: str | None = None
    chapter_id: str | None = None
    description: str | None = None
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)

    def can_be_used_as_effective_knowledge(self) -> bool:
        """Return whether this card can participate in future AI reference."""
        return self.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED


KNOWLEDGE_TYPE_LABELS: dict[StructuredKnowledgeType, str] = {
    StructuredKnowledgeType.CHARACTER: "角色",
    StructuredKnowledgeType.REALM: "境界",
    StructuredKnowledgeType.TECHNIQUE: "功法",
    StructuredKnowledgeType.LOCATION: "地点",
    StructuredKnowledgeType.FACTION: "势力",
    StructuredKnowledgeType.ITEM: "物品",
    StructuredKnowledgeType.RULE: "规则",
    StructuredKnowledgeType.EVENT: "事件",
}

FORBIDDEN_KNOWLEDGE_FIELD_KEYS = frozenset(
    {
        "body",
        "tags",
        "fields",
        "confidence",
        "source_refs",
        "relations",
        "foreshadow",
        "personality",
        "motivation",
        "appearance",
        "importance",
    }
)

COMMON_KNOWLEDGE_FIELD_KEYS = frozenset(
    {
        "name",
        "aliases",
        "summary",
        "appearance_chapter_count",
        "lifecycle",
        "source_origin",
        "source_note",
    }
)


def all_knowledge_type_schemas() -> list[KnowledgeTypeSchema]:
    """Return schema definitions for all supported knowledge types."""
    return [knowledge_type_schema(knowledge_type) for knowledge_type in StructuredKnowledgeType]


def knowledge_type_schema(
    knowledge_type: StructuredKnowledgeType,
) -> KnowledgeTypeSchema:
    """Return the schema definition for one knowledge type."""
    return KnowledgeTypeSchema(
        type=knowledge_type,
        label=KNOWLEDGE_TYPE_LABELS[knowledge_type],
        fields=[*_COMMON_FIELD_SCHEMAS, *_TYPE_FIELD_SCHEMAS[knowledge_type]],
    )


def knowledge_type_field_keys(knowledge_type: StructuredKnowledgeType) -> set[str]:
    """Return editable field keys allowed for one knowledge type."""
    return {
        field.field_key
        for field in knowledge_type_schema(knowledge_type).fields
    }


def type_specific_field_keys(knowledge_type: StructuredKnowledgeType) -> set[str]:
    """Return type-specific top-level field keys for one knowledge type."""
    return {field.field_key for field in _TYPE_FIELD_SCHEMAS[knowledge_type]}


def knowledge_type_label(knowledge_type: StructuredKnowledgeType) -> str:
    """Return the Chinese label for one knowledge type."""
    return KNOWLEDGE_TYPE_LABELS[knowledge_type]


def all_knowledge_card_field_keys() -> set[str]:
    """Return all first-version card field keys, including system-managed keys."""
    editable_keys = set(COMMON_KNOWLEDGE_FIELD_KEYS)
    for knowledge_type in StructuredKnowledgeType:
        editable_keys.update(type_specific_field_keys(knowledge_type))
    return {
        "id",
        "type",
        *editable_keys,
        "created_at",
        "updated_at",
    }


def _option(value: str, label: str) -> KnowledgeFieldOption:
    return KnowledgeFieldOption(value=value, label=label)


def _field(
    field_key: str,
    label: str,
    field_type: KnowledgeSchemaFieldType,
    *,
    required_when_confirmed: bool = False,
    options: list[KnowledgeFieldOption] | None = None,
    placeholder: str = "",
    display_group: str = "基础信息",
    list_display: bool = False,
    author_editable: bool = True,
    ai_usage: str = "",
) -> KnowledgeFieldSchema:
    return KnowledgeFieldSchema(
        field_key=field_key,
        label=label,
        field_type=field_type,
        required_when_confirmed=required_when_confirmed,
        options=options or [],
        placeholder=placeholder,
        display_group=display_group,
        list_display=list_display,
        author_editable=author_editable,
        ai_usage=ai_usage,
    )


_LIFECYCLE_OPTIONS = [
    _option("draft", "草稿"),
    _option("confirmed", "已确认"),
    _option("rejected", "已拒绝"),
]

_SOURCE_ORIGIN_OPTIONS = [
    _option("inbox_fact", "收件箱事实转化"),
    _option("agent_extract", "正文自动提取"),
    _option("manual", "人工添加"),
]

_COMMON_FIELD_SCHEMAS = [
    _field(
        "name",
        "名称",
        KnowledgeSchemaFieldType.SHORT_TEXT,
        required_when_confirmed=True,
        placeholder="输入知识卡名称",
        list_display=True,
        ai_usage="知识卡主名称，用于检索和引用。",
    ),
    _field(
        "aliases",
        "别名",
        KnowledgeSchemaFieldType.STRING_ARRAY,
        placeholder="多个别名用换行或逗号分隔",
        list_display=True,
        ai_usage="名称、称号、旧名和简称。",
    ),
    _field(
        "summary",
        "摘要",
        KnowledgeSchemaFieldType.LONG_TEXT,
        required_when_confirmed=True,
        placeholder="一句话或一段摘要",
        list_display=True,
        ai_usage="面向写作和 AI 引用的核心事实摘要。",
    ),
    _field(
        "appearance_chapter_count",
        "重要程度",
        KnowledgeSchemaFieldType.NUMBER,
        list_display=True,
        author_editable=False,
        ai_usage="由正文知识沉淀按实际出现章节累计，前端按全书章节占比显示重要程度。",
    ),
    _field(
        "lifecycle",
        "生命周期",
        KnowledgeSchemaFieldType.ENUM,
        options=_LIFECYCLE_OPTIONS,
        list_display=True,
        ai_usage="草稿不参与 AI 检索，已确认卡可用于后续引用。",
    ),
    _field(
        "source_origin",
        "来源方式",
        KnowledgeSchemaFieldType.ENUM,
        required_when_confirmed=True,
        options=_SOURCE_ORIGIN_OPTIONS,
        placeholder="选择来源方式",
        display_group="来源",
        list_display=True,
        ai_usage="说明知识卡来源类型。",
    ),
    _field(
        "source_note",
        "来源说明",
        KnowledgeSchemaFieldType.LONG_TEXT,
        required_when_confirmed=True,
        placeholder="作者手动添加。可写章节、原文摘录、人工说明。",
        display_group="来源",
        list_display=True,
        ai_usage="知识卡可被信任和追溯的自由文本来源说明。",
    ),
]

_ROLE_TYPE_OPTIONS = [
    _option("protagonist", "主角"),
    _option("supporting", "配角"),
    _option("antagonist", "反派"),
    _option("passerby", "路人"),
    _option("faction_representative", "势力代表"),
]

_TECHNIQUE_TYPE_OPTIONS = [
    _option("cultivation_method", "功法"),
    _option("spell", "术法"),
    _option("divine_ability", "神通"),
    _option("sword_art", "剑诀"),
    _option("forbidden_art", "禁术"),
    _option("alchemy", "炼丹"),
    _option("formation", "阵法"),
    _option("other", "其他"),
]

_FACTION_TYPE_OPTIONS = [
    _option("sect", "宗门"),
    _option("family", "家族"),
    _option("dynasty", "王朝"),
    _option("guild", "商会"),
    _option("demonic", "魔道"),
    _option("alliance", "联盟"),
    _option("academy", "学院"),
    _option("other", "其他"),
]

_ITEM_TYPE_OPTIONS = [
    _option("magic_treasure", "法宝"),
    _option("pill", "丹药"),
    _option("material", "材料"),
    _option("other", "其他"),
]

_TYPE_FIELD_SCHEMAS: dict[StructuredKnowledgeType, list[KnowledgeFieldSchema]] = {
    StructuredKnowledgeType.CHARACTER: [
        _field(
            "role_type",
            "角色定位",
            KnowledgeSchemaFieldType.ENUM,
            options=_ROLE_TYPE_OPTIONS,
            display_group="类型字段",
            list_display=True,
            ai_usage="角色在故事中的基础定位。",
        ),
        _field(
            "identity",
            "身份",
            KnowledgeSchemaFieldType.SHORT_TEXT,
            display_group="类型字段",
            list_display=True,
            ai_usage="角色出身、身份或公开身份。",
        ),
        _field(
            "relationship_summary",
            "关系摘要",
            KnowledgeSchemaFieldType.LONG_TEXT,
            display_group="类型字段",
            ai_usage="人物关系的文字概述。",
        ),
        _field(
            "death_chapter_id",
            "死亡章节",
            KnowledgeSchemaFieldType.CHAPTER_REF,
            display_group="类型字段",
            ai_usage="角色死亡确认章节的稳定 chapter_id。",
        ),
        _field(
            "current_realm_text",
            "当前境界",
            KnowledgeSchemaFieldType.SHORT_TEXT,
            display_group="类型字段",
            list_display=True,
            ai_usage="角色当前境界文本。",
        ),
        _field(
            "first_seen_chapter_id",
            "首次登场章节",
            KnowledgeSchemaFieldType.CHAPTER_REF,
            display_group="类型字段",
            ai_usage="角色首次登场章节的稳定 chapter_id。",
        ),
        _field(
            "last_seen_chapter_id",
            "最近出现章节",
            KnowledgeSchemaFieldType.CHAPTER_REF,
            display_group="类型字段",
            ai_usage="角色最近出现章节的稳定 chapter_id。",
        ),
    ],
    StructuredKnowledgeType.REALM: [
        _field(
            "system",
            "修炼体系",
            KnowledgeSchemaFieldType.SHORT_TEXT,
            display_group="类型字段",
            list_display=True,
            ai_usage="境界所属修炼体系。",
        ),
        _field(
            "level_order",
            "境界排序值",
            KnowledgeSchemaFieldType.NUMBER,
            display_group="类型字段",
            list_display=True,
            ai_usage="用于比较境界高低的数字。",
        ),
    ],
    StructuredKnowledgeType.TECHNIQUE: [
        _field(
            "technique_type",
            "功法类型",
            KnowledgeSchemaFieldType.ENUM,
            options=_TECHNIQUE_TYPE_OPTIONS,
            display_group="类型字段",
            list_display=True,
            ai_usage="功法、术法、神通等类型。",
        ),
        _field(
            "grade",
            "品阶",
            KnowledgeSchemaFieldType.SHORT_TEXT,
            display_group="类型字段",
            list_display=True,
            ai_usage="功法品阶或等级。",
        ),
        _field(
            "practice_condition",
            "修炼条件",
            KnowledgeSchemaFieldType.LONG_TEXT,
            display_group="类型字段",
            ai_usage="修炼、施展或学习条件。",
        ),
        _field(
            "owner_faction_id",
            "所属势力",
            KnowledgeSchemaFieldType.KNOWLEDGE_REF,
            display_group="类型字段",
            ai_usage="所属势力或传承的知识卡 id。",
        ),
    ],
    StructuredKnowledgeType.LOCATION: [
        _field(
            "controlling_faction_id",
            "控制势力",
            KnowledgeSchemaFieldType.KNOWLEDGE_REF,
            display_group="类型字段",
            list_display=True,
            ai_usage="控制该地点的势力知识卡 id。",
        ),
        _field(
            "first_seen_chapter_id",
            "首次出现章节",
            KnowledgeSchemaFieldType.CHAPTER_REF,
            display_group="类型字段",
            ai_usage="地点首次出现章节的稳定 chapter_id。",
        ),
    ],
    StructuredKnowledgeType.FACTION: [
        _field(
            "faction_type",
            "势力类型",
            KnowledgeSchemaFieldType.ENUM,
            options=_FACTION_TYPE_OPTIONS,
            display_group="类型字段",
            list_display=True,
            ai_usage="宗门、家族、王朝等势力类型。",
        ),
        _field(
            "leader_id",
            "当前首领",
            KnowledgeSchemaFieldType.KNOWLEDGE_REF,
            display_group="类型字段",
            list_display=True,
            ai_usage="当前首领角色知识卡 id。",
        ),
    ],
    StructuredKnowledgeType.ITEM: [
        _field(
            "item_type",
            "物品类型",
            KnowledgeSchemaFieldType.ENUM,
            options=_ITEM_TYPE_OPTIONS,
            display_group="类型字段",
            list_display=True,
            ai_usage="法宝、丹药、材料或其他物品类型。",
        ),
        _field(
            "grade",
            "品阶",
            KnowledgeSchemaFieldType.SHORT_TEXT,
            display_group="类型字段",
            list_display=True,
            ai_usage="物品品阶。",
        ),
        _field(
            "current_holder_id",
            "当前持有人",
            KnowledgeSchemaFieldType.KNOWLEDGE_REF,
            display_group="类型字段",
            list_display=True,
            ai_usage="当前持有者的角色知识卡 id。",
        ),
        _field(
            "first_seen_chapter_id",
            "首次出现章节",
            KnowledgeSchemaFieldType.CHAPTER_REF,
            display_group="类型字段",
            ai_usage="物品首次出现章节的稳定 chapter_id。",
        ),
        _field(
            "last_seen_chapter_id",
            "最近出现章节",
            KnowledgeSchemaFieldType.CHAPTER_REF,
            display_group="类型字段",
            ai_usage="物品最近出现章节的稳定 chapter_id。",
        ),
    ],
    StructuredKnowledgeType.RULE: [
        _field(
            "exceptions",
            "例外情况",
            KnowledgeSchemaFieldType.LONG_TEXT,
            display_group="类型字段",
            ai_usage="规则例外情况。",
        ),
    ],
    StructuredKnowledgeType.EVENT: [
        _field(
            "chapter_id",
            "发生章节",
            KnowledgeSchemaFieldType.CHAPTER_REF,
            display_group="类型字段",
            list_display=True,
            ai_usage="事件发生或首次确认章节的稳定 chapter_id。",
        ),
        _field(
            "description",
            "事件描述",
            KnowledgeSchemaFieldType.LONG_TEXT,
            display_group="类型字段",
            ai_usage="事件内容与影响的简要描述。",
        ),
    ],
}
