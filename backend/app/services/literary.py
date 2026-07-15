"""Literary citation retrieval (v1.1, Feature A).

Goal: let an in-novel character *quote and discuss* real literature the way a
cultured person would — grounded in fact, never hallucinated. The LLM may only
surface rows that exist in literary_knowledge; the public-domain whitelist is
enforced at ingest, so retrieval can't leak a copyrighted or fabricated work.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embed_text
from app.models.literary import LiteraryKnowledge, LiteraryWork
from app.schemas.literary import LiteraryQuote


async def retrieve_quotes(
    db: AsyncSession, query: str, top_k: int = 5, category: str | None = None
) -> list[LiteraryQuote]:
    query_vec = await embed_text(query)
    distance = LiteraryKnowledge.embedding.cosine_distance(query_vec)
    stmt = (
        select(LiteraryKnowledge, LiteraryWork, distance.label("distance"))
        .join(LiteraryWork, LiteraryKnowledge.work_id == LiteraryWork.id)
        .where(LiteraryKnowledge.embedding.isnot(None))
        .where(LiteraryWork.is_public_domain.is_(True))
        .order_by(distance)
        .limit(top_k)
    )
    if category:
        stmt = stmt.where(LiteraryWork.category == category)
    rows = (await db.execute(stmt)).all()
    return [
        LiteraryQuote(
            work_title=work.title,
            author=work.author,
            era=work.era,
            category=work.category,
            knowledge_type=knowledge.knowledge_type,
            content=knowledge.content,
            score=round(1.0 - float(dist), 4),
        )
        for knowledge, work, dist in rows
    ]
