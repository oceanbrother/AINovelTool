from __future__ import annotations

from pydantic import BaseModel


class LiteraryQuoteRequest(BaseModel):
    """根据当前场景/主题检索可引用的文学知识（仅公有领域白名单）。"""

    query: str
    top_k: int = 5


class LiteraryQuote(BaseModel):
    work_title: str
    author: str
    era: str | None
    knowledge_type: str          # 作者背景 / 主题解读 / 公认名句 / 句式
    content: str
    score: float


class LiteraryQuoteResponse(BaseModel):
    query: str
    quotes: list[LiteraryQuote]
