from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.retrieval import RetrieveRequest, RetrieveResponse
from app.services import retrieval

router = APIRouter(prefix="/projects/{project_id}/retrieve", tags=["retrieval"])


@router.post("", response_model=RetrieveResponse)
async def retrieve(
    project_id: int,
    payload: RetrieveRequest,
    db: AsyncSession = Depends(get_session),
):
    """Inspect what the RAG layer would feed the generator for a query.

    Useful on its own and for the retrieval-recall eval harness."""
    chunks = await retrieval.retrieve_settings(
        db,
        project_id,
        payload.query,
        top_k=payload.top_k,
        source_types=payload.source_types,
    )
    return RetrieveResponse(query=payload.query, chunks=chunks)
