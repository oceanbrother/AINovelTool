from __future__ import annotations

from pydantic import BaseModel


class LiteraryQuoteRequest(BaseModel):
    """根据当前场景/主题检索可引用的文学知识（仅公有领域白名单）。"""

    query: str
    top_k: int = 5
    # 可选分类过滤：诗歌 / 戏剧 / 散文 / 志怪文学 / 爱情文学 / 战争文学 /
    # 现实文学 / 哲学 / 成长文学
    category: str | None = None
    # 可选库过滤："金句"（原文引用，仅公有领域）或 "素材"（背景/主题/情节等
    # 事实性知识，可含版权期内作品）。None = 两库都检索。
    library: str | None = None


class LiteraryQuote(BaseModel):
    work_title: str
    author: str
    era: str | None
    category: str | None         # 体裁/主题分类
    library: str                 # 金句 / 素材
    knowledge_type: str          # 作者背景 / 写作背景 / 主题解读 / 内容概括 / 公认名句 / 典故 / 公认评价
    content: str
    score: float


class LiteraryQuoteResponse(BaseModel):
    query: str
    quotes: list[LiteraryQuote]
