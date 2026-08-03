# -*- coding: utf-8 -*-
"""Generate ab_plan.json and ab3_materials.json from project 7 data.

These are the input files for eval/run_three_arm.py, needed for the
blind review regeneration (T2-3).
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.world import WorldSetting
from app.models.style_override import StyleOverride
from sqlalchemy import select


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # Get first chapter with substantial content
        chapters = (
            await db.execute(
                select(Chapter)
                .where(Chapter.project_id == 7)
                .order_by(Chapter.order_index)
            )
        ).scalars().all()

        if not chapters:
            raise SystemExit("No chapters found in project 7")

        ch = chapters[0]
        fragment = ch.content[:800] if ch.content else ""

        # Characters
        chars = (
            await db.execute(
                select(Character).where(Character.project_id == 7)
            )
        ).scalars().all()

        # World settings
        world = (
            await db.execute(
                select(WorldSetting).where(WorldSetting.project_id == 7)
            )
        ).scalars().all()

        # Style samples (from overrides where accepted)
        overrides = (
            await db.execute(
                select(StyleOverride).where(StyleOverride.project_id == 7)
            )
        ).scalars().all()

    # Build plan
    ab_plan = {
        "goal": "推进主线剧情，揭示世界观的一角",
        "desire": "主角想弄清楚异常事件的真相",
        "conflict": "周围人不相信主角的发现",
        "info_shift": "读者获得新线索但主角仍困惑",
        "emotion_curve": "日常 → 违和 → 紧张 → 暂时平息",
        "must_include": [
            "主角发现某个异常细节",
            "至少一个配角否认或忽视该细节",
            "场景结束时回到日常表面",
        ],
        "must_not": [
            "直接揭示超自然存在的真实身份",
            "主角获得决定性证据",
            "使用命运的齿轮等俗套表达",
        ],
        "end_state": "reader_curiosity_up, character_frustrated",
        "grounded": [],
        "chapter_id": ch.id if chapters else 1,
    }

    # Build materials
    ab3_materials = {
        "fragment": fragment,
        "characters": [
            {
                "name": c.name,
                "summary": c.summary or "",
            }
            for c in chars
        ],
        "world": [
            {
                "category": w.category or "规则",
                "title": w.title,
                "content": w.content or "",
            }
            for w in world
        ],
        "style_samples": [
            ov.accepted_body[:500]
            for ov in overrides
            if ov.accepted_body and len(ov.accepted_body.strip()) > 100
        ][:4],
    }

    out_dir = os.path.join(os.path.dirname(__file__), "..", "eval")
    with open(os.path.join(out_dir, "ab_plan.json"), "w", encoding="utf-8") as f:
        json.dump(ab_plan, f, ensure_ascii=False, indent=2)
    with open(os.path.join(out_dir, "ab3_materials.json"), "w", encoding="utf-8") as f:
        json.dump(ab3_materials, f, ensure_ascii=False, indent=2)

    print(f"Generated ab_plan.json ({len(ab_plan['must_include'])} must_include)")
    print(f"Generated ab3_materials.json "
          f"({len(ab3_materials['characters'])} chars, "
          f"{len(ab3_materials['world'])} world, "
          f"{len(ab3_materials['style_samples'])} style samples)")
    print(f"Fragment: {len(ab3_materials['fragment'])} chars")
    print(f"\nNext: python eval/run_three_arm.py --plan eval/ab_plan.json "
          f"--materials eval/ab3_materials.json --out-dir <REPO_EXTERNAL_DIR>")


if __name__ == "__main__":
    asyncio.run(main())
