# -*- coding: utf-8 -*-
"""A/B: does splitting writing into content-then-voice beat doing both at once?

One call is currently asked for events, continuity, plan constraints and a
target voice simultaneously. The claim under test is that these compete: prose
aiming at a voice will blur an event to keep a sentence, and a draft aiming at
constraints reads like a synopsis. Splitting them should let each pass do one
job — but that is a hypothesis, and this project has twice found such
hypotheses to measure as noise or worse.

One variable, everything else fixed — the same plans, the same chapter, the same
verifier:

  arm B (baseline)  one call: plan + style samples + constraints
  arm A (two-stage) content pass with no style samples, then a voice pass
                    forbidden from changing events or information boundaries

Two metrics:

  约束兑现率  the primary one, and the reason the voice pass is verified
              separately. A rewrite that reads better while quietly dropping a
              required object is a regression, not an improvement.
  style 分    the judge, median of 3, since a single call swings on identical
              input.

Also reported: how often the voice pass *lowered* constraint satisfaction and
had to be discarded. That number is the real risk of this design.

    python eval/run_twostage_ablation.py --project-id 7 --chapter-id 3 [--n 6]

Costs credit: roughly 3 generations + 9 judge calls per plan.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics

import httpx
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.schemas.refine import PlanCandidate
from app.services import imitation, refine

# Generic directions: no private plot names, so this harness stays repo-safe.
DIRECTIONS = [
    "主角决定弄清刚才那个异常，暗中留意周围人的反应",
    "有人来找主角说话，话里带着他没听懂的暗示",
    "主角回到住处，发现有人来过的痕迹",
    "一场原本轻松的谈话因为一句话变得紧绷",
    "主角在人群里看见一个不该出现的身影",
    "夜里主角被吵醒，外面有动静",
]


async def _retry(factory, attempts: int = 4, delay: float = 4.0):
    for i in range(attempts):
        try:
            return await factory()
        except httpx.HTTPError as exc:
            if i == attempts - 1:
                raise
            print(f"    (retry {i + 1}: {type(exc).__name__})")
            await asyncio.sleep(delay * (i + 1))


async def _write(db, chapter, plan, two_stage: bool):
    """Drain the write loop, returning (draft, attempts)."""
    result = ("", [])
    async for kind, data in refine.refine_write_stream(
        db, chapter, plan, None, max_attempts=1, two_stage=two_stage
    ):
        if kind == "result":
            draft, attempts, _clues = data
            result = (draft, attempts)
    return result


def _fulfilment(attempts) -> float:
    if not attempts or not attempts[-1].checks:
        return 1.0
    last = attempts[-1].checks
    return sum(c.satisfied for c in last) / len(last)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--chapter-id", type=int, required=True)
    ap.add_argument("--n", type=int, default=6)
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        chapter = await db.get(Chapter, args.chapter_id)
        if chapter is None or chapter.project_id != args.project_id:
            raise SystemExit("chapter not found in that project")
        fragment = (chapter.content or "")[-300:]
        if len(fragment) < 50:
            raise SystemExit("chapter has too little text to plan from")

        style_refs: list[str] = []
        fa, fb, sa, sb = [], [], [], []
        discarded = 0

        print(f"=== 两阶段 A/B（n={args.n}）===")
        for i, direction in enumerate(DIRECTIONS[: args.n], 1):
            candidate = PlanCandidate(summary=direction)
            planned = await _retry(
                lambda: refine.expand_plan(db, args.project_id, fragment, candidate)
            )
            plan = planned.plan
            if not plan.must_include and not plan.must_not:
                print(f"  {i}. 计划无可校验约束，跳过")
                continue

            draft_b, att_b = await _retry(lambda: _write(db, chapter, plan, False))
            draft_a, att_a = await _retry(lambda: _write(db, chapter, plan, True))
            # a discarded voice pass shows up as the loop keeping the plain draft
            if len(att_a) >= 2 and sum(c.satisfied for c in att_a[-1].checks) < sum(
                c.satisfied for c in att_a[-2].checks
            ):
                discarded += 1

            if not style_refs:
                _c, _ch, styles = await refine.generation.build_imitation_context(
                    db, chapter, plan.goal or chapter.title or ""
                )
                style_refs = [s.content for s in styles]

            va = await _retry(lambda: imitation.judge_draft_stable(draft_a, style_refs))
            vb = await _retry(lambda: imitation.judge_draft_stable(draft_b, style_refs))
            ra, rb = _fulfilment(att_a), _fulfilment(att_b)
            fa.append(ra); fb.append(rb)
            sa.append(va["style_score"]); sb.append(vb["style_score"])
            print(f"  {i}. 兑现 A={ra:.0%} B={rb:.0%}  |  style A={va['style_score']} "
                  f"B={vb['style_score']}", flush=True)

    if not fa:
        print("no comparable runs")
        return
    n = len(fa)
    mean = statistics.mean
    print("\n===== 汇总 =====")
    print(f"n={n}")
    print(f"【主指标】约束兑现率  A(两阶段)={mean(fa):.1%}  B(单阶段)={mean(fb):.1%}"
          f"  差={mean(fa) - mean(fb):+.1%}")
    print(f"【副指标】style 分     A={mean(sa):.2f}  B={mean(sb):.2f}"
          f"  差={mean(sa) - mean(sb):+.2f}")
    print(f"声音实现被判回退而丢弃: {discarded}/{n}"
          "  ← 这是两阶段设计的真实风险")


if __name__ == "__main__":
    asyncio.run(main())
