"""Embedding abstraction.

Two interchangeable backends behind one async `embed_texts` call:

  * "local"  -> sentence-transformers (default: BAAI/bge-m3, 1024 dims).
               Best Chinese semantic recall; the deliberate improvement over a
               multilingual MiniLM baseline.
  * "openai" -> any OpenAI-compatible /embeddings endpoint.

Whichever is chosen MUST output `settings.embedding_dim` dimensions, matching
the vector(N) columns in init_pgvector.sql.

Concurrency design (local backend)
----------------------------------
CPU inference is the bottleneck: naive concurrent encodes each spawn a full
set of torch threads and thrash each other (measured 5.8x P95 degradation at
10 in-flight retrievals). Two layers fix this:

  1. micro-batching — concurrent embed calls are merged by a single worker
     into one batched model.encode() (a 10ms collection window); batching N
     short texts costs barely more than encoding one.
  2. LRU cache — repeated texts (retrieval queries especially) skip the model
     entirely.
"""
from __future__ import annotations

import asyncio
from collections import OrderedDict
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


class _MicroBatcher:
    """Serialises local encodes into one worker and batches whatever piles up.

    One encode runs at a time (no torch thread thrash); requests that arrive
    while a batch is being collected/encoded ride along in the next batch.
    """

    WINDOW_S = 0.002  # concurrent arrivals enqueue within the same few event-loop
    # ticks, so a tiny window batches them; keeps the solo-request tax negligible

    def __init__(self) -> None:
        self._queue: asyncio.Queue | None = None
        self._worker: asyncio.Task | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    async def embed(self, texts: list[str]) -> list[list[float]]:
        loop = asyncio.get_running_loop()
        if self._loop is not loop:  # fresh loop (tests, scripts): reset state
            self._loop = loop
            self._queue = asyncio.Queue()
            self._worker = None
        if self._worker is None or self._worker.done():
            self._worker = loop.create_task(self._run())
        future: asyncio.Future = loop.create_future()
        await self._queue.put((texts, future))
        return await future

    async def _run(self) -> None:
        while True:
            batch = [await self._queue.get()]
            await asyncio.sleep(self.WINDOW_S)
            while not self._queue.empty():
                batch.append(self._queue.get_nowait())
            flat = [t for texts, _f in batch for t in texts]
            try:
                vectors = await asyncio.to_thread(_embed_local_sync, flat)
                offset = 0
                for texts, future in batch:
                    if not future.done():
                        future.set_result(vectors[offset : offset + len(texts)])
                    offset += len(texts)
            except Exception as exc:  # propagate to every waiter in the batch
                for _texts, future in batch:
                    if not future.done():
                        future.set_exception(exc)


_batcher = _MicroBatcher()

# --- query cache ---------------------------------------------------------------

_CACHE_MAX = 2048  # ~2048 * 1024 floats * 8B ≈ 16MB, worth it for repeat queries
_cache: OrderedDict[str, list[float]] = OrderedDict()


def _cache_get(text: str) -> list[float] | None:
    vec = _cache.get(text)
    if vec is not None:
        _cache.move_to_end(text)
    return vec


def _cache_put(text: str, vec: list[float]) -> None:
    _cache[text] = vec
    _cache.move_to_end(text)
    while len(_cache) > _CACHE_MAX:
        _cache.popitem(last=False)


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

    # cache hits skip the model; misses ride the micro-batcher together
    misses = list({t for t in texts if _cache_get(t) is None})
    if misses:
        vectors = await _batcher.embed(misses)
        for text, vec in zip(misses, vectors):
            _cache_put(text, vec)
    return [_cache_get(t) for t in texts]


async def embed_text(text: str) -> list[float]:
    """Embed a single text -> one vector."""
    vectors = await embed_texts([text])
    return vectors[0]
