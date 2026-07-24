# -*- coding: utf-8 -*-
"""Judge scale calibration — is the style_score bar (>=7) even reachable?

Uses the EXACT rubric the imitation gate uses (imitation.judge_draft) and asks:
where does real human prose land on it?

  ceiling: a REAL style-library passage judged against OTHER held-out real
           passages of the same scene (the author judged against the author —
           the maximum a style imitation could ever aspire to)
  floor:   plainly-written neutral prose (my own, non-copyrighted) judged
           against real passages — should score low if the axis discriminates

Reading:
  * ceiling ~9-10 & floor ~1-3  → rubric spreads well, 7 is a fair bar, and
    AI drafts stuck at 4-6 (see run_scene_ablation) are a GENERATION gap.
  * ceiling ~6-7                → even the author's own text can't clear 7;
    the bar / rubric is miscalibrated → a SCORING problem.
  * ceiling ~= floor            → the style_score axis doesn't discriminate →
    the metric is noise.

Prints scores only, never the private passages.

    python eval/run_judge_scale.py --project-id 7
"""
from __future__ import annotations

import argparse
import asyncio
import statistics

import httpx
from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.setting_chunk import SettingChunk
from app.services import imitation


async def judge(draft: str, refs: list[str], attempts: int = 5, delay: float = 4.0):
    """imitation.judge_draft with retry — the LLM API flakes through the proxy."""
    for i in range(attempts):
        try:
            return await imitation.judge_draft(draft, refs)
        except httpx.HTTPError as e:
            if i == attempts - 1:
                raise
            print(f"    (retry {i+1}: {type(e).__name__})")
            await asyncio.sleep(delay * (i + 1))

SCENES = ["战斗", "对话", "心理", "日常", "景物"]
CANDIDATES_PER_SCENE = 2
REFS = 2

# neutral off-voice controls (my own plain Chinese — clearly not a literary voice)
FLOOR_TEXTS = [
    "会议定于周三下午两点在三楼会议室召开，请各部门负责人准时参加，"
    "并提前准备好本季度的工作总结材料，会后统一收取。",
    "使用前请仔细阅读说明书。将设备连接电源后，长按开关键三秒即可启动，"
    "指示灯变为绿色表示就绪，红色表示需要充电。",
]


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    args = ap.parse_args()

    ceiling_style: list[int] = []
    ceiling_ai: list[int] = []
    floor_style: list[int] = []

    async with AsyncSessionLocal() as db:
        async def scene_samples(scene: str) -> list[str]:
            rows = (
                await db.execute(
                    select(SettingChunk.content)
                    .where(
                        SettingChunk.project_id == args.project_id,
                        SettingChunk.source_type == "style",
                        SettingChunk.scene_tag == scene,
                    )
                    .order_by(SettingChunk.id)
                    .limit(CANDIDATES_PER_SCENE + REFS)
                )
            ).scalars().all()
            return list(rows)

        print("== ceiling: 真·原文 vs 同场景留出原文 ==")
        for scene in SCENES:
            s = await scene_samples(scene)
            if len(s) < CANDIDATES_PER_SCENE + REFS:
                print(f"  [skip] {scene}: 样本不足")
                continue
            refs = s[CANDIDATES_PER_SCENE:]  # held out
            for i in range(CANDIDATES_PER_SCENE):
                v = await judge(s[i], refs)
                ceiling_style.append(v["style_score"])
                ceiling_ai.append(v["ai_flavor"])
                print(f"  {scene}: style={v['style_score']} ai={v['ai_flavor']}")

        # floor: neutral text vs a spread of real passages
        ref_pool = await scene_samples("对话")
        print("\n== floor: 中性异质文本 vs 真·原文 ==")
        for txt in FLOOR_TEXTS:
            v = await judge(txt, ref_pool[:REFS])
            floor_style.append(v["style_score"])
            print(f"  中性文本: style={v['style_score']} ai={v['ai_flavor']}")

    print("\n===== 汇总 =====")
    if ceiling_style:
        print(f"天花板 style: 均值 {statistics.mean(ceiling_style):.2f}  "
              f"范围 {min(ceiling_style)}–{max(ceiling_style)}  n={len(ceiling_style)}")
        print(f"天花板 ai_flavor: 均值 {statistics.mean(ceiling_ai):.2f} "
              f"(真人文本应当很低)")
    if floor_style:
        print(f"地板 style: 均值 {statistics.mean(floor_style):.2f}  n={len(floor_style)}")
    print("参照：AI 仿写稿 style 约 4–6（run_scene_ablation）")


if __name__ == "__main__":
    asyncio.run(main())
