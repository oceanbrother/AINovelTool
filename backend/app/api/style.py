from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embed_text
from app.db import get_session
from app.models.setting_chunk import SettingChunk
from app.schemas.style import StyleSampleCreate, StyleSampleList, StyleSampleOut
from app.services import scene

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
    vec = await embed_text(payload.content)
    anchors = await scene.anchor_vectors_public()
    obj = SettingChunk(
        project_id=project_id,
        source_type="style",
        source_id=None,
        source_label=payload.label,
        scene_tag=scene.classify_vector(vec, anchors),
        content=payload.content,
        embedding=vec,
    )
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=StyleSampleList)
async def list_style_samples(
    project_id: int,
    label: str | None = None,
    scene: str | None = None,
    offset: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_session),
):
    async def _facet(col):
        rows = (
            await db.execute(
                select(col, func.count())
                .where(
                    SettingChunk.project_id == project_id,
                    SettingChunk.source_type == "style",
                )
                .group_by(col)
            )
        ).all()
        return {str(k): n for k, n in rows if k is not None}

    by_label = await _facet(SettingChunk.source_label)
    by_scene = await _facet(SettingChunk.scene_tag)

    filtered = select(SettingChunk).where(
        SettingChunk.project_id == project_id,
        SettingChunk.source_type == "style",
    )
    if label:
        filtered = filtered.where(SettingChunk.source_label == label)
    if scene:
        filtered = filtered.where(SettingChunk.scene_tag == scene)

    total = (
        await db.execute(select(func.count()).select_from(filtered.subquery()))
    ).scalar_one()
    items = (
        await db.execute(
            filtered.order_by(SettingChunk.id.desc()).offset(offset).limit(limit)
        )
    ).scalars().all()

    return StyleSampleList(
        total=total, items=items, by_label=by_label, by_scene=by_scene
    )


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
