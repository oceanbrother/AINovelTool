"""Rolling summary service.

To keep long-novel context bounded, we maintain one running summary per project.
Recent chapters go into the prompt verbatim; everything older is compressed into
`rolling_summary`. After a chapter is finalized we fold it into the summary.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.models.chapter import Chapter
from app.models.rolling_summary import RollingSummary

_SUMMARY_SYSTEM = (
    "你是小说连载的剧情记录员。把【已有摘要】和【新章节】合并为一份不超过 400 字的"
    "滚动摘要，保留关键人物状态、已埋伏笔、未解冲突与世界观要点，删去细节描写。"
    "直接输出摘要正文，不要解释。"
)


async def get_or_create_summary(
    db: AsyncSession, project_id: int
) -> RollingSummary:
    existing = (
        await db.execute(
            select(RollingSummary).where(RollingSummary.project_id == project_id)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    summary = RollingSummary(project_id=project_id, content="")
    db.add(summary)
    await db.flush()
    return summary


async def fold_chapter(db: AsyncSession, chapter: Chapter) -> RollingSummary:
    """Merge a finalized chapter into the project's rolling summary."""
    summary = await get_or_create_summary(db, chapter.project_id)
    messages = [
        {"role": "system", "content": _SUMMARY_SYSTEM},
        {
            "role": "user",
            "content": (
                f"【已有摘要】\n{summary.content or '（暂无）'}\n\n"
                f"【新章节】{chapter.title or ''}\n{chapter.content}"
            ),
        },
    ]
    summary.content = await llm.complete(messages, temperature=0.3)
    summary.up_to_chapter_id = chapter.id
    await db.flush()
    return summary


async def recent_chapters_text(
    db: AsyncSession, project_id: int, window: int, before_order: int | None = None
) -> str:
    """Raw text of the most recent `window` chapters (for verbatim context)."""
    stmt = select(Chapter).where(Chapter.project_id == project_id)
    if before_order is not None:
        stmt = stmt.where(Chapter.order_index < before_order)
    stmt = stmt.order_by(Chapter.order_index.desc()).limit(window)
    rows = (await db.execute(stmt)).scalars().all()
    rows = list(reversed(rows))
    return "\n\n".join(f"【{c.title or '章节'}】\n{c.content}" for c in rows)
