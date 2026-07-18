"""Literary citation retrieval (v1.1, Feature A).

Goal: let an in-novel character *quote and discuss* real literature the way a
cultured person would — grounded in fact, never hallucinated. The LLM may only
surface rows that exist in literary_knowledge; it cannot invent authors, works,
or lines.

Two sub-libraries, split by knowledge_type:

  金句库 — verbatim famous lines (公认名句). PUBLIC-DOMAIN WORKS ONLY: enforced
           at ingest (seed script) and re-enforced here at query time.
  素材库 — factual knowledge (写作背景/主题解读/内容概括/典故/公认评价…).
           Facts are not copyrightable, so works still under copyright may
           contribute here — the system can reference their plots and themes
           while structurally unable to emit their prose.
"""
from __future__ import annotations

from sqlalchemy import and_, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embed_text
from app.models.literary import LiteraryKnowledge, LiteraryWork
from app.schemas.literary import LiteraryQuote

QUOTE_TYPE = "公认名句"  # the 金句库 marker; everything else is 素材库


async def retrieve_quotes(
    db: AsyncSession,
    query: str,
    top_k: int = 5,
    category: str | None = None,
    library: str | None = None,
) -> list[LiteraryQuote]:
    query_vec = await embed_text(query)
    distance = LiteraryKnowledge.embedding.cosine_distance(query_vec)
    stmt = (
        select(LiteraryKnowledge, LiteraryWork, distance.label("distance"))
        .join(LiteraryWork, LiteraryKnowledge.work_id == LiteraryWork.id)
        .where(LiteraryKnowledge.embedding.isnot(None))
        # Safety net regardless of filters: a verbatim quote may never come
        # from a work still under copyright.
        .where(
            not_(
                and_(
                    LiteraryKnowledge.knowledge_type == QUOTE_TYPE,
                    LiteraryWork.is_public_domain.is_(False),
                )
            )
        )
        .order_by(distance)
        .limit(top_k)
    )
    if category:
        stmt = stmt.where(LiteraryWork.category == category)
    if library == "金句":
        stmt = stmt.where(LiteraryKnowledge.knowledge_type == QUOTE_TYPE)
    elif library == "素材":
        stmt = stmt.where(LiteraryKnowledge.knowledge_type != QUOTE_TYPE)
    rows = (await db.execute(stmt)).all()
    return [
        LiteraryQuote(
            work_title=work.title,
            author=work.author,
            era=work.era,
            category=work.category,
            library="金句" if knowledge.knowledge_type == QUOTE_TYPE else "素材",
            knowledge_type=knowledge.knowledge_type,
            content=knowledge.content,
            score=round(1.0 - float(dist), 4),
        )
        for knowledge, work, dist in rows
    ]
