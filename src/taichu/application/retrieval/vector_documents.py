"""把已确认知识卡投影成可追溯的向量文档片段。"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal, Self
from uuid import NAMESPACE_URL, uuid5

from pydantic import BaseModel, ConfigDict, Field, model_validator

from taichu.domain.models.structured_knowledge import (
    KnowledgeFieldSchema,
    KnowledgeSchemaFieldType,
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
    knowledge_type_label,
    knowledge_type_schema,
)

PROJECTION_STRATEGY_ID: Literal["structured_card_fields"] = "structured_card_fields"


class KnowledgeVectorDocumentKind(StrEnum):
    """结构化知识卡的稳定片段边界。"""

    IDENTITY = "identity"
    SUMMARY = "summary"
    TYPE_FIELDS = "type_fields"


class KnowledgeVectorDocument(BaseModel):
    """只在索引构建期持有正文的可追溯向量文档。"""

    model_config = ConfigDict(frozen=True, extra="forbid")

    point_id: str = Field(pattern=r"^[a-f0-9-]{36}$")
    card_id: str = Field(min_length=1)
    knowledge_type: StructuredKnowledgeType
    kind: KnowledgeVectorDocumentKind
    content: str = Field(min_length=1)
    field_paths: list[str] = Field(min_length=1)
    content_sha256: str = Field(min_length=64, max_length=64)
    card_updated_at: str = Field(min_length=1)
    source_lifecycle: Literal["confirmed"] = "confirmed"
    projection_strategy_id: Literal["structured_card_fields"] = (
        PROJECTION_STRATEGY_ID
    )

    @model_validator(mode="after")
    def validate_content_hash(self) -> Self:
        if _sha256(self.content) != self.content_sha256:
            raise ValueError("向量文档内容校验和不匹配。")
        if len(self.field_paths) != len(set(self.field_paths)):
            raise ValueError("向量文档字段路径不能重复。")
        return self

    def qdrant_payload(self) -> dict[str, str | list[str]]:
        """只返回定位、过滤和过期校验字段，不复制卡片事实。"""
        return {
            "card_id": self.card_id,
            "knowledge_type": self.knowledge_type.value,
            "document_kind": self.kind.value,
            "field_paths": self.field_paths,
            "content_sha256": self.content_sha256,
            "card_updated_at": self.card_updated_at,
            "source_lifecycle": self.source_lifecycle,
            "projection_strategy_id": self.projection_strategy_id,
        }


def project_confirmed_knowledge_cards(
    cards: list[StructuredKnowledgeCard],
) -> list[KnowledgeVectorDocument]:
    """按卡片 ID 稳定排序并生成身份、摘要和类型字段片段。"""
    _validate_confirmed_cards(cards)
    card_lookup = {card.id: card for card in cards}
    documents: list[KnowledgeVectorDocument] = []
    for card in sorted(cards, key=lambda item: item.id):
        documents.extend(_project_card(card, card_lookup))
    return documents


def knowledge_snapshot_sha256(cards: list[StructuredKnowledgeCard]) -> str:
    """对完整 confirmed 卡快照做确定性哈希，用于索引过期检测。"""
    _validate_confirmed_cards(cards)
    payload = [
        card.model_dump(mode="json")
        for card in sorted(cards, key=lambda item: item.id)
    ]
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return _sha256(canonical)


def _project_card(
    card: StructuredKnowledgeCard,
    card_lookup: dict[str, StructuredKnowledgeCard],
) -> list[KnowledgeVectorDocument]:
    type_label = knowledge_type_label(card.type)
    aliases = _unique_nonempty(card.aliases)
    identity_lines = [f"知识类型：{type_label}", f"名称：{card.name.strip()}"]
    identity_paths = ["type", "name"]
    if aliases:
        identity_lines.append("别名：" + "、".join(aliases))
        identity_paths.append("aliases")
    documents = [
        _document(
            card,
            KnowledgeVectorDocumentKind.IDENTITY,
            identity_lines,
            identity_paths,
        )
    ]

    if card.summary.strip():
        documents.append(
            _document(
                card,
                KnowledgeVectorDocumentKind.SUMMARY,
                [f"{type_label}：{card.name.strip()}", f"摘要：{card.summary.strip()}"],
                ["name", "summary"],
            )
        )

    field_lines = [f"{type_label}：{card.name.strip()}"]
    field_paths = ["name"]
    for field_schema in knowledge_type_schema(card.type).fields:
        field_key = field_schema.field_key
        if field_schema.display_group != "类型字段":
            continue
        value = getattr(card, field_key)
        rendered = _render_field_value(field_schema, value, card_lookup)
        if rendered is None:
            continue
        field_lines.append(f"{field_schema.label}：{rendered}")
        field_paths.append(field_key)
    if len(field_lines) > 1:
        documents.append(
            _document(
                card,
                KnowledgeVectorDocumentKind.TYPE_FIELDS,
                field_lines,
                field_paths,
            )
        )
    return documents


def _document(
    card: StructuredKnowledgeCard,
    kind: KnowledgeVectorDocumentKind,
    lines: list[str],
    field_paths: list[str],
) -> KnowledgeVectorDocument:
    content = "\n".join(lines)
    point_identity = f"taichu:{card.id}:{kind.value}:{PROJECTION_STRATEGY_ID}"
    return KnowledgeVectorDocument(
        point_id=str(uuid5(NAMESPACE_URL, point_identity)),
        card_id=card.id,
        knowledge_type=card.type,
        kind=kind,
        content=content,
        field_paths=field_paths,
        content_sha256=_sha256(content),
        card_updated_at=card.updated_at,
    )


def _render_field_value(
    field_schema: KnowledgeFieldSchema,
    value: Any,
    card_lookup: dict[str, StructuredKnowledgeCard],
) -> str | None:
    if value is None or value == "" or value == []:
        return None
    if field_schema.field_type is KnowledgeSchemaFieldType.KNOWLEDGE_REF:
        referenced = card_lookup.get(str(value))
        return referenced.name if referenced is not None else str(value)
    if field_schema.field_type is KnowledgeSchemaFieldType.ENUM:
        option = next(
            (item for item in field_schema.options if item.value == str(value)),
            None,
        )
        return option.label if option is not None else str(value)
    if isinstance(value, list):
        rendered = _unique_nonempty([str(item) for item in value])
        return "、".join(rendered) if rendered else None
    if isinstance(value, bool):
        return "是" if value else "否"
    return str(value).strip() or None


def _validate_confirmed_cards(cards: list[StructuredKnowledgeCard]) -> None:
    card_ids = [card.id for card in cards]
    if len(card_ids) != len(set(card_ids)):
        raise ValueError("知识快照包含重复的知识卡标识。")
    for card in cards:
        if card.lifecycle is not StructuredKnowledgeLifecycle.CONFIRMED:
            raise ValueError("向量索引只能投影已确认知识卡。")
        if not card.name.strip():
            raise ValueError("已确认知识卡缺少可投影的名称。")


def _unique_nonempty(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
