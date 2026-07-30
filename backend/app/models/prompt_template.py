from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PromptTemplate(Base):
    """An author's override of one generation prompt.

    Only overrides live here — the defaults stay in the service modules, which
    keeps a fresh database working and lets an upgrade change a default without
    silently rewriting what the author edited. `list_all` in
    `services/prompts.py` joins the two.

    Deliberately NOT a place for the three measurement prompts (constraint
    verification, style judging, function labelling). Every number this project
    has recorded — 约束兑现 59%→93%, kappa 0.310, 两阶段 88.0% vs 72.6% — was
    produced with those exact strings. Letting them drift would make the
    recorded numbers incomparable with no way to notice. The lock is structural,
    not advisory: `verify_draft` / `judge_draft` / the labellers take no DB
    session, so there is no code path that could read an override.
    """

    __tablename__ = "prompt_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    # slot key declared in services/prompts.py, e.g. "refine.plan"
    key: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    # bumped on every save, so the UI can show "改过 3 次" and a future eval can
    # record which revision produced a given draft
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # the default this edit was branched from. If a later release changes the
    # code default, `list_all` compares against this and flags the slot as
    # stale — the author's edit is preserved, but they get told it is now
    # sitting on top of an older base.
    based_on: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
