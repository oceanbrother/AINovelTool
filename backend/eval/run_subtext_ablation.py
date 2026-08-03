# -*- coding: utf-8 -*-
"""A/B: does injecting emotional subtext reduce direct-emotion telling?

Compares two arms against the same scene plan:

  A 续写 baseline — plain continue, no subtext
  B 精修 + 潜台词 — plan-conditioned generation with subtext injected

Metrics (zero-LLM, program-side):
  * direct-emotion sentence count (rhythm.direct_emotion_sentences)
  * concrete-detail density (ratio of specific objects/actions to abstractions)
  * stock-phrase count (cliche.find_cliches)

The subtext feature's value proposition is: "telling the model what to show
instead of telling it not to tell produces measurably fewer direct-emotion
sentences." This is a program check — the project has evidence that explicit
ordered constraints work (must_include 59→93%) and statistics don't (rhythm),
so the subtext feature is designed as the former.

    python eval/run_subtext_ablation.py --project-id 7 [--num 4]

Costs LLM credit (~3 calls per direction). Prints incrementally.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.core import llm
from app.core.config import settings
from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.schemas.refine import ScenePlan, SubtextPlan
from app.services import refine, rhythm, cliche, generation


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--num", type=int, default=4, help="number of directions to test")
    ap.add_argument("--chapter-id", type=int, default=0)
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        chapters = (await db.execute(
            select(Chapter).where(Chapter.project_id == args.project_id).order_by(
                Chapter.order_index
            ).limit(1)
        )).scalars().all()
        if not chapters:
            raise SystemExit("No chapters found")
        chapter = chapters[0]

    print(f"=== 潜台词 A/B (project {args.project_id}, chapter {chapter.order_index or 1}) ===")
    print(f"模型 {settings.llm_model} · 温度 {settings.llm_temperature}\n")

    # Shared direction for both arms
    fragment = (chapter.content or "")[-800:]
    results = []

    for n in range(1, args.num + 1):
        print(f"--- 方向 {n}/{args.num} ---", flush=True)

        # Get a direction by composing candidates first
        candidates = await refine.compose_candidates(db, args.project_id, fragment, num_candidates=3)
        if not candidates.candidates:
            print("  无候选 → 跳过")
            continue
        c = candidates.candidates[0]

        # Arm A: baseline — plain continue without subtext
        print("  A 续写 baseline ...", end=" ", flush=True)
        context_a, chunks_a, styles_a = await generation.build_imitation_context(
            db, chapter, c.summary
        )
        system_a = await refine.prompts.resolve(db, "generation.continue")
        draft_a = await llm.complete(
            [{"role": "system", "content": system_a},
             {"role": "user", "content": context_a + "\n\n【方向指引】" + c.summary}],
            max_tokens=llm.PROSE_MAX_TOKENS, **llm.NO_REASONING, _op="subtext_a",
        )
        print(f"{len(draft_a)}字", flush=True)

        # Arm B: 精修 + subtext
        print("  B 精修+潜台词 ...", end=" ", flush=True)
        # Build a ScenePlan with explicit subtext
        plan_b = ScenePlan(
            goal="推进情节并暴露人物内心",
            desire=c.summary,
            conflict=c.conflict_source,
            emotion_curve=c.emotion_arc or "试探→不安→短暂失控→克制",
            must_include=[f"与「{c.summary[:30]}」相关的具体事件"],
            must_not=["直接揭示全部真相", "人物直接宣布自己的深层情感"],
            subtext=SubtextPlan(
                surface_event="人物在外界推动下做出反应",
                hidden_need="希望被某人真正看见",
                denied_emotion="害怕自己无足轻重",
                masking_behavior="用玩笑和日常琐事转移注意力",
                rupture_moment="有人无意间触到最在意的那件事",
                emotional_residue="短暂暴露后迅速恢复平静，但读者知道不一样了",
                emotion_explicitness=0.25,
            ),
        )
        draft_b = ""
        async for kind, data in refine.refine_write_stream(
            db, chapter, plan_b, instruction=c.summary, max_attempts=1, two_stage=True
        ):
            if kind == "result":
                draft_b, _, _ = data
        print(f"{len(draft_b)}字", flush=True)

        # Program metrics
        metrics_a = {
            "direct_emotion": len(rhythm.direct_emotion_sentences(draft_a)),
            "cliches": len(cliche.find_cliches(draft_a)),
            "chars": len(draft_a),
        }
        metrics_b = {
            "direct_emotion": len(rhythm.direct_emotion_sentences(draft_b)),
            "cliches": len(cliche.find_cliches(draft_b)),
            "chars": len(draft_b),
        }
        winner = (
            "B" if metrics_b["direct_emotion"] < metrics_a["direct_emotion"]
            else "A" if metrics_a["direct_emotion"] < metrics_b["direct_emotion"]
            else "="
        )
        print(f"  A: {metrics_a}  B: {metrics_b}  直接情绪较少: {winner}", flush=True)
        results.append((metrics_a, metrics_b, winner))

    # Summary
    print("\n===== 汇总 =====")
    a_wins = sum(1 for _, _, w in results if w == "A")
    b_wins = sum(1 for _, _, w in results if w == "B")
    ties = sum(1 for _, _, w in results if w == "=")
    avg_a = sum(r[0]["direct_emotion"] for r in results) / max(len(results), 1)
    avg_b = sum(r[1]["direct_emotion"] for r in results) / max(len(results), 1)
    print(f"直接情绪句均值: A={avg_a:.1f}  B={avg_b:.1f}")
    print(f"B更少: {b_wins}/{len(results)}  A更少: {a_wins}/{len(results)}  平: {ties}/{len(results)}")
    if b_wins > a_wins:
        print("→ 潜台词注入有效减少了直接情绪句")
    elif a_wins > b_wins:
        print("→ 潜台词注入未显示效果，需检查 subtext 是否被有效传达")
    else:
        print("→ 样本不足或效果不显著")


if __name__ == "__main__":
    asyncio.run(main())
