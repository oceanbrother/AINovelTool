from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ProjectCreate(BaseModel):
    title: str
    description: str | None = None
    genre: str | None = "都市幻想"


class ProjectUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    genre: str | None = None


class ProjectOut(ORMModel):
    id: int
    title: str
    description: str | None
    genre: str | None
    created_at: datetime
    updated_at: datetime
