"""统一知识召回的策略执行、范围守卫、预算控制与技术观测。"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter
from uuid import uuid4

from taichu.application.contracts.retrieval import (
    RetrievalBackend,
    RetrievalTraceRepository,
)
from taichu.application.retrieval.execution import RetrievalExecutionPlan
from taichu.application.retrieval.models import (
    RetrievalBackendCandidate,
    RetrievalBackendResult,
    RetrievalBranchStatus,
    RetrievalFallbackReasonCode,
    RetrievalItem,
    RetrievalRequest,
    RetrievalResult,
    RetrievalStatus,
    RetrievalTraceBranch,
    RetrievalTraceItem,
    RetrievalTraceRecord,
)
from taichu.application.retrieval.policy import (
    MONGO_LEXICAL_STRATEGY,
    RetrievalPolicyResolver,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeLifecycle


class RetrievalService:
    """向所有 AI 消费者提供唯一的只读知识召回入口。"""

    def __init__(
        self,
        backend: RetrievalBackend,
        trace_repository: RetrievalTraceRepository,
        *,
        policy_resolver: RetrievalPolicyResolver | None = None,
        additional_backends: Mapping[str, RetrievalBackend] | None = None,
    ) -> None:
        primary_strategy = _backend_strategy_name(backend)
        self._backends: dict[str, RetrievalBackend] = {primary_strategy: backend}
        self._backends.update(additional_backends or {})
        self._trace_repository = trace_repository
        self._policy_resolver = policy_resolver or RetrievalPolicyResolver()
        self._policy_resolver.validate_backends(set(self._backends))

    async def retrieve(self, request: RetrievalRequest) -> RetrievalResult:
        """按策略计划执行召回，并记录完成、空结果、回退或失败。"""
        retrieval_id = f"retrieval_{uuid4().hex}"
        started_at = _now_iso()
        total_timer = perf_counter()
        plan = self._policy_resolver.resolve(request)
        branches: list[RetrievalTraceBranch] = []
        fallback_used = False
        fallback_reason_code: RetrievalFallbackReasonCode | None = None
        effective_strategy: str | None = None

        try:
            try:
                backend_result, branch = await self._invoke_backend(
                    plan.requested_strategy,
                    request,
                    timeout_ms=plan.timeout_ms,
                )
                branches.append(branch)
            except _BackendInvocationFailure as primary_failure:
                branches.append(primary_failure.branch)
                if plan.fallback_strategy is None:
                    raise primary_failure.cause from primary_failure
                fallback_used = True
                fallback_reason_code = primary_failure.reason_code
                try:
                    backend_result, branch = await self._invoke_backend(
                        plan.fallback_strategy,
                        request,
                        timeout_ms=plan.timeout_ms,
                    )
                    branches.append(branch)
                except _BackendInvocationFailure as fallback_failure:
                    branches.append(fallback_failure.branch)
                    raise fallback_failure.cause from fallback_failure

            effective_strategy = backend_result.strategy
            post_filter_timer = perf_counter()
            items, truncated, content_chars_used, budget_limited = _apply_budget(
                backend_result.candidates,
                top_k=plan.top_k,
                max_content_chars=plan.max_content_chars,
            )
            post_filter_duration_ms = _elapsed_ms(post_filter_timer)
            branches[-1] = branches[-1].model_copy(
                update={"hit_count": len(items)}
            )
            finished_at = _now_iso()
            duration_ms = _elapsed_ms(total_timer)
            backend_duration_ms = sum(branch.duration_ms for branch in branches)
            status = RetrievalStatus.COMPLETED if items else RetrievalStatus.EMPTY
            result = RetrievalResult(
                retrieval_id=retrieval_id,
                status=status,
                mode=request.mode,
                scope=request.scope,
                source=request.source,
                strategy=effective_strategy,
                items=items,
                candidate_count=backend_result.candidate_count,
                hit_count=len(items),
                truncated=truncated,
                empty_reason=(None if items else "当前没有检索到可用的已确认知识卡。"),
                started_at=started_at,
                finished_at=finished_at,
                duration_ms=duration_ms,
                policy_name=plan.policy_name,
                requested_strategy=plan.requested_strategy,
                effective_strategy=effective_strategy,
                fallback_used=fallback_used,
                fallback_reason_code=fallback_reason_code,
                applied_top_k=plan.top_k,
                applied_max_content_chars=plan.max_content_chars,
                content_chars_used=content_chars_used,
                budget_limited=budget_limited,
                backend_duration_ms=backend_duration_ms,
                post_filter_duration_ms=post_filter_duration_ms,
                index_snapshot_id=backend_result.index_snapshot_id,
                backend_metrics=backend_result.metrics,
                strategy_snapshot=plan.snapshot(),
            )
            warning = await self._append_trace(
                _trace_from_result(request, result, plan=plan, branches=branches)
            )
            return (
                result.model_copy(update={"warnings": [warning]})
                if warning is not None
                else result
            )
        except Exception as error:
            finished_at = _now_iso()
            duration_ms = _elapsed_ms(total_timer)
            await self._append_trace(
                RetrievalTraceRecord(
                    retrieval_id=retrieval_id,
                    status=RetrievalStatus.FAILED,
                    mode=request.mode,
                    scope=request.scope,
                    source=request.source,
                    strategy=effective_strategy or "unavailable",
                    consumer=request.consumer,
                    query_sha256=_query_sha256(request),
                    query_char_count=len(request.query_text),
                    context_char_count=len(request.context_text),
                    knowledge_types=sorted(
                        request.knowledge_types,
                        key=lambda item: item.value,
                    ),
                    requested_top_k=plan.top_k,
                    requested_max_content_chars=plan.max_content_chars,
                    candidate_count=0,
                    hit_count=0,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=duration_ms,
                    error_type=type(error).__name__,
                    error_message=_safe_error_summary(error),
                    policy_name=plan.policy_name,
                    requested_strategy=plan.requested_strategy,
                    effective_strategy=effective_strategy,
                    fallback_used=fallback_used,
                    fallback_reason_code=fallback_reason_code,
                    backend_duration_ms=sum(
                        branch.duration_ms for branch in branches
                    ),
                    post_filter_duration_ms=0,
                    strategy_snapshot=plan.snapshot(),
                    branches=branches,
                )
            )
            raise

    async def _invoke_backend(
        self,
        strategy: str,
        request: RetrievalRequest,
        *,
        timeout_ms: int,
    ) -> tuple[RetrievalBackendResult, RetrievalTraceBranch]:
        backend = self._backends.get(strategy)
        if backend is None:
            cause = RetrievalStrategyUnavailableError(
                f"召回策略“{strategy}”当前不可用。"
            )
            raise _BackendInvocationFailure(
                cause,
                RetrievalTraceBranch(
                    strategy=strategy,
                    status=RetrievalBranchStatus.UNAVAILABLE,
                    reason_code=(
                        RetrievalFallbackReasonCode.STRATEGY_UNAVAILABLE
                    ),
                    error_summary="请求的召回策略当前不可用。",
                ),
                RetrievalFallbackReasonCode.STRATEGY_UNAVAILABLE,
            )

        timer = perf_counter()
        try:
            result = await asyncio.wait_for(
                backend.retrieve(request),
                timeout=timeout_ms / 1000,
            )
        except TimeoutError as error:
            timeout_cause = RetrievalBackendTimeoutError("召回后端执行超时。")
            raise _BackendInvocationFailure(
                timeout_cause,
                RetrievalTraceBranch(
                    strategy=strategy,
                    status=RetrievalBranchStatus.FAILED,
                    duration_ms=_elapsed_ms(timer),
                    reason_code=RetrievalFallbackReasonCode.BACKEND_TIMEOUT,
                    error_summary="召回后端执行超时。",
                ),
                RetrievalFallbackReasonCode.BACKEND_TIMEOUT,
            ) from error
        except Exception as error:
            raise _BackendInvocationFailure(
                error,
                RetrievalTraceBranch(
                    strategy=strategy,
                    status=RetrievalBranchStatus.FAILED,
                    duration_ms=_elapsed_ms(timer),
                    reason_code=RetrievalFallbackReasonCode.BACKEND_ERROR,
                    error_summary="召回后端执行失败。",
                ),
                RetrievalFallbackReasonCode.BACKEND_ERROR,
            ) from error

        return result, RetrievalTraceBranch(
            strategy=strategy,
            status=RetrievalBranchStatus.COMPLETED,
            candidate_count=result.candidate_count,
            duration_ms=_elapsed_ms(timer),
        )

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
) -> tuple[list[RetrievalItem], bool, int, bool]:
    items: list[RetrievalItem] = []
    used_chars = 0
    truncated = False
    budget_limited = False
    for candidate in candidates:
        if candidate.card.lifecycle is not StructuredKnowledgeLifecycle.CONFIRMED:
            continue
        if len(items) >= top_k:
            break
        next_size = candidate.estimated_content_chars
        if used_chars + next_size > max_content_chars:
            truncated = True
            budget_limited = True
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
    return items, truncated, used_chars, budget_limited


def _trace_from_result(
    request: RetrievalRequest,
    result: RetrievalResult,
    *,
    plan: RetrievalExecutionPlan,
    branches: list[RetrievalTraceBranch],
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
        requested_top_k=plan.top_k,
        requested_max_content_chars=plan.max_content_chars,
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
        policy_name=plan.policy_name,
        requested_strategy=plan.requested_strategy,
        effective_strategy=result.effective_strategy,
        fallback_used=result.fallback_used,
        fallback_reason_code=result.fallback_reason_code,
        backend_duration_ms=result.backend_duration_ms,
        post_filter_duration_ms=result.post_filter_duration_ms,
        strategy_snapshot=plan.snapshot(),
        index_snapshot_id=result.index_snapshot_id,
        branches=branches,
        backend_metrics=result.backend_metrics,
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


def _safe_error_summary(error: Exception) -> str:
    if isinstance(error, RetrievalStrategyUnavailableError):
        return "请求的召回策略当前不可用。"
    if isinstance(error, RetrievalBackendTimeoutError):
        return "召回后端执行超时。"
    return "召回后端执行失败。"


def _backend_strategy_name(backend: RetrievalBackend) -> str:
    strategy_name = getattr(backend, "strategy_name", MONGO_LEXICAL_STRATEGY)
    return str(strategy_name)


def _elapsed_ms(timer: float) -> int:
    return max(0, round((perf_counter() - timer) * 1000))


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class RetrievalStrategyUnavailableError(RuntimeError):
    """执行计划请求了当前未注册的召回策略。"""


class RetrievalBackendTimeoutError(TimeoutError):
    """召回后端超过策略预算。"""


@dataclass(frozen=True, slots=True)
class _BackendInvocationFailure(Exception):
    cause: Exception
    branch: RetrievalTraceBranch
    reason_code: RetrievalFallbackReasonCode
