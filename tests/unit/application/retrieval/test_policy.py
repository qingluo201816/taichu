"""消费者级召回策略解析和启动配置测试。"""

from pathlib import Path

import pytest

from taichu.application.retrieval.models import (
    RetrievalConsumerContext,
    RetrievalIdentityQuery,
    RetrievalMode,
    RetrievalRequest,
)
from taichu.application.retrieval.policy import RetrievalPolicyResolver
from taichu.config import Settings
from taichu.domain.models.structured_knowledge import StructuredKnowledgeType
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


@pytest.mark.parametrize(
    ("consumer_type", "expected_policy", "expected_top_k"),
    [
        ("writing_task", "writing_task", 12),
        ("chapter_summary", "chapter_summary", 20),
        ("knowledge_workflow", "knowledge_workflow", 20),
        ("general_agent_runtime", "general_agent_runtime", 12),
        ("retrieval_evaluation", "retrieval_evaluation", 10),
    ],
)
def test_consumer_profiles_resolve_distinct_budgets(
    consumer_type: str,
    expected_policy: str,
    expected_top_k: int,
) -> None:
    resolver = RetrievalPolicyResolver()

    plan = resolver.resolve(
        RetrievalRequest(
            query_text="秦浩轩",
            consumer=RetrievalConsumerContext(consumer_type=consumer_type),
        )
    )

    assert plan.policy_name == expected_policy
    assert plan.top_k == expected_top_k
    assert plan.requested_strategy == "mongo_lexical"


def test_identity_and_catalog_have_deterministic_fallback_profiles() -> None:
    resolver = RetrievalPolicyResolver()

    identity = resolver.resolve(
        RetrievalRequest(
            mode=RetrievalMode.IDENTITY,
            identity=RetrievalIdentityQuery(
                knowledge_type=StructuredKnowledgeType.CHARACTER,
                name="秦浩轩",
            ),
        )
    )
    catalog = resolver.resolve(RetrievalRequest(mode=RetrievalMode.CATALOG))

    assert identity.policy_name == "identity"
    assert identity.top_k == 20
    assert catalog.policy_name == "catalog"
    assert catalog.top_k == 200
    assert identity.requested_strategy == catalog.requested_strategy == "mongo_lexical"


def test_json_override_changes_budget_without_changing_fact_scope() -> None:
    resolver = RetrievalPolicyResolver.from_json(
        '{"writing_task":{"top_k":7,"max_content_chars":3500,"timeout_ms":900}}'
    )

    plan = resolver.resolve(
        RetrievalRequest(
            query_text="秦浩轩",
            consumer=RetrievalConsumerContext(consumer_type="writing_task"),
        )
    )

    assert plan.top_k == 7
    assert plan.max_content_chars == 3500
    assert plan.timeout_ms == 900


@pytest.mark.parametrize(
    "raw_json",
    [
        "[]",
        "{",
        '{"unknown_profile":{}}',
        '{"writing_task":{"top_k":0}}',
        '{"catalog":{"strategy":"vector"}}',
    ],
)
def test_invalid_policy_json_fails_with_visible_chinese_error(raw_json: str) -> None:
    with pytest.raises(ValueError, match="召回策略"):
        RetrievalPolicyResolver.from_json(raw_json)


def test_unregistered_configured_backend_blocks_app_startup(tmp_path: Path) -> None:
    settings = Settings(
        project_assets_dir=tmp_path,
        retrieval_default_relevance_strategy="vector",
    )

    with pytest.raises(ValueError, match="未注册的后端"):
        create_app(
            settings,
            knowledge_repository=InMemoryKnowledgeRepository(),
        )
