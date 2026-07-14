from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.world import WorldSetting
from app.schemas.world import WorldCreate, WorldOut, WorldUpdate
from app.services import indexing

router = APIRouter(prefix="/projects/{project_id}/world", tags=["world"])


@router.post("", response_model=WorldOut, status_code=201)
async def create_world(
    project_id: int, payload: WorldCreate, db: AsyncSession = Depends(get_session)
):
    obj = WorldSetting(project_id=project_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    await indexing.index_world(db, obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=list[WorldOut])
async def list_world(project_id: int, db: AsyncSession = Depends(get_session)):
    rows = (
        await db.execute(
            select(WorldSetting)
            .where(WorldSetting.project_id == project_id)
            .order_by(WorldSetting.id)
        )
    ).scalars().all()
    return rows


@router.patch("/{world_id}", response_model=WorldOut)
async def update_world(
    project_id: int,
    world_id: int,
    payload: WorldUpdate,
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(WorldSetting, world_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "world setting not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.flush()
    await indexing.index_world(db, obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{world_id}", status_code=204)
async def delete_world(
    project_id: int, world_id: int, db: AsyncSession = Depends(get_session)
):
    obj = await db.get(WorldSetting, world_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "world setting not found")
    await db.delete(obj)
    await db.commit()
