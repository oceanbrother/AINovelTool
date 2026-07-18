from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db import Base


class LiteraryWork(Base):
    """A literary work. Only public-domain works should be admitted, which is
    enforced at ingest time (see scripts/seed_literary.py) — that whitelist is
    what keeps citations safe, not a prompt instruction."""

    __tablename__ = "literary_works"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    author: Mapped[str] = mapped_column(Text, nullable=False)
    era: Mapped[str | None] = mapped_column(Text)
    # 体裁/主题分类：诗歌/戏剧/散文/志怪文学；小说按主题：爱情/战争/现实/哲学/成长文学
    category: Mapped[str | None] = mapped_column(Text)
    is_public_domain: Mapped[bool] = mapped_column(Boolean, default=True)
    themes: Mapped[list] = mapped_column(JSONB, default=list)
    school: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LiteraryKnowledge(Base):
    """Retrievable literary knowledge grounded in a work.

    knowledge_type ∈ {作者背景, 主题解读, 公认名句, 句式}. The LLM may only cite
    from rows that exist here — it cannot invent authors, works, or lines."""

    __tablename__ = "literary_knowledge"

    id: Mapped[int] = mapped_column(primary_key=True)
    work_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("literary_works.id", ondelete="CASCADE"), index=True
    )
    knowledge_type: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
