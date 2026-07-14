"""Idiom recommendation (v1.1, Feature B).

Route: idiom library + vector retrieval, NOT a raw LLM. We embed the scene
description, recall candidate idioms from the library, then let the LLM *select
and explain* — choosing only from the recalled list. The LLM is never allowed to
emit an idiom that isn't in the database, which is what stops it from fabricating
plausible-but-nonexistent 成语.
"""
from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.core.embedding import embed_text
from app.models.idiom import Idiom
from app.schemas.idiom import IdiomSuggestion

_SELECT_SYSTEM = (
    "你是中文文学顾问。下面给你一段画面描述和一组【候选成语】。"
    "你只能从候选成语中挑选最贴切的若干个，绝对不能使用候选列表之外的任何成语。"
    "为每个入选成语给出一句推荐理由。严格输出 JSON 数组，每项形如："
    '{"text":"成语","reason":"推荐理由"}。'
)


async def _recall(db: AsyncSession, scene: str, top_k: int) -> list[tuple[Idiom, float]]:
    query_vec = await embed_text(scene)
    distance = Idiom.embedding.cosine_distance(query_vec)
    stmt = (
        select(Idiom, distance.label("distance"))
        .where(Idiom.embedding.isnot(None))
        .order_by(distance)
        .limit(top_k)
    )
    rows = (await db.execute(stmt)).all()
    return [(idiom, 1.0 - float(dist)) for idiom, dist in rows]


async def suggest_idioms(
    db: AsyncSession, scene: str, top_k: int = 8, num_final: int = 5
) -> list[IdiomSuggestion]:
    recalled = await _recall(db, scene, top_k)
    if not recalled:
        return []

    by_text = {idiom.text: (idiom, score) for idiom, score in recalled}
    candidates = "\n".join(
        f"- {idiom.text}：{idiom.meaning}" for idiom, _ in recalled
    )
    messages = [
        {"role": "system", "content": _SELECT_SYSTEM},
        {
            "role": "user",
            "content": (
                f"画面描述：{scene}\n\n候选成语（最多挑选 {num_final} 个）：\n"
                f"{candidates}"
            ),
        },
    ]

    raw = await llm.complete(messages, temperature=0.3)
    picks = _parse_picks(raw)

    suggestions: list[IdiomSuggestion] = []
    for pick in picks[:num_final]:
        text = pick.get("text", "").strip()
        # Hard guard: ignore anything the LLM invented outside the recall set.
        if text not in by_text:
            continue
        idiom, score = by_text[text]
        suggestions.append(
            IdiomSuggestion(
                text=idiom.text,
                meaning=idiom.meaning,
                usage_context=idiom.usage_context,
                reason=pick.get("reason"),
                score=round(score, 4),
            )
        )
    return suggestions


def _parse_picks(raw: str) -> list[dict]:
    """Best-effort JSON extraction from the model output."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw[raw.find("\n") + 1 :] if "\n" in raw else raw
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(raw[start : end + 1])
        return data if isinstance(data, list) else []
    except json.JSONDecodeError:
        return []
