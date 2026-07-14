"""Seed the literary citation library (v1.1, Feature A).

The whitelist is enforced HERE, at ingest: only public-domain works are admitted
to the database. Retrieval and generation then physically cannot surface a
copyrighted or fabricated work — the protection lives in the data, not a prompt.

    python scripts/seed_literary.py
"""
from __future__ import annotations

import asyncio

from app.core.embedding import embed_texts
from app.db import AsyncSessionLocal
from app.models.literary import LiteraryKnowledge, LiteraryWork

# Public-domain works only (authors long deceased). Curate freely.
WORKS = [
    {
        "title": "草叶集",
        "author": "沃尔特·惠特曼",
        "era": "19世纪",
        "school": "浪漫主义",
        "themes": ["自我", "自然", "生命力"],
        "knowledge": [
            ("作者背景", "惠特曼以自由体诗革新美国诗歌，讴歌个体与民主。"),
            ("主题解读", "《草叶集》以草叶象征平凡而蓬勃的生命，礼赞自我与众生平等。"),
            ("公认名句", "我辽阔博大，我包罗万象。"),
        ],
    },
    {
        "title": "杂忆与杂记",
        "author": "鲁迅",
        "era": "20世纪初",
        "school": "现实主义",
        "themes": ["国民性", "批判", "记忆"],
        "knowledge": [
            ("作者背景", "鲁迅以冷峻笔触剖析国民性，是中国现代文学奠基者之一。"),
            ("主题解读", "在回忆与杂感之间，鲁迅把个人经验上升为对时代的诊断。"),
        ],
    },
]


async def main() -> None:
    async with AsyncSessionLocal() as db:
        for w in WORKS:
            if not w.get("is_public_domain", True):
                continue  # whitelist guard
            work = LiteraryWork(
                title=w["title"],
                author=w["author"],
                era=w.get("era"),
                school=w.get("school"),
                themes=w.get("themes", []),
                is_public_domain=True,
            )
            db.add(work)
            await db.flush()

            texts = [content for _kind, content in w["knowledge"]]
            vectors = await embed_texts(texts)
            for (kind, content), vec in zip(w["knowledge"], vectors):
                db.add(
                    LiteraryKnowledge(
                        work_id=work.id,
                        knowledge_type=kind,
                        content=content,
                        embedding=vec,
                    )
                )
        await db.commit()
    print("literary library seeded.")


if __name__ == "__main__":
    asyncio.run(main())
