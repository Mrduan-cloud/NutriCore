"""全局配置 — 12-Factor 风格，通过 .env / 环境变量加载。

约定：
- 所有秘密走环境变量 / .env，永不进仓库
- 配置默认值适配本地开发；生产部署务必覆盖 jwt_secret_key / mysql_password 等
"""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # ============ App ============
    app_name: str = "NutriCore"
    app_env: str = Field("dev", description="dev / staging / prod")
    log_level: str = "INFO"
    log_json: bool = Field(False, description="生产建议开启 JSON 结构化日志")
    cors_origins: list[str] = ["*"]

    # ============ Security ============
    jwt_secret_key: str = Field("change-me-in-prod-please", min_length=8)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24
    api_key_header: str = "X-API-Key"

    # ============ LLM (vLLM 私有化) ============
    # 默认：2× RTX 4090 + Qwen2.5-32B-Instruct-AWQ + Tensor Parallel(TP=2)
    # 启动命令见 docs/DEPLOYMENT.md §2.5
    llm_base_url: str = "http://vllm:8001/v1"
    llm_api_key: str = "EMPTY"
    llm_model: str = "Qwen/Qwen2.5-32B-Instruct-AWQ"
    llm_timeout: int = 120
    llm_max_retries: int = 3
    llm_temperature: float = 0.3

    # ============ Embedding & Reranker ============
    embedding_model: str = "BAAI/bge-large-zh-v1.5"
    reranker_model: str = "BAAI/bge-reranker-large"
    embedding_dim: int = 1024  # bge-large-zh = 1024
    model_cache_dir: str = "/app/.cache/models"

    # ============ Milvus ============
    milvus_host: str = "milvus"
    milvus_port: int = 19530
    milvus_user: str = ""
    milvus_password: str = ""
    milvus_collection_food: str = "food_kb"
    milvus_collection_guide: str = "dietary_guide_kb"

    # ============ MySQL ============
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "nutricore"
    mysql_password: str = "changeme"
    mysql_db: str = "nutricore"

    @property
    def mysql_dsn(self) -> str:
        return (
            f"mysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4"
        )

    # ============ Redis ============
    redis_url: str = "redis://redis:6379/0"

    # ============ MinIO ============
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "nutricore"
    minio_secure: bool = False

    # ============ Dify (Data Insight) ============
    dify_api_base: str = "http://dify-api:8080/v1"
    dify_api_key: str = ""
    dify_workflow_id: str = "nl2sql_insight"

    # ============ Vanna.ai ============
    vanna_api_key: str = ""
    vanna_model: str = "nutricore-sql"

    # ============ Observability ============
    metrics_enabled: bool = True
    metrics_path: str = "/metrics"
    sentry_dsn: str = ""

    @property
    def is_prod(self) -> bool:
        return self.app_env == "prod"


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
