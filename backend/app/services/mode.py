# -*- coding: utf-8 -*-
"""Rendering-mode classification — the axis rhythm is actually made of.

Why this exists alongside services/scene.py: that module's labels
(战斗/对话/日常/景物/心理) quietly mix two different axes —

    战斗 / 日常          what is happening      (content)
    对话 / 景物 / 心理    how it is written      (rendering mode)

so a fight rendered as dialogue belongs to two labels at once. Overlap is
guaranteed by construction, which is fine for style-sample recall (its original
job: pull roughly comparable prose) but fatal for rhythm, where the whole point
is to watch modes *alternate*. Measured on the reference corpus: 54% of ~450-char
segments were dialogue/narration mixtures, because a segment spans ~8 paragraphs
and therefore contains every mode at once.

So rhythm uses one axis only, at paragraph granularity (~64 chars, usually a
single mode):

    对话 spoken lines · 描写 the external world, physical action included
    心理 interior thought · 叙述 summary, exposition, time passing

Four labels, not five: 动作 was originally split out from 描写, and measurement
against a hand-labelled gold set said that split was wrong. Merging them lifted
agreement more than any other regrouping tried (anchor .396→.562, judge
.511→.660), while folding 叙述 into 描写 barely helped (.396→.458) — so 叙述 is
genuinely its own mode and stays. The author's own account agrees: action
description reads as a kind of description, whereas summary that compresses
time does not.

Nothing is lost by dropping 动作. Fast-versus-slow lives in the texture layer
(short-sentence ratio, mean sentence length), measured directly and
deterministically rather than inferred from a contested category label.

scene.py keeps its labels for retrieval; the two axes stay separate.

Classification is the same anchor-vector nearest-centroid trick: embed a handful
of prototype sentences per mode, average them, and take the closest by cosine.
No LLM, no per-row cost. Anchor sentences below are written for this purpose,
not quoted from any source.
"""
from __future__ import annotations

from app.core.embedding import embed_texts
from app.services.scene import classify_vector

MODES: dict[str, list[str]] = {
    "对话": [
        "“你到底想说什么？”他冷冷地反问。",
        "“不关你的事。”她把头扭开，没有再看他。",
        "“我知道了，”他顿了顿，“不过我还是想去看看。”",
    ],
    # 描写 covers the external world as rendered: both what is there (scene,
    # appearance, atmosphere) and what visibly happens (physical action). The
    # anchors carry both halves so the centroid sits between them.
    "描写": [
        "雨顺着屋檐一线线淌下来，远处的海面泛着灰白的光。",
        "屋子里堆满旧书，窗帘半掩着，灰尘在光柱里慢慢浮动。",
        "那是个瘦高的男人，穿一件洗得发白的外套，袖口磨出了毛边。",
        "他猛地站起身，椅子在地上刮出刺耳的声响。",
        "她一把抓住对方的手腕，用力往回一拽。",
        "他侧身闪开，反手把门重重关上。",
    ],
    "心理": [
        "他忽然生出一种说不清的感觉，像有什么东西正在悄悄改变。",
        "那句话在她心里反复回荡，越想越觉得不安。",
        "他知道自己不该问，可那个念头怎么也压不下去。",
    ],
    "叙述": [
        "这件事要从三年前说起，那时候他还在念高中。",
        "接下来的一个星期，什么都没有发生。",
        "镇上的人都知道那家店，但很少有人真正走进去过。",
    ],
}

MODE_NAMES = list(MODES.keys())

_cache: dict[str, list[float]] = {}


async def anchor_vectors() -> dict[str, list[float]]:
    """Embed and average each mode's prototypes → one unit vector per mode."""
    if _cache:
        return _cache
    flat: list[str] = []
    spans: list[tuple[str, int, int]] = []
    for name, phrases in MODES.items():
        start = len(flat)
        flat.extend(phrases)
        spans.append((name, start, len(flat)))
    vectors = await embed_texts(flat)
    for name, lo, hi in spans:
        group = vectors[lo:hi]
        dim = len(group[0])
        avg = [sum(v[i] for v in group) / len(group) for i in range(dim)]
        norm = sum(x * x for x in avg) ** 0.5 or 1.0
        _cache[name] = [x / norm for x in avg]
    return _cache


async def classify_vectors(vectors: list[list[float]]) -> list[str]:
    """Batch-classify pre-computed embeddings by nearest mode centroid."""
    anchors = await anchor_vectors()
    return [classify_vector(v, anchors) for v in vectors]


async def classify_text(text: str) -> str:
    anchors = await anchor_vectors()
    vec = (await embed_texts([text]))[0]
    return classify_vector(vec, anchors)
