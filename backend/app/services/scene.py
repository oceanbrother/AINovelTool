# -*- coding: utf-8 -*-
"""Scene classification for style samples — anchor-vector nearest neighbour.

Imitation quality suffered from voice cross-talk: a battle draft judged against
randomly-recalled dialogue samples never matched. The fix is to tag each style
sample with a scene (战斗/对话/日常/景物/心理) and, at imitation time, recall
only same-scene samples.

Classification is pure vector work — no LLM, no per-row cost. Each scene has a
handful of anchor phrases; we embed and average them into one anchor vector per
scene. A sample's scene is the anchor with the highest cosine similarity (all
vectors are bge-m3 L2-normalised, so a dot product is the cosine). The same
routine classifies a generation query, closing the loop: infer the draft's
target scene, then pull that scene's samples.
"""
from __future__ import annotations

from functools import lru_cache

from app.core.embedding import embed_texts

SCENES: dict[str, list[str]] = {
    "战斗": [
        "刀光剑影的搏杀，拳脚相加，生死一线的交锋",
        "他挥拳砸过去，对方侧身闪避，鲜血溅在墙上",
        "枪声炸响，众人扑倒在地，危险迫在眉睫",
    ],
    "对话": [
        "两个人你一言我一语地交谈，互相试探与质问",
        "“你到底想说什么？”他冷冷地反问",
        "她压低声音，把话一句句说清楚，等着对方的回答",
    ],
    "日常": [
        "吃饭睡觉上学的琐碎日常，平静无波的生活片段",
        "他晃回家吃饭，看饿了就随手翻两页书，太阳照常挂着",
        "小店的午后，老板打着盹，街上没什么人经过",
    ],
    "景物": [
        "环境与风景的描写，天色、光线、气味与氛围",
        "雨顺着屋檐一线线淌下来，远处的海面泛着灰白的光",
        "夜色压下来，霓虹在积水里碎成一片一片的红",
    ],
    "心理": [
        "内心独白与情绪的流动，回忆、犹疑与思绪",
        "他忽然生出一种说不清的感觉，像有什么东西正悄悄改变",
        "那句话在她心里反复回荡，越想越觉得不安",
    ],
}

SCENE_NAMES = list(SCENES.keys())


@lru_cache(maxsize=1)
def _cached_anchor_key() -> tuple:
    # cache invalidation handle — anchors are static, so a single key is fine
    return tuple(SCENE_NAMES)


_anchor_cache: dict[str, list[float]] = {}


async def _anchor_vectors() -> dict[str, list[float]]:
    """Embed and average each scene's anchor phrases → one vector per scene."""
    if _anchor_cache:
        return _anchor_cache
    flat: list[str] = []
    spans: list[tuple[str, int, int]] = []
    for scene, phrases in SCENES.items():
        start = len(flat)
        flat.extend(phrases)
        spans.append((scene, start, len(flat)))
    vecs = await embed_texts(flat)
    for scene, lo, hi in spans:
        group = vecs[lo:hi]
        dim = len(group[0])
        avg = [sum(v[i] for v in group) / len(group) for i in range(dim)]
        # renormalise the average so dot product stays a cosine
        norm = sum(x * x for x in avg) ** 0.5 or 1.0
        _anchor_cache[scene] = [x / norm for x in avg]
    return _anchor_cache


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def classify_vector(vec: list[float], anchors: dict[str, list[float]]) -> str:
    """Nearest anchor by cosine similarity."""
    return max(anchors, key=lambda s: _cosine(vec, anchors[s]))


async def anchor_vectors_public() -> dict[str, list[float]]:
    """Public accessor for the cached anchor vectors (scripts / batch callers)."""
    return await _anchor_vectors()


async def classify_text(text: str) -> str:
    """Scene of an arbitrary text (used to infer a generation query's scene)."""
    anchors = await _anchor_vectors()
    vec = (await embed_texts([text]))[0]
    return classify_vector(vec, anchors)


async def classify_vectors(vectors: list[list[float]]) -> list[str]:
    """Batch-classify pre-computed embeddings (used by the backfill script)."""
    anchors = await _anchor_vectors()
    return [classify_vector(v, anchors) for v in vectors]
