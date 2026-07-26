from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StyleOverride(Base):
    """One (what the tool suggested, what the author kept) pair.

    Every time the author rewrites a suggestion before merging it, that edit is
    a statement about their own voice — and it is *behavioural* data, which
    beats asking an author to describe their style (self-reports are usually
    wrong). Accumulated, these pairs define a voice by the author's choices
    rather than by imitation of a reference book.

    The pairing only exists because the draft box is editable BEFORE the merge.
    Once text lands in the chapter, the author's edits blend into the whole and
    "what was suggested" versus "what was kept" becomes unrecoverable — which is
    exactly what the old read-only draft box lost.

    Texture deltas are computed on write via services/rhythm.texture() (pure,
    zero LLM) so analysis never has to recompute them.

    IMPORTANT: these numbers must never be written into a generation prompt.
    Injecting measured statistics as instructions was tested and measurably hurt
    output (rhythm ablation: distance 1.219 vs 0.619, style 3.25 vs 4.65). They
    are legitimate for choosing between candidates after the fact, and for
    surfacing the author's own accepted prose as few-shot examples.
    """

    __tablename__ = "style_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    chapter_id: Mapped[int | None] = mapped_column(BigInteger)
    # which tool produced the suggestion: continue / imitate / refine
    source: Mapped[str] = mapped_column(Text, nullable=False)

    suggested_text: Mapped[str] = mapped_column(Text, nullable=False)
    accepted_text: Mapped[str] = mapped_column(Text, nullable=False)
    # 0.0 = merged verbatim, 1.0 = rewritten from scratch (difflib ratio based)
    edit_ratio: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # accepted − suggested, per texture metric. Sign carries the preference:
    # negative avg_sent_len means the author shortens what the model writes.
    d_dialogue_ratio: Mapped[float | None] = mapped_column(Float)
    d_short_sent_ratio: Mapped[float | None] = mapped_column(Float)
    d_avg_sent_len: Mapped[float | None] = mapped_column(Float)
    d_punct_density: Mapped[float | None] = mapped_column(Float)
    d_avg_para_len: Mapped[float | None] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
