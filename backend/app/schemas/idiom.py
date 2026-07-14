from __future__ import annotations

from pydantic import BaseModel


class IdiomSuggestRequest(BaseModel):
    """输入画面描述，检索召回候选成语，再由 LLM 从召回列表中筛选解释。"""

    scene: str
    top_k: int = 8       # 召回数量（LLM 会从中精选 3-5 个）
    num_final: int = 5   # 最终返回数量


class IdiomSuggestion(BaseModel):
    text: str
    meaning: str
    usage_context: str | None
    reason: str | None = None  # LLM 为何在此场景推荐它
    score: float


class IdiomSuggestResponse(BaseModel):
    scene: str
    suggestions: list[IdiomSuggestion]
