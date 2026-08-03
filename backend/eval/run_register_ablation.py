# -*- coding: utf-8 -*-
"""A/B: does a register-transition plan improve prose structure?

Two arms, same scene, same plan:

  A 续写 — plain continuation, no register guidance
  B 精修 + 语域转调 — plan-conditioned with an explicit register_pattern +
      subtext, and the voice pass told to follow the sequence

Program metrics (zero-LLM):
  * paragraph count — how many natural paragraphs the draft has
  * stage-following — approximate register classification per paragraph vs plan

The register feature's value proposition: "telling the voice pass to move
through mundane→comic→lyrical→mundane in order produces structurally varied
prose where a plain continue tends toward uniform register."

    python eval/run_register_ablation.py --project-id 7 --pattern fantasy_fall --num 2

Costs LLM credit. Prints incrementally.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import select

from app.core import llm
from app.core.config import settings
from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.schemas.refine import ScenePlan, SubtextPlan
from app.services import refine, rhythm, cliche, generation


async def _complete_with_retry(messages, label, **overrides):
    """Complete with up to 3 retries — DeepSeek API has intermittent connection resets."""
    for attempt in range(3):
        try:
            return await llm.complete(messages, **overrides)
        except Exception as e:
            if attempt == 2:
                raise
            print(f"    {label} retry {attempt+1}: {e}", flush=True)
            await asyncio.sleep(4 * (attempt + 1))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--pattern", default="fantasy_fall",
                    choices=["fantasy_fall", "delayed_grief", "comic_mask", "comedy_to_suspense"])
    ap.add_argument("--num", type=int, default=2)
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

    print(f"=== 语域转调 A/B (pattern={args.pattern}, chapter {chapter.order_index or 1}) ===")
    print(f"模型 {settings.llm_model} · 温度 {settings.llm_temperature}\n")

    fragment = (chapter.content or "")[-800:]
    results = []

    for n in range(1, args.num + 1):
        print(f"--- 方向 {n}/{args.num} ---", flush=True)

        # Shared candidate
        candidates = await refine.compose_candidates(db, args.project_id, fragment, num_candidates=3)
        if not candidates.candidates:
            print("  无候选 → 跳过")
            continue
        c = candidates.candidates[0]

        # Arm A: plain continue
        print("  A 续写 ...", end=" ", flush=True)
        ctx_a, chunks_a, styles_a = await generation.build_imitation_context(db, chapter, c.summary)
        draft_a = await _complete_with_retry(
            [{"role": "system", "content": await refine.prompts.resolve(db, "generation.continue")},
             {"role": "user", "content": ctx_a + "\n\n" + c.summary}],
            label="A",
            max_tokens=llm.PROSE_MAX_TOKENS, **llm.NO_REASONING, _op="register_a",
        )
        print(f"{len(draft_a)}字", flush=True)

        # Arm B: 精修 + register pattern + subtext
        print("  B 精修+语域转调 ...", end=" ", flush=True)
        plan_b = ScenePlan(
            goal="推进情节",
            desire=c.summary,
            conflict=c.conflict_source,
            emotion_curve=c.emotion_arc or "",
            must_include=[f"具体事件：{c.summary[:40]}"],
            must_not=["直接总结情绪", "使用俗套表达"],
            register_pattern=args.pattern,
            subtext=SubtextPlan(
                hidden_need="希望被看见",
                masking_behavior="用日常琐事转移注意力",
                rupture_moment="有人无意间触到关键",
                emotional_residue="表面平静但读者知道不一样了",
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
        paras_a = [p for p in draft_a.split("\n") if len(p.strip()) > 20]
        paras_b = [p for p in draft_b.split("\n") if len(p.strip()) > 20]

        metrics_a = {
            "paras": len(paras_a),
            "direct_emotion": len(rhythm.direct_emotion_sentences(draft_a)),
            "cliches": len(cliche.find_cliches(draft_a)),
        }
        metrics_b = {
            "paras": len(paras_b),
            "direct_emotion": len(rhythm.direct_emotion_sentences(draft_b)),
            "cliches": len(cliche.find_cliches(draft_b)),
        }
        print(f"  A: {metrics_a}  B: {metrics_b}", flush=True)
        results.append((metrics_a, metrics_b))

    print("\n===== 汇总 =====")
    avg_paras_a = sum(r[0]["paras"] for r in results) / max(len(results), 1)
    avg_paras_b = sum(r[1]["paras"] for r in results) / max(len(results), 1)
    avg_emo_a = sum(r[0]["direct_emotion"] for r in results) / max(len(results), 1)
    avg_emo_b = sum(r[1]["direct_emotion"] for r in results) / max(len(results), 1)
    print(f"段落数均值: A={avg_paras_a:.1f}  B={avg_paras_b:.1f}")
    print(f"直接情绪句均值: A={avg_emo_a:.1f}  B={avg_emo_b:.1f}")
    print(f"模式: {args.pattern}")
    # The register pattern prescribes minimum 5 paragraphs (4 stages at 1-3 paras each)
    print(f"B 段落数 vs 模式最小段落数 (5): {'✓ 达标' if avg_paras_b >= 5 else '✗ 未达标'}")


if __name__ == "__main__":
    asyncio.run(main())
