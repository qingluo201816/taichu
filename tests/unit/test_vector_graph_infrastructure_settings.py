"""Milvus Vector Graph RAG 配置与生产注册回归测试。"""

from pathlib import Path

from taichu.config import Settings
from taichu.main import create_app
from tests.fakes import InMemoryKnowledgeRepository


def test_vector_graph_defaults_use_milvus_and_local_embedding() -> None:
    settings = Settings.model_construct()

    assert settings.milvus_uri == "http://127.0.0.1:19530"
    assert settings.milvus_collection_prefix == "taichu_story"
    assert settings.milvus_hnsw_m == 24
    assert settings.milvus_hnsw_ef_construction == 300
    assert settings.milvus_hnsw_ef_search == 150
    assert settings.milvus_rrf_k == 60
    assert settings.embedding_base_url == "http://127.0.0.1:8011/v1"
    assert settings.embedding_model_id == "Qwen3-Embedding-4B-Q4_K_M"
    assert settings.embedding_dimensions == 2560
    assert settings.vector_graph_manuscript_chunk_size == 1_000
    assert settings.vector_graph_manuscript_chunk_overlap == 200
    assert settings.vector_graph_expansion_degree == 2
    assert settings.vector_graph_relation_number_threshold == 60
    assert settings.vector_graph_expansion_max_seed_entities == 3
    assert settings.vector_graph_expansion_initial_relations_per_entity == 20
    assert settings.vector_graph_expansion_initial_beam_width == 20
    assert settings.vector_graph_expansion_max_entities_per_hop == 12
    assert settings.vector_graph_expansion_relations_per_entity == 8
    assert settings.vector_graph_expansion_hub_relations_per_entity == 5
    assert settings.vector_graph_expansion_hub_degree_threshold == 100
    assert settings.vector_graph_expansion_beam_width == 20
    assert settings.vector_graph_ann_top_k == 30
    assert settings.vector_graph_reranker_top_k == 10
    assert settings.reranker_model_id == "BAAI/bge-reranker-v2-m3"
    assert settings.vector_graph_llm_model == "deepseek-v4-pro"


def test_vector_graph_service_is_registered_in_production_capabilities(
    tmp_path: Path,
) -> None:
    application = create_app(
        app_settings=Settings(project_assets_dir=tmp_path),
        knowledge_repository=InMemoryKnowledgeRepository(),
    )

    assert application.state.vector_graph_rag_service is not None
    assert application.state.vector_graph_backend is not None
    assert (
        application.state.vector_graph_backend._milvus._llm._gateway
        is application.state.llm_gateway
    )
    assert (
        application.state.vector_graph_backend._milvus._llm.model_id
        == "deepseek-v4-pro"
    )
    assert application.state.vector_graph_backend.candidate_top_k == 30
    assert application.state.vector_graph_backend.final_top_k == 10
    assert (
        application.state.vector_graph_backend._milvus._settings.relation_number_threshold
        == 60
    )
    expansion = application.state.vector_graph_backend._milvus._controlled_expansion
    assert expansion.initial_relations_per_entity == 20
    assert expansion.max_hop == 2
    assert expansion.max_total_relations == 60
    manifest = application.state.tool_registry.get_manifest("retrieve_story_context")
    assert manifest.required_capabilities == frozenset({"vector_graph_rag_service"})
