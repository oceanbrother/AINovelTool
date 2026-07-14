from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class CharacterCreate(BaseModel):
    name: str
    persona: dict = Field(default_factory=dict)  # {"性格":..,"能力":..,"口癖":..}
    summary: str | None = None


class CharacterUpdate(BaseModel):
    name: str | None = None
    persona: dict | None = None
    summary: str | None = None


class CharacterOut(ORMModel):
    id: int
    project_id: int
    name: str
    persona: dict
    summary: str | None
    created_at: datetime
