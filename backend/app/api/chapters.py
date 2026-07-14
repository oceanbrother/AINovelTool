from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.chapter import Chapter
from app.schemas.chapter import ChapterCreate, ChapterOut, ChapterUpdate
from app.services import summary

router = APIRouter(prefix="/projects/{project_id}/chapters", tags=["chapters"])


async def _get_or_404(db: AsyncSession, project_id: int, chapter_id: int) -> Chapter:
    obj = await db.get(Chapter, chapter_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "chapter not found")
    return obj


@router.post("", response_model=ChapterOut, status_code=201)
async def create_chapter(
    project_id: int, payload: ChapterCreate, db: AsyncSession = Depends(get_session)
):
    obj = Chapter(project_id=project_id, **payload.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=list[ChapterOut])
async def list_chapters(project_id: int, db: AsyncSession = Depends(get_session)):
    rows = (
        await db.execute(
            select(Chapter)
            .where(Chapter.project_id == project_id)
            .order_by(Chapter.order_index, Chapter.id)
        )
    ).scalars().all()
    return rows


@router.get("/{chapter_id}", response_model=ChapterOut)
async def get_chapter(
    project_id: int, chapter_id: int, db: AsyncSession = Depends(get_session)
):
    return await _get_or_404(db, project_id, chapter_id)


@router.patch("/{chapter_id}", response_model=ChapterOut)
async def update_chapter(
    project_id: int,
    chapter_id: int,
    payload: ChapterUpdate,
    db: AsyncSession = Depends(get_session),
):
    obj = await _get_or_404(db, project_id, chapter_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.post("/{chapter_id}/fold", response_model=ChapterOut)
async def fold_chapter(
    project_id: int, chapter_id: int, db: AsyncSession = Depends(get_session)
):
    """Finalize a chapter: fold its content into the project rolling summary."""
    obj = await _get_or_404(db, project_id, chapter_id)
    await summary.fold_chapter(db, obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{chapter_id}", status_code=204)
async def delete_chapter(
    project_id: int, chapter_id: int, db: AsyncSession = Depends(get_session)
):
    obj = await _get_or_404(db, project_id, chapter_id)
    await db.delete(obj)
    await db.commit()
