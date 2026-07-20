from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embed_text
from app.db import get_session
from app.models.setting_chunk import SettingChunk
from app.schemas.style import StyleSampleCreate, StyleSampleOut

router = APIRouter(prefix="/projects/{project_id}/style-samples", tags=["style"])

# Style samples live directly in setting_chunks (source_type='style',
# source_id NULL) — same embedding + pgvector base, no extra table. The chunk
# id doubles as the sample id.


@router.post("", response_model=StyleSampleOut, status_code=201)
async def add_style_sample(
    project_id: int,
    payload: StyleSampleCreate,
    db: AsyncSession = Depends(get_session),
):
    obj = SettingChunk(
        project_id=project_id,
        source_type="style",
        source_id=None,
        content=payload.content,
        embedding=await embed_text(payload.content),
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=list[StyleSampleOut])
async def list_style_samples(
    project_id: int, db: AsyncSession = Depends(get_session)
):
    rows = (
        await db.execute(
            select(SettingChunk)
            .where(
                SettingChunk.project_id == project_id,
                SettingChunk.source_type == "style",
            )
            .order_by(SettingChunk.id)
        )
    ).scalars().all()
    return rows


@router.delete("/{sample_id}", status_code=204)
async def delete_style_sample(
    project_id: int, sample_id: int, db: AsyncSession = Depends(get_session)
):
    obj = await db.get(SettingChunk, sample_id)
    if (
        obj is None
        or obj.project_id != project_id
        or obj.source_type != "style"
    ):
        raise HTTPException(404, "style sample not found")
    await db.delete(obj)
    await db.commit()
