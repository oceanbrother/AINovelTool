# -*- coding: utf-8 -*-
"""拆书 — surface scenes worth hand-labelling, without asking the model first.

The function-label gate has failed twice, and both times for the same reason:
40 randomly drawn scenes contained 2 转折 and 2 回收, so those classes had no
verdict at all. Drawing more at random is the obvious fix and the wrong one —
at a 5% natural rate, 25 instances of a class costs ~500 hand labels.

Stratified sampling is the right fix, but it needs something to stratify *by*,
and the obvious candidate is disqualified: the labeller scored 0/2 on both
minority classes. A pre-labeller that cannot find 转折 cannot be used to surface
转折 candidates. Its argmax is exactly the signal that is missing.

So the candidate channels here are deliberately **not** the classifier:

  回收  a payoff re-uses something planted long ago. That is a measurable
        property of an ordered corpus — a term that appeared once, far back,
        and comes back. No judgement about the prose is required.
  转折  a reversal tends to break the texture it sits in. Adjacent-segment
        distance in z-scored texture space finds discontinuities cheaply.

Neither channel is a classifier and neither is claimed to be accurate. They are
**recall devices**: their only job is to make the author's labelling queue
contain enough minority-class instances to be worth their time. Precision is
the author's to decide, one scene at a time — which is the entire point, since
the author's labels are what the gate measures against.

**MEASURED, AND BOTH CHANNELS FAILED. Do not wire them into a labelling queue.**

Scored against the 40 hand-labelled scenes in `style_data/function_gold.v1.json`
— the only ground truth that exists — as a percentile rank (0% = channel ranked
it first, 50% = indistinguishable from random):

    转折 (n=2)   转折通道 67%   ← worse than random
    回收 (n=2)   回收通道 35%   ← better than random, but two data points
    建立 (n=9)   回收通道 73%   ← the largest separation is on the wrong class

Two earlier versions were fixed before this test and neither fix was the
problem: measuring gap from a term's *first* occurrence instead of its previous
one (which ranked the wordiest scenes top), and letting Latin stanzas through
(an English song registers as the largest texture break in the book). After
both fixes the echo channel still marks 98% of segments non-zero, and its top
hits are proper-noun-dense exposition — mythology being explained, not a thread
being closed.

The honest reading is that neither is a weak signal to be tuned; there is no
signal at this granularity. Character n-grams cannot tell a planted object from
a lore term, and texture discontinuity cannot tell a reversal from a change of
room. Continuing to tune against a 2-item ground truth would be fitting to
noise — the failure mode this project has already recorded twice.

The code stays because the queue machinery below it is correct and independent:
blinding, the random control stratum, and the rule that headline accuracy may
only be computed on the random part. Only the two channels are dead. A working
回收 detector needs recorded plants (the `foreshadowing` table has them for the
author's own work, not for a reference corpus) or real entity extraction.

Two consequences that the caller must respect, both of them methodological:

1. **Blind the queue.** If the author sees which channel proposed a scene, or
   what the model guessed, the labels stop being independent evidence. The
   stratum tag travels alongside the item, never inside it.
2. **Keep a random stratum.** Accuracy and kappa computed on a stratified
   sample answer a different question than on a random one — the marginals are
   engineered. Per-class recall comes from the stratified part; the headline
   accuracy/kappa may only come from the random part. Mixing them silently is
   how a stratified study reports a number nobody can interpret.

Zero LLM calls, zero network, no database session — everything here is a pure
function over text so it can be unit-tested and costs nothing to re-run.
"""
from __future__ import annotations

import math
import random
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from app.services import rhythm

# --- 回收通道 ---------------------------------------------------------------

# Character n-grams rather than words: no tokeniser dependency, and Chinese
# proper nouns (人名/地名/组织) are exactly the distinctive strings that a payoff
# brings back. 2-grams are too common to be distinctive, 5+ too sparse to recur.
_NGRAM_MIN, _NGRAM_MAX = 3, 4

# A planted term appears a handful of times across a whole book, not dozens.
# An earlier version used 2% of the corpus (df ≤ 33 on 龙族) and measured
# vocabulary density instead: 99% of segments scored non-zero, median 16.3,
# and the top hits were simply the wordiest scenes. Absolute and small.
_DF_MAX = 4

# How far back counts as "planted long ago". Below this, recurrence is just the
# same scene continuing to talk about the same thing.
_MIN_GAP = 20

# Latin runs (song lyrics, epigraphs, foreign titles) wreck both channels:
# rhythm.texture's sentence/paragraph statistics assume CJK, so an English
# stanza registers as an enormous texture break that has nothing to do with the
# story turning over. Segments below this CJK share are excluded from candidacy.
_MIN_CJK_RATIO = 0.6

_PUNCT = re.compile(r"[\s。，、；：？！…—·「」『』“”‘’（）《》〈〉,.;:!?\"'()\[\]-]+")
_CJK = re.compile(r"[一-鿿]")


def cjk_ratio(text: str) -> float:
    stripped = _PUNCT.sub("", text)
    if not stripped:
        return 0.0
    return len(_CJK.findall(stripped)) / len(stripped)


def _ngrams(text: str) -> set[str]:
    """Distinct character n-grams of a segment, punctuation stripped.

    CJK-only: a payoff brings back a name, a place, an object. Latin runs are
    quoted lyrics and titles, which recur for reasons unrelated to plot.
    """
    out: set[str] = set()
    for run in _PUNCT.split(text):
        run = "".join(_CJK.findall(run))
        for n in range(_NGRAM_MIN, _NGRAM_MAX + 1):
            for i in range(len(run) - n + 1):
                out.add(run[i : i + n])
    return out


