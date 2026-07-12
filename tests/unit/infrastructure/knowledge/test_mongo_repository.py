"""Pure mapping and schema tests for the Mongo knowledge repository."""

from datetime import datetime

from taichu.domain.models.structured_knowledge import StructuredKnowledgeCard
from taichu.infrastructure.knowledge.mongo_repository import (
    card_to_document,
    document_to_card,
    identity_keys,
    knowledge_collection_validator,
)


def _card() -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard.model_validate(
        {
            "id": "character-qin",
            "type": "character",
            "name": " 秦 阳 ",
            "aliases": ["ＱＩＮ", "秦阳"],
            "summary": "测试摘要",
            "importance": "normal",
            "lifecycle": "confirmed",
            "source_origin": "manual",
            "source_note": "作者确认",
            "created_at": "2026-07-11T08:00:00.123456+08:00",
            "updated_at": "2026-07-11T00:01:00Z",
        }
    )


def test_document_mapping_uses_business_id_and_bson_dates() -> None:
    document = card_to_document(_card())

    assert document["_id"] == "character-qin"
    assert "id" not in document
    assert "status" not in document
    assert document["lifecycle"] == "confirmed"
    assert document["identity_keys"] == ["qin", "秦阳"]
    assert isinstance(document["created_at"], datetime)

    restored = document_to_card(document)
    assert restored.id == "character-qin"
    assert restored.created_at == "2026-07-11T00:00:00.123000Z"


def test_identity_normalization_is_nfkc_casefolded_and_deduplicated() -> None:
    assert identity_keys(" Ａlice ", ["alice", "AL ICE", "爱 丽 丝"]) == [
        "alice",
        "爱丽丝",
    ]


def test_validator_requires_lifecycle_and_has_no_legacy_status() -> None:
    schema = knowledge_collection_validator()["$jsonSchema"]

    assert "lifecycle" in schema["required"]
    assert "status" not in schema["properties"]
    assert schema["additionalProperties"] is False
