"""Lifecycle contract tests for structured knowledge cards."""

from pydantic import ValidationError
import pytest

from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeType,
    knowledge_type_schema,
)


def _payload() -> dict[str, object]:
    return {
        "id": "character-test",
        "type": "character",
        "name": "秦阳",
        "aliases": ["秦师兄"],
        "summary": "太初教弟子。",
        "lifecycle": "confirmed",
        "source_origin": "manual",
        "source_note": "作者确认。",
        "created_at": "2026-07-11T00:00:00Z",
        "updated_at": "2026-07-11T00:00:00Z",
    }


def test_confirmed_card_is_effective_knowledge() -> None:
    card = StructuredKnowledgeCard.model_validate(_payload())

    assert card.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED
    assert card.can_be_used_as_effective_knowledge() is True
    assert card.appearance_chapter_count is None
    payload = _payload()
    payload["importance"] = "major"
    with pytest.raises(ValidationError):
        StructuredKnowledgeCard.model_validate(payload)


def test_legacy_status_is_not_accepted() -> None:
    payload = _payload()
    payload.pop("lifecycle")
    payload["status"] = "active"

    try:
        StructuredKnowledgeCard.model_validate(payload)
    except ValidationError as error:
        assert "lifecycle" in str(error)
        assert "status" in str(error)
    else:
        raise AssertionError("旧 status 字段不应继续被领域模型接受")


def test_schema_exposes_lifecycle_and_confirmed_requirement_name() -> None:
    schema = knowledge_type_schema(StructuredKnowledgeType.CHARACTER)
    fields = {field.field_key: field for field in schema.fields}

    assert "status" not in fields
    assert [option.value for option in fields["lifecycle"].options] == [
        "draft",
        "confirmed",
        "rejected",
    ]
    assert fields["name"].required_when_confirmed is True
    assert fields["appearance_chapter_count"].author_editable is False
