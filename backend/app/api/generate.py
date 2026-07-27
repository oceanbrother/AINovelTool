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
    ImitateRequest,
    ImitateResponse,
)
from app.schemas.refine import (
    RefineCandidatesRequest,
    RefineCandidatesResponse,
    RefinePlanRequest,
    RefinePlanResponse,
    RefineWriteRequest,
    RefineWriteResponse,
)
from app.services import generation, imitation, refine

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


@router.post("/imitate")
async def imitate(project_id: int, payload: ImitateRequest):
    """仿写模式 — generate → self-check (judge + plagiarism gate) → rewrite.

    Streams the self-check loop's progress over SSE (the loop takes 1–3 min):
      event: stage    — human-readable current phase
      event: attempt  — one scorecard as each draft is judged
      event: result   — final ImitateResponse JSON
    Every draft surfaced has already run the vetting loop; SSE just narrates it.
    """

    async def event_stream():
        async with AsyncSessionLocal() as db:
            chapter = await db.get(Chapter, payload.chapter_id)
            if chapter is None or chapter.project_id != project_id:
                yield {"event": "error", "data": "chapter not found"}
                return
            try:
                async for kind, data in imitation.imitate_stream(
                    db,
                    chapter,
                    payload.instruction,
                    payload.previous_draft,
                    payload.feedback,
                    payload.max_attempts,
                ):
                    if kind == "stage":
                        yield {"event": "stage", "data": data}
                    elif kind == "attempt":
                        yield {"event": "attempt", "data": data.model_dump_json()}
                    elif kind == "result":
                        text, attempts, clues = data
                        resp = ImitateResponse(
                            text=text, attempts=attempts, clues=clues
                        )
                        yield {"event": "result", "data": resp.model_dump_json()}
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


# --- 精修模式 (refine) ---------------------------------------------------------
# Three stages split by two author decision points (pick a candidate, edit the
# plan), so these are plain JSON calls; only the final /refine/write streams.

@router.post("/refine/candidates", response_model=RefineCandidatesResponse)
async def refine_candidates(
    project_id: int,
    payload: RefineCandidatesRequest,
    db: AsyncSession = Depends(get_session),
):
    """① N 条差异化候选走向 + 程序侧重复检测旗标。"""
    return await refine.compose_candidates(
        db,
        project_id,
        payload.fragment,
        payload.num_candidates,
        payload.top_k_settings,
    )


@router.post("/refine/plan", response_model=RefinePlanResponse)
async def refine_plan(
    project_id: int,
    payload: RefinePlanRequest,
    db: AsyncSession = Depends(get_session),
):
    """② 把选中候选扩成可编辑的场景计划（+ 场景标签），并落库。

    带 previous_plan_id 时，上一版里被作者锁定的字段原样继承——重新生成不会
    覆盖已经做过的判断。
    """
    return await refine.expand_plan(
        db,
        project_id,
        payload.fragment,
        payload.candidate,
        payload.top_k_settings,
        chapter_id=payload.chapter_id,
        previous_plan_id=payload.previous_plan_id,
    )


@router.post("/refine/write")
async def refine_write(project_id: int, payload: RefineWriteRequest):
    """③ 依场景计划生成 → 校验必须出现/不能发生 → 不达标带失败约束重写。

    Streams over SSE like /imitate (the loop takes minutes):
      event: stage    — current phase
      event: attempt  — one scorecard (constraint checks) per draft
      event: result   — final RefineWriteResponse JSON
    """

    async def event_stream():
        async with AsyncSessionLocal() as db:
            chapter = await db.get(Chapter, payload.chapter_id)
            if chapter is None or chapter.project_id != project_id:
                yield {"event": "error", "data": "chapter not found"}
                return
            try:
                async for kind, data in refine.refine_write_stream(
                    db,
                    chapter,
                    payload.plan,
                    payload.instruction,
                    payload.max_attempts,
                    two_stage=payload.two_stage,
                ):
                    if kind == "stage":
                        yield {"event": "stage", "data": data}
                    elif kind == "attempt":
                        yield {"event": "attempt", "data": data.model_dump_json()}
                    elif kind == "result":
                        text, attempts, clues = data
                        resp = RefineWriteResponse(
                            text=text, attempts=attempts, clues=clues
                        )
                        yield {"event": "result", "data": resp.model_dump_json()}
                yield {"event": "done", "data": ""}
            except Exception as exc:  # surface upstream errors to the client
                yield {"event": "error", "data": str(exc)}

    return EventSourceResponse(event_stream())
