from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class CorpusSegment(Base):
    """An ordered segment of a reference corpus, for RHYTHM ANALYSIS only.

    Deliberately decoupled from `setting_chunks`: that table serves *retrieval*
    (order-free, evenly sampled, deduped), which destroys adjacency — the very
    thing rhythm modelling needs. Here the contract is the opposite: segments
    are contiguous and ordered by (work, chapter_no, seq), nothing is sampled
    away, and no embedding is stored because sequence statistics don't need
    vectors.

    Corpus text is local-only private data (see .gitignore: *.epub, style_data/).
    What may leave this machine are aggregate statistics, never the prose.
    """

    __tablename__ = "corpus_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    work: Mapped[str] = mapped_column(Text, nullable=False)
    chapter_no: Mapped[int] = mapped_column(Integer, nullable=False)  # spine order
    chapter_title: Mapped[str | None] = mapped_column(Text)
    seq: Mapped[int] = mapped_column(Integer, nullable=False)  # order within chapter
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_len: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- texture layer (services/rhythm.py — pure program, zero LLM) ---
    dialogue_ratio: Mapped[float | None] = mapped_column(Float)
    short_sent_ratio: Mapped[float | None] = mapped_column(Float)
    avg_sent_len: Mapped[float | None] = mapped_column(Float)
    punct_density: Mapped[float | None] = mapped_column(Float)
    avg_para_len: Mapped[float | None] = mapped_column(Float)

    # --- tag layer (two independent labellers, so they can be cross-checked) ---
    scene_tag_anchor: Mapped[str | None] = mapped_column(Text)  # services/scene.py
    scene_tag_llm: Mapped[str | None] = mapped_column(Text)     # judge model
    func_tag: Mapped[str | None] = mapped_column(Text)          # 转折/揭示/承接/铺垫

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
