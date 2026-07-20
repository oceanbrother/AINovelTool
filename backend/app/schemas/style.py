from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StyleSampleCreate(BaseModel):
    """一段文风样本 — 作者自己（或授权使用）的代表性段落。

    生成时按当前正文语境召回最相关的样本注入 prompt，让续写维持统一语感。
    """

    content: str = Field(min_length=20, description="建议 100-500 字的段落")


class StyleSampleOut(ORMModel):
    id: int
    content: str
    created_at: datetime
