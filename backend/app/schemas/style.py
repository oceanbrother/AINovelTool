from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class StyleSampleCreate(BaseModel):
    """一段文风样本 — 作者自己（或授权使用）的代表性段落。

    生成时按当前正文语境召回最相关的样本注入 prompt，让续写维持统一语感。
    """

    content: str = Field(min_length=20, description="建议 100-500 字的段落")
    # 来源标记：manual（手贴）/ 内化（仿写过检稿并入正文时自动存入）。
    # epub 由导入脚本写入，不经此接口。
    label: str = Field(default="manual", pattern="^(manual|内化)$")


class StyleSampleOut(ORMModel):
    id: int
    content: str
    source_label: str | None
    scene_tag: str | None
    created_at: datetime


class StyleSampleList(BaseModel):
    total: int                       # rows matching the current filter
    items: list[StyleSampleOut]      # this page
    by_label: dict[str, int]         # project-wide facet counts (unfiltered)
    by_scene: dict[str, int]
