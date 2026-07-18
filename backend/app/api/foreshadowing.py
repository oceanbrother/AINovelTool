from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.foreshadowing import Foreshadowing
from app.schemas.foreshadowing import (
    ForeshadowingCreate,
    ForeshadowingOut,
    ForeshadowingUpdate,
)
from app.services import indexing

router = APIRouter(
    prefix="/projects/{project_id}/foreshadowing", tags=["foreshadowing"]
)


async def _get_or_404(
    db: AsyncSession, project_id: int, foreshadowing_id: int
) -> Foreshadowing:
    obj = await db.get(Foreshadowing, foreshadowing_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "foreshadowing not found")
    return obj


@router.post("", response_model=ForeshadowingOut, status_code=201)
async def create_foreshadowing(
    project_id: int,
    payload: ForeshadowingCreate,
    db: AsyncSession = Depends(get_session),
):
    obj = Foreshadowing(project_id=project_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    # Index immediately so open threads surface during generation retrieval.
    await indexing.index_foreshadowing(db, obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=list[ForeshadowingOut])
async def list_foreshadowing(
    project_id: int,
    status: str | None = None,
    db: AsyncSession = Depends(get_session),
):
    stmt = (
        select(Foreshadowing)
        .where(Foreshadowing.project_id == project_id)
        .order_by(Foreshadowing.id)
    )
    if status:
        stmt = stmt.where(Foreshadowing.status == status)
    return (await db.execute(stmt)).scalars().all()


@router.patch("/{foreshadowing_id}", response_model=ForeshadowingOut)
async def update_foreshadowing(
    project_id: int,
    foreshadowing_id: int,
    payload: ForeshadowingUpdate,
    db: AsyncSession = Depends(get_session),
):
    obj = await _get_or_404(db, project_id, foreshadowing_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.flush()
    await indexing.index_foreshadowing(db, obj)  # re-embed (status is in the text)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{foreshadowing_id}", status_code=204)
async def delete_foreshadowing(
    project_id: int,
    foreshadowing_id: int,
    db: AsyncSession = Depends(get_session),
):
    obj = await _get_or_404(db, project_id, foreshadowing_id)
    await indexing.remove_chunks(db, "foreshadowing", obj.id)
    await db.delete(obj)
    await db.commit()
