"""只供专项评测显式调用的独立知识向量召回后端。"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
from time import perf_counter
import unicodedata

from taichu.application.contracts.embedding import EmbeddingGateway
from taichu.application.contracts.knowledge_repository import (
    StructuredKnowledgeRepository,
)
from taichu.application.contracts.vector_index import (
    VectorIndexBackend,
    VectorIndexManifestRepository,
)
from taichu.application.embeddings.models import (
    EmbeddingPurpose,
    EmbeddingRequest,
)
from taichu.application.retrieval.models import (
    RetrievalBackendCandidate,
    RetrievalBackendMetrics,
    RetrievalBackendResult,
    RetrievalMode,
    RetrievalRequest,
)
from taichu.application.retrieval.vector_documents import (
    PROJECTION_STRATEGY_ID,
    knowledge_snapshot_sha256,
)
from taichu.application.retrieval.vector_index_models import (
    VectorIndexManifest,
    VectorIndexSearchHit,
    VectorIndexSearchRequest,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    type_specific_field_keys,
)

STRATEGY_NAME = "knowledge_vector"
_DOCUMENT_KIND_LABELS = {
    "identity": "身份片段",
    "summary": "摘要片段",
    "type_fields": "类型字段片段",
}
_UNCONFIRMED_SCOPE_TERMS = (
    "未确认",
    "草稿",
    "已拒绝",
    "已删除",
    "忽略事实范围",
    "编造",
)
_TARGET_INTERROGATIVES = ("谁", "哪位", "哪个", "哪座", "哪条", "什么")
_DIRECT_QUESTION_PREFIXES = (
    "是谁",
    "是什么",
    "怎么样",
    "如何",
    "为什么",
    "怎么",
    "有哪些",
    "有什么",
    "的身份",
    "的能力",
    "的境界",
    "的规则",
)


class KnowledgeVectorRetrievalBackend:
    """验证索引新鲜度、生成查询向量并按卡片聚合 Qdrant 命中。"""

    strategy_name = STRATEGY_NAME

    def __init__(
        self,
        *,
        knowledge_repository: StructuredKnowledgeRepository,
        embedding_gateway: EmbeddingGateway,
        vector_index: VectorIndexBackend,
        manifests: VectorIndexManifestRepository,
        query_char_budget: int = 12_000,
        candidate_multiplier: int = 4,
        score_threshold: float = 0.50,
        coverage_bonus: float = 0.02,
    ) -> None:
        if query_char_budget < 1:
            raise ValueError("向量查询字符预算必须大于零。")
        if candidate_multiplier < 1 or candidate_multiplier > 20:
            raise ValueError("向量候选倍数必须为 1 到 20。")
        if score_threshold < -1 or score_threshold > 1:
            raise ValueError("向量最低相似度必须位于 -1 到 1。")
        if coverage_bonus < 0 or coverage_bonus > 0.1:
            raise ValueError("向量多片段覆盖奖励必须位于 0 到 0.1。")
        self._knowledge_repository = knowledge_repository
        self._embedding_gateway = embedding_gateway
        self._vector_index = vector_index
        self._manifests = manifests
        self._query_char_budget = query_char_budget
        self._candidate_multiplier = candidate_multiplier
        self._score_threshold = score_threshold
        self._coverage_bonus = coverage_bonus

    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult:
        if request.mode is not RetrievalMode.RELEVANCE:
            raise KnowledgeVectorRetrievalError(
                "VECTOR_MODE_UNSUPPORTED", "独立向量后端只支持相关性召回。"
            )
        manifest, current_cards = await self._require_current_manifest()
        query_filter = _query_candidate_filter(request, current_cards)
        if query_filter.reject_unconfirmed_scope:
            return RetrievalBackendResult(
                strategy=STRATEGY_NAME,
                candidate_count=0,
                candidates=[],
                index_snapshot_id=manifest.index_id,
            )
        query_text = _query_input(request, self._query_char_budget)

        embedding_timer = perf_counter()
        embedding = await self._embedding_gateway.embed(
            EmbeddingRequest(
                texts=[query_text],
                purpose=EmbeddingPurpose.KNOWLEDGE_QUERY,
                model_role="knowledge_embedding",
                input_char_budget=self._query_char_budget,
                run_id=request.consumer.run_id,
                invocation_id=request.consumer.stage,
            )
        )
        embedding_duration_ms = _elapsed_ms(embedding_timer)
        if (
            embedding.model_id != manifest.embedding_model_id
            or embedding.dimensions != manifest.vector_dimensions
            or embedding.normalization is not manifest.vector_normalization
        ):
            raise KnowledgeVectorRetrievalError(
                "VECTOR_EMBEDDING_MISMATCH",
                "查询 Embedding 与 active 向量索引不兼容。",
            )

        requested_top_k = request.top_k or 10
        vector_top_k = min(
            200,
            max(requested_top_k, requested_top_k * self._candidate_multiplier),
        )
        search_timer = perf_counter()
        hits = await self._vector_index.search(
            VectorIndexSearchRequest(
                collection_name=manifest.active_alias,
                vector=embedding.vectors[0],
                top_k=vector_top_k,
                knowledge_types=request.knowledge_types,
                score_threshold=self._score_threshold,
            )
        )
        search_duration_ms = _elapsed_ms(search_timer)
        candidates = await self._aggregate_current_cards(
            hits,
            only_card_ids=query_filter.only_card_ids,
            excluded_card_ids=query_filter.excluded_card_ids,
        )
        candidates.sort(
            key=lambda item: (
                -item.score,
                _descending_timestamp_key(item.card.updated_at),
                item.card.id,
            )
        )
        return RetrievalBackendResult(
            strategy=STRATEGY_NAME,
            candidate_count=len(candidates),
            candidates=candidates,
            index_snapshot_id=manifest.index_id,
            metrics=RetrievalBackendMetrics(
                embedding_call_id=embedding.call_id,
                embedding_duration_ms=embedding_duration_ms,
                embedding_input_tokens=embedding.input_tokens,
                embedding_cost_amount=embedding.cost_amount,
                index_search_duration_ms=search_duration_ms,
            ),
        )

    async def _require_current_manifest(
        self,
    ) -> tuple[VectorIndexManifest, list[StructuredKnowledgeCard]]:
        manifest = await self._manifests.load_active()
        if manifest is None:
            raise KnowledgeVectorRetrievalError(
                "VECTOR_INDEX_MISSING", "尚未构建可用的 active 向量索引。"
            )
        profile = self._embedding_gateway.profile()
        if (
            manifest.embedding_model_id != profile.model_id
            or manifest.vector_dimensions != profile.dimensions
            or manifest.vector_normalization is not profile.normalization
        ):
            raise KnowledgeVectorRetrievalError(
                "VECTOR_INDEX_MODEL_MISMATCH",
                "active 向量索引与当前 Embedding 模型不兼容。",
            )
        if manifest.document_projection_strategy_id != PROJECTION_STRATEGY_ID:
            raise KnowledgeVectorRetrievalError(
                "VECTOR_INDEX_PROJECTION_MISMATCH",
                "active 向量索引使用了不同的知识投影策略。",
            )
        cards = await self._knowledge_repository.list_confirmed_cards()
        if knowledge_snapshot_sha256(cards) != manifest.knowledge_snapshot_sha256:
            raise KnowledgeVectorRetrievalError(
                "VECTOR_INDEX_STALE",
                "MongoDB confirmed 知识已变化，必须先重建向量索引。",
            )
        alias_target = await self._vector_index.get_alias_target(
            manifest.active_alias
        )
        if alias_target != manifest.physical_collection_name:
            raise KnowledgeVectorRetrievalError(
                "VECTOR_INDEX_ALIAS_MISMATCH",
                "Qdrant active alias 与索引清单不一致。",
            )
        state = await self._vector_index.collection_state(
            manifest.physical_collection_name
        )
        if state is None:
            raise KnowledgeVectorRetrievalError(
                "VECTOR_INDEX_MISSING", "active 向量物理集合不存在。"
            )
        if (
            state.point_count != manifest.document_count
            or state.dimensions != manifest.vector_dimensions
        ):
            raise KnowledgeVectorRetrievalError(
                "VECTOR_INDEX_CORRUPTED",
                "active 向量物理集合未通过条目数或维度校验。",
            )
        return manifest, cards

    async def _aggregate_current_cards(
        self,
        hits: list[VectorIndexSearchHit],
        *,
        only_card_ids: frozenset[str],
        excluded_card_ids: frozenset[str],
    ) -> list[RetrievalBackendCandidate]:
        grouped: dict[str, list[VectorIndexSearchHit]] = defaultdict(list)
        for hit in hits:
            if hit.projection_strategy_id == PROJECTION_STRATEGY_ID:
                grouped[hit.card_id].append(hit)

        candidates: list[RetrievalBackendCandidate] = []
        for card_id, card_hits in grouped.items():
            if only_card_ids and card_id not in only_card_ids:
                continue
            if card_id in excluded_card_ids:
                continue
            card = await self._knowledge_repository.get_card(card_id)
            if card is None or card.lifecycle is not StructuredKnowledgeLifecycle.CONFIRMED:
                continue
            valid_hits = [
                hit for hit in card_hits if hit.card_updated_at == card.updated_at
            ]
            if not valid_hits:
                continue
            kinds = sorted({hit.document_kind for hit in valid_hits})
            best_score = max(hit.score for hit in valid_hits)
            score = min(
                1.0,
                best_score + self._coverage_bonus * min(2, max(0, len(kinds) - 1)),
            )
            reasons = [
                "向量语义命中" + _DOCUMENT_KIND_LABELS.get(kind, "知识片段")
                for kind in kinds
            ]
            candidates.append(
                RetrievalBackendCandidate(
                    card=card,
                    score=round(score, 6),
                    match_reasons=reasons,
                    estimated_content_chars=_estimated_content_chars(card),
                )
            )
        return candidates


class KnowledgeVectorRetrievalError(RuntimeError):
    """索引缺失、过期、损坏或模型不兼容的稳定错误。"""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True, slots=True)
class _QueryCandidateFilter:
    reject_unconfirmed_scope: bool = False
    only_card_ids: frozenset[str] = frozenset()
    excluded_card_ids: frozenset[str] = frozenset()


def _query_candidate_filter(
    request: RetrievalRequest,
    cards: list[StructuredKnowledgeCard],
) -> _QueryCandidateFilter:
    query = request.query_text.strip()
    if any(term in query for term in _UNCONFIRMED_SCOPE_TERMS):
        return _QueryCandidateFilter(reject_unconfirmed_scope=True)
    eligible = [
        card
        for card in cards
        if not request.knowledge_types or card.type in request.knowledge_types
    ]
    normalized_query = _normalize_identity_text(query)
    exact_ids = {
        card.id
        for card in eligible
        if normalized_query
        in {
            _normalize_identity_text(card.name),
            *(_normalize_identity_text(alias) for alias in card.aliases),
        }
    }
    if exact_ids:
        return _QueryCandidateFilter(only_card_ids=frozenset(exact_ids))
    if len(request.knowledge_types) != 1 or not any(
        marker in query for marker in _TARGET_INTERROGATIVES
    ):
        return _QueryCandidateFilter()
    explicit_anchor_ids = {
        card.id
        for card in eligible
        if any(
            _is_explicit_relation_anchor(query, identity)
            for identity in [card.name, *card.aliases]
        )
    }
    return _QueryCandidateFilter(
        excluded_card_ids=frozenset(explicit_anchor_ids)
    )


def _is_explicit_relation_anchor(query: str, identity: str) -> bool:
    identity = identity.strip()
    if not identity or identity not in query:
        return False
    normalized_query = _normalize_identity_text(query)
    normalized_identity = _normalize_identity_text(identity)
    if normalized_query.startswith(normalized_identity):
        suffix = normalized_query[len(normalized_identity) :]
        if suffix.startswith(_DIRECT_QUESTION_PREFIXES):
            return False
    return True


def _query_input(request: RetrievalRequest, budget: int) -> str:
    query = request.query_text.strip()
    context = request.context_text.strip()
    if query and context:
        combined = f"查询：{query}\n辅助上下文：{context}"
    else:
        combined = query or context
    if len(combined) > budget:
        combined = combined[:budget]
    if not combined.strip():
        raise KnowledgeVectorRetrievalError(
            "VECTOR_QUERY_EMPTY", "向量召回缺少可用查询文本。"
        )
    return combined


def _normalize_identity_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    return re.sub(r"[\s，。！？、：；,.!?:;‘’“”\-—_]+", "", normalized)


def _estimated_content_chars(card: StructuredKnowledgeCard) -> int:
    type_fields = [
        str(getattr(card, field_key))
        for field_key in type_specific_field_keys(card.type)
        if getattr(card, field_key) is not None
    ]
    return max(
        1,
        len(card.name)
        + sum(len(alias) for alias in card.aliases)
        + len(card.summary)
        + sum(len(value) for value in type_fields),
    )


def _descending_timestamp_key(value: str) -> tuple[int, ...]:
    return tuple(-ord(character) for character in value)


def _elapsed_ms(timer: float) -> int:
    return max(0, round((perf_counter() - timer) * 1000))
