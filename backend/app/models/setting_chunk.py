from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.config import settings
from app.db import Base


class SettingChunk(Base):
    """A retrievable chunk of project setting material.

    source_type ∈ {character, world, foreshadowing, style}; source_id points
    back at the originating row so re-embedding can target one source.
    """

    __tablename__ = "setting_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int | None] = mapped_column(BigInteger)
    # provenance for style samples: 'epub' (imported book), 'manual' (pasted),
    # '内化' (imitation draft that passed the self-check and was accepted) —
    # the continue channel prefers 内化 so the author's derived voice, not the
    # source material, anchors formal writing
    source_label: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim)
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
