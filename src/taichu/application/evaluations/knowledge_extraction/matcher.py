"""Deterministic one-to-one identity matching for knowledge cards."""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass

from taichu.application.evaluations.knowledge_extraction.models import (
    ActualCandidate,
    AmbiguousMatch,
    CandidateMatch,
    CandidateMatchResult,
    CandidateRef,
    ExpectedCard,
    MatchKind,
)
from taichu.application.evaluations.knowledge_extraction.normalization import (
    normalize_identity,
    normalized_identities,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType


_MATCH_WEIGHTS = (100, 95, 90)


@dataclass(frozen=True, slots=True)
class _Edge:
    actual_id: str
    expected_id: str
    kind: MatchKind
    weight: int
    normalized_keys: tuple[str, ...]

    @property
    def normalized_key(self) -> str:
        return self.normalized_keys[0]


def _expected_name(card: ExpectedCard) -> str:
    value = card.card.get("name")
    return value if isinstance(value, str) else ""


def _expected_aliases(card: ExpectedCard) -> list[str]:
    value = card.card.get("aliases")
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _edge(actual: ActualCandidate, expected: ExpectedCard) -> _Edge | None:
    if actual.knowledge_type is not expected.knowledge_type:
        return None

    actual_name = normalize_identity(actual.name)
    expected_name = normalize_identity(_expected_name(expected))
    if actual_name and actual_name == expected_name:
        return _Edge(
            actual_id=actual.actual_candidate_id,
            expected_id=expected.expected_card_id,
            kind=MatchKind.EXACT_NAME,
            weight=100,
            normalized_keys=(actual_name,),
        )

    accepted_names = {
        normalize_identity(value)
        for value in expected.accepted_names
        if normalize_identity(value)
    }
    if actual_name and actual_name in accepted_names:
        return _Edge(
            actual_id=actual.actual_candidate_id,
            expected_id=expected.expected_card_id,
            kind=MatchKind.ACCEPTED_NAME,
            weight=95,
            normalized_keys=(actual_name,),
        )

    actual_aliases = normalized_identities("", actual.aliases)
    expected_aliases = normalized_identities("", _expected_aliases(expected))
    cross_keys = set(actual_aliases & expected_aliases)
    if actual_name and actual_name in expected_aliases:
        cross_keys.add(actual_name)
    if expected_name and expected_name in actual_aliases:
        cross_keys.add(expected_name)
    if not cross_keys:
        return None
    return _Edge(
        actual_id=actual.actual_candidate_id,
        expected_id=expected.expected_card_id,
        kind=MatchKind.ALIAS_CROSS,
        weight=90,
        normalized_keys=tuple(sorted(cross_keys)),
    )


def _candidate_ref(candidate: ActualCandidate) -> CandidateRef:
    return CandidateRef(
        card_id=candidate.actual_candidate_id,
        knowledge_type=candidate.knowledge_type,
        name=candidate.name,
    )


def _expected_ref(card: ExpectedCard) -> CandidateRef:
    return CandidateRef(
        card_id=card.expected_card_id,
        knowledge_type=card.knowledge_type,
        name=_expected_name(card),
    )


def _connected_components(edges: list[_Edge]) -> list[list[_Edge]]:
    by_actual: dict[str, list[_Edge]] = defaultdict(list)
    by_expected: dict[str, list[_Edge]] = defaultdict(list)
    for edge in edges:
        by_actual[edge.actual_id].append(edge)
        by_expected[edge.expected_id].append(edge)

    unseen = set(edges)
    components: list[list[_Edge]] = []
    while unseen:
        first = min(
            unseen,
            key=lambda item: (
                item.actual_id,
                item.expected_id,
                item.normalized_key,
            ),
        )
        queue: deque[_Edge] = deque([first])
        component: set[_Edge] = set()
        while queue:
            current = queue.popleft()
            if current in component:
                continue
            component.add(current)
            for neighbour in by_actual[current.actual_id]:
                if neighbour not in component:
                    queue.append(neighbour)
            for neighbour in by_expected[current.expected_id]:
                if neighbour not in component:
                    queue.append(neighbour)
        unseen.difference_update(component)
        components.append(
            sorted(component, key=lambda item: (item.actual_id, item.expected_id))
        )
    return components


def _maximum_matching(edges: list[_Edge]) -> list[_Edge]:
    """Return one stable maximum-cardinality matching for a bipartite graph."""

    by_actual: dict[str, list[_Edge]] = defaultdict(list)
    for edge in edges:
        by_actual[edge.actual_id].append(edge)
    for actual_edges in by_actual.values():
        actual_edges.sort(
            key=lambda item: (item.expected_id, item.normalized_key, item.kind.value)
        )

    matched_expected: dict[str, _Edge] = {}

    def augment(actual_id: str, seen_expected: set[str]) -> bool:
        for edge in by_actual[actual_id]:
            if edge.expected_id in seen_expected:
                continue
            seen_expected.add(edge.expected_id)
            current = matched_expected.get(edge.expected_id)
            if current is None or augment(current.actual_id, seen_expected):
                matched_expected[edge.expected_id] = edge
                return True
        return False

    for actual_id in sorted(by_actual):
        augment(actual_id, set())
    return sorted(
        matched_expected.values(),
        key=lambda item: (item.actual_id, item.expected_id),
    )


def _component_is_ambiguous(
    component: list[_Edge],
    maximum_matching: list[_Edge],
) -> bool:
    expected_by_key: dict[str, set[str]] = defaultdict(set)
    for edge in component:
        for normalized_key in edge.normalized_keys:
            expected_by_key[normalized_key].add(edge.expected_id)
    if any(len(expected_ids) > 1 for expected_ids in expected_by_key.values()):
        return True

    maximum_size = len(maximum_matching)
    return any(
        len(_maximum_matching([edge for edge in component if edge != selected]))
        == maximum_size
        for selected in maximum_matching
    )


def _validate_unique_ids(
    actual_candidates: Sequence[ActualCandidate],
    expected_cards: Sequence[ExpectedCard],
) -> None:
    actual_ids = [candidate.actual_candidate_id for candidate in actual_candidates]
    expected_ids = [card.expected_card_id for card in expected_cards]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("actual_candidate_id must be unique")
    if len(expected_ids) != len(set(expected_ids)):
        raise ValueError("expected_card_id must be unique")


def match_candidates(
    actual_candidates: Sequence[ActualCandidate],
    expected_cards: Sequence[ExpectedCard],
) -> CandidateMatchResult:
    """Match cards by stable identity rules without fuzzy or positional matching.

    Each equal-weight component is solved as a maximum-cardinality bipartite
    matching. A component is blocked only when that maximum has multiple valid
    solutions or one normalized identity key points to multiple gold cards. Its
    actual cards remain false positives and expected cards remain false negatives.
    """

    _validate_unique_ids(actual_candidates, expected_cards)
    actual_by_id = {
        candidate.actual_candidate_id: candidate for candidate in actual_candidates
    }
    expected_by_id = {card.expected_card_id: card for card in expected_cards}
    all_edges = [
        edge
        for actual in actual_candidates
        for expected in expected_cards
        if (edge := _edge(actual, expected)) is not None
    ]

    matched_actual: set[str] = set()
    matched_expected: set[str] = set()
    blocked_actual: set[str] = set()
    blocked_expected: set[str] = set()
    matches: list[CandidateMatch] = []
    ambiguities: list[AmbiguousMatch] = []

    for weight in _MATCH_WEIGHTS:
        eligible_edges = [
            edge
            for edge in all_edges
            if edge.weight == weight
            and edge.actual_id not in matched_actual | blocked_actual
            and edge.expected_id not in matched_expected | blocked_expected
        ]
        for component in _connected_components(eligible_edges):
            actual_ids = {edge.actual_id for edge in component}
            expected_ids = {edge.expected_id for edge in component}
            maximum_matching = _maximum_matching(component)
            if not _component_is_ambiguous(component, maximum_matching):
                for edge in maximum_matching:
                    actual = actual_by_id[edge.actual_id]
                    matches.append(
                        CandidateMatch(
                            actual_candidate_id=edge.actual_id,
                            expected_card_id=edge.expected_id,
                            knowledge_type=actual.knowledge_type,
                            kind=edge.kind,
                            weight=edge.weight,
                            normalized_key=edge.normalized_key,
                        )
                    )
                    matched_actual.add(edge.actual_id)
                    matched_expected.add(edge.expected_id)
                continue

            blocked_actual.update(actual_ids)
            blocked_expected.update(expected_ids)
            knowledge_types = {
                actual_by_id[actual_id].knowledge_type for actual_id in actual_ids
            }
            if len(knowledge_types) != 1:
                raise AssertionError("ambiguous component crossed knowledge types")
            ambiguities.append(
                AmbiguousMatch(
                    knowledge_type=next(iter(knowledge_types)),
                    weight=weight,
                    actual_candidates=[
                        _candidate_ref(actual_by_id[actual_id])
                        for actual_id in sorted(actual_ids)
                    ],
                    expected_cards=[
                        _expected_ref(expected_by_id[expected_id])
                        for expected_id in sorted(expected_ids)
                    ],
                    normalized_keys=sorted(
                        {
                            normalized_key
                            for edge in component
                            for normalized_key in edge.normalized_keys
                        }
                    ),
                )
            )

    false_positives = [
        _candidate_ref(candidate)
        for candidate in sorted(
            actual_candidates,
            key=lambda item: item.actual_candidate_id,
        )
        if candidate.actual_candidate_id not in matched_actual
    ]
    false_negatives = [
        _expected_ref(card)
        for card in sorted(expected_cards, key=lambda item: item.expected_card_id)
        if card.expected_card_id not in matched_expected
    ]
    return CandidateMatchResult(
        matches=sorted(matches, key=lambda item: item.actual_candidate_id),
        false_positives=false_positives,
        false_negatives=false_negatives,
        ambiguities=sorted(
            ambiguities,
            key=lambda item: (
                item.knowledge_type.value,
                -item.weight,
                item.actual_candidates[0].card_id,
            ),
        ),
    )


def match_weight_for(
    actual: ActualCandidate,
    expected: ExpectedCard,
) -> int | None:
    """Expose the deterministic edge weight for preview and focused diagnostics."""

    edge = _edge(actual, expected)
    return edge.weight if edge is not None else None


def knowledge_types_in_result(
    result: CandidateMatchResult,
) -> frozenset[StructuredKnowledgeType]:
    """Return every knowledge type represented by a match result."""

    types = {match.knowledge_type for match in result.matches}
    types.update(item.knowledge_type for item in result.false_positives)
    types.update(item.knowledge_type for item in result.false_negatives)
    return frozenset(types)
