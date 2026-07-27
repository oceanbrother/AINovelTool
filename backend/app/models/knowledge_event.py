from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class KnowledgeEvent(Base):
    """When someone's awareness of a fact changed.

    `story_facts` records what is known *now*. That is enough to stop a
    character saying what they cannot know, but it cannot answer the question
    the function labels turned out to need: had the reader met this before
    chapter N? A single current value has no history to consult.

    So awareness becomes an event log. A fact's level for a given holder at a
    given point in the story is the most recent event at or before that chapter;
    with no events, the columns on `story_facts` still apply, which keeps every
    existing row and the constraints derived from it working untouched.

    Author-controlled by design. The narrative-function draft is explicit that
    deciding *when* something may be known is the most consequential pacing
    power in a long work, and one a model should not quietly take: it will
    resolve tension early because a resolved scene feels complete.
    """

    __tablename__ = "knowledge_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    fact_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("story_facts.id", ondelete="CASCADE"), index=True
    )
    # 'reader' or 'character'; holder_id is set only for the latter
    holder_type: Mapped[str] = mapped_column(Text, nullable=False)
    holder_id: Mapped[int | None] = mapped_column(BigInteger)
    level: Mapped[str] = mapped_column(Text, nullable=False)
    # the chapter this takes effect from. NULL means "from the beginning",
    # which is how the pre-timeline columns on story_facts are interpreted.
    chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chapters.id", ondelete="CASCADE")
    )
    note: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
