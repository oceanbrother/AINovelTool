# -*- coding: utf-8 -*-
"""细纲生成 (compose-outline) — retrieval-grounded execution outlines.

The clue pane used to be a passive advisor (which settings are similar, which
motif to lean on) — but "give ideas for what's next" is already what 续写 does
by retrieving and using settings, and "recover foreshadowing" is what the 伏笔
manager does. So the pane is repurposed into the missing planning layer:

  input   a fragment of actual prose (the current draft's tail)
  step 1  retrieve facts through the *hints* channel (settings / characters /
          open foreshadowing — no style samples, no verbatim quotes)
  step 2  an LLM drafts N editable EXECUTION outlines for the next stretch,
          each specifying: 走向 / 视角调度 / 角色入场 / 设定引出 / 节拍,
          grounded in the retrieved hits (referenced by index, never invented).

The author edits an outline, then hands it to 续写 or 仿写 as the direction —
this fills the gap between "an idea" and "prose": an editable plan in between.
破壁 stays for divergent ideation; this is convergent staging.
"""
from __future__ import annotations

import json
import re

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.schemas.compose import ComposeOutlineResponse, OutlineOption
from app.services import prompts, retrieval

_SYSTEM = (
    "你是长篇小说作者的剧情排布助手。作者给你一段正文片段和一组【设定命中】"
    "（已确立的角色 / 世界规则 / 未回收伏笔）。请为接下来的一段剧情草拟"
    "{n} 条不同的【执行细纲】——不是发散的走向分支，而是把这一段落如何写出来"
    "的具体排布。每条细纲必须包含：\n"
    "· direction：一句话走向（这条细纲把故事推到哪一步）\n"
    "· pov：视角调度（用谁的视角、何时切换、为何这样切）\n"
    "· entrances：角色入场（哪些角色登场、以什么方式进来）\n"
    "· reveals：设定引出（哪条设定/规则/伏笔在此浮现、如何自然带出而非硬塞）\n"
    "· beats：2-4 个具体节拍（有序的小事件）\n"
    "· refs：这条细纲用到的设定编号数组（只能引用给定编号）\n\n"
    '只输出 JSON：{"options":[{"direction":"...","pov":"...","entrances":"...",'
    '"reveals":"...","beats":["...","..."],"refs":[0,2]}]}\n'
    "规则：细纲之间要有实质差异（视角/入场/节奏不同）；每条都要能直接指导写作，"
    "具体到这段正文的情境，不写通用建议；设定引出必须基于给定的设定命中，不得虚构。"
)


def _parse(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}


async def compose_outline(
    db: AsyncSession,
    project_id: int,
    fragment: str,
    num_outlines: int = 2,
    top_k_settings: int = 6,
) -> ComposeOutlineResponse:
    chunks = await retrieval.retrieve_settings(
        db, project_id, fragment, channel="hints", top_k=top_k_settings
    )
    settings_block = "\n".join(
        f"[设定{i}] ({c.source_type}) {c.content}" for i, c in enumerate(chunks)
    ) or "（无命中；可基于片段本身排布，设定引出留空）"

    raw = await llm.complete(
        [
            {
                "role": "system",
                "content": (await prompts.resolve(db, "compose.outline"))
                .replace("{n}", str(num_outlines)),
            },
            {
                "role": "user",
                "content": f"【正文片段】\n{fragment}\n\n【设定命中】\n{settings_block}",
            },
        ],
        temperature=0.6,
    )
    data = _parse(raw)

    options: list[OutlineOption] = []
    for o in data.get("options", []):
        refs = o.get("refs", [])
        grounded = [
            chunks[i].content
            for i in refs
            if isinstance(i, int) and 0 <= i < len(chunks)
        ]
        beats = [str(b) for b in o.get("beats", []) if str(b).strip()]
        if not o.get("direction"):
            continue
        options.append(
            OutlineOption(
                direction=str(o.get("direction", "")),
                pov=str(o.get("pov", "")),
                entrances=str(o.get("entrances", "")),
                reveals=str(o.get("reveals", "")),
                beats=beats,
                grounded=grounded,
            )
        )

    return ComposeOutlineResponse(options=options, raw_settings=chunks)
