from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Foreshadowing(Base):
    __tablename__ = "foreshadowing"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="open")  # open / closed
    setup_chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chapters.id", ondelete="SET NULL")
    )
    payoff_chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chapters.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
