# -*- coding: utf-8 -*-
"""Backfill scene_tag for a project's style samples (anchor-vector NN).

Pure vector classification — reuses each sample's stored embedding, no LLM and
no re-embedding. Idempotent unless --force (re-classifies already-tagged rows).

    python scripts/classify_style_scenes.py --project-id 7 [--force]
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from sqlalchemy import select, update

from app.db import AsyncSessionLocal
from app.models.setting_chunk import SettingChunk
from app.services import scene


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--force", action="store_true", help="re-tag already-tagged rows")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        stmt = select(SettingChunk).where(
            SettingChunk.project_id == args.project_id,
            SettingChunk.source_type == "style",
            SettingChunk.embedding.isnot(None),
        )
        if not args.force:
            stmt = stmt.where(SettingChunk.scene_tag.is_(None))
        rows = (await db.execute(stmt)).scalars().all()
        print(f"classifying {len(rows)} style samples…")
        if not rows:
            return

        anchors = await scene.anchor_vectors_public()
        counts: Counter = Counter()
        for chunk in rows:
            tag = scene.classify_vector(list(chunk.embedding), anchors)
            chunk.scene_tag = tag
            counts[tag] += 1
        await db.commit()

    print("done. distribution:")
    for tag, n in counts.most_common():
        print(f"  {tag:<4} {n}")


if __name__ == "__main__":
    asyncio.run(main())
