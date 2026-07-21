# -*- coding: utf-8 -*-
"""剧情参谋 (compose-hints) — retrieval-driven plot counsel.

The clue pane's old mode ("one line in, top-k similar chunks out") answers
"which entries are similar", but the author's real question is "where should
this scene go". This service upgrades retrieval output into counsel:

  input   a fragment of actual prose (not a one-line summary)
  step 1  retrieve facts through the *hints* channel (settings/threads only —
          style samples and verbatim quotes must not intrude here)
  step 2  retrieve literary 素材 (factual knowledge: themes, plot synopses)
  step 3  an LLM organises the hits into a structured brief:
            drivers    — what each fact could push forward at this point
            directions — which motif/atmosphere each material suggests
            organization — one integrated "which way to flow" suggestion
          The LLM may only reference retrieved hits by index — it organises
          evidence, it does not invent sources (the project's core thesis).

Raw hits ride along in the response for the collapsible debug view.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.schemas.compose import ComposeHintsResponse, DirectionHint, DriverHint
from app.services import literary, retrieval

_SYSTEM = (
    "你是长篇小说作者的剧情参谋。作者给你一段正文片段，以及两组检索命中：\n"
    "【设定命中】——这个故事已确立的角色/世界规则/未回收伏笔；\n"
    "【素材命中】——文学素材库里主题相关的知识（母题、结构、氛围参照）。\n\n"
    "你的任务不是复述这些条目，而是回答：在这段正文的当下，它们各自能推动什么。\n"
    '只输出 JSON：{\n'
    '  "drivers": [{"ref": 设定编号, "suggestion": "此设定在此处能驱动什么，一句话，具体到情节动作"}],\n'
    '  "directions": [{"ref": 素材编号, "suggestion": "这段可以往该母题/氛围的哪个方向流动，一句话"}],\n'
    '  "organization": "两三句话的整合建议：让以上元素往同一个方向流动的组织方式"\n'
    "}\n"
    "规则：不相关的命中直接省略，不硬凑；drivers 至多 4 条、directions 至多 2 条；"
    "建议要具体到这段正文的情境，不要写通用写作建议。"
)


def _parse(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}


async def compose_hints(
    db: AsyncSession,
    project_id: int,
    fragment: str,
    top_k_settings: int = 6,
    top_k_literary: int = 4,
) -> ComposeHintsResponse:
    chunks = await retrieval.retrieve_settings(
        db, project_id, fragment, channel="hints", top_k=top_k_settings
    )
    quotes = await literary.retrieve_quotes(
        db, fragment, top_k=top_k_literary, library="素材"
    )

    settings_block = "\n".join(
        f"[设定{i}] ({c.source_type}) {c.content}" for i, c in enumerate(chunks)
    ) or "（无命中）"
    literary_block = "\n".join(
        f"[素材{i}] 《{q.work_title}》{q.author}·{q.knowledge_type}：{q.content}"
        for i, q in enumerate(quotes)
    ) or "（无命中）"

    raw = await llm.complete(
        [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": (
                    f"【正文片段】\n{fragment}\n\n"
                    f"【设定命中】\n{settings_block}\n\n"
                    f"【素材命中】\n{literary_block}"
                ),
            },
        ],
        temperature=0.4,
    )
    data = _parse(raw)

    drivers = []
    for d in data.get("drivers", []):
        i = d.get("ref")
        if isinstance(i, int) and 0 <= i < len(chunks) and d.get("suggestion"):
            c = chunks[i]
            drivers.append(
                DriverHint(
                    source_type=c.source_type,
                    content=c.content,
                    score=c.score,
                    suggestion=str(d["suggestion"]),
                )
            )
    directions = []
    for d in data.get("directions", []):
        i = d.get("ref")
        if isinstance(i, int) and 0 <= i < len(quotes) and d.get("suggestion"):
            q = quotes[i]
            directions.append(
                DirectionHint(
                    work_title=q.work_title,
                    author=q.author,
                    knowledge_type=q.knowledge_type,
                    content=q.content,
                    score=q.score,
                    suggestion=str(d["suggestion"]),
                )
            )

    return ComposeHintsResponse(
        drivers=drivers,
        directions=directions,
        organization=str(data.get("organization", "")) or "（参谋输出解析失败，请重试）",
        raw_settings=chunks,
        raw_literary=quotes,
    )
