from __future__ import annotations

from pydantic import BaseModel


class RetrievedChunk(BaseModel):
    id: int
    source_type: str
    source_id: int | None
    content: str
    score: float  # cosine similarity, 0..1 (higher = closer)


class RetrieveRequest(BaseModel):
    query: str
    top_k: int | None = None
    source_types: list[str] | None = None  # filter, e.g. ["character", "world"]


class RetrieveResponse(BaseModel):
    query: str
    chunks: list[RetrievedChunk]
