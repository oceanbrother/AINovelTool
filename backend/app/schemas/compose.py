from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievedChunk


class ComposeOutlineRequest(BaseModel):
    """细纲生成：输入正文片段，输出几条可编辑的后续排布细纲。"""

    fragment: str = Field(min_length=10, description="正文片段（非一句话概括）")
    num_outlines: int = Field(default=2, ge=1, le=3)
    top_k_settings: int = Field(default=6, ge=1, le=12)


class OutlineOption(BaseModel):
    """一条细纲 = 一种把后续这一段落写出来的执行排布。"""

    direction: str            # 一句话走向：这条细纲把故事推向何处
    pov: str                  # 视角调度：用谁的视角、何时切换
    entrances: str            # 角色入场：哪些角色登场、怎么进来
    reveals: str              # 设定引出：哪些设定/规则/伏笔在此浮现、如何自然带出
    beats: list[str]          # 节拍序列：2-4 个具体节拍
    grounded: list[str]       # 这条细纲用到的检索命中（设定原文，供作者核对依据）


class ComposeOutlineResponse(BaseModel):
    options: list[OutlineOption]
    # raw retrieval hits for the collapsible 依据/debug view — honest window
    raw_settings: list[RetrievedChunk]
