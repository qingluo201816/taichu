"""读取并校验应用配置。"""

from pathlib import Path

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """太初运行配置。"""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    host: str = "127.0.0.1"
    port: int = 8000

    project_assets_dir: Path = Path("project_assets")


settings = Settings()
