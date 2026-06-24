"""配置管理：所有配置从 .env 文件和环境变量读取。"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

    # LLM
    llm_provider: str = "deepseek"
    deepseek_api_key: str = ""
    deepseek_api_base: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    # Server
    host: str = "127.0.0.1"
    port: int = 8000

    # Storage
    data_dir: str = "data"


settings = Settings()
