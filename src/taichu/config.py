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

    mongodb_home: Path | None = None
    mongodb_data_dir: Path | None = None
    mongodb_log_dir: Path | None = None
    mongodb_uri: str = "mongodb://127.0.0.1:27017"
    mongodb_database: str = "taichu"


settings = Settings()
