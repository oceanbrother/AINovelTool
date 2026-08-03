# -*- coding: utf-8 -*-
"""Export three-arm blind review drafts as pure-prose files.

Runs the same three arms as run_three_arm.py (A: style only, B: full settings,
C: the pipeline) but exports immediately before verification so a transient
network error on the verify call doesn't lose the drafts.

    python scripts/export_blind_review.py --out-dir <REPO_EXTERNAL_DIR>
"""
import argparse
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core import llm
from app.core.config import settings
from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.schemas.refine import ScenePlan
from app.services import refine
from sqlalchemy import select


# A arm: style samples only — the floor
_A_SYSTEM = (
    "你是中文小说写作者。模仿【文风样本】的语感与节奏，写一个场景，2000-2500 字。\n"
    "只借语感，**不得复述样本里的任何句子、人名、地名、专有名词**。\n"
    "不要写设定说明，直接写场景。只输出正文。"
)

# B arm: settings stuffed into prompt — the honest baseline
_B_SYSTEM = (
    "你是中文小说写作者。依据【世界观】【人物】【前文】接着往下写一场，2000-2500 字。\n"
    "人物与世界观规则必须与给定设定一致，不得自造设定。\n"
    "模仿【文风样本】的语感与节奏，但**不得复述样本里的任何句子、人名、地名、专有名词**。\n"
    "不要写设定说明，直接写场景。只输出正文。"
)


def _mats_block(m, *, with_settings):
    styles = "\n---\n".join(m.get("style_samples", []) or ["（无文风样本）"])
    if not with_settings:
        return f"【文风样本】\n{styles}"
    world = "\n".join(
        f"·（{w['category']}）{w['title']}：{w['content']}" for w in m.get("world", [])
    )
    chars = "\n".join(f"·{c['name']}：{c['summary']}" for c in m.get("characters", []))
    return (
        f"【世界观】\n{world}\n\n【人物】\n{chars}\n\n"
        f"【前文】\n{m.get('fragment', '')}\n\n【文风样本】\n{styles}"
    )


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True, help="仓库外目录")
    ap.add_argument("--plan", default="eval/ab_plan.json")
    ap.add_argument("--materials", default="eval/ab3_materials.json")
    args = ap.parse_args()

    p = json.load(open(args.plan, encoding="utf-8"))
    m = json.load(open(args.materials, encoding="utf-8"))
    plan = ScenePlan(
        goal=p["goal"], desire=p["desire"], conflict=p["conflict"],
        info_shift=p["info_shift"], emotion_curve=p["emotion_curve"],
        must_include=p["must_include"], must_not=p["must_not"],
        end_state=p["end_state"], grounded=p.get("grounded", []),
    )
    os.makedirs(args.out_dir, exist_ok=True)
    direction = p["goal"].split("；")[0][:60]
    print(f"共用约束：{len(plan.must_include)} 必须 / {len(plan.must_not)} 禁止")
    print(f"三臂同模型 {settings.llm_model} · 温度 {settings.llm_temperature}\n")

    # Arm A: style only
    print("A 只给文风 ...", flush=True)
    draft_a = await llm.complete(
        [{"role": "system", "content": _A_SYSTEM},
         {"role": "user", "content": _mats_block(m, with_settings=False) + f"\n\n【场景】\n{direction}"}],
        temperature=settings.llm_temperature, max_tokens=llm.PROSE_MAX_TOKENS,
        _op="three_arm_a",
    )
    # Arm B: settings stuffed
    print("B 设定全塞 ...", flush=True)
    draft_b = await llm.complete(
        [{"role": "system", "content": _B_SYSTEM},
         {"role": "user", "content": _mats_block(m, with_settings=True) + f"\n\n【场景】\n{direction}"}],
        temperature=settings.llm_temperature, max_tokens=llm.PROSE_MAX_TOKENS,
        _op="three_arm_b",
    )
    # Arm C: pipeline
    print("C 现有管线 ...", flush=True)
    async with AsyncSessionLocal() as db:
        chapter = await db.get(Chapter, p["chapter_id"])
        draft_c = ""
        attempts_count = 0
        async for kind, data in refine.refine_write_stream(
            db, chapter, plan, None, max_attempts=2, two_stage=True
        ):
            if kind == "result":
                draft_c, attempts, _ = data
                attempts_count = len(attempts)

    drafts = {"A": draft_a, "B": draft_b, "C": draft_c}
    for arm, text in drafts.items():
        path = os.path.join(args.out_dir, f"arm_{arm}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"{arm}: {len(text)} 字 → {path}")

    # Also write the constraint spec (shared by all arms)
    with open(os.path.join(args.out_dir, "constraints.md"), "w", encoding="utf-8") as f:
        f.write("# 三臂共用约束\n\n## 必须出现\n\n")
        for i, x in enumerate(plan.must_include, 1):
            f.write(f"{i}. {x}\n")
        f.write("\n## 不能发生\n\n")
        for i, x in enumerate(plan.must_not, 1):
            f.write(f"{i}. {x}\n")

    print(f"\n盲读材料 → {args.out_dir}")
    print("审阅步骤：")
    print("  1. 不看出处，独立阅读 arm_A.md / arm_B.md / arm_C.md")
    print("  2. 按写作质量排序（不用管是哪个臂生成的）")
    print("  3. 对照 constraints.md 检查关键要求是否满足")
    print("  4. 揭晓 A/B/C 身份，对比自己的排序")


if __name__ == "__main__":
    asyncio.run(main())
