"""独立向量基础设施配置的回归测试。"""

from taichu.config import Settings


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
