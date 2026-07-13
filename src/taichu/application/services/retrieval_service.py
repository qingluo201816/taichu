"""统一知识召回的范围守卫、预算控制与技术观测。"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from taichu.application.contracts.retrieval import (
    RetrievalBackend,
    RetrievalTraceRepository,
)
from taichu.application.retrieval.models import (
    RetrievalBackendCandidate,
    RetrievalItem,
    RetrievalMode,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatus,
    RetrievalTraceItem,
    RetrievalTraceRecord,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeLifecycle


@dataclass(frozen=True, slots=True)
class RetrievalPolicy:
    """第一版召回的默认值和硬上限。"""

    relevance_top_k: int = 12
    identity_top_k: int = 20
    catalog_top_k: int = 200
    relevance_max_content_chars: int = 6_000
    identity_max_content_chars: int = 10_000
    catalog_max_content_chars: int = 50_000
    hard_max_top_k: int = 200
    hard_max_content_chars: int = 50_000


class RetrievalService:
    """向所有 AI 消费者提供唯一的只读知识召回入口。"""

    def __init__(
        self,
        backend: RetrievalBackend,
        trace_repository: RetrievalTraceRepository,
        *,
        policy: RetrievalPolicy | None = None,
    ) -> None:
        self._backend = backend
        self._trace_repository = trace_repository
        self._policy = policy or RetrievalPolicy()

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """执行召回并以轻量遥测记录成功、空结果或失败。"""
        retrieval_id = f"retrieval_{uuid4().hex}"
        started_at = _now_iso()
        timer = perf_counter()
        top_k = self._resolved_top_k(request)
        max_content_chars = self._resolved_max_content_chars(request)
        try:
            backend_result = await self._backend.retrieve(request)
            items, truncated = _apply_budget(
                backend_result.candidates,
                top_k=top_k,
                max_content_chars=max_content_chars,
            )
            finished_at = _now_iso()
            duration_ms = max(0, round((perf_counter() - timer) * 1000))
            status = RetrievalStatus.COMPLETED if items else RetrievalStatus.EMPTY
            result = RetrievalResult(
                retrieval_id=retrieval_id,
                status=status,
                mode=request.mode,
                scope=request.scope,
                source=request.source,
                strategy=backend_result.strategy,
                items=items,
                candidate_count=backend_result.candidate_count,
                hit_count=len(items),
                truncated=truncated,
                empty_reason=(None if items else "当前没有检索到可用的已确认知识卡。"),
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
            )
            trace = _trace_from_result(
                request,
                result,
                top_k=top_k,
                max_content_chars=max_content_chars,
            )
            warning = await self._append_trace(trace)
            return (
                result.model_copy(update={"warnings": [warning]})
                if warning is not None
                else result
            )
        except Exception as error:
            finished_at = _now_iso()
            duration_ms = max(0, round((perf_counter() - timer) * 1000))
            await self._append_trace(
                RetrievalTraceRecord(
                    retrieval_id=retrieval_id,
                    status=RetrievalStatus.FAILED,
                    mode=request.mode,
                    scope=request.scope,
                    source=request.source,
                    strategy="unavailable",
                    consumer=request.consumer,
                    query_sha256=_query_sha256(request),
                    query_char_count=len(request.query_text),
                    context_char_count=len(request.context_text),
                    knowledge_types=sorted(
                        request.knowledge_types,
                        key=lambda item: item.value,
                    ),
                    requested_top_k=top_k,
                    requested_max_content_chars=max_content_chars,
                    candidate_count=0,
                    hit_count=0,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    error_type=type(error).__name__,
                    error_message=str(error)[:500],
                )
            )
            raise

    def _resolved_top_k(self, request: RetrievalRequest) -> int:
        if request.top_k is not None:
            return min(request.top_k, self._policy.hard_max_top_k)
        return {
            RetrievalMode.RELEVANCE: self._policy.relevance_top_k,
            RetrievalMode.IDENTITY: self._policy.identity_top_k,
            RetrievalMode.CATALOG: self._policy.catalog_top_k,
        }[request.mode]

    def _resolved_max_content_chars(self, request: RetrievalRequest) -> int:
        if request.max_content_chars is not None:
            return min(
                request.max_content_chars,
                self._policy.hard_max_content_chars,
            )
        return {
            RetrievalMode.RELEVANCE: self._policy.relevance_max_content_chars,
            RetrievalMode.IDENTITY: self._policy.identity_max_content_chars,
            RetrievalMode.CATALOG: self._policy.catalog_max_content_chars,
        }[request.mode]

    async def _append_trace(self, trace: RetrievalTraceRecord) -> str | None:
        try:
            await self._trace_repository.append(trace)
        except Exception:  # noqa: BLE001
            return "召回已完成，但技术观测记录写入失败。"
        return None


def _apply_budget(
    candidates: Sequence[RetrievalBackendCandidate],
    *,
    top_k: int,
    max_content_chars: int,
) -> tuple[list[RetrievalItem], bool]:
    items: list[RetrievalItem] = []
    used_chars = 0
    truncated = False
    for candidate in candidates:
        if candidate.card.lifecycle is not StructuredKnowledgeLifecycle.CONFIRMED:
            continue
        if len(items) >= top_k:
            truncated = True
            break
        next_size = candidate.estimated_content_chars
        if used_chars + next_size > max_content_chars:
            truncated = True
            continue
        items.append(
            RetrievalItem(
                source_id=candidate.card.id,
                display_name=candidate.card.name,
                rank=len(items) + 1,
                score=candidate.score,
                match_reasons=candidate.match_reasons,
                estimated_content_chars=next_size,
                knowledge_card=candidate.card,
            )
        )
        used_chars += next_size
    return items, truncated


def _trace_from_result(
    request: RetrievalRequest,
    result: RetrievalResult,
    *,
    top_k: int,
    max_content_chars: int,
) -> RetrievalTraceRecord:
    return RetrievalTraceRecord(
        retrieval_id=result.retrieval_id,
        status=result.status,
        mode=result.mode,
        scope=result.scope,
        source=result.source,
        strategy=result.strategy,
        consumer=request.consumer,
        query_sha256=_query_sha256(request),
        query_char_count=len(request.query_text),
        context_char_count=len(request.context_text),
        knowledge_types=sorted(
            request.knowledge_types,
            key=lambda item: item.value,
        ),
        requested_top_k=top_k,
        requested_max_content_chars=max_content_chars,
        candidate_count=result.candidate_count,
        hit_count=result.hit_count,
        truncated=result.truncated,
        items=[
            RetrievalTraceItem(
                source_id=item.source_id,
                rank=item.rank,
                score=item.score,
                match_reasons=_trace_match_reasons(item.match_reasons),
            )
            for item in result.items
        ],
        started_at=result.started_at,
        finished_at=result.finished_at,
        duration_ms=result.duration_ms,
    )


def _query_sha256(request: RetrievalRequest) -> str:
    identity = (
        request.identity.model_dump_json() if request.identity is not None else ""
    )
    payload = "\n".join([request.query_text, request.context_text, identity])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _trace_match_reasons(reasons: list[str]) -> list[str]:
    categories: list[str] = []
    mappings = (
        ("查询文本命中名称或别名", "查询命中名称或别名"),
        ("辅助上下文命中名称或别名", "辅助上下文命中名称或别名"),
        ("查询关键词命中名称或别名", "查询关键词命中名称或别名"),
        ("查询关键词命中知识摘要", "查询关键词命中知识摘要"),
        ("查询关键词命中类型专属字段", "查询关键词命中类型专属字段"),
        ("命中已有已确认知识卡", "精确身份匹配"),
        ("已确认知识快照", "有效知识快照"),
    )
    for reason in reasons:
        category = next(
            (label for prefix, label in mappings if reason.startswith(prefix)),
            "其他匹配",
        )
        if category not in categories:
            categories.append(category)
    return categories


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")
