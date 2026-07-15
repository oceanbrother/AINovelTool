from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.literary import LiteraryQuoteRequest, LiteraryQuoteResponse
from app.services import literary

router = APIRouter(prefix="/literary", tags=["literary"])


@router.post("/quotes", response_model=LiteraryQuoteResponse)
async def literary_quotes(
    payload: LiteraryQuoteRequest, db: AsyncSession = Depends(get_session)
):
    """Feature A — retrieve grounded, public-domain literary citations for a
    scene/theme. The LLM may only surface what exists in the library."""
    quotes = await literary.retrieve_quotes(
        db, payload.query, payload.top_k, payload.category
    )
    return LiteraryQuoteResponse(query=payload.query, quotes=quotes)
