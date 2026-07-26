from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CorpusParagraph(Base):
    """One paragraph of the reference corpus — the unit rhythm is measured in.

    Segments (~450 chars, ~8 paragraphs) turned out to be the wrong granularity
    for mode labelling: 54% of them mixed dialogue and narration, because a
    segment spans a whole scene beat and therefore contains every mode at once.
    Rhythm is the *alternation* between modes, so the unit has to be small
    enough to hold one mode — a paragraph, ~64 chars here.

    Derived from corpus_segments by splitting on newlines, so no re-segmentation
    (and no re-embedding) is needed; `segment_id` keeps the link back for
    scene-level joins.

    Three label columns on purpose: `mode_rule` is free and near-certain for
    dialogue (quotation marks), `mode_anchor` is the local classifier, and
    `mode_llm` is the judge model. Keeping them apart is what allows measuring
    one against another instead of trusting any single labeller.
    """

    __tablename__ = "corpus_paragraphs"

    id: Mapped[int] = mapped_column(primary_key=True)
    work: Mapped[str] = mapped_column(Text, nullable=False)
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # order within chapter
    segment_id: Mapped[int | None] = mapped_column(Integer)    # parent scene beat
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_len: Mapped[int] = mapped_column(Integer, nullable=False)

    is_dialogue: Mapped[bool | None] = mapped_column(Boolean)  # quotation-mark rule
    mode_rule: Mapped[str | None] = mapped_column(Text)        # 对话, when the rule fires
    mode_anchor: Mapped[str | None] = mapped_column(Text)      # services/mode.py
    mode_llm: Mapped[str | None] = mapped_column(Text)         # judge model

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
