"""Tests for storage-independent knowledge query contracts."""

import pytest

from taichu.application.contracts.knowledge_repository import KnowledgeCardQuery
from taichu.domain.models.structured_knowledge import StructuredKnowledgeLifecycle


def test_default_query_excludes_rejected_cards() -> None:
    query = KnowledgeCardQuery()

    assert query.lifecycles == frozenset(
        {
            StructuredKnowledgeLifecycle.DRAFT,
            StructuredKnowledgeLifecycle.CONFIRMED,
        }
    )


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"lifecycles": frozenset()}, "生命周期"),
        ({"offset": -1}, "偏移量"),
        ({"limit": 201}, "1 到 200"),
    ],
)
def test_query_rejects_unsafe_pagination(
    kwargs: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        KnowledgeCardQuery(**kwargs)  # type: ignore[arg-type]
