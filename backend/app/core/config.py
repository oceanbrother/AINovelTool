"""Central configuration, loaded from environment / .env.

Everything tunable lives here so the rest of the code never reads os.environ
directly. See .env.example for the full list.
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- App ---
    app_name: str = "AI Novel Assistant"
    debug: bool = False

    # --- Database ---
    # Async SQLAlchemy URL. docker-compose provides a matching default.
    database_url: str = (
        "postgresql+asyncpg://novel:novel@localhost:5433/ainovel"
    )

    # --- Embedding ---
    # backend: "local" (sentence-transformers) or "openai" (compatible API)
    embedding_backend: str = "local"
    embedding_model: str = "BAAI/bge-m3"
    embedding_dim: int = 1024  # MUST match vector(N) in init_pgvector.sql
    # used only when embedding_backend == "openai"
    embedding_api_base: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""

    # --- LLM (OpenAI-compatible) ---
    llm_api_base: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_temperature: float = 0.8
    llm_max_tokens: int = 2048
    # judge for the imitation self-check loop — deliberately a DIFFERENT model
    # from the generator to avoid LLM self-preference bias
    llm_judge_model: str = "deepseek-reasoner"

    # --- Retrieval ---
    retrieval_top_k: int = 6
    retrieval_min_score: float = 0.30  # cosine similarity floor (0..1)

    # --- Generation ---
    # how many recent chapters of raw text to keep in context (rolling summary
    # covers everything before that)
    recent_chapters_window: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
