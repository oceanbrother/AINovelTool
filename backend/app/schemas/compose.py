from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.literary import LiteraryQuote
from app.schemas.retrieval import RetrievedChunk


class ComposeHintsRequest(BaseModel):
    """剧情参谋：输入正文片段，输出检索驱动的剧情构成建议。"""

    fragment: str = Field(min_length=10, description="正文片段（非一句话概括）")
    top_k_settings: int = Field(default=6, ge=1, le=12)
    top_k_literary: int = Field(default=4, ge=1, le=8)


class DriverHint(BaseModel):
    """设定 = 驱动：这条设定在此处能推动什么。"""

    source_type: str
    content: str
    score: float
    suggestion: str


class DirectionHint(BaseModel):
    """素材 = 方向：这段可以往哪种母题/氛围流动。"""

    work_title: str
    author: str
    knowledge_type: str
    content: str
    score: float
    suggestion: str


class ComposeHintsResponse(BaseModel):
    drivers: list[DriverHint]
    directions: list[DirectionHint]
    organization: str
    # raw hits for the collapsible debug view — the honest window stays open
    raw_settings: list[RetrievedChunk]
    raw_literary: list[LiteraryQuote]
