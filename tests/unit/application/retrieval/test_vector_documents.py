from __future__ import annotations

import pytest

from taichu.application.retrieval.vector_documents import (
    KnowledgeVectorDocumentKind,
    knowledge_snapshot_sha256,
    project_confirmed_knowledge_cards,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)


def _card(
    *,
    card_id: str = "character-qin",
    lifecycle: StructuredKnowledgeLifecycle = StructuredKnowledgeLifecycle.CONFIRMED,
    updated_at: str = "2026-07-19T00:00:00Z",
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=StructuredKnowledgeType.CHARACTER,
        name="秦浩轩",
        aliases=["浩轩", "浩轩"],
        summary="大田镇少年，能够让灵魂附体五彩小蛇。",
        lifecycle=lifecycle,
        source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
        source_note="第一章完整原文，不得进入向量载荷。",
        role_type="protagonist",
        identity="大田镇猎户少年",
        relationship_summary="与张狂有旧怨。",
        created_at="2026-07-18T00:00:00Z",
        updated_at=updated_at,
    )


def test_projects_confirmed_card_into_traceable_structured_fragments() -> None:
    documents = project_confirmed_knowledge_cards([_card()])

    assert [document.kind for document in documents] == [
        KnowledgeVectorDocumentKind.IDENTITY,
        KnowledgeVectorDocumentKind.SUMMARY,
        KnowledgeVectorDocumentKind.TYPE_FIELDS,
    ]
    assert documents[0].content == "知识类型：角色\n名称：秦浩轩\n别名：浩轩"
    assert "角色定位：主角" in documents[2].content
    assert "身份：大田镇猎户少年" in documents[2].content
    assert all(document.source_lifecycle == "confirmed" for document in documents)
    assert all(document.card_updated_at == _card().updated_at for document in documents)
    assert all("source_note" not in document.field_paths for document in documents)
    assert all("第一章完整原文" not in document.content for document in documents)
    assert all("importance" not in document.model_dump() for document in documents)
    assert set(documents[0].qdrant_payload()) == {
        "card_id",
        "knowledge_type",
        "document_kind",
        "field_paths",
        "content_sha256",
        "card_updated_at",
        "source_lifecycle",
        "projection_strategy_id",
    }


def test_projection_and_snapshot_are_deterministic_and_content_sensitive() -> None:
    first = _card(card_id="character-a")
    second = _card(card_id="character-b")
    forward = project_confirmed_knowledge_cards([first, second])
    reversed_documents = project_confirmed_knowledge_cards([second, first])

    assert [item.point_id for item in forward] == [
        item.point_id for item in reversed_documents
    ]
    assert knowledge_snapshot_sha256([first, second]) == knowledge_snapshot_sha256(
        [second, first]
    )
    changed = second.model_copy(update={"summary": "不同摘要"})
    assert knowledge_snapshot_sha256([first, second]) != knowledge_snapshot_sha256(
        [first, changed]
    )


def test_rejects_unconfirmed_empty_name_and_duplicate_cards() -> None:
    with pytest.raises(ValueError, match="只能投影已确认"):
        project_confirmed_knowledge_cards(
            [_card(lifecycle=StructuredKnowledgeLifecycle.DRAFT)]
        )
    with pytest.raises(ValueError, match="缺少可投影的名称"):
        project_confirmed_knowledge_cards([_card().model_copy(update={"name": ""})])
    with pytest.raises(ValueError, match="重复"):
        knowledge_snapshot_sha256([_card(), _card()])
