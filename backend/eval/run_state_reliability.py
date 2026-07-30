# -*- coding: utf-8 -*-
"""Test-retest reliability of the discrete state scales (B6 人物压力 / B7 叙事压力).

This runs BEFORE any state-layer feature is built, and it is deliberately not a
comparison against human labels. It asks a cheaper and more damning question:

    label the same scene twice, with the same prompt, and see if the labeller
    agrees with ITSELF.

If it does not, comparing it to a human gold standard is meaningless — the
disagreement would be noise, not a taxonomy problem, and no amount of prompt
work on the *definitions* would fix it. This project has already been bitten
once by the reverse mistake: two machine labellers agreed with each other at
0.675 while both were wrong, because nobody measured the right thing first.

Two axes, not one. A character can be calm while the reader is terrified
(dramatic irony), and a character can be in agony during a scene that carries no
narrative pressure at all (a flashback whose outcome is known). Collapsing them
would destroy exactly the gap that makes the pair useful.

**Quadratic-weighted kappa, not plain kappa.** These are ordinal scales, so
confusing 2 with 3 must cost far less than confusing 1 with 5. Plain kappa
treats every disagreement as total and would understate reliability on an
ordinal scale by construction.

Reported alongside, because a high number can be an artefact:

  分布            a labeller that always answers 3 gets perfect exact-agreement
                  and QWK 0 — the distribution is what catches that.
  精确/±1 一致率  interpretable without knowing what kappa is.
  退化基线        QWK of "always answer the modal value", printed so the headline
                  number is never read on its own.

Gate (from the roadmap's 止损 for R4): the **bootstrap CI lower bound** of QWK
must clear 0.60 on both axes before the scale may drive automatic extraction.
The point estimate is not the gate — at this n it sits roughly 0.25 above its own
lower bound, so reading it alone would wave through a scale that is coin-flip
reliable. Below the gate, B6/B7 degrade to author-filled only.

Checked before either of those: whether the two axes are distinguishable at all.
If cross-axis QWK is as high as each axis's test-retest QWK, the gap between them
— the only thing two axes buy over one — is the same size as the noise, and no
sample size fixes that.

    python eval/run_state_reliability.py --project-id 7 [--limit 46]

Costs credit: 2 judge calls per scene.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import random
import re
from collections import Counter

import httpx
from sqlalchemy import select

from app.core import llm
from app.core.config import settings
from app.db import AsyncSessionLocal
from app.models.chapter import Chapter

GATE_QWK = 0.60

# Anchors are concrete and behavioural on purpose. "中等压力" is unlabelable;
# "他在权衡，但还有退路" can be checked against the text.
_SYSTEM = """你是叙事分析标注员。读一个场景，给两个独立的五档评分。

【人物压力】视角人物此刻承受的压力（看人物，不看读者）
 1 无压力：处境安全，没有需要应付的事
 2 轻压力：有点不对劲，但还能照常生活
 3 中压力：必须做点什么了，还有退路
 4 高压力：退路正在消失，代价已经开始付
 5 极限：正在失去无法挽回的东西

【叙事压力】读者此刻感受到的紧张度（看读者，不看人物）
 1 松弛：读者在休息、在了解世界
 2 微悬：有个没答的问题挂着
 3 明确悬念：读者知道有坏事要来，不知道是什么
 4 紧绷：坏事正在发生，读者算得出代价
 5 顶点：本章最重的一击

两个分数可以差很多。人物平静而读者恐惧（读者比人物知道得多）是常见情况，
反过来也有（人物在痛苦，但读者已知结局，不紧张）。不要让它们互相靠拢。

