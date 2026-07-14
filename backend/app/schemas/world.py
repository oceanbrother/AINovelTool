from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class WorldCreate(BaseModel):
    category: str  # 规则 / 势力 / 地点
    title: str
    content: str


class WorldUpdate(BaseModel):
    category: str | None = None
    title: str | None = None
    content: str | None = None


class WorldOut(ORMModel):
    id: int
    project_id: int
    category: str
    title: str
    content: str
    created_at: datetime
