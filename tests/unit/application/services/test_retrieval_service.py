"""统一召回服务的范围、排序、预算与观测测试。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Coroutine
from functools import wraps
from pathlib import Path
from typing import Any

import pytest

from taichu.application.retrieval.models import (
    RetrievalBackendCandidate,
    RetrievalBackendResult,
    RetrievalConsumerContext,
    RetrievalFallbackReasonCode,
    RetrievalIdentityQuery,
    RetrievalMode,
    RetrievalRequest,
    RetrievalStatus,
)
from taichu.application.retrieval.policy import RetrievalPolicyResolver
from taichu.application.capabilities import CapabilityContext
from taichu.application.contracts.knowledge_repository import (
    KnowledgeRepositoryUnavailableError,
)
from taichu.application.invocations.models import InvocationContext
from taichu.application.services.retrieval_service import RetrievalService
from taichu.application.tools.knowledge_retrieval.tool import (
    KnowledgeRetrievalToolInput,
    manifest as retrieval_tool_manifest,
    run as run_retrieval_tool,
)
from taichu.domain.models.structured_knowledge import (
    StructuredKnowledgeCard,
    StructuredKnowledgeLifecycle,
    StructuredKnowledgeSourceOrigin,
    StructuredKnowledgeType,
)
from taichu.domain.rules.fact_scope import FactScopeSource, RetrievalScopeName
from taichu.infrastructure.retrieval import (
    JsonlRetrievalTraceRepository,
    MongoLexicalRetrievalBackend,
)
from tests.fakes import InMemoryKnowledgeRepository


def _async_test(
    test: Callable[..., Coroutine[Any, Any, None]],
) -> Callable[..., None]:
    @wraps(test)
    def run(*args: Any, **kwargs: Any) -> None:
        asyncio.run(test(*args, **kwargs))

    return run


@_async_test
async def test_relevance_returns_only_confirmed_cards_in_stable_rank_order(
    tmp_path: Path,
) -> None:
    repository = InMemoryKnowledgeRepository(
        [
            _card(
                "character-qin-yang",
                "秦阳",
                summary="本书主角，太初教弟子。",
                aliases=["秦师兄"],
            ),
            _card(
                "faction-taichu",
                "太初教",
                knowledge_type=StructuredKnowledgeType.FACTION,
                summary="秦阳所在的修仙宗门。",
            ),
            _card(
                "character-draft",
                "草稿人物",
                summary="尚未确认。",
                lifecycle=StructuredKnowledgeLifecycle.DRAFT,
            ),
        ]
    )
    service = _service(repository, tmp_path)

    result = await service.retrieve(
        RetrievalRequest(
            query_text="秦阳返回太初教后如何继续行动？",
            context_text="秦师兄站在山门前。",
            consumer=RetrievalConsumerContext(
                consumer_type="writing_task",
                run_id="writing-1",
                stage="retrieving",
            ),
        )
    )

    assert result.status is RetrievalStatus.COMPLETED
    assert [item.source_id for item in result.items] == [
        "character-qin-yang",
        "faction-taichu",
    ]
    assert all(
        item.knowledge_card.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED
        for item in result.items
    )
    assert result.items[0].score > result.items[1].score
    assert result.candidate_count == 2


@_async_test
async def test_identity_and_catalog_share_result_contract(tmp_path: Path) -> None:
    repository = InMemoryKnowledgeRepository(
        [
            _card("character-qin-yang", "秦阳", aliases=["秦师兄"]),
            _card(
                "faction-taichu",
                "太初教",
                knowledge_type=StructuredKnowledgeType.FACTION,
            ),
        ]
    )
    service = _service(repository, tmp_path)

    identity = await service.retrieve(
        RetrievalRequest(
            mode=RetrievalMode.IDENTITY,
            identity=RetrievalIdentityQuery(
                knowledge_type=StructuredKnowledgeType.CHARACTER,
                name="秦师兄",
            ),
            consumer=RetrievalConsumerContext(
                consumer_type="knowledge_workflow",
                stage="match_existing",
            ),
        )
    )
    catalog = await service.retrieve(
        RetrievalRequest(
            mode=RetrievalMode.CATALOG,
            knowledge_types=frozenset({StructuredKnowledgeType.FACTION}),
            consumer=RetrievalConsumerContext(
                consumer_type="knowledge_workflow",
                stage="active_knowledge_index",
            ),
        )
    )

    assert [item.source_id for item in identity.items] == ["character-qin-yang"]
    assert [item.source_id for item in catalog.items] == ["faction-taichu"]
    assert identity.strategy == catalog.strategy == "mongo_lexical"


@_async_test
async def test_top_k_selection_is_not_content_truncation(tmp_path: Path) -> None:
    repository = InMemoryKnowledgeRepository(
        [
            _card(f"character-{index}", f"秦阳{index}", summary="秦阳相关设定。")
            for index in range(3)
        ]
    )
    service = _service(repository, tmp_path)

    result = await service.retrieve(
        RetrievalRequest(query_text="秦阳", top_k=1, max_content_chars=500)
    )

    assert result.hit_count == 1
    assert result.candidate_count == 3
    assert result.truncated is False
    assert result.budget_limited is False


@_async_test
async def test_content_budget_marks_result_as_truncated(tmp_path: Path) -> None:
    repository = InMemoryKnowledgeRepository(
        [
            _card(
                "character-qin-yang",
                "秦阳",
                summary="秦阳相关设定。" * 100,
            )
        ]
    )
    service = _service(repository, tmp_path)

    result = await service.retrieve(
        RetrievalRequest(query_text="秦阳", top_k=12, max_content_chars=500)
    )

    assert result.candidate_count == 1
    assert result.hit_count == 0
    assert result.truncated is True
    assert result.budget_limited is True


@_async_test
async def test_trace_uses_hash_and_does_not_store_raw_query(tmp_path: Path) -> None:
    repository = InMemoryKnowledgeRepository([_card("character-qin-yang", "秦阳")])
    service = _service(repository, tmp_path)
    raw_query = "秦阳的秘密行动"

    result = await service.retrieve(RetrievalRequest(query_text=raw_query))

    trace_path = tmp_path / "derived" / "retrieval" / "calls.jsonl"
    payload = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert payload["retrieval_id"] == result.retrieval_id
    assert payload["lifecycle"] == "confirmed"
    assert payload["query_char_count"] == len(raw_query)
    assert raw_query not in trace_path.read_text(encoding="utf-8")
    assert "秘密" not in trace_path.read_text(encoding="utf-8")
    assert payload["policy_name"] == "default_relevance"
    assert payload["requested_strategy"] == "mongo_lexical"
    assert payload["effective_strategy"] == "mongo_lexical"
    assert payload["fallback_used"] is False
    assert payload["backend_duration_ms"] >= 0
    assert payload["post_filter_duration_ms"] >= 0
    assert payload["strategy_snapshot"]["top_k"] == 12
    assert payload["index_snapshot_id"].startswith("mongo_confirmed_")
    assert payload["branches"][0]["status"] == "completed"


def test_request_rejects_workspace_and_non_confirmed_sources() -> None:
    with pytest.raises(ValueError, match="事实范围"):
        RetrievalRequest(
            query_text="秦阳",
            scope=RetrievalScopeName.WORKSPACE,
        )
    with pytest.raises(ValueError, match="已确认知识库"):
        RetrievalRequest(
            query_text="秦阳",
            source=FactScopeSource.CHAPTERS,
        )


@_async_test
async def test_agent_tool_delegates_to_the_same_retrieval_service(
    tmp_path: Path,
) -> None:
    repository = InMemoryKnowledgeRepository([_card("character-qin-yang", "秦阳")])
    service = _service(repository, tmp_path)
    context = CapabilityContext(capabilities={"retrieval_service": service})

    result = await run_retrieval_tool(
        KnowledgeRetrievalToolInput(
            query_text="秦阳",
            run_id="agent-run-1",
            stage="research",
        ),
        InvocationContext(
            task_id="task-1",
            run_id="agent-run-1",
            caller_type="test",
            caller_name="test",
            phase="research",
        ),
        context,
    )

    assert retrieval_tool_manifest.name == "retrieve_knowledge"
    assert result.model_dump()["items"][0]["source_id"] == "character-qin-yang"


@_async_test
async def test_backend_failure_is_traced_and_reraised(tmp_path: Path) -> None:
    service = RetrievalService(
        _FailingRetrievalBackend(),
        JsonlRetrievalTraceRepository(tmp_path),
    )

    with pytest.raises(RuntimeError, match="模拟召回失败"):
        await service.retrieve(RetrievalRequest(query_text="秦阳"))

    trace_path = tmp_path / "derived" / "retrieval" / "calls.jsonl"
    payload = json.loads(trace_path.read_text(encoding="utf-8").strip())
    assert payload["status"] == "failed"
    assert payload["strategy"] == "unavailable"
    assert payload["error_type"] == "RuntimeError"
    assert payload["error_message"] == "召回后端执行失败。"
    assert "模拟召回失败" not in trace_path.read_text(encoding="utf-8")


@_async_test
async def test_mongo_repository_failure_has_failed_branch_trace(tmp_path: Path) -> None:
    service = RetrievalService(
        MongoLexicalRetrievalBackend(_UnavailableKnowledgeRepository()),
        JsonlRetrievalTraceRepository(tmp_path),
    )

    with pytest.raises(KnowledgeRepositoryUnavailableError):
        await service.retrieve(RetrievalRequest(query_text="秦阳"))

    payload = json.loads(
        (tmp_path / "derived" / "retrieval" / "calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "failed"
    assert payload["branches"][0]["status"] == "failed"
    assert payload["branches"][0]["reason_code"] == "backend_error"


@_async_test
async def test_empty_result_is_successfully_traced(tmp_path: Path) -> None:
    service = _service(InMemoryKnowledgeRepository(), tmp_path)

    result = await service.retrieve(RetrievalRequest(query_text="不存在的知识"))

    assert result.status is RetrievalStatus.EMPTY
    assert result.items == []
    payload = json.loads(
        (tmp_path / "derived" / "retrieval" / "calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "empty"


@_async_test
async def test_trace_failure_does_not_change_retrieval_result() -> None:
    repository = InMemoryKnowledgeRepository([_card("character-qin-yang", "秦阳")])
    service = RetrievalService(
        MongoLexicalRetrievalBackend(repository),
        _FailingTraceRepository(),
    )

    result = await service.retrieve(RetrievalRequest(query_text="秦阳"))

    assert result.status is RetrievalStatus.COMPLETED
    assert result.items[0].source_id == "character-qin-yang"
    assert result.warnings == ["召回已完成，但技术观测记录写入失败。"]


@_async_test
async def test_service_filters_unconfirmed_backend_candidates(tmp_path: Path) -> None:
    service = RetrievalService(
        _MixedLifecycleBackend(),
        JsonlRetrievalTraceRepository(tmp_path),
    )

    result = await service.retrieve(RetrievalRequest(query_text="秦阳"))

    assert [item.source_id for item in result.items] == ["confirmed-card"]
    assert all(
        item.knowledge_card.lifecycle is StructuredKnowledgeLifecycle.CONFIRMED
        for item in result.items
    )


@_async_test
async def test_unavailable_requested_strategy_falls_back_and_is_observable(
    tmp_path: Path,
) -> None:
    repository = InMemoryKnowledgeRepository([_card("character-qin-yang", "秦阳")])
    service = _service(repository, tmp_path)

    result = await service.retrieve(
        RetrievalRequest(query_text="秦阳", requested_strategy="vector")
    )

    assert result.fallback_used is True
    assert (
        result.fallback_reason_code
        is RetrievalFallbackReasonCode.STRATEGY_UNAVAILABLE
    )
    assert result.effective_strategy == "mongo_lexical"
    payload = json.loads(
        (tmp_path / "derived" / "retrieval" / "calls.jsonl").read_text(
            encoding="utf-8"
        )
    )
    assert [branch["status"] for branch in payload["branches"]] == [
        "unavailable",
        "completed",
    ]


@_async_test
async def test_backend_timeout_falls_back_to_mongo_lexical(tmp_path: Path) -> None:
    repository = InMemoryKnowledgeRepository([_card("character-qin-yang", "秦阳")])
    resolver = RetrievalPolicyResolver.from_json(
        '{"default_relevance":{"timeout_ms":100}}',
        default_relevance_strategy="slow_backend",
    )
    service = RetrievalService(
        _SlowBackend(),
        JsonlRetrievalTraceRepository(tmp_path),
        policy_resolver=resolver,
        additional_backends={
            "mongo_lexical": MongoLexicalRetrievalBackend(repository),
        },
    )

    result = await service.retrieve(RetrievalRequest(query_text="秦阳"))

    assert result.status is RetrievalStatus.COMPLETED
    assert result.fallback_used is True
    assert result.fallback_reason_code is RetrievalFallbackReasonCode.BACKEND_TIMEOUT
    assert result.effective_strategy == "mongo_lexical"


@_async_test
async def test_same_snapshot_and_input_have_stable_order(tmp_path: Path) -> None:
    repository = InMemoryKnowledgeRepository(
        [
            _card("card-b", "秦阳乙", summary="秦阳相关设定。"),
            _card("card-a", "秦阳甲", summary="秦阳相关设定。"),
        ]
    )
    service = _service(repository, tmp_path)
    request = RetrievalRequest(query_text="秦阳")

    first = await service.retrieve(request)
    second = await service.retrieve(request)

    assert [item.source_id for item in first.items] == [
        item.source_id for item in second.items
    ]
    assert first.index_snapshot_id == second.index_snapshot_id


class _FailingRetrievalBackend:
    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult:
        del request
        raise RuntimeError("模拟召回失败")


class _UnavailableKnowledgeRepository(InMemoryKnowledgeRepository):
    async def list_confirmed_cards(
        self,
        type: StructuredKnowledgeType | None = None,
    ) -> list[StructuredKnowledgeCard]:
        del type
        raise KnowledgeRepositoryUnavailableError("模拟 MongoDB 不可用")


class _FailingTraceRepository:
    async def append(self, record: object) -> None:
        del record
        raise OSError("模拟遥测磁盘失败")


class _MixedLifecycleBackend:
    strategy_name = "mongo_lexical"

    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult:
        del request
        return RetrievalBackendResult(
            strategy="mongo_lexical",
            candidate_count=2,
            candidates=[
                RetrievalBackendCandidate(
                    card=_card(
                        "draft-card",
                        "草稿秦阳",
                        lifecycle=StructuredKnowledgeLifecycle.DRAFT,
                    ),
                    score=100,
                    estimated_content_chars=10,
                ),
                RetrievalBackendCandidate(
                    card=_card("confirmed-card", "秦阳"),
                    score=90,
                    estimated_content_chars=10,
                ),
            ],
        )


class _SlowBackend:
    strategy_name = "slow_backend"

    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult:
        del request
        await asyncio.sleep(0.2)
        return RetrievalBackendResult(
            strategy="slow_backend",
            candidate_count=0,
        )


def _service(
    repository: InMemoryKnowledgeRepository,
    assets_root: Path,
) -> RetrievalService:
    return RetrievalService(
        MongoLexicalRetrievalBackend(repository),
        JsonlRetrievalTraceRepository(assets_root),
    )


def _card(
    card_id: str,
    name: str,
    *,
    knowledge_type: StructuredKnowledgeType = StructuredKnowledgeType.CHARACTER,
    summary: str | None = None,
    aliases: list[str] | None = None,
    lifecycle: StructuredKnowledgeLifecycle = StructuredKnowledgeLifecycle.CONFIRMED,
) -> StructuredKnowledgeCard:
    return StructuredKnowledgeCard(
        id=card_id,
        type=knowledge_type,
        name=name,
        aliases=aliases or [],
        summary=summary or f"{name}的已确认事实。",
        lifecycle=lifecycle,
        source_origin=StructuredKnowledgeSourceOrigin.MANUAL,
        source_note="作者确认。",
        created_at="2026-07-13T00:00:00Z",
        updated_at="2026-07-13T00:00:00Z",
    )
