from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Base for response models read straight from ORM objects."""

    model_config = ConfigDict(from_attributes=True)
