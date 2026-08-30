"""Native input and output schemas for the knowledge extraction Agent."""

from typing import Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class _StrictStructuredOutput(BaseModel):
    """Base contract passed through the model API's native tool parameters."""

    model_config = ConfigDict(extra="forbid")


class KnowledgeExtractionAgentInput(BaseModel):
    """Input accepted by the knowledge extraction Agent graph."""

    chapter_id: str = Field(min_length=1)
    model_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("model_id", "model_name"),
    )
    force: bool = False


class KnowledgeExtractionAgentOutput(BaseModel):
    """Minimal output returned by the knowledge extraction Agent graph."""

    run_id: str
    status: str
    candidate_count: int = 0


KnowledgeTypeName = Literal[
    "character",
    "location",
    "faction",
    "item",
    "realm",
    "technique",
    "event",
    "rule",
]


class GeneralMention(_StrictStructuredOutput):
    """One source-grounded mention discovered in the chapter."""

    name: str = Field(description="正文中的稳定名称或可追踪事件、规则名称。")
    knowledge_type: KnowledgeTypeName = Field(description="知识类型。")
    description: str = Field(description="仅依据正文形成的简要说明。")
    evidence_excerpts: list[str] = Field(
        min_length=1,
        max_length=5,
        description="来自正文的原文证据，每条不超过三百字。",
    )
    reason: str = Field(description="保留该提及的理由。")


class IgnoredMention(_StrictStructuredOutput):
    """One rejected fragment and its reason."""

    text: str = Field(description="被忽略的原文对象或片段。")
    reason: str = Field(description="不进入后续聚合流程的理由。")


class GeneralExtractionOutput(_StrictStructuredOutput):
    """Native structured result of the general extraction node."""

    mentions: list[GeneralMention]
    ignored: list[IgnoredMention]


class SummaryItem(_StrictStructuredOutput):
    """One synthesized fact snapshot."""

    candidate_id: str = Field(description="输入中不可改写的候选标识。")
    summary: str = Field(description="综合旧事实与新增证据形成的单段事实摘要。")


class SummarySynthesisOutput(_StrictStructuredOutput):
    """Native structured result of summary synthesis."""

    summaries: list[SummaryItem]


class _ExpertCardBase(_StrictStructuredOutput):
    """Fields shared by every expert-produced knowledge candidate."""

    entity_group_id: str = Field(description="来源实体组标识。")
    name: str = Field(description="可唯一追踪的知识卡名称。")
    aliases: list[str] = Field(description="正文明确出现的别名、旧名或称号。")
    summary: str = Field(description="依据全部证据综合形成的事实摘要。")
    source_origin: Literal["agent_extract"] = Field(description="固定为正文自动提取。")
    source_note: str = Field(description="包含章节标题与关键原文的中文来源说明。")
    evidence_excerpt: str = Field(description="最具代表性的主证据原文。")
    evidence_excerpts: list[str] = Field(
        min_length=1,
        max_length=12,
        description="支持该候选的多条原文证据。",
    )


class CharacterCardOutput(_ExpertCardBase):
    """Character candidate fields allowed in the first knowledge schema."""

    role_type: (
        Literal[
            "protagonist",
            "supporting",
            "antagonist",
            "passerby",
            "faction_representative",
        ]
        | None
    )
    identity: str | None
    relationship_summary: str | None
    death_chapter_id: str | None
    current_realm_text: str | None
    first_seen_chapter_id: str
    last_seen_chapter_id: str


class CharacterExpertOutput(_StrictStructuredOutput):
    """Native structured result of the character expert."""

    knowledge_type: Literal["character"]
    cards: list[CharacterCardOutput]


class RealmCardOutput(_ExpertCardBase):
    """Realm candidate fields."""

    system: str | None
    level_order: float | None


class TechniqueCardOutput(_ExpertCardBase):
    """Technique candidate fields."""

    technique_type: (
        Literal[
            "cultivation_method",
            "spell",
            "divine_ability",
            "sword_art",
            "forbidden_art",
            "alchemy",
            "formation",
            "other",
        ]
        | None
    )
    grade: str | None
    practice_condition: str | None
    owner_faction_id: str | None


class LocationCardOutput(_ExpertCardBase):
    """Location candidate fields."""

    controlling_faction_id: str | None
    first_seen_chapter_id: str


class FactionCardOutput(_ExpertCardBase):
    """Faction candidate fields."""

    faction_type: (
        Literal[
            "sect",
            "family",
            "dynasty",
            "guild",
            "demonic",
            "alliance",
            "academy",
            "other",
        ]
        | None
    )
    leader_id: str | None


class ItemCardOutput(_ExpertCardBase):
    """Item candidate fields."""

    item_type: Literal["magic_treasure", "pill", "material", "other"] | None
    grade: str | None
    current_holder_id: str | None
    first_seen_chapter_id: str
    last_seen_chapter_id: str


class EntityExpertOutput(_StrictStructuredOutput):
    """Native structured result of the entity expert."""

    realms: list[RealmCardOutput]
    techniques: list[TechniqueCardOutput]
    locations: list[LocationCardOutput]
    factions: list[FactionCardOutput]
    items: list[ItemCardOutput]


class EventCardOutput(_ExpertCardBase):
    """Event candidate fields."""

    chapter_id: str
    description: str


class RuleCardOutput(_ExpertCardBase):
    """Rule candidate fields."""

    exceptions: str | None


class EventRuleExpertOutput(_StrictStructuredOutput):
    """Native structured result of the event and rule expert."""

    events: list[EventCardOutput]
    rules: list[RuleCardOutput]
