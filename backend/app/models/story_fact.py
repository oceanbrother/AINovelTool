from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Awareness levels, per the narrative-function design's knowledge-state axis.
# believes_false matters as much as the others: a character actively holding a
# wrong belief constrains what they may say just as tightly as ignorance does.
LEVELS = ("unknown", "suspects", "knows", "believes_false")


class StoryFact(Base):
    """One story fact, plus who currently knows it.

    The reader's awareness is kept separate from every character's on purpose —
    that gap IS suspense. A reader who knows what the protagonist does not is
    dramatic irony; collapse the two into one "is this revealed yet" flag and
    the distinction disappears, which is what `foreshadowing.status` does today.

    Character awareness lives in JSONB keyed by character id rather than in a
    join table: the row count is small (dozens of facts), the shape matches the
    existing `characters.persona` precedent, and it keeps the whole state of a
    fact readable in a single row.

    Only characters the author explicitly registers appear in character_levels.
    Absence means "not modelled", not "ignorant" — otherwise every fact would
    generate a constraint for every character in the book.
    """

    __tablename__ = "story_facts"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    # the fact stated plainly, as it would read if someone said it out loud —
    # it gets quoted verbatim into the constraints derived from it
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    # whether it actually holds in the story world. False = a lie or a red
    # herring that some characters nonetheless believe.
    is_true: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    reader_level: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    # {"<character_id>": "unknown|suspects|knows|believes_false"}
    character_levels: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}"
    )
    # an unpaid-off thread is live tension, which is what makes its fact the
    # most spoiler-sensitive — used to prioritise which constraints survive the cap
    foreshadowing_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("foreshadowing.id", ondelete="SET NULL")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
