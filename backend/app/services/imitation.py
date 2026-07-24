# -*- coding: utf-8 -*-
"""Imitation mode — generate → self-check → rewrite loop (仿写自检环).

Workflow (one /generate/imitate call):

  1. build the retrieval-grounded context, with style samples injected
  2. generate a draft
  3. self-check the draft on three independent gates:
       a. n-gram overlap vs the injected style samples — the plagiarism gate:
          style may be borrowed, content may not
       b. style-match score from a JUDGE model (deepseek-reasoner by default,
          deliberately different from the generator to dodge self-preference)
       c. AI-flavor score from the same judge (stock phrases, over-neat
          parallelism, hollow ornament — the "一眼AI" tells)
  4. below the bar -> rewrite with the judge's notes as feedback, up to
     max_attempts; return the best draft plus the full attempt report

Revision mode: pass previous_draft + feedback and the loop starts from the
author's own notes instead of a cold generation.
"""
from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncGenerator
from statistics import median

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.core.config import settings
from app.models.chapter import Chapter
from app.schemas.generation import ImitateAttempt
from app.services import generation

# --- gates ---------------------------------------------------------------------
# Calibrated against ground truth (eval/run_judge_scale.py): real human prose
# judged against held-out real prose averages style 7.4 (range 5–9) and only
# clears 7 about 7/10 of the time — so a >=7 single-shot bar is stricter than
# the author's own text, and the judge is high-variance. Hence: floor at 6, and
# denoise each verdict by taking the median of JUDGE_SAMPLES calls.
NGRAM_N = 8            # char n-gram size: 8+ shared chars ≈ verbatim lift
NGRAM_MAX_OVERLAP = 0.05
STYLE_SCORE_MIN = 6    # style-match floor (calibrated to real-text performance)
AI_FLAVOR_MAX = 4      # AI-flavor ceiling (1-10, 10 = reeks of AI)
JUDGE_SAMPLES = 3      # median over N judge calls to cut the judge's variance


def ngram_overlap(text: str, samples: list[str], n: int = NGRAM_N) -> float:
    """Fraction of `text`'s char n-grams that appear verbatim in any sample."""
    clean = re.sub(r"\s", "", text)
    if len(clean) < n:
        return 0.0
    sample_blob = " ".join(re.sub(r"\s", "", s) for s in samples)
    grams = [clean[i : i + n] for i in range(len(clean) - n + 1)]
    hits = sum(1 for g in grams if g in sample_blob)
    return hits / len(grams)


_JUDGE_SYSTEM = (
    "你是严苛的文学编辑。给你若干【文风参考】和一段【待评稿】。"
    "从两个独立维度打分并指出问题：\n"
    "1. style_score（1-10）：待评稿的句长节奏、用词习惯、修辞密度、叙述口吻"
    "与文风参考的接近程度，10 为难以区分。\n"
    "2. ai_flavor（1-10）：待评稿的「AI 腔」程度——套话堆砌、排比过于工整、"
    "空洞形容词、缺乏具体物象、情绪直给不留白。10 为一眼 AI，1 为浑然人写。\n"
    '只输出 JSON：{"style_score": n, "ai_flavor": n, "notes": "一两句具体问题，'
    '给改写者看的"}'
)


async def judge_draft(draft: str, style_refs: list[str]) -> dict:
    refs = "\n---\n".join(style_refs)
    raw = await llm.complete(
        [
            {"role": "system", "content": _JUDGE_SYSTEM},
            {
                "role": "user",
                "content": f"【文风参考】\n{refs}\n\n【待评稿】\n{draft}",
            },
        ],
        model=settings.llm_judge_model,
        temperature=0.0,
    )
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {"style_score": 0, "ai_flavor": 10, "notes": "judge 输出不可解析"}
    try:
        data = json.loads(match.group())
    except json.JSONDecodeError:
        return {"style_score": 0, "ai_flavor": 10, "notes": "judge JSON 解析失败"}
    return {
        "style_score": int(data.get("style_score", 0)),
        "ai_flavor": int(data.get("ai_flavor", 10)),
        "notes": str(data.get("notes", "")),
    }


