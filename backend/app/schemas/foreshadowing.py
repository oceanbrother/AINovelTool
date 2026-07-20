from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ForeshadowingCreate(BaseModel):
    title: str
    content: str | None = None
    setup_chapter_id: int | None = None  # 埋设章


class ForeshadowingUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    status: str | None = None            # open / closed
    setup_chapter_id: int | None = None
    payoff_chapter_id: int | None = None  # 回收章


class ForeshadowingOut(ORMModel):
    id: int
    project_id: int
    title: str
    content: str | None
    status: str
    setup_chapter_id: int | None
    payoff_chapter_id: int | None
    created_at: datetime
