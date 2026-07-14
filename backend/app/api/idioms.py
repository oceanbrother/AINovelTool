from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.idiom import IdiomSuggestRequest, IdiomSuggestResponse
from app.services import idiom

router = APIRouter(prefix="/idioms", tags=["idioms"])


@router.post("/suggest", response_model=IdiomSuggestResponse)
async def suggest(
    payload: IdiomSuggestRequest, db: AsyncSession = Depends(get_session)
):
    """Feature B — recall candidate idioms by scene, LLM selects & explains from
    the recalled set only (no fabricated 成语)."""
    suggestions = await idiom.suggest_idioms(
        db, payload.scene, payload.top_k, payload.num_final
    )
    return IdiomSuggestResponse(scene=payload.scene, suggestions=suggestions)
