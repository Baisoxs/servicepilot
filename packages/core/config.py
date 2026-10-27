"""全局配置。

所有环境变量只在这里读一次，其他模块统一从这里拿：

from packages.core.config import get_settings

"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# 项目根目录：config.py -> core -> packages -> 项目根
ENV_FILE = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    """字段名小写，对应 .env 里的大写变量（pydantic 自动不区分大小写）。"""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- LLM ----
    llm_base_url: str = "https://api.deepseek.com/v1"
    llm_api_key: str = ""
    llm_model: str = "deepseek-chat"

    # ---- Postgres ----
    database_url: str = "postgresql+psycopg://servicepilot:servicepilot@localhost:5432/servicepilot"

    # ---- Redis ----
    redis_url: str = "redis://localhost:6379/0"

    # ---- MinIO / S3 ----
    minio_root_user: str = "minioadmin"
    minio_root_password: str = "minioadmin"
    minio_endpoint: str = "localhost:9000"
    minio_bucket: str = "servicepilot"

    # ---- App ----
    app_env: str = "local"
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    """单例：第一次调用读 .env，之后直接返回缓存。"""
    return Settings()
