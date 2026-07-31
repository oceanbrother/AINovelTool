# -*- coding: utf-8 -*-
"""Label corpus scenes with narrative function, and check the labels are usable.

Function is not a property of a passage read alone: "揭示" means someone now
knows what they did not know a moment ago, and "回收" means a thread planted
earlier came due. Both are claims about what came BEFORE. So every item carries
the tail of the preceding segment as context — a labeller shown only the passage
is being asked to guess.

    python scripts/label_functions.py --work 龙族 --export-gold 40
    python scripts/label_functions.py --work 龙族 --llm --limit 300

The gold worksheet holds corpus prose and is written under style_data/
(gitignored). Only the agreement numbers may leave this machine.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random

import httpx
from sqlalchemy import select

from app.core import llm
from app.core.config import settings
from app.db import AsyncSessionLocal
from app.models.corpus_segment import CorpusSegment
from app.services import function_label

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "style_data")
LLM_CONCURRENCY = 4
BATCH = 25            # commit this often, so a mid-run failure loses at most this many
CONTEXT_CHARS = 120   # tail of the previous segment, enough to place the scene


async def _retry(factory, attempts: int = 4, delay: float = 3.0):
    for i in range(attempts):
        try:
            return await factory()
        except httpx.HTTPError:
            if i == attempts - 1:
                raise
            await asyncio.sleep(delay * (i + 1))


async def load(db, work: str) -> list[CorpusSegment]:
    return list(
        (
            await db.execute(
                select(CorpusSegment)
                .where(CorpusSegment.work == work)
                .order_by(CorpusSegment.chapter_no, CorpusSegment.seq)
            )
        ).scalars().all()
    )


def _context_of(rows: list[CorpusSegment], index: int) -> str:
    """Tail of the previous segment in the same chapter, or a note that it opens one."""
    if index == 0:
        return "（本章开头）"
    prev = rows[index - 1]
    if prev.chapter_no != rows[index].chapter_no:
        return "（本章开头）"
    return "…" + prev.text[-CONTEXT_CHARS:]


def export_gold(rows: list[CorpusSegment], n: int, seed: int) -> str:
    """Sample a worksheet, spread across chapters so it isn't all opening scenes."""
    rng = random.Random(seed)
    # skip the first segment of each chapter: with no preceding context the
    # 建立/揭示 distinction cannot be made fairly
    candidates = [i for i in range(1, len(rows)) if rows[i].chapter_no == rows[i - 1].chapter_no]
    picked = sorted(rng.sample(candidates, min(n, len(candidates))))

    payload = {
        "task": "narrative function gold standard — 人工标注（场景级）",
        "labels": function_label.FUNCTION_NAMES,
        "howto": (
            "判断这一段**把故事状态改成了什么**，不是写了什么内容。\n"
            + function_label.taxonomy_block()
            + "\n关键区分：回收必须说得出它闭合了此前哪一条线；说不出对应埋设的新信息算揭示。\n"
            "拿不准填 '?'，统计时会剔除。**如果很多段都拿不准，说明切块粒度不对——"
            "那本身就是要报告的结果，不要硬猜。**"
        ),
        "items": [
            {
                "id": rows[i].id,
                "chapter_no": rows[i].chapter_no,
                "seq": rows[i].seq,
                "context_before": _context_of(rows, i),
                "text": rows[i].text,
                "label": "",
            }
            for i in picked
        ],
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.abspath(os.path.join(OUT_DIR, "function_gold.todo.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


async def run_llm(
    db, rows: list[CorpusSegment], limit: int, seed: int, gold: str | None = None
) -> None:
    """Label with the judge model — gold items first, so llm-vs-gold is measurable.

    `gold` names the hand-labelled set to prioritise. It used to be a hardcoded
    pair of filenames, which silently mislabelled the wrong 40 segments the
    moment a second gold set existed: the run reported success, the agreement
    script then found 7 overlapping items and printed kappa 0.000. Nothing in
    either output said "these two files are about different scenes".
    """
    gold_ids: set[int] = set()
    candidates = (gold,) if gold else ("function_gold.v1.json", "function_gold.todo.json")
    for name in candidates:
        path = name if os.path.isabs(name) else os.path.join(OUT_DIR, name)
        if not os.path.exists(path):
            if gold:
                raise SystemExit(f"gold file not found: {path}")
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                gold_ids = {int(i["id"]) for i in json.load(fh).get("items", [])}
            break
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            print(f"  (skipping {name}: {exc})")

    by_id = {r.id: i for i, r in enumerate(rows)}
    todo = [r for r in rows if r.func_tag is None]
    gold_rows = [r for r in todo if r.id in gold_ids]
    rest = [r for r in todo if r.id not in gold_ids]
    random.Random(seed).shuffle(rest)
    picked = gold_rows + rest[: max(0, limit - len(gold_rows))]
    print(f"labelling {len(picked)} segments with {settings.llm_judge_model} "
          f"({len(gold_rows)} gold + {len(picked) - len(gold_rows)} sampled)")

    sem = asyncio.Semaphore(LLM_CONCURRENCY)

    async def one(row: CorpusSegment) -> None:
        context = _context_of(rows, by_id[row.id])
        async with sem:
            raw = await _retry(
                lambda: llm.complete(
                    [
                        {"role": "system", "content": function_label.LLM_SYSTEM},
                        {
                            "role": "user",
                            "content": f"【前文】{context}\n\n【待判片段】\n{row.text}",
                        },
                    ],
                    model=settings.llm_judge_model,
                    temperature=0.0,
                )
            )
        hit = [f for f in function_label.FUNCTION_NAMES if f in raw]
        row.func_tag = hit[0] if hit else None

    # Commit per batch, not once at the end. A run that dies partway — an
    # exhausted balance, a dropped connection — used to discard every call it
    # had already paid for. Batching bounds that loss to the batch in flight.
    for start in range(0, len(picked), BATCH):
        batch = picked[start : start + BATCH]
        try:
            await asyncio.gather(*(one(r) for r in batch))
        finally:
            await db.commit()  # keep whatever this batch managed to label
        print(f"  {min(start + BATCH, len(picked))}/{len(picked)}", flush=True)
    ok = sum(1 for r in picked if r.func_tag)
    print(f"labelled {ok}/{len(picked)} (unparseable: {len(picked) - ok})")
    dist: dict[str, int] = {}
    for r in picked:
        if r.func_tag:
            dist[r.func_tag] = dist.get(r.func_tag, 0) + 1
    print("distribution:", dict(sorted(dist.items(), key=lambda kv: -kv[1])))


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--export-gold", type=int, default=0)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--limit", type=int, default=300)
    ap.add_argument("--seed", type=int, default=20260727)
    ap.add_argument("--gold", help="要优先标注的人工金标准文件（默认沿用旧的搜索顺序）")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        rows = await load(db, args.work)
        if not rows:
            raise SystemExit(f"no segments for '{args.work}' — run build_corpus.py first")
        print(f"{len(rows)} segments over {rows[-1].chapter_no} chapters")

        if args.export_gold:
            path = export_gold(rows, args.export_gold, args.seed)
            print(f"gold worksheet → {path}\n  填好 label 后另存为 function_gold.v1.json")
        if args.llm:
            await run_llm(db, rows, args.limit, args.seed, args.gold)


if __name__ == "__main__":
    asyncio.run(main())
