# -*- coding: utf-8 -*-
"""Narrative function labels — what a scene DOES to the story.

    ┌──────────────────────────────────────────────────────────────────────┐
    │ ABANDONED. Three attempts at the gate, and the third one answered    │
    │ the question instead of running out of data. Nothing may be built on │
    │ these labels: no function_embedding, no function-aware retrieval.    │
    │ The taxonomy and prompt stay for the record and for the eval that    │
    │ produced the verdict.                                                │
    └──────────────────────────────────────────────────────────────────────┘

Final measurement, 294 hand-labelled scenes from a 300-scene random draw
(`eval/run_function_agreement.py --work 龙族`):

    accuracy 0.724 · kappa 0.246 · majority baseline 0.762 → **-0.037**

    recall by hand label   信息 196/224 (88%)   升级 11/39 (28%)
                           转折   2/16  (13%)   回收  4/15 (27%)
    top confusions         升级→信息 ×19 · 信息→升级 ×16
                           转折→信息 ×12 · 回收→信息 ×11

A program that says 信息 and nothing else scores higher than the classifier.
That is not "close" — the labeller has no value on this task.

Why this attempt settles it where the first two did not: those runs had 2
instances of each minority class and honestly reported "no verdict available".
This one had 16 转折 and 15 回收 — enough to answer — and the answer is that
three quarters of the reversals are read as exposition.

The merge scan points somewhere not worth going. 信息+升级 → 0.844 (+0.119) is
the only pair above the merge threshold, and collapsing it leaves three labels
of which one covers 88% of scenes. That is a binary "did the story move", and a
binary label cannot retrieve a scene that does what the next one needs to do —
which was the entire purpose.

The author's labels are the durable asset here and are not wasted: they are what
turned this from "insufficient data" into a decision. Kept in `style_data/`.

One cost worth recording for next time: 1 of 294 items carries a written reason.
Without them there is no way to separate "the model cannot see 转折" from "转折
is not stable as a category in this prose" — two findings with opposite fixes.
The 40-item v1 set had reasons on every row, and that is what produced the 6→4
taxonomy revision. Reasons scale worse than labels and are worth more.

---

Original design notes follow.

Retrieval can already find prose that *reads* like the current draft. It cannot
find a scene that *does* what the next one needs to do — raise the pressure,
pay off a thread, let the reader breathe. That gap is what these labels close.

Why six, and why these six. The design draft lists roughly fifty labels across
six groups, but those groups are themselves different axes: 人物/关系/信息/冲突
say which dimension of the story moved, 节奏 says what the reader feels, and
setup/payoff says where the scene sits on a planting-and-discharging chain. One
scene is legitimately all three at once, so a single label drawn from that pool
can never be exclusive — the same fault that scored 0.396 when 战斗 (content)
and 对话 (rendering) were mixed into one vocabulary.

So one axis only: **what did this scene change about the story's state**.

Four labels, not six — and the cut was made by measurement, not taste.

The first attempt split the informational side three ways: 建立 (first time the
reader meets something), 揭示 (understanding changes), 过渡 (nothing much moves).
Against 40 hand-labelled scenes that scored 0.300 with kappa 0.089 — chance. The
confusion ran three ways at once, and the author's own notes show why: their 建立
cases read "first appearance of X", their 揭示 cases read "fills in more about
X". The distinction is **whether the reader has met this before**, which is a
fact about the whole book so far. A labeller holding one 450-character scene and
120 characters of preceding context cannot know it, and no prompt can supply
what the window does not contain.

Collapsing those three into one 信息 label takes agreement to 0.800. Merging any
two of them only reaches 0.45–0.50, which is what makes the three-way collapse
the honest cut rather than a convenient one.

The cost is real and should not be glossed: 信息 covers 80% of scenes in the gold
sample, so this taxonomy separates "does the story move" from "does it lay
groundwork" far better than it says what a scene specifically does. Function-aware
retrieval built on it will be correspondingly coarse.

Splitting 信息 back into 建立/揭示 needs reader-knowledge state — which the
`story_facts` table exists to hold. That ordering was discovered here rather than
planned: function labels turn out to depend on the state layer, not the reverse.

回收 stays separate from the rest of the informational side because it is decided
structurally, not by feel: it requires an actual recorded thread being closed,
a fact about the `foreshadowing` table rather than a judgement about the prose.

Nothing here is trusted until it clears the gold-standard gate — accuracy and
kappa against hand labels, and below 0.6 the taxonomy gets fixed rather than
built upon.
"""
from __future__ import annotations

# label -> (one-line meaning, the question to ask when unsure)
FUNCTIONS: dict[str, tuple[str, str]] = {
    "信息": (
        "交代、补全或铺陈信息；也包括只起连接与缓冲的过场",
        "这一场主要是在**给出或铺陈情况**，而不是让局势变糟、掉头或了结旧账？",
    ),
    "升级": (
        "压力、威胁或冲突加剧，方向不变",
        "局势是不是变得更糟、更紧，但**走向没有掉头**？",
    ),
    "转折": (
        "局势反向：优势逆转、信任破裂、做出不可逆的选择",
        "有什么**掉头**了吗？某件做完就回不去的事发生了吗？",
    ),
    "回收": (
        "兑现此前明确埋下的伏笔",
        "这一场闭合的是**哪一条**之前埋过的线？说得出来才算。",
    ),
}

# The three labels folded into 信息, kept so a later round can split it back out
# once reader-knowledge state makes the distinction decidable. Measured against
# the gold set: three-way collapse 0.800, any two-way merge only 0.45–0.50.
MERGED_INTO_INFO = ("建立", "揭示", "过渡")

FUNCTION_NAMES = list(FUNCTIONS)


def taxonomy_block() -> str:
    """The label list rendered for a prompt — meaning plus the disambiguating test."""
    return "\n".join(
        f"· {name}：{meaning}（判据：{test}）"
        for name, (meaning, test) in FUNCTIONS.items()
    )


LLM_SYSTEM = (
    "你是小说结构分析员。判断给定片段**主要**承担哪一种叙事功能，只回答其中一个词：\n"
    + " / ".join(FUNCTION_NAMES)
    + "\n\n"
    + taxonomy_block()
    + "\n\n"
    "判断的是「这一场把故事状态改成了什么」，不是「写的什么内容」，也不是「写得像什么」。\n"
    "关键区分：**回收**必须能指出它闭合了此前埋下的哪一条线；说不出对应埋设的算**信息**。\n"
    "**信息**是正当功能，不是缺陷——交代情况、补全背景、以及只起连接缓冲的过场都算信息，\n"
    "不必为了显得有戏而硬判成升级或转折。\n"
    "只输出那一个词，不要解释。"
)
