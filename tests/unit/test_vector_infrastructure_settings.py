"""独立向量基础设施配置的回归测试。"""

from pathlib import Path

from taichu.config import Settings
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


def test_vector_infrastructure_defaults_remain_independent_from_production_retrieval() -> None:
    settings = Settings.model_construct()

    assert settings.retrieval_default_relevance_strategy == "mongo_lexical"
    assert settings.qdrant_url == "http://127.0.0.1:6333"
    assert settings.qdrant_collection == "taichu_knowledge_vectors"
    assert settings.qdrant_api_key.get_secret_value() == ""
    assert settings.embedding_base_url == "http://127.0.0.1:8011/v1"
    assert settings.embedding_model_id == "Qwen3-Embedding-4B-Q4_K_M"
    assert settings.embedding_dimensions == 2560
    assert settings.embedding_request_timeout_seconds == 120
    assert settings.vector_document_batch_size == 16
    assert settings.vector_embedding_input_char_budget == 24_000
    assert settings.vector_query_char_budget == 12_000
    assert settings.vector_candidate_multiplier == 4
    assert settings.vector_score_threshold == 0.50
    assert settings.vector_coverage_bonus == 0.02


def test_vector_backend_is_registered_only_in_retrieval_evaluation_runtime(
    tmp_path: Path,
) -> None:
    application = create_app(
        app_settings=Settings(project_assets_dir=tmp_path),
        knowledge_repository=InMemoryKnowledgeRepository(),
    )

    production_backends = application.state.retrieval_service._backends
    evaluation_backends = application.state.retrieval_evaluation_runtime._backends

    assert set(production_backends) == {"mongo_lexical"}
    assert set(evaluation_backends) == {"mongo_lexical", "knowledge_vector"}
    assert application.state.retrieval_service is not (
        application.state.retrieval_evaluation_runtime
    )
