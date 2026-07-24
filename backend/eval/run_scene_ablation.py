# -*- coding: utf-8 -*-
"""A/B: does scene-aligned style recall improve imitation style scores?

Isolates ONE variable — the style samples fed to the generator — while
holding the judge's bar fixed:

  For each generic scene probe (no character names, so this harness is
  repo-safe):
    * scene = classify_text(probe)               # what the product infers
    * scene-aligned samples  = top-k where scene_tag == scene
    * mixed samples          = top-k with no scene filter (old behaviour)
    * gen-refs are ranks 0..G-1 of each set; a HELD-OUT judge-ref is
      ranks G..G+J-1 of the scene-aligned set — same bar for both arms
    * Arm A: generate from scene-aligned gen-refs
    * Arm B: generate from mixed gen-refs
    * judge BOTH drafts against the held-out scene-ref
  style_score(A) vs style_score(B), paired per probe.

Because the judge reference is identical across arms, a higher A means
scene-matched examples produced more on-voice prose against the same
target — not that the judge was handed an easier reference. Also reports
how many mixed gen-refs were off-scene (the filter only helps when they are).

    python eval/run_scene_ablation.py --project-id 7 [--trials 1]

Costs LLM credit: 2 generations + 2 judgements per probe per trial.
Drafts print to stdout only; nothing is written to the repo.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics

import httpx

from app.core import llm
from app.db import AsyncSessionLocal
from app.services import imitation, retrieval, scene


async def _retry(coro_factory, attempts: int = 4, delay: float = 4.0):
    """DeepSeek streams flake; retry transient network errors."""
    for i in range(attempts):
        try:
            return await coro_factory()
        except (httpx.HTTPError,) as e:
            if i == attempts - 1:
                raise
            print(f"    (retry {i+1}: {type(e).__name__})")
            await asyncio.sleep(delay * (i + 1))

# generic scene probes — no private character/plot names
PROBES = [
    "写一段激烈的近身搏斗，约120字",
    "写两个人针锋相对、互相试探的对话，约120字",
    "写一段紧张不安、思绪翻涌的内心独白，约120字",
    "写一段平静无波的日常生活片段，约120字",
    "写一段黄昏城市街景的环境描写，约120字",
]

GEN_REFS = 2      # style samples shown to the generator
JUDGE_REFS = 2    # held-out same-scene samples used as the fixed judge bar

_GEN_SYSTEM = (
    "你是小说代笔。严格模仿【文风样本】的句长节奏、标点密度与用词习惯，"
    "只借语感、不复述内容，完成【任务】。"
)


async def generate(gen_refs: list[str], task: str) -> str:
    block = "\n---\n".join(gen_refs)
    return await llm.complete(
        [
            {"role": "system", "content": _GEN_SYSTEM},
            {"role": "user", "content": f"【文风样本】\n{block}\n\n【任务】{task}"},
        ],
        temperature=0.8,
    )


async def run(project_id: int, trials: int) -> None:
    a_scores: list[int] = []
    b_scores: list[int] = []
    a_ai: list[int] = []
    b_ai: list[int] = []

    async with AsyncSessionLocal() as db:
        for probe in PROBES:
            target = await scene.classify_text(probe)
            aligned = await retrieval.retrieve_settings(
                db, project_id, probe, channel="style",
                scene_tags=[target], top_k=GEN_REFS + JUDGE_REFS, min_score=0.0,
            )
            mixed = await retrieval.retrieve_settings(
                db, project_id, probe, channel="style",
                top_k=GEN_REFS, min_score=0.0,
            )
            if len(aligned) < GEN_REFS + JUDGE_REFS or not mixed:
                print(f"[skip] {probe[:16]} — 样本不足")
                continue

            gen_aligned = [c.content for c in aligned[:GEN_REFS]]
            judge_ref = [c.content for c in aligned[GEN_REFS:GEN_REFS + JUDGE_REFS]]
            gen_mixed = [c.content for c in mixed[:GEN_REFS]]

            print(f"\n■ {probe}  (推断场景={target})")
            for t in range(trials):
                draft_a = await _retry(lambda: generate(gen_aligned, probe))
                draft_b = await _retry(lambda: generate(gen_mixed, probe))
                va = await _retry(lambda: imitation.judge_draft(draft_a, judge_ref))
                vb = await _retry(lambda: imitation.judge_draft(draft_b, judge_ref))
                a_scores.append(va["style_score"]); a_ai.append(va["ai_flavor"])
                b_scores.append(vb["style_score"]); b_ai.append(vb["ai_flavor"])
                print(f"  trial{t+1}: A(场景对齐) style={va['style_score']} ai={va['ai_flavor']}"
                      f"  |  B(混合) style={vb['style_score']} ai={vb['ai_flavor']}")

    n = len(a_scores)
    if not n:
        print("no data"); return
    wins = sum(1 for a, b in zip(a_scores, b_scores) if a > b)
    ties = sum(1 for a, b in zip(a_scores, b_scores) if a == b)
    print("\n===== 汇总 =====")
    print(f"样本对数 n={n}")
    print(f"style 均值  A(场景对齐)={statistics.mean(a_scores):.2f}  B(混合)={statistics.mean(b_scores):.2f}")
    print(f"ai_flavor 均值  A={statistics.mean(a_ai):.2f}  B={statistics.mean(b_ai):.2f}")
    print(f"A 胜 {wins} / 平 {ties} / 负 {n - wins - ties}")
    print(f"A 过 7 分线：{sum(1 for s in a_scores if s >= 7)}/{n}  |  "
          f"B 过 7 分线：{sum(1 for s in b_scores if s >= 7)}/{n}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--trials", type=int, default=1)
    args = ap.parse_args()
    asyncio.run(run(args.project_id, args.trials))
