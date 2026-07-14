"""Indexing service — turn structured settings into embedded setting_chunks.

Whenever a character / world setting / foreshadowing is created or edited, we
(re)build its searchable chunk(s) so the RAG layer can retrieve it. Keeping the
chunk text human-readable also makes the retrieval recall harness auditable.
"""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embed_texts
from app.models.character import Character
from app.models.foreshadowing import Foreshadowing
from app.models.setting_chunk import SettingChunk
from app.models.world import WorldSetting


def _character_text(c: Character) -> str:
    parts = [f"角色：{c.name}"]
    for key, val in (c.persona or {}).items():
        parts.append(f"{key}：{val}")
    if c.summary:
        parts.append(f"简介：{c.summary}")
    return "；".join(parts)


def _world_text(w: WorldSetting) -> str:
    return f"世界观设定（{w.category}）{w.title}：{w.content}"


def _foreshadowing_text(f: Foreshadowing) -> str:
    return f"伏笔：{f.title}。{f.content or ''}（状态：{f.status}）"


async def _replace_chunks(
    db: AsyncSession,
    project_id: int,
    source_type: str,
    source_id: int,
    texts: list[str],
) -> None:
    """Delete existing chunks for a source and insert freshly embedded ones."""
    await db.execute(
        delete(SettingChunk).where(
            SettingChunk.source_type == source_type,
            SettingChunk.source_id == source_id,
        )
    )
    vectors = await embed_texts(texts)
    for text, vec in zip(texts, vectors):
        db.add(
            SettingChunk(
                project_id=project_id,
                source_type=source_type,
                source_id=source_id,
                content=text,
                embedding=vec,
            )
        )
    await db.flush()


async def index_character(db: AsyncSession, c: Character) -> None:
    await _replace_chunks(db, c.project_id, "character", c.id, [_character_text(c)])


async def index_world(db: AsyncSession, w: WorldSetting) -> None:
    await _replace_chunks(db, w.project_id, "world", w.id, [_world_text(w)])


async def index_foreshadowing(db: AsyncSession, f: Foreshadowing) -> None:
    await _replace_chunks(
        db, f.project_id, "foreshadowing", f.id, [_foreshadowing_text(f)]
    )
