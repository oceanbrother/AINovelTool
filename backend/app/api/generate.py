from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.db import AsyncSessionLocal, get_session
from app.models.chapter import Chapter
from app.schemas.generation import (
    BreakthroughRequest,
    BreakthroughResponse,
    ContinueRequest,
)
from app.services import generation

router = APIRouter(prefix="/projects/{project_id}/generate", tags=["generate"])


@router.post("/continue")
async def continue_writing(project_id: int, payload: ContinueRequest):
    """续写模式 — streams the continuation token-by-token over SSE.

    Opens its own DB session for the lifetime of the stream (the request-scoped
    dependency session would be closed before streaming finishes).
    """

    async def event_stream():
        async with AsyncSessionLocal() as db:
            chapter = await db.get(Chapter, payload.chapter_id)
            if chapter is None or chapter.project_id != project_id:
                yield {"event": "error", "data": "chapter not found"}
                return
            try:
                async for kind, data in generation.continue_chapter_stream(
                    db, chapter, payload.instruction
                ):
                    if kind == "clues":
                        # retrieval evidence, sent while the first LLM token is
                        # still in flight — the UI lights these up immediately
                        yield {
                            "event": "clues",
                            "data": json.dumps(
                                [
                                    {
                                        "source_type": c.source_type,
                                        "content": c.content,
                                        "score": c.score,
                                    }
                                    for c in data
                                ],
                                ensure_ascii=False,
                            ),
                        }
                    else:
                        yield {"event": "token", "data": data}
                yield {"event": "done", "data": ""}
            except Exception as exc:  # surface upstream errors to the client
                yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(event_stream())


@router.post("/breakthrough", response_model=BreakthroughResponse)
async def breakthrough(
    project_id: int,
    payload: BreakthroughRequest,
    db: AsyncSession = Depends(get_session),
):
    """破壁模式 — N divergent next-arc branches (non-streaming JSON)."""
    chapter = await db.get(Chapter, payload.chapter_id)
    if chapter is None or chapter.project_id != project_id:
        raise HTTPException(404, "chapter not found")
    branches, clues = await generation.breakthrough(
        db, chapter, payload.state, payload.num_branches
    )
    return BreakthroughResponse(branches=branches, clues=clues)
