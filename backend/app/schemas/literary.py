from __future__ import annotations

from pydantic import BaseModel


class LiteraryQuoteRequest(BaseModel):
    """根据当前场景/主题检索可引用的文学知识（仅公有领域白名单）。"""

    query: str
    top_k: int = 5
    # 可选分类过滤：诗歌 / 戏剧 / 散文 / 志怪文学 / 爱情文学 / 战争文学 /
    # 现实文学 / 哲学 / 成长文学
    category: str | None = None


class LiteraryQuote(BaseModel):
    work_title: str
    author: str
    era: str | None
    category: str | None         # 体裁/主题分类
    knowledge_type: str          # 作者背景 / 主题解读 / 公认名句 / 句式
    content: str
    score: float


class LiteraryQuoteResponse(BaseModel):
    query: str
    quotes: list[LiteraryQuote]
