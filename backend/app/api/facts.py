from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.knowledge_event import KnowledgeEvent
from app.models.story_fact import LEVELS, StoryFact
from app.schemas.knowledge import (
    KnowledgeEventCreate,
    KnowledgeEventOut,
    StoryFactCreate,
    StoryFactOut,
    StoryFactUpdate,
)

router = APIRouter(prefix="/projects/{project_id}/story-facts", tags=["knowledge"])


async def _get_or_404(db: AsyncSession, project_id: int, fact_id: int) -> StoryFact:
    obj = await db.get(StoryFact, fact_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "story fact not found")
    return obj


def _check_levels(levels: dict[str, str] | None) -> None:
    """Reject unknown awareness levels rather than storing them.

    A typo here would silently produce no constraint at all — the derivation
    only reacts to levels it recognises — so it has to fail loudly at the edge.
    """
    for character_id, level in (levels or {}).items():
        if level not in LEVELS:
            raise HTTPException(
                422, f"character {character_id}: 未知认知档位 '{level}'，"
                     f"可选 {'/'.join(LEVELS)}"
            )


@router.post("", response_model=StoryFactOut, status_code=201)
async def create_fact(
    project_id: int,
    payload: StoryFactCreate,
    db: AsyncSession = Depends(get_session),
):
    _check_levels(payload.character_levels)
    obj = StoryFact(project_id=project_id, **payload.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=list[StoryFactOut])
async def list_facts(project_id: int, db: AsyncSession = Depends(get_session)):
    return (
        await db.execute(
            select(StoryFact)
            .where(StoryFact.project_id == project_id)
            .order_by(StoryFact.id)
        )
    ).scalars().all()


@router.patch("/{fact_id}", response_model=StoryFactOut)
async def update_fact(
    project_id: int,
    fact_id: int,
    payload: StoryFactUpdate,
    db: AsyncSession = Depends(get_session),
):
    obj = await _get_or_404(db, project_id, fact_id)
    data = payload.model_dump(exclude_unset=True)
    _check_levels(data.get("character_levels"))
    for field, value in data.items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{fact_id}", status_code=204)
async def delete_fact(
    project_id: int, fact_id: int, db: AsyncSession = Depends(get_session)
):
    obj = await _get_or_404(db, project_id, fact_id)
    await db.delete(obj)
    await db.commit()


# --- 认知变化时间线 ------------------------------------------------------------
# 事实上的"信息释放时机表"：谁从第几章起知道了什么。设计文档把这个决定权明确
# 留给作者——大模型倾向于尽快回答问题，因为回答会让当前场景显得完整。


@router.post("/events", response_model=KnowledgeEventOut, status_code=201)
async def create_event(
    project_id: int,
    payload: KnowledgeEventCreate,
    db: AsyncSession = Depends(get_session),
):
    await _get_or_404(db, project_id, payload.fact_id)  # 事实必须属于本项目
    if payload.holder_type == "character" and payload.holder_id is None:
        raise HTTPException(422, "holder_type=character 时必须给出 holder_id")
    obj = KnowledgeEvent(project_id=project_id, **payload.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("/events", response_model=list[KnowledgeEventOut])
async def list_events(
    project_id: int,
    fact_id: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    stmt = select(KnowledgeEvent).where(KnowledgeEvent.project_id == project_id)
    if fact_id is not None:
        stmt = stmt.where(KnowledgeEvent.fact_id == fact_id)
    return (await db.execute(stmt.order_by(KnowledgeEvent.id))).scalars().all()


@router.delete("/events/{event_id}", status_code=204)
async def delete_event(
    project_id: int, event_id: int, db: AsyncSession = Depends(get_session)
):
    obj = await db.get(KnowledgeEvent, event_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "knowledge event not found")
    await db.delete(obj)
    await db.commit()
