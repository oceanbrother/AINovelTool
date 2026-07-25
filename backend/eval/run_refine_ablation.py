# -*- coding: utf-8 -*-
"""A/B: does 精修 (explicit plan + verify/rewrite loop) fulfil more of the
author's intended constraints than plain 续写?

The ScenePlan's must_include / must_not ARE the author's explicit intent, and
they're objectively checkable. So we hold the plan fixed and measure how well
each generation mode satisfies it:

  For each candidate direction (same chapter throughout):
    plan = expand_plan(candidate)              # the constraint spec
    Arm 续写   : continue_chapter_stream(instruction = candidate.summary)
                 — the REAL 续写 path, given only the one-line direction, NOT
                   the explicit constraints (this is how 续写 is actually used)
    Arm 精修单稿: refine_write_stream's first draft (plan-conditioned, no loop)
    Arm 精修终稿: refine_write_stream's best draft (plan + verify + rewrite)
    verify every draft against the SAME plan → fulfilment rate.

The asymmetry is the point, not a flaw: 续写 isn't handed the constraints, and
the gap this measures is exactly what the planning layer fills. Reporting three
arms separates the value of plan-conditioning (续写→单稿) from the value of the
verify/rewrite loop (单稿→终稿).

    python eval/run_refine_ablation.py --project-id 7 [--num 4]

Costs LLM credit (~5-8 calls per direction, verifies on the pro judge). Prints
incrementally so a mid-run stop still yields data; nothing is written to repo.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics

import httpx

from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.models.project import Project
from app.services import generation, refine
from sqlalchemy import select


async def _retry(coro_factory, attempts: int = 4, delay: float = 4.0):
    """DeepSeek flakes through the proxy; retry transient network errors."""
    for i in range(attempts):
        try:
            return await coro_factory()
        except httpx.HTTPError as e:
            if i == attempts - 1:
                raise
            print(f"    (retry {i+1}: {type(e).__name__})")
            await asyncio.sleep(delay * (i + 1))


async def _drain_continue(db, chapter, instruction) -> str:
    text = ""
    async for kind, data in generation.continue_chapter_stream(db, chapter, instruction):
        if kind == "token":
            text += data
    return text


async def _drain_refine(db, chapter, plan):
    """Returns (attempts) — the RefineAttempt list, each with .checks."""
    attempts = []
    async for kind, data in refine.refine_write_stream(db, chapter, plan, None, max_attempts=2):
        if kind == "result":
            _draft, attempts, _clues = data
    return attempts


def _rates(checks) -> dict:
    """fulfilment / must_include hit / must_not avoid, from a checks list."""
    inc = [c for c in checks if c.kind == "include"]
    exc = [c for c in checks if c.kind == "exclude"]
    total = len(checks)
    return {
        "fulfill": sum(c.satisfied for c in checks) / total if total else 1.0,
        "inc_hit": (sum(c.satisfied for c in inc) / len(inc)) if inc else None,
        "exc_avoid": (sum(c.satisfied for c in exc) / len(exc)) if exc else None,
        "n": total,
    }


def _best(attempts):
    """The attempt refine_write_stream would return (most constraints met)."""
    return max(attempts, key=lambda a: sum(c.satisfied for c in a.checks))


def _fmt(r: dict) -> str:
    inc = f"{r['inc_hit']*100:.0f}%" if r["inc_hit"] is not None else "—"
    exc = f"{r['exc_avoid']*100:.0f}%" if r["exc_avoid"] is not None else "—"
    return f"兑现 {r['fulfill']*100:5.1f}%  (必须出现 {inc} / 规避 {exc})"


async def run(project_id: int, num: int) -> None:
    xu, jd1, jdf = [], [], []  # 续写 / 精修单稿 / 精修终稿  fulfilment rates
    xu_exc, jdf_exc = [], []   # must_not avoidance (the "don't spoil" metric)

    async with AsyncSessionLocal() as db:
        proj = await db.get(Project, project_id)
        chapter = (
            await db.execute(
                select(Chapter).where(Chapter.project_id == project_id)
                .order_by(Chapter.order_index)
            )
        ).scalars().first()
        if not chapter or not (chapter.content or "").strip():
            print("no chapter with content"); return
        print(f"project {project_id} 《{proj.title if proj else '?'}》 / 章 《{chapter.title}》")
        fragment = chapter.content[-300:]

        cres = await _retry(lambda: refine.compose_candidates(db, project_id, fragment, num))
        print(f"候选 {len(cres.candidates)} 条\n")

        for i, cand in enumerate(cres.candidates):
            plan = await _retry(lambda: refine.expand_plan(db, project_id, fragment, cand))
            plan = plan.plan
            if not plan.must_include and not plan.must_not:
                print(f"[skip {i}] 计划无可校验约束"); continue

            print(f"■ 走向{i}: {cand.summary[:40]}  (约束 {len(plan.must_include)}必须/{len(plan.must_not)}禁止, 场景={plan.scene_tag})")

            draft_c = await _retry(lambda: _drain_continue(db, chapter, cand.summary))
            v_c = await _retry(lambda: refine.verify_draft(draft_c, plan))
            attempts = await _retry(lambda: _drain_refine(db, chapter, plan))
            v_1 = attempts[0]
            v_f = _best(attempts)

            r_c, r_1, r_f = _rates(v_c.checks), _rates(v_1.checks), _rates(v_f.checks)
            print(f"   续写      {_fmt(r_c)}")
            print(f"   精修单稿  {_fmt(r_1)}")
            print(f"   精修终稿  {_fmt(r_f)}  ({len(attempts)}稿)")

            xu.append(r_c["fulfill"]); jd1.append(r_1["fulfill"]); jdf.append(r_f["fulfill"])
            if r_c["exc_avoid"] is not None: xu_exc.append(r_c["exc_avoid"])
            if r_f["exc_avoid"] is not None: jdf_exc.append(r_f["exc_avoid"])

    n = len(xu)
    if not n:
        print("no data"); return
    m = statistics.mean
    print("\n===== 汇总 =====")
    print(f"走向数 n={n}")
    print(f"约束兑现率   续写={m(xu)*100:.1f}%  精修单稿={m(jd1)*100:.1f}%  精修终稿={m(jdf)*100:.1f}%")
    if xu_exc and jdf_exc:
        print(f"不能发生·规避率  续写={m(xu_exc)*100:.1f}%  精修终稿={m(jdf_exc)*100:.1f}%")
    wins = sum(1 for a, b in zip(jdf, xu) if a > b)
    ties = sum(1 for a, b in zip(jdf, xu) if abs(a - b) < 1e-9)
    print(f"精修终稿 胜 {wins} / 平 {ties} / 负 {n - wins - ties}  (对 续写)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--num", type=int, default=4)
    args = ap.parse_args()
    asyncio.run(run(args.project_id, args.num))
