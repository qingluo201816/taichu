"""统一召回输入和兼容遥测契约测试。"""

import json

import pytest
from pydantic import ValidationError

from taichu.application.retrieval.models import (
    RetrievalIdentityQuery,
    RetrievalMode,
    RetrievalRequest,
    RetrievalTraceRecord,
)
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType
from taichu.domain.rules.fact_scope import FactScopeSource, RetrievalScopeName


def test_relevance_requires_query_or_context() -> None:
    with pytest.raises(ValidationError, match="相关性召回"):
        RetrievalRequest()

    request = RetrievalRequest(context_text="只提供辅助上下文也有效。")

    assert request.mode is RetrievalMode.RELEVANCE


def test_identity_requires_identity_and_catalog_rejects_it() -> None:
    with pytest.raises(ValidationError, match="身份召回"):
        RetrievalRequest(mode=RetrievalMode.IDENTITY)

    identity = RetrievalIdentityQuery(
        knowledge_type=StructuredKnowledgeType.CHARACTER,
        name="秦浩轩",
        aliases=["秦师兄"],
    )
    request = RetrievalRequest(mode=RetrievalMode.IDENTITY, identity=identity)
    assert request.identity == identity

    with pytest.raises(ValidationError, match="快照"):
        RetrievalRequest(mode=RetrievalMode.CATALOG, identity=identity)


def test_fact_scope_and_hard_budgets_cannot_be_expanded() -> None:
    with pytest.raises(ValidationError, match="事实范围"):
        RetrievalRequest(
            query_text="秦浩轩",
            scope=RetrievalScopeName.WORKSPACE,
        )
    with pytest.raises(ValidationError, match="已确认知识库"):
        RetrievalRequest(
            query_text="秦浩轩",
            source=FactScopeSource.CHAPTERS,
        )
    with pytest.raises(ValidationError):
        RetrievalRequest(query_text="秦浩轩", top_k=201)
    with pytest.raises(ValidationError):
        RetrievalRequest(query_text="秦浩轩", max_content_chars=50_001)


def test_identity_and_catalog_reject_non_deterministic_strategy() -> None:
    with pytest.raises(ValidationError, match="确定性词法策略"):
        RetrievalRequest(
            mode=RetrievalMode.CATALOG,
            requested_strategy="vector",
        )


def test_legacy_trace_record_remains_readable_with_new_defaults() -> None:
    legacy = {
        "lifecycle": "confirmed",
        "retrieval_id": "retrieval_legacy",
        "status": "empty",
        "mode": "relevance",
        "scope": "fact_scope",
        "source": "confirmed_knowledge",
        "strategy": "mongo_lexical",
        "consumer": {"consumer_type": "writing_task"},
        "query_sha256": "a" * 64,
        "query_char_count": 4,
        "context_char_count": 0,
        "knowledge_types": [],
        "requested_top_k": 12,
        "requested_max_content_chars": 6000,
        "candidate_count": 0,
        "hit_count": 0,
        "truncated": False,
        "items": [],
        "started_at": "2026-07-18T00:00:00Z",
        "finished_at": "2026-07-18T00:00:00Z",
        "duration_ms": 0,
        "error_type": None,
        "error_message": None,
    }

    record = RetrievalTraceRecord.model_validate_json(json.dumps(legacy))

    assert record.policy_name == "legacy_default"
    assert record.fallback_used is False
    assert record.branches == []
    assert record.index_snapshot_id is None
