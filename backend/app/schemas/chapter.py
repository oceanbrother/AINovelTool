from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ChapterCreate(BaseModel):
    title: str | None = None
    content: str = ""
    order_index: int = 0


class ChapterUpdate(BaseModel):
    title: str | None = None
    content: str | None = None
    summary: str | None = None
    order_index: int | None = None


class ChapterOut(ORMModel):
    id: int
    project_id: int
    order_index: int
    title: str | None
    content: str
    summary: str | None
    created_at: datetime
    updated_at: datetime
