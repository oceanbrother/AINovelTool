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


class StyleOverrideCreate(BaseModel):
    """作者接受一段生成稿时提交的 (建议稿, 接受稿) 配对。

    只在「并入正文」那一刻记录 —— 那是唯一还能干净配对的时机，
    文字一旦落进章节，作者的修改就与整章混在一起、无法还原。
    """

    source: str = Field(pattern="^(continue|imitate|refine)$")
    suggested_text: str = Field(min_length=1, description="模型给出的原稿")
    accepted_text: str = Field(min_length=1, description="作者实际并入的版本")
    chapter_id: int | None = None
    # 该稿是否通过了自检门（仿写/精修有，续写没有 → None）。
    # 只在作者一字未改时才用得上：改过的稿子无条件内化。
    passed_check: bool | None = None


class StyleOverrideOut(BaseModel):
    id: int
    source: str
    edit_ratio: float          # 0 = 一字未改，1 = 完全重写
    internalized: bool         # 是否已把作者的版本存为文风样本
    created_at: datetime


class StyleExpandRequest(BaseModel):
    """从一段选中的样本出发，借其手法扩写贴合当前构思的新文字。"""

    idea: str = Field(min_length=4, description="作者当前的构思/场景方向")


class StyleExpandResponse(BaseModel):
    text: str
    ngram_overlap: float  # 与原样本的 8 字重叠率，复述检测（越低越好）
