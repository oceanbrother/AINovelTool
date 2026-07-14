from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Character(Base):
    __tablename__ = "characters"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # structured traits: {"性格": ..., "能力": ..., "口癖": ...}
    persona: Mapped[dict] = mapped_column(JSONB, default=dict)
    summary: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Relationship(Base):
    __tablename__ = "relationships"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    character_a_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("characters.id", ondelete="CASCADE")
    )
    character_b_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("characters.id", ondelete="CASCADE")
    )
    relation_type: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)
