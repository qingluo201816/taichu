"""读取并校验应用配置。"""

from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """太初运行配置。"""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    rightcode_api_key: SecretStr = SecretStr("")
    rightcode_responses_base_url: str = "https://www.right.codes/codex/v1"
    rightcode_claude_sale_base_url: str = "https://right.codes/claude-sale"
    rightcode_deepseek_anthropic_base_url: str = (
        "https://right.codes/deepseek/anthropic"
    )
    rightcode_default_model_id: str = "deepseek-v4-pro"
    rightcode_request_timeout_seconds: float = 180
    rightcode_max_retries: int = 2
    rightcode_model_prices_json: str = "{}"
    agent_model_roles_json: str = "{}"

    host: str = "127.0.0.1"
    port: int = 8000

    project_assets_dir: Path = Path("project_assets")
    evaluation_datasets_dir: Path = Path("tests/fixtures/evaluations")
    evaluation_judge_model: str = ""

    retrieval_policies_json: str = "{}"
    retrieval_default_relevance_strategy: str = "mongo_lexical"

    qdrant_url: str = "http://127.0.0.1:6333"
    qdrant_collection: str = "taichu_knowledge_vectors"
    qdrant_api_key: SecretStr = SecretStr("")

    embedding_base_url: str = "http://127.0.0.1:8011/v1"
    embedding_model_id: str = "Qwen3-Embedding-4B-Q4_K_M"
    embedding_dimensions: int = 2560
    embedding_request_timeout_seconds: float = 120
    embedding_max_input_tokens: int = 8192

    vector_document_batch_size: int = 16
    vector_embedding_input_char_budget: int = 24_000
    vector_query_char_budget: int = 12_000
    vector_candidate_multiplier: int = 4
    vector_score_threshold: float = 0.50
    vector_coverage_bonus: float = 0.02

    general_agent_related_memory_top_k: int = 12
    general_agent_related_memory_char_budget: int = 12_000
    general_agent_working_memory_char_budget: int = 24_000
    general_agent_memory_age_decay_days: int = 30
    general_agent_memory_minimum_relevance: float = 0.01
    general_agent_context_char_budget: int = 180_000
    general_agent_process_history_limit: int = 10
    general_agent_process_history_char_budget: int = 24_000
    general_agent_node_summary_char_budget: int = 32_000
    general_agent_plan_summary_char_budget: int = 24_000
    general_agent_message_compaction_threshold: int = 20
    general_agent_node_output_compaction_threshold: int = 48_000
    general_agent_capability_catalog_char_budget: int = 80_000

    mongodb_home: Path | None = None
    mongodb_data_dir: Path | None = None
    mongodb_log_dir: Path | None = None
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_database: str = "taichu"


settings = Settings()
