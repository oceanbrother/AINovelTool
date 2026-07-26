# -*- coding: utf-8 -*-
"""Stock-phrase detection — the cheapest quality gate in the pipeline.

Reaching for "youth" or "fate" or "melancholy", a model falls back on the same
handful of phrases every time. They are not wrong exactly; they are simply
nobody's writing, and a page of them reads as competent and anonymous.

Detection here is plain substring matching: no model, no embedding, no
threshold. That makes it deterministic, free, unit-testable, and impossible to
argue with — the same properties that make the n-gram plagiarism gate reliable.
It sits on the correct side of this project's dividing line: a concrete,
checkable prohibition, not a statistic to be interpreted.

What this deliberately does NOT do is judge whether a metaphor is fresh or
whether an image belongs to a particular character's experience. Those need
semantics and would need their own validation before being trusted; they are
left for a later round rather than faked with a word list.

The list is a starting point meant to be edited per project — it currently
lives in code, so changes need a restart. Moving it into the database is the
obvious next step once a project's own habits become clear.
"""
from __future__ import annotations

import re

# Common Chinese web-fiction stock phrases. Kept deliberately short: a long
# list catches more but also fires on legitimate usage, and a gate that cries
# wolf gets ignored.
DEFAULT_CLICHES: tuple[str, ...] = (
    "命运的齿轮",
    "世界突然安静",
    "时间仿佛静止",
    "空气仿佛凝固",
    "影子拉得很长",
    "心里某处柔软的地方",
    "内心深处最柔软",
    "嘴角勾起一抹",
    "眼底闪过一丝",
    "不易察觉的",
    "仿佛过了一个世纪",
    "如同被抽走了全身力气",
    "血液仿佛凝固",
    "脑海中一片空白",
    "五味杂陈",
    "百感交集",
    "说不出的滋味",
    "阳光正好",
    "岁月静好",
    "微风不燥",
)

_WS = re.compile(r"\s+")


def find_cliches(text: str, extra: tuple[str, ...] = ()) -> list[str]:
    """Stock phrases present in `text`, in the order they were declared.

    Whitespace is stripped before matching so a line break inside a phrase
    cannot smuggle it past the check.
    """
    dense = _WS.sub("", text or "")
    if not dense:
        return []
    return [p for p in (*DEFAULT_CLICHES, *extra) if p and p in dense]


def prohibition_line(extra: tuple[str, ...] = (), limit: int = 8) -> str:
    """A must-not line for the generation prompt.

    Only the first `limit` phrases go in: the point is to set the register
    ("don't write like this"), and pasting the whole list would spend prompt
    space that the scene's own constraints need more.
    """
    sample = [*DEFAULT_CLICHES, *extra][:limit]
    return "使用套话（如：" + "、".join(sample) + " 等陈词）"