只输出 JSON，不要解释：{"人物压力": <1-5>, "叙事压力": <1-5>}"""


def _parse(text: str) -> tuple[int, int] | None:
    m = re.search(r"\{.*?\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
        a, b = int(d["人物压力"]), int(d["叙事压力"])
    except (ValueError, KeyError, TypeError):
        return None
    return (a, b) if 1 <= a <= 5 and 1 <= b <= 5 else None


def quadratic_weighted_kappa(a: list[int], b: list[int], k: int = 5) -> float:
    """QWK on 1..k ordinal labels. Returns 0.0 when expected disagreement is 0."""
    n = len(a)
    if n == 0:
        return 0.0
    obs = [[0] * k for _ in range(k)]
    for x, y in zip(a, b):
        obs[x - 1][y - 1] += 1
    ha, hb = Counter(a), Counter(b)
    num = den = 0.0
    for i in range(k):
        for j in range(k):
            w = ((i - j) ** 2) / ((k - 1) ** 2)
            exp = ha[i + 1] * hb[j + 1] / n
            num += w * obs[i][j]
            den += w * exp
    return 1.0 - num / den if den else 0.0


async def _label(scene: str, attempts: int = 3) -> tuple[int, int] | None:
    msgs = [{"role": "system", "content": _SYSTEM}, {"role": "user", "content": scene}]
    for i in range(attempts):
        try:
            out = await llm.complete(msgs, model=settings.llm_judge_model)
        except httpx.HTTPError:
            await asyncio.sleep(3 * (i + 1))
            continue
        parsed = _parse(out)
        if parsed:
            return parsed
    return None


def bootstrap_ci(
    r1: list[int], r2: list[int], reps: int = 10000, seed: int = 0
) -> tuple[float, float]:
    """Percentile CI for QWK by resampling scenes.

    Present because the point estimate alone already cost this project one wrong
    verdict: 0.800 was called a pass before anyone printed the majority-class
    baseline it happened to equal. At n≈46 the CI on an ordinal kappa is roughly
    ±0.25 wide, which is easily the difference between "usable" and "unusable",
    so the gate is decided by the lower bound and never by the headline.
    """
    rng = random.Random(seed)
    n = len(r1)
    vals = []
    for _ in range(reps):
        idx = [rng.randrange(n) for _ in range(n)]
        vals.append(
            quadratic_weighted_kappa([r1[i] for i in idx], [r2[i] for i in idx])
        )
    vals.sort()
    return vals[int(0.025 * reps)], vals[int(0.975 * reps)]


def _report(name: str, r1: list[int], r2: list[int]) -> tuple[float, float]:
    n = len(r1)
    exact = sum(x == y for x, y in zip(r1, r2)) / n
    within1 = sum(abs(x - y) <= 1 for x, y in zip(r1, r2)) / n
    qwk = quadratic_weighted_kappa(r1, r2)
    lo, hi = bootstrap_ci(r1, r2)
    # degenerate control: what would "always answer the modal value" score?
    modal = Counter(r1 + r2).most_common(1)[0][0]
    qwk_flat = quadratic_weighted_kappa(r1, [modal] * n)
    dist = Counter(r1 + r2)
    top = (dist[4] + dist[5]) / (2 * n)

    verdict = "✓ 过闸" if lo > GATE_QWK else (
        "✗ 证据不足（点估计够，下界不够）" if qwk >= GATE_QWK else "✗ 未过闸"
    )
    print(f"\n--- {name} (n={n}) ---")
    print(f"  QWK(重测)     {qwk:.3f}  95%CI [{lo:.3f}, {hi:.3f}]   {verdict}"
          f"（闸门：下界 > {GATE_QWK}）")
    print(f"  精确一致率     {exact:.1%}")
    print(f"  ±1 一致率      {within1:.1%}")
    print(f"  分布 1-5      " + " ".join(f"{d}:{dist.get(d,0):>3}" for d in range(1, 6))
          + f"    4-5 档占 {top:.0%}")
    print(f"  退化基线      恒答 {modal} 时 QWK={qwk_flat:.3f}"
          "  ← 主指标必须显著高于它")
    return qwk, lo


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--limit", type=int, default=0, help="0 = 全部场景")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == args.project_id)
                .order_by(Chapter.order_index)
            )
        ).scalars().all()

    scenes = [
        s.strip()
        for ch in rows
        for s in (ch.content or "").split("※")
        if len(s.strip()) > 200
    ]
    if args.limit:
        scenes = scenes[: args.limit]
    if not scenes:
        raise SystemExit("没有可标注的场景")

    print(f"=== 状态量表重测信度（{settings.llm_judge_model}, temp="
          f"{settings.llm_temperature}）===")
    print(f"场景 {len(scenes)} 个 · 每个标两遍 · 共 {len(scenes) * 2} 次调用\n")

    a6, a7, b6, b7, dropped = [], [], [], [], 0
    for i, sc in enumerate(scenes, 1):
        first, second = await asyncio.gather(_label(sc), _label(sc))
        if first is None or second is None:
            dropped += 1
            print(f"  {i:>3}. 解析失败，丢弃")
            continue
        a6.append(first[0]); a7.append(first[1])
        b6.append(second[0]); b7.append(second[1])
        flag = "" if first == second else "  ←不一致"
        print(f"  {i:>3}. 人物 {first[0]}/{second[0]}  叙事 {first[1]}/{second[1]}{flag}",
              flush=True)

    if not a6:
        raise SystemExit("全部解析失败")

    q6, lo6 = _report("B6 人物压力", a6, b6)
    q7, lo7 = _report("B7 叙事压力", a7, b7)

    # The two axes must not collapse into each other, or one is dead weight.
    # The comparison that matters is cross-axis agreement against the labeller's
    # OWN noise: if they are the same size, the gap between the axes — which is
    # the entire reason for having two — cannot be told apart from error.
    cross = quadratic_weighted_kappa(a6, a7)
    same = sum(x == y for x, y in zip(a6, a7)) / len(a6)
    noise = min(q6, q7)
    print("\n--- 两轴独立性 ---")
    print(f"  同一遍里两个分数相同的比例  {same:.1%}")
    print(f"  两轴之间的 QWK             {cross:.3f}")
    print(f"  重测 QWK（噪声下限）        {noise:.3f}")
    redundant = cross >= noise - 0.05
    print("  → " + ("两轴差异 ≈ 标注噪声，落差无法被可靠测出：其中一轴是冗余的"
                    if redundant else "两轴差异显著大于噪声，落差可测"))

    print("\n===== 裁决 =====")
    if dropped:
        print(f"（丢弃 {dropped} 个解析失败的场景）")
    if redundant:
        print("止损：不按两轴建 B4/B9/G3。两个分数分别测再相减 = 噪声叠加，")
        print("      应改为直接问那一个落差（读者比人物多知道多少），单次测量。")
    elif lo6 > GATE_QWK and lo7 > GATE_QWK:
        print("两轴均过闸 → 量表可驱动自动抽取，可以继续建 B4/B9/G3。")
    elif max(q6, q7) >= GATE_QWK:
        print(f"证据不足：点估计够但 CI 下界不够（n={len(a6)} 太小）。")
        print("      扩样本再判，期间 B6/B7 只做人工填写。")
    else:
        print("两轴均未过闸 → 按路线图止损：B6/B7 降级为纯人工填写，不做自动抽取。")


if __name__ == "__main__":
    asyncio.run(main())