def echo_scores(texts: list[str]) -> list[float]:
    """Per-segment score for "brings back something that had gone away".

    Returns one float per input segment, in the same order.

    The gap is measured from the term's **previous** occurrence, not its first.
    That distinction is the whole signal: a term mentioned continuously from
    chapter 1 to chapter 12 has a large first-occurrence gap and is not a payoff
    of anything, while a term that appears once, disappears for twenty segments,
    and returns is exactly the shape of a plant being discharged. Getting this
    wrong is what made the first version rank the wordiest scenes top.

    Deliberately NOT symmetric: a returning term counts for the segment that
    brings it back, never for the one that planted it.
    """
    n = len(texts)
    if n == 0:
        return []

    grams = [_ngrams(t) for t in texts]
    df: Counter[str] = Counter()
    for g in grams:
        df.update(g)

    last_at: dict[str, int] = {}
    scores = []
    for i, g in enumerate(grams):
        hits = 0
        for term in g:
            prev = last_at.get(term)
            if prev is not None and 2 <= df[term] <= _DF_MAX and i - prev >= _MIN_GAP:
                hits += 1
            last_at[term] = i
        # log-length normalisation: linear over-corrects and makes very short
        # segments dominate, which are exactly the ones with too little signal.
        denom = math.log(max(len(texts[i]), 50))
        scores.append(0.0 if cjk_ratio(texts[i]) < _MIN_CJK_RATIO else hits / denom)
    return scores


# --- 转折通道 ---------------------------------------------------------------

_TEXTURE_KEYS = (
    "dialogue_ratio",
    "short_sent_ratio",
    "avg_sent_len",
    "punct_density",
    "avg_para_len",
)


def _zscore(col: list[float]) -> list[float]:
    n = len(col)
    if n < 2:
        return [0.0] * n
    mu = sum(col) / n
    var = sum((x - mu) ** 2 for x in col) / n
    sd = math.sqrt(var)
    return [0.0] * n if sd == 0 else [(x - mu) / sd for x in col]


def discontinuity_scores(texts: list[str]) -> list[float]:
    """Per-segment texture break against the preceding segment.

    Texture is z-scored per dimension across the whole corpus first, so a
    dimension with a naturally large range (avg_sent_len) does not drown the
    ones measured in [0,1]. The score of segment i is the Euclidean distance
    between z(i) and z(i-1); segment 0 scores 0 by definition.

    This measures *rendering* change (dialogue giving way to narration, long
    sentences to short), which is a proxy for a reversal and nothing more.
    A scene can turn the story over without changing its texture at all, and
    a scene can change texture merely by moving indoors. Recall device only.
    """
    n = len(texts)
    if n == 0:
        return []
    tex = [rhythm.texture(t) for t in texts]
    cols = {k: _zscore([t[k] for t in tex]) for k in _TEXTURE_KEYS}
    cjk = [cjk_ratio(t) for t in texts]
    scores = [0.0]
    for i in range(1, n):
        # A Latin stanza next to Chinese prose is the largest "break" in the
        # book and means nothing: texture() counts sentences by CJK punctuation.
        if cjk[i] < _MIN_CJK_RATIO or cjk[i - 1] < _MIN_CJK_RATIO:
            scores.append(0.0)
            continue
        d = sum((cols[k][i] - cols[k][i - 1]) ** 2 for k in _TEXTURE_KEYS)
        scores.append(math.sqrt(d))
    return scores


# --- 分层队列 ---------------------------------------------------------------


@dataclass
class QueueItem:
    """One scene awaiting a hand label.

    `stratum` is metadata for the analysis, NOT for the labeller: it says which
    channel surfaced the item, and showing it would tell the author what answer
    is expected. Callers rendering this to a human must not send it.
    """

    index: int                      # position in the source ordering
    stratum: str                    # "回收候选" / "转折候选" / "随机"
    payload: dict = field(default_factory=dict)


def build_queue(
    texts: list[str],
    *,
    n_echo: int = 30,
    n_break: int = 30,
    n_random: int = 40,
    seed: int = 0,
) -> list[QueueItem]:
    """Mix the two recall channels with a random control, then shuffle.

    The random stratum is not padding. It is the only part of the queue whose
    labels can carry the headline accuracy and kappa, because it is the only
    part drawn from the distribution the classifier will actually meet. The
    stratified parts answer a narrower question — does the classifier recognise
    a 转折 when one is in front of it — and that question has no answer at all
    without them.

    Overlap between channels is resolved by first-claim, so an item surfaced by
    both is labelled once and attributed to one stratum. Counts are therefore
    upper bounds; the caller should report what it actually got.
    """
    n = len(texts)
    if n == 0:
        return []

    echo = echo_scores(texts)
    brk = discontinuity_scores(texts)

    by_echo = sorted(range(n), key=lambda i: echo[i], reverse=True)
    by_break = sorted(range(n), key=lambda i: brk[i], reverse=True)

    taken: dict[int, str] = {}
    for i in by_echo[:n_echo]:
        taken.setdefault(i, "回收候选")
    for i in by_break[:n_break]:
        taken.setdefault(i, "转折候选")

    rng = random.Random(seed)
    rest = [i for i in range(n) if i not in taken]
    rng.shuffle(rest)
    for i in rest[:n_random]:
        taken[i] = "随机"

    items = [
        QueueItem(index=i, stratum=s, payload={"echo": echo[i], "break": brk[i]})
        for i, s in taken.items()
    ]
    # Shuffle the presentation order so the author does not label all payoff
    # candidates in a row and drift into a rhythm of answering 回收.
    rng.shuffle(items)
    return items


def stratum_counts(items: list[QueueItem]) -> dict[str, int]:
    out: dict[str, int] = defaultdict(int)
    for it in items:
        out[it.stratum] += 1
    return dict(out)
