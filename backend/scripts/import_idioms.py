# -*- coding: utf-8 -*-
"""Bulk-import idioms from the chinese-xinhua dataset (MIT licensed).

Source: https://github.com/pwxcoo/chinese-xinhua (data/idiom.json, ~31k rows).
We keep the subset that reads like a living vocabulary rather than a museum:
4-character idioms that ship with a dictionary example sentence (a good proxy
for common usage) and a substantive explanation — roughly 10k rows.

    python scripts/import_idioms.py --source path/to/idiom.json [--limit N]

Embeds in batches; safe to re-run (existing idioms are skipped).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time

from sqlalchemy import select

from app.core.embedding import embed_texts
from app.db import AsyncSessionLocal
from app.models.idiom import Idiom

BATCH = 64


def load_rows(path: str, limit: int | None) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    rows = [
        d for d in data
        if len(d.get("word", "")) == 4
        and d.get("example", "").strip() not in ("", "无")
        and len(d.get("explanation", "")) >= 10
    ]
    return rows[:limit] if limit else rows


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True, help="path to idiom.json")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    rows = load_rows(args.source, args.limit)
    print(f"candidate rows after filtering: {len(rows)}")

    async with AsyncSessionLocal() as db:
        existing = set((await db.execute(select(Idiom.text))).scalars().all())
        rows = [d for d in rows if d["word"] not in existing]
        print(f"new rows to import: {len(rows)}")

        t0 = time.perf_counter()
        for i in range(0, len(rows), BATCH):
            batch = rows[i : i + BATCH]
            texts = [f"{d['word']}：{d['explanation']}" for d in batch]
            vectors = await embed_texts(texts)
            for d, vec in zip(batch, vectors):
                db.add(
                    Idiom(
                        text=d["word"],
                        meaning=d["explanation"],
                        tags=[],
                        usage_context=d.get("example") or None,
                        embedding=vec,
                    )
                )
            await db.commit()
            done = min(i + BATCH, len(rows))
            rate = done / (time.perf_counter() - t0)
            print(f"  {done}/{len(rows)}  ({rate:.0f} rows/s)", flush=True)

    print("import complete.")


if __name__ == "__main__":
    asyncio.run(main())
