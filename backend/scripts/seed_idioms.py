"""Seed the idiom library (v1.1, Feature B).

Idioms are a public asset — no copyright concern. Each row is embedded so the
recommender can recall by scene semantics. Expand this list (or load from a CSV)
to a few thousand for a useful recall pool.

    python scripts/seed_idioms.py
"""
from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.embedding import embed_texts
from app.db import AsyncSessionLocal
from app.models.idiom import Idiom

IDIOMS = [
    ("灯火阑珊", "灯光稀疏、将尽的样子", ["夜景", "孤寂", "城市"], "描写夜晚冷清的街景"),
    ("剑拔弩张", "形势紧张，一触即发", ["对峙", "紧张", "冲突"], "两方强者对峙之时"),
    ("不动声色", "内心活动不流露在外", ["沉稳", "心机", "反制"], "暗中识破并反击"),
    ("光怪陆离", "形容现象奇异、色彩繁杂", ["都市", "奇幻", "光影"], "霓虹与超自然交织的画面"),
    ("如临大敌", "好像面对强大的敌人，形容戒备森严", ["戒备", "紧张"], "组织严阵以待"),
    ("暗流涌动", "表面平静而潜藏激烈变化", ["阴谋", "紧张", "伏笔"], "平静下的危机"),
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        existing = set(
            (await db.execute(select(Idiom.text))).scalars().all()
        )
        new = [row for row in IDIOMS if row[0] not in existing]
        if not new:
            print("no new idioms to seed.")
            return
        texts = [f"{text}：{meaning}" for text, meaning, _tags, _ctx in new]
        vectors = await embed_texts(texts)
        for (text, meaning, tags, ctx), vec in zip(new, vectors):
            db.add(
                Idiom(
                    text=text,
                    meaning=meaning,
                    tags=tags,
                    usage_context=ctx,
                    embedding=vec,
                )
            )
        await db.commit()
    print(f"seeded {len(new)} idioms.")


if __name__ == "__main__":
    asyncio.run(main())
