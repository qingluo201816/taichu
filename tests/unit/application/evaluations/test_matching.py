"""Tests for knowledge-card normalization and deterministic matching."""

from __future__ import annotations

import pytest

from taichu.application.evaluations.knowledge_extraction.matcher import (
    match_candidates,
    match_weight_for,
)
from taichu.application.evaluations.knowledge_extraction.models import (
    ActualCandidate,
    ExpectedCard,
    MatchKind,
)
from taichu.application.evaluations.knowledge_extraction.normalization import (
    normalize_identity,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


def _actual(
    candidate_id: str,
    name: str,
    *,
    knowledge_type: StructuredKnowledgeType = StructuredKnowledgeType.CHARACTER,
    aliases: list[str] | None = None,
) -> ActualCandidate:
    return ActualCandidate(
        actual_candidate_id=candidate_id,
        knowledge_type=knowledge_type,
        card={
            "type": knowledge_type.value,
            "name": name,
            "aliases": aliases or [],
        },
    )


def _expected(
    card_id: str,
    name: str,
    *,
    knowledge_type: StructuredKnowledgeType = StructuredKnowledgeType.CHARACTER,
    aliases: list[str] | None = None,
    accepted_names: list[str] | None = None,
) -> ExpectedCard:
    return ExpectedCard(
        expected_card_id=card_id,
        knowledge_type=knowledge_type,
        card={
            "type": knowledge_type.value,
            "name": name,
            "aliases": aliases or [],
        },
        accepted_names=accepted_names or [],
        exact_fields=[],
        set_fields=[],
        semantic_fields=[],
        expected_claims=[],
        source_quote_ids=[f"quote_{card_id}"],
    )


def test_normalize_identity_applies_nfkc_whitespace_case_and_punctuation() -> None:
    assert normalize_identity(" Ａ b　１２（Test） ") == "ab12(test)"
    assert normalize_identity("第三长老") == "第三长老"


@pytest.mark.parametrize(
    ("actual", "expected", "weight"),
    [
        (_actual("a", " 秦浩轩 "), _expected("e", "秦浩轩"), 100),
        (
            _actual("a", "秦少侠"),
            _expected("e", "秦浩轩", accepted_names=["秦少侠"]),
            95,
        ),
        (
            _actual("a", "秦浩轩", aliases=["小轩"]),
            _expected("e", "少年", aliases=["小轩"]),
            90,
        ),
    ],
)
def test_match_weight_follows_documented_priority(
    actual: ActualCandidate,
    expected: ExpectedCard,
    weight: int,
) -> None:
    assert match_weight_for(actual, expected) == weight
    result = match_candidates([actual], [expected])
    assert result.true_positive_count == 1
    assert result.matches[0].weight == weight


def test_different_knowledge_types_never_match() -> None:
    actual = _actual("actual", "太初教")
    expected = _expected(
        "expected",
        "太初教",
        knowledge_type=StructuredKnowledgeType.FACTION,
    )

    result = match_candidates([actual], [expected])

    assert result.true_positive_count == 0
    assert result.false_positive_count == 1
    assert result.false_negative_count == 1


def test_higher_weight_unique_match_wins_over_lower_alias_edge() -> None:
    actual = _actual("actual", "秦浩轩", aliases=["小轩"])
    exact = _expected("exact", "秦浩轩")
    alias = _expected("alias", "少年", aliases=["小轩"])

    result = match_candidates([actual], [alias, exact])

    assert [(match.expected_card_id, match.kind) for match in result.matches] == [
        ("exact", MatchKind.EXACT_NAME)
    ]
    assert [item.card_id for item in result.false_negatives] == ["alias"]


def test_equal_weight_duplicate_actuals_are_ambiguous_and_penalized() -> None:
    actual = [_actual("a1", "秦浩轩"), _actual("a2", "秦浩轩")]
    expected = [_expected("e1", "秦浩轩")]

    result = match_candidates(actual, expected)

    assert result.true_positive_count == 0
    assert result.false_positive_count == 2
    assert result.false_negative_count == 1
    assert result.ambiguous_count == 1
    ambiguity = result.ambiguities[0]
    assert [item.card_id for item in ambiguity.actual_candidates] == ["a1", "a2"]
    assert [item.card_id for item in ambiguity.expected_cards] == ["e1"]


def test_one_identity_pointing_to_two_gold_cards_is_ambiguous() -> None:
    actual = [_actual("a1", "无名少年")]
    expected = [
        _expected("e1", "事件甲", accepted_names=["无名少年"]),
        _expected("e2", "事件乙", accepted_names=["无名少年"]),
    ]

    result = match_candidates(actual, expected)

    assert result.true_positive_count == 0
    assert result.false_positive_count == 1
    assert result.false_negative_count == 2
    assert result.ambiguities[0].weight == 95


def test_unique_equal_weight_maximum_is_not_marked_ambiguous() -> None:
    actual = [
        _actual("a1", "甲", aliases=["连接一", "连接二"]),
        _actual("a2", "乙", aliases=["连接三"]),
    ]
    expected = [
        _expected("e1", "金标一", aliases=["连接一"]),
        _expected("e2", "金标二", aliases=["连接二", "连接三"]),
    ]

    result = match_candidates(actual, expected)

    assert result.ambiguous_count == 0
    assert {
        (match.actual_candidate_id, match.expected_card_id) for match in result.matches
    } == {("a1", "e1"), ("a2", "e2")}


def test_shared_alias_key_blocks_otherwise_unique_maximum() -> None:
    actual = [
        _actual("a1", "甲", aliases=["独有一", "共享键"]),
        _actual("a2", "乙", aliases=["独有二"]),
    ]
    expected = [
        _expected("e1", "金标一", aliases=["独有一", "共享键"]),
        _expected("e2", "金标二", aliases=["共享键", "独有二"]),
    ]

    result = match_candidates(actual, expected)

    assert result.true_positive_count == 0
    assert result.ambiguous_count == 1
    assert result.ambiguities[0].normalized_keys == ["共享键", "独有一", "独有二"]


def test_duplicate_input_ids_fail_closed() -> None:
    with pytest.raises(ValueError, match="actual_candidate_id"):
        match_candidates(
            [_actual("same", "甲"), _actual("same", "乙")],
            [_expected("e", "甲")],
        )
