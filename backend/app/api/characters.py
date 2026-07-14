from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.character import Character
from app.schemas.character import CharacterCreate, CharacterOut, CharacterUpdate
from app.services import indexing

router = APIRouter(prefix="/projects/{project_id}/characters", tags=["characters"])


@router.post("", response_model=CharacterOut, status_code=201)
async def create_character(
    project_id: int,
    payload: CharacterCreate,
    db: AsyncSession = Depends(get_session),
):
    obj = Character(project_id=project_id, **payload.model_dump())
    db.add(obj)
    await db.flush()
    # Index immediately so the new character is retrievable for generation.
    await indexing.index_character(db, obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=list[CharacterOut])
async def list_characters(
    project_id: int, db: AsyncSession = Depends(get_session)
):
    rows = (
        await db.execute(
            select(Character)
            .where(Character.project_id == project_id)
            .order_by(Character.id)
        )
    ).scalars().all()
    return rows


@router.patch("/{character_id}", response_model=CharacterOut)
async def update_character(
    project_id: int,
    character_id: int,
    payload: CharacterUpdate,
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Character, character_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "character not found")
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.flush()
    await indexing.index_character(db, obj)  # re-embed on edit
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{character_id}", status_code=204)
async def delete_character(
    project_id: int,
    character_id: int,
    db: AsyncSession = Depends(get_session),
):
    obj = await db.get(Character, character_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "character not found")
    await db.delete(obj)
    await db.commit()
