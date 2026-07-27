from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class NarrativeUnit(Base):
    """A scene — the unit everything structural hangs off.

    Chapters exist already, but a chapter is one long text blob: there is no
    handle for "the scene where he finds the note", so nothing can point at a
    scene, order scenes, or say which scene pays off which setup. This table
    supplies that handle.

    Deliberately NOT mirroring `chapters` as chapter-level rows — that would
    duplicate a table that already works. Scenes reference their chapter
    directly, and `parent_id` is left for beat-level nesting later.
    """

    __tablename__ = "narrative_units"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chapters.id", ondelete="CASCADE")
    )
    parent_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("narrative_units.id", ondelete="CASCADE")
    )
    level: Mapped[str] = mapped_column(Text, nullable=False, default="scene")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    # what happened, plainly. The *function* summary ("why the author needed
    # this") is a separate axis and waits for the round that validates it.
    surface_summary: Mapped[str | None] = mapped_column(Text)
    scene_tag: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class NarrativePlan(Base):
    """A saved ScenePlan — the decisions the author made before writing.

    Until now a plan was generated, edited, posted back to the writer, and then
    dropped: every judgement the author made about a scene was thrown away the
    moment prose came out. That cost three things at once — nothing could be
    locked against regeneration, no long-form metric could be computed for want
    of a per-scene record, and no function label had anywhere to live.

    The plan itself is JSONB rather than columns: its shape is still moving,
    and nothing queries into individual fields — it is fetched whole, shown,
    edited, and handed to the writer.

    `locked_fields` is the point of the whole table. A field the author locked
    survives regeneration untouched; the generator may propose everything else,
    but not overwrite a decision that was already made.
    """

    __tablename__ = "narrative_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chapters.id", ondelete="SET NULL")
    )
    # set once the scene is actually written and accepted
    unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("narrative_units.id", ondelete="SET NULL")
    )
    # the prose this was planned from — keeps a plan interpretable months later
    fragment: Mapped[str | None] = mapped_column(Text)
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    # names of ScenePlan fields the author froze, e.g. ["goal", "must_not"]
    locked_fields: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list, server_default="[]"
    )
    review_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="pending"  # pending / approved / rejected
    )
    generation_status: Mapped[str] = mapped_column(
        Text, nullable=False, default="planned"  # planned / written / accepted
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
