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
    RetrievalBackendResult,
    RetrievalConsumerContext,
    RetrievalIdentityQuery,
    RetrievalMode,
    RetrievalRequest,
    RetrievalStatus,
)
from taichu.application.capabilities import CapabilityContext
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
async def test_budget_and_top_k_mark_result_as_truncated(tmp_path: Path) -> None:
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
    assert result.truncated is True


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


class _FailingRetrievalBackend:
    async def retrieve(self, request: RetrievalRequest) -> RetrievalBackendResult:
        del request
        raise RuntimeError("模拟召回失败")


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