async def judge_draft_stable(draft: str, style_refs: list[str]) -> dict:
    """Median over JUDGE_SAMPLES judge calls — the judge is high-variance
    (same input can swing style 5↔9), so a single call is an unreliable gate.
    Returns median style/ai and the notes from the run closest to the median."""
    verdicts = await asyncio.gather(
        *(judge_draft(draft, style_refs) for _ in range(JUDGE_SAMPLES))
    )
    style = int(median(v["style_score"] for v in verdicts))
    ai = int(median(v["ai_flavor"] for v in verdicts))
    # notes from the verdict whose style is nearest the median (most typical)
    rep = min(verdicts, key=lambda v: abs(v["style_score"] - style))
    return {"style_score": style, "ai_flavor": ai, "notes": rep["notes"]}


# --- the loop ------------------------------------------------------------------

_IMITATE_EXTRA = (
    "\n\n【修改要求】\n{feedback}\n"
    "依据以上要求重写，其余约束不变。"
)


async def imitate_stream(
    db: AsyncSession,
    chapter: Chapter,
    instruction: str | None,
    previous_draft: str | None,
    feedback: str | None,
    max_attempts: int = 2,
) -> AsyncGenerator[tuple[str, object], None]:
    """The self-check loop as a stage-emitting generator.

    The loop takes 1–3 min (a generate + a judge call per attempt), so instead
    of a black-box wait the UI gets narrated progress. Yields:
      ("stage", str)               human-readable current phase
      ("attempt", ImitateAttempt)  one scorecard as each draft is judged
      ("result", (draft, attempts, clues))   final payload
    """
    yield "stage", "检索文风样本与设定"
    query = (chapter.content[-500:] + " " + (instruction or "")).strip()
    context, chunks, styles = await generation.build_imitation_context(
        db, chapter, query or chapter.title or ""
    )
    style_refs = [s.content for s in styles]

    base_user = context
    if instruction:
        base_user += f"\n\n【方向指引】{instruction}"
    if previous_draft and feedback:
        base_user += (
            f"\n\n【上一稿】\n{previous_draft}\n\n【作者反馈】\n{feedback}\n"
            "在保留上一稿可用之处的前提下按反馈修改。"
        )

    attempts: list[ImitateAttempt] = []
    best_draft = ""
    best_key = -999.0
    notes = None
    for i in range(max_attempts):
        yield "stage", (f"生成第 {i + 1} 稿" if notes is None else f"按裁判意见重写第 {i + 1} 稿")
        user = base_user if notes is None else base_user + _IMITATE_EXTRA.format(feedback=notes)
        draft = await llm.complete(
            [
                {"role": "system", "content": generation._CONTINUE_SYSTEM},
                {"role": "user", "content": user},
            ]
        )
        yield "stage", f"第 {i + 1} 稿自检中（异模型裁判 ×{JUDGE_SAMPLES} 取中位 + 复述检测）"
        overlap = ngram_overlap(draft, style_refs) if style_refs else 0.0
        if style_refs:
            verdict = await judge_draft_stable(draft, style_refs)
        else:
            verdict = {"style_score": 0, "ai_flavor": 10, "notes": "项目内无文风样本"}
        passed = (
            overlap <= NGRAM_MAX_OVERLAP
            and verdict["style_score"] >= STYLE_SCORE_MIN
            and verdict["ai_flavor"] <= AI_FLAVOR_MAX
        )
        attempt = ImitateAttempt(
            attempt=i + 1,
            style_score=verdict["style_score"],
            ai_flavor=verdict["ai_flavor"],
            ngram_overlap=round(overlap, 4),
            passed=passed,
            notes=verdict["notes"],
        )
        attempts.append(attempt)
        yield "attempt", attempt
        # best = highest (style - ai_flavor); plagiarism failures ranked last
        key = (
            float(verdict["style_score"] - verdict["ai_flavor"])
            if overlap <= NGRAM_MAX_OVERLAP
            else -100.0
        )
        if key > best_key:
            best_key, best_draft = key, draft
        if passed:
            break
        notes = verdict["notes"] or "文风贴合度不足，收紧句子节奏。"

    yield "result", (best_draft, attempts, chunks)


async def imitate(
    db: AsyncSession,
    chapter: Chapter,
    instruction: str | None,
    previous_draft: str | None,
    feedback: str | None,
    max_attempts: int = 2,
) -> tuple[str, list[ImitateAttempt], list]:
    """Non-streaming drainer over imitate_stream — for eval scripts and tests."""
    result: tuple = ("", [], [])
    async for kind, payload in imitate_stream(
        db, chapter, instruction, previous_draft, feedback, max_attempts
    ):
        if kind == "result":
            result = payload
    return result
