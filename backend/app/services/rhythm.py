# -*- coding: utf-8 -*-
"""Texture metrics — the programmatic half of rhythm analysis.

Rhythm splits into two layers, and mixing them is what makes tagging unreliable:

  * texture (here)  — how the prose *moves*: dialogue share, sentence length,
    punctuation density. Countable straight off the characters, so it is
    deterministic, free, reproducible, and needs no model at all.
  * function (elsewhere) — what a passage *does* for the plot (转折/揭示/…),
    which genuinely requires reading comprehension and therefore an LLM.

Everything in this module is a pure function of a string: no IO, no DB, no
network. That is deliberate — these numbers feed the density curves and the
rhythm gate, and both are worthless if the measurement itself drifts.

Conventions: ratios are in [0, 1]; lengths are in characters; whitespace is
excluded from length totals so indentation style can't move the numbers.
"""
from __future__ import annotations

import re

# Paired quotes used in Chinese prose. Straight quotes are included because
# converted epubs often mix them in.
_QUOTE_SPANS = (
    re.compile(r"“[^”]*”"),
    re.compile(r"「[^」]*」"),
    re.compile(r"『[^』]*』"),
    re.compile(r"\"[^\"]*\""),
)

# A sentence ends on 。！？… — never on ，or ；, which mark clauses. Trailing
# closing quotes/brackets belong to the sentence they close, so they're pulled
# into the terminator rather than orphaned onto the next sentence.
_SENT_END = re.compile(r"[。！？!?…]+[”』」\"）)]*")

_PUNCT = set("，。！？；：、…—～·「」『』“”‘’（）()《》〈〉【】,.!?;:")

_WS = re.compile(r"\s+")

SHORT_SENTENCE_MAX = 10  # a sentence this short reads as a beat, not a clause


def _dense(text: str) -> str:
    """Text with whitespace removed — the denominator for every ratio."""
    return _WS.sub("", text)


def dialogue_ratio(text: str) -> float:
    """Share of characters that sit inside quotation marks.

    Spans are matched non-crossing (a closing mark ends the span), so an
    unbalanced quote costs one span rather than swallowing the rest of the text.
    """
    total = len(_dense(text))
    if not total:
        return 0.0
    inside = 0
    for pattern in _QUOTE_SPANS:
        for match in pattern.finditer(text):
            inside += len(_dense(match.group()))
    return min(inside / total, 1.0)


def split_sentences(text: str) -> list[str]:
    """Split into sentences on 。！？… (clause marks don't end a sentence)."""
    parts = _SENT_END.split(text)
    out = [_WS.sub("", p) for p in parts]
    return [p for p in out if p]


def avg_sentence_len(text: str) -> float:
    sentences = split_sentences(text)
    if not sentences:
        return 0.0
    return sum(len(s) for s in sentences) / len(sentences)


def short_sentence_ratio(text: str, max_len: int = SHORT_SENTENCE_MAX) -> float:
    """Share of sentences at or below `max_len` chars — the staccato measure.

    Short-sentence runs are how Chinese prose signals acceleration: action,
    tension, a hard stop at a chapter's end.
    """
    sentences = split_sentences(text)
    if not sentences:
        return 0.0
    return sum(1 for s in sentences if len(s) <= max_len) / len(sentences)


def punct_density(text: str) -> float:
    """Punctuation marks per character — a proxy for how often the reader pauses."""
    dense = _dense(text)
    if not dense:
        return 0.0
    return sum(1 for ch in dense if ch in _PUNCT) / len(dense)


def avg_paragraph_len(text: str) -> float:
    """Mean characters per paragraph — visual breathing room on the page."""
    paras = [p for p in (_WS.sub("", ln) for ln in text.split("\n")) if p]
    if not paras:
        return 0.0
    return sum(len(p) for p in paras) / len(paras)


def is_dialogue_paragraph(text: str) -> bool:
    """Rule-based 对话 detection — free and near-certain, so no model is asked.

    A paragraph that opens with a quotation mark is a spoken line; one that is
    mostly quoted content is too, even when a speech tag comes first. Everything
    else is left to the classifier, which only has to separate the four harder
    modes (动作/描写/心理/叙述).
    """
    stripped = text.lstrip()
    if stripped[:1] in "“「『\"":
        return True
    return dialogue_ratio(text) >= 0.5


def texture(text: str) -> dict[str, float]:
    """All five metrics, keyed to match CorpusSegment's columns."""
    return {
        "dialogue_ratio": round(dialogue_ratio(text), 4),
        "short_sent_ratio": round(short_sentence_ratio(text), 4),
        "avg_sent_len": round(avg_sentence_len(text), 2),
        "punct_density": round(punct_density(text), 4),
        "avg_para_len": round(avg_paragraph_len(text), 2),
    }
