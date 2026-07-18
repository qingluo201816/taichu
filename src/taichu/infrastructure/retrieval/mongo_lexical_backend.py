"""基于 MongoDB 知识事实源的确定性词法召回后端。"""

from __future__ import annotations

import hashlib
import re
import unicodedata

from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.retrieval.models import (
    RetrievalBackendCandidate,
    RetrievalBackendResult,
    RetrievalMode,
    RetrievalRequest,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    type_specific_field_keys,
)

STRATEGY_NAME = "mongo_lexical"
_IGNORED_QUERY_TERMS = {
    "一下",
    "当前",
    "本章",
    "这个",
    "那个",
    "内容",
    "进行",
    "继续",
    "需要",
    "写作",
    "小说",
}


class MongoLexicalRetrievalBackend:
    """从 MongoDB 唯一结构事实源读取并排序已确认知识卡。"""

    strategy_name = STRATEGY_NAME

    def __init__(self, repository: StructuredKnowledgeRepository) -> None:
        self._repository = repository

    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult:
        if request.mode is RetrievalMode.IDENTITY:
            return await self._retrieve_identity(request)
        cards = await self._repository.list_confirmed_cards()
        if request.knowledge_types:
            cards = [card for card in cards if card.type in request.knowledge_types]
        if request.mode is RetrievalMode.CATALOG:
            return RetrievalBackendResult(
                strategy=STRATEGY_NAME,
                candidate_count=len(cards),
                candidates=[
                    RetrievalBackendCandidate(
                        card=card,
                        score=0,
                        match_reasons=["已确认知识快照"],
                        estimated_content_chars=_estimated_content_chars(card),
                    )
                    for card in cards
                ],
                index_snapshot_id=_snapshot_id(cards),
            )
        candidates = [
            candidate
            for card in cards
            if (candidate := _relevance_candidate(card, request)) is not None
        ]
        candidates.sort(
            key=lambda item: (
                -item.score,
                _descending_timestamp_key(item.card.updated_at),
                item.card.id,
            )
        )
        return RetrievalBackendResult(
            strategy=STRATEGY_NAME,
            candidate_count=len(cards),
            candidates=candidates,
            index_snapshot_id=_snapshot_id(cards),
        )

    async def _retrieve_identity(
        self,
        request: RetrievalRequest,
    ) -> RetrievalBackendResult:
        identity = request.identity
        if identity is None:
            raise ValueError("身份召回缺少身份参数。")
        cards = await self._repository.search_confirmed_identity(
            identity.knowledge_type,
            identity.name,
            identity.aliases,
        )
        return RetrievalBackendResult(
            strategy=STRATEGY_NAME,
            candidate_count=len(cards),
            candidates=[
                RetrievalBackendCandidate(
                    card=card,
                    score=100,
                    match_reasons=["命中已有已确认知识卡的名称或别名"],
                    estimated_content_chars=_estimated_content_chars(card),
                )
                for card in cards
            ],
        )


def _relevance_candidate(
    card: StructuredKnowledgeCard,
    request: RetrievalRequest,
) -> RetrievalBackendCandidate | None:
    compact_query = _normalize_compact(request.query_text)
    compact_context = _normalize_compact(request.context_text)
    identities = [card.name, *card.aliases]
    normalized_identities = [
        (value, _normalize_compact(value)) for value in identities if value.strip()
    ]
    score = 0.0
    reasons: list[str] = []
    for raw_value, identity in normalized_identities:
        if len(identity) < 2:
            continue
        if identity in compact_query:
            score += 120
            _append_reason(reasons, f"查询文本命中名称或别名“{raw_value}”")
        elif identity in compact_context:
            score += 80
            _append_reason(reasons, f"辅助上下文命中名称或别名“{raw_value}”")

    searchable_fields = _searchable_fields(card)
    identity_text = " ".join(value for _, value in normalized_identities)
    summary_text = _normalize_search_text(card.summary)
    structured_text = _normalize_search_text(" ".join(searchable_fields))
    for term in _query_terms(request.query_text):
        normalized_term = _normalize_compact(term)
        if not normalized_term:
            continue
        if normalized_term in identity_text:
            score += 30 + min(len(normalized_term), 8)
            _append_reason(reasons, f"查询关键词命中名称或别名“{term}”")
        elif normalized_term in summary_text:
            score += 10 + min(len(normalized_term), 6)
            _append_reason(reasons, f"查询关键词命中知识摘要“{term}”")
        elif normalized_term in structured_text:
            score += 6 + min(len(normalized_term), 4)
            _append_reason(reasons, f"查询关键词命中类型专属字段“{term}”")
    if score <= 0:
        return None
    return RetrievalBackendCandidate(
        card=card,
        score=score,
        match_reasons=reasons[:8],
        estimated_content_chars=_estimated_content_chars(card),
    )


def _searchable_fields(card: StructuredKnowledgeCard) -> list[str]:
    payload = card.model_dump(mode="json", exclude_none=True)
    return [
        str(payload[key])
        for key in sorted(type_specific_field_keys(card.type))
        if key in payload and payload[key] not in ("", [], None)
    ]


def _query_terms(text: str) -> list[str]:
    terms: set[str] = set()
    for value in re.findall(r"[A-Za-z0-9_]{2,24}", text):
        terms.add(value.casefold())
    for sequence in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        if len(sequence) <= 8:
            terms.add(sequence)
        for size in (2, 3, 4):
            for start in range(max(0, len(sequence) - size + 1)):
                terms.add(sequence[start : start + size])
                if len(terms) >= 256:
                    break
            if len(terms) >= 256:
                break
        if len(terms) >= 256:
            break
    return sorted(term for term in terms if term not in _IGNORED_QUERY_TERMS)


def _estimated_content_chars(card: StructuredKnowledgeCard) -> int:
    return max(
        1,
        len(card.name)
        + sum(len(alias) for alias in card.aliases)
        + len(card.summary)
        + sum(len(value) for value in _searchable_fields(card)),
    )


def _normalize_compact(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return "".join(normalized.split())


def _normalize_search_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _append_reason(reasons: list[str], reason: str) -> None:
    if reason not in reasons:
        reasons.append(reason)


def _descending_timestamp_key(value: str) -> tuple[int, ...]:
    return tuple(-ord(character) for character in value)


def _snapshot_id(cards: list[StructuredKnowledgeCard]) -> str:
    payload = "\n".join(
        f"{card.id}:{card.updated_at}"
        for card in sorted(cards, key=lambda item: item.id)
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"mongo_confirmed_{digest}"
