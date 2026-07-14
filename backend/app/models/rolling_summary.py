from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class RollingSummary(Base):
    __tablename__ = "rolling_summary"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("projects.id", ondelete="CASCADE"),
        unique=True,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, default="")
    up_to_chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chapters.id", ondelete="SET NULL")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
