"""Embedding abstraction.

Two interchangeable backends behind one async `embed_texts` call:

  * "local"  -> sentence-transformers (default: BAAI/bge-m3, 1024 dims).
               Best Chinese semantic recall; the deliberate improvement over a
               multilingual MiniLM baseline.
  * "openai" -> any OpenAI-compatible /embeddings endpoint.

Whichever is chosen MUST output `settings.embedding_dim` dimensions, matching
the vector(N) columns in init_pgvector.sql.
"""
from __future__ import annotations

import asyncio
from functools import lru_cache

import httpx

from app.core.config import settings


# --- local (sentence-transformers) --------------------------------------------

@lru_cache
def _local_model():
    # Imported lazily so the API can boot without torch installed when using the
    # "openai" backend.
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(settings.embedding_model)


def _embed_local_sync(texts: list[str]) -> list[list[float]]:
    model = _local_model()
    vectors = model.encode(
        texts, normalize_embeddings=True, convert_to_numpy=True
    )
    return [v.tolist() for v in vectors]


# --- openai-compatible API ----------------------------------------------------

async def _embed_openai(texts: list[str]) -> list[list[float]]:
    headers = {"Authorization": f"Bearer {settings.embedding_api_key}"}
    payload = {"model": settings.embedding_model, "input": texts}
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.embedding_api_base}/embeddings",
            json=payload,
            headers=headers,
        )
        resp.raise_for_status()
        data = resp.json()["data"]
    # API may not preserve order guarantees uniformly; sort by index to be safe.
    data.sort(key=lambda d: d["index"])
    return [d["embedding"] for d in data]


# --- public API ---------------------------------------------------------------

async def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed a batch of texts -> list of vectors (each length embedding_dim)."""
    if not texts:
        return []
    if settings.embedding_backend == "openai":
        return await _embed_openai(texts)
    # Run the blocking model call off the event loop.
    return await asyncio.to_thread(_embed_local_sync, texts)


async def embed_text(text: str) -> list[float]:
    """Embed a single text -> one vector."""
    vectors = await embed_texts([text])
    return vectors[0]
