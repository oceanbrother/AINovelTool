# -*- coding: utf-8 -*-
"""Derive the paragraph layer — the unit rhythm is measured in.

Segments were the wrong granularity for mode labelling: at ~450 chars they span
~8 paragraphs, so 54% of them mixed dialogue with narration and a single label
could never fit. Rhythm is the alternation *between* modes, so the unit has to
be small enough to hold one.

Paragraphs are recovered by splitting the stored segment text on newlines — the
segmentation and its embeddings are not redone, so this step is free.

Labelling is layered cheapest-first:
  1. rule      quotation marks settle 对话 outright, no model consulted
  2. anchor    the remaining four modes via services/mode.py (local, free)
  3. llm/gold  measured against the others, never assumed correct

    python scripts/build_paragraphs.py --work 龙族 --replace
    python scripts/build_paragraphs.py --work 龙族 --export-gold 50
    python scripts/build_paragraphs.py --work 龙族 --anchor --chapters 8

Gold worksheets embed corpus prose and are written under style_data/
(gitignored). Only aggregate agreement numbers may leave this machine.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import random

import httpx
from sqlalchemy import delete, select

from app.core import llm
from app.core.config import settings
from app.core.embedding import embed_texts
from app.db import AsyncSessionLocal
from app.models.corpus_paragraph import CorpusParagraph
from app.models.corpus_segment import CorpusSegment
from app.services import mode, rhythm

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "style_data")
GOLD_MIN_CHARS = 8      # shorter fragments are ambiguous; don't burn hand-labelling on them
GOLD_DIALOGUE_SHARE = 0.2   # a fifth of the gold set checks the rule; the rest are hard cases


async def build(db, work: str, replace: bool) -> int:
    segments = list(
        (
            await db.execute(
                select(CorpusSegment)
                .where(CorpusSegment.work == work)
                .order_by(CorpusSegment.chapter_no, CorpusSegment.seq)
            )
        ).scalars().all()
    )
    if not segments:
        raise SystemExit(f"no segments for '{work}' — run build_corpus.py first")

    if replace:
        await db.execute(delete(CorpusParagraph).where(CorpusParagraph.work == work))
        await db.commit()
    elif (
        await db.execute(
            select(CorpusParagraph.id).where(CorpusParagraph.work == work).limit(1)
        )
    ).first():
        raise SystemExit(f"paragraphs for '{work}' already exist; pass --replace")

    rows: list[CorpusParagraph] = []
    seq_by_chapter: dict[int, int] = {}
    for seg in segments:
        for para in (p.strip() for p in seg.text.split("\n")):
            if not para:
                continue
            seq = seq_by_chapter.get(seg.chapter_no, 0) + 1
            seq_by_chapter[seg.chapter_no] = seq
            dialogue = rhythm.is_dialogue_paragraph(para)
            rows.append(
                CorpusParagraph(
                    work=work,
                    chapter_no=seg.chapter_no,
                    seq=seq,
                    segment_id=seg.id,
                    text=para,
                    char_len=len(para),
                    is_dialogue=dialogue,
                    mode_rule="对话" if dialogue else None,
                )
            )
    for i in range(0, len(rows), 1000):
        db.add_all(rows[i : i + 1000])
        await db.commit()
    return len(rows)


async def run_anchor(db, work: str, chapters: int) -> None:
    """Classify the four non-dialogue modes. Dialogue is already settled by rule."""
    stmt = select(CorpusParagraph).where(
        CorpusParagraph.work == work, CorpusParagraph.is_dialogue.is_(False)
    )
    if chapters:
        stmt = stmt.where(CorpusParagraph.chapter_no <= chapters)
    rows = list((await db.execute(stmt.order_by(CorpusParagraph.id))).scalars().all())
    print(f"anchor-classifying {len(rows)} non-dialogue paragraphs"
          f"{f' (chapters 1-{chapters})' if chapters else ''}…")

    vectors: list[list[float]] = []
    for i in range(0, len(rows), 128):
        vectors.extend(await embed_texts([r.text for r in rows[i : i + 128]]))
        if (i // 128) % 5 == 0:
            print(f"  {min(i + 128, len(rows))}/{len(rows)}", flush=True)
    tags = await mode.classify_vectors(vectors)
    for row, tag in zip(rows, tags):
        row.mode_anchor = tag
    # dialogue paragraphs inherit the rule's verdict, so every row ends up labelled
    dialogue_rows = (
        await db.execute(
            select(CorpusParagraph).where(
                CorpusParagraph.work == work, CorpusParagraph.is_dialogue.is_(True)
            )
        )
    ).scalars().all()
    for row in dialogue_rows:
        row.mode_anchor = "对话"
    await db.commit()

    dist: dict[str, int] = {}
    for t in tags:
        dist[t] = dist.get(t, 0) + 1
    dist["对话"] = dist.get("对话", 0) + len(dialogue_rows)
    print("mode distribution:", dict(sorted(dist.items(), key=lambda kv: -kv[1])))


_LLM_SYSTEM = (
    "你是文学文本分析员。判断给定的一个自然段**主要**采用哪种呈现方式，只回答其中一个词：\n"
    + " / ".join(mode.MODE_NAMES)
    + "\n对话=引号内的说话。\n"
    "描写=外部世界的呈现，**包括人物的身体动作**——环境、外貌、氛围、以及当场发生的动作事件。\n"
    "心理=想法、感受、回忆等内心活动。\n"
    "叙述=概述、交代背景、时间流逝（压缩时间，而非当场展开）。\n"
    "判断依据是「这段怎么写的」，不是「写的什么事」。\n"
    "特别注意：人物动作属于**描写**，不要因为有动作就归为别的类。\n"
    "只输出那一个词，不要解释。"
)

LLM_CONCURRENCY = 4


async def _retry(factory, attempts: int = 4, delay: float = 3.0):
    """The judge flakes through the proxy; retry transient network errors."""
    for i in range(attempts):
        try:
            return await factory()
        except httpx.HTTPError:
            if i == attempts - 1:
                raise
            await asyncio.sleep(delay * (i + 1))


async def run_llm(db, work: str, limit: int, seed: int, chapters: int) -> None:
    """Third labeller, scoped to what the statistics actually consume.

    Only non-dialogue paragraphs are sent: the quotation-mark rule settles
    dialogue at .875 against gold, better than either learned labeller, so
    paying a model to re-decide it would be waste.

    Three groups, in priority order:
      gold        the only way to measure the judge against a human
      chapters    a CONTIGUOUS run — the transition matrix needs adjacency,
                  so a random scatter across the book would be useless
      tails       each chapter's last paragraph, for the chapter-end profile
    """
    # Gold ids only decide labelling priority, so a malformed worksheet must not
    # take the whole run down with it — hand-edited JSON does get typos.
    gold_ids: set[int] = set()
    for name in ("mode_gold.v1.json", "mode_gold.todo.json"):
        path = os.path.join(OUT_DIR, name)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                gold_ids = {int(i["id"]) for i in json.load(fh).get("items", [])}
            break
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            print(f"  (skipping {name}: {exc})")

    rows = list(
        (
            await db.execute(
                select(CorpusParagraph)
                .where(CorpusParagraph.work == work, CorpusParagraph.mode_llm.is_(None))
                .order_by(CorpusParagraph.chapter_no, CorpusParagraph.seq)
            )
        ).scalars().all()
    )
    tail_ids = {}
    for r in rows:
        tail_ids[r.chapter_no] = r.id  # ordered, so the last write is the tail

    def needs_model(r: CorpusParagraph) -> bool:
        return not r.is_dialogue  # the rule already answers dialogue

    gold_rows = [r for r in rows if r.id in gold_ids and needs_model(r)]
    picked_ids = {r.id for r in gold_rows}
    run_rows = [
        r for r in rows
        if r.chapter_no <= chapters and needs_model(r) and r.id not in picked_ids
    ]
    picked_ids |= {r.id for r in run_rows}
    tail_rows = [
        r for r in rows
        if r.id in tail_ids.values() and needs_model(r) and r.id not in picked_ids
    ]
    picked = gold_rows + run_rows + tail_rows
    if limit:
        picked = picked[:limit]
    print(f"llm-labelling {len(picked)} non-dialogue paragraphs with "
          f"{settings.llm_judge_model} ({len(gold_rows)} gold + "
          f"{len(run_rows)} chapters 1-{chapters} + {len(tail_rows)} chapter tails)")

    sem = asyncio.Semaphore(LLM_CONCURRENCY)
    done = 0

    async def one(row: CorpusParagraph) -> None:
        nonlocal done
        async with sem:
            raw = await _retry(
                lambda: llm.complete(
                    [
                        {"role": "system", "content": _LLM_SYSTEM},
                        {"role": "user", "content": row.text},
                    ],
                    model=settings.llm_judge_model,
                    temperature=0.0,
                )
            )
        hit = [m for m in mode.MODE_NAMES if m in raw]
        row.mode_llm = hit[0] if hit else None
        done += 1
        if done % 25 == 0:
            print(f"  {done}/{len(picked)}", flush=True)

    await asyncio.gather(*(one(r) for r in picked))
    await db.commit()
    ok = sum(1 for r in picked if r.mode_llm)
    print(f"llm labelled {ok}/{len(picked)} (unparseable: {len(picked) - ok})")


def export_gold(rows: list[CorpusParagraph], n: int, seed: int) -> str:
    """Sample a hand-labelling worksheet, weighted toward the hard cases.

    Dialogue is settled by a quotation-mark rule, so only a fifth of the sheet
    checks that rule; the rest are non-dialogue paragraphs, where the classifier
    has to separate 动作/描写/心理/叙述 and where errors actually live.
    """
    rng = random.Random(seed)
    usable = [r for r in rows if r.char_len >= GOLD_MIN_CHARS]
    dialogue = [r for r in usable if r.is_dialogue]
    other = [r for r in usable if not r.is_dialogue]
    n_dlg = min(int(n * GOLD_DIALOGUE_SHARE), len(dialogue))
    sample = rng.sample(dialogue, n_dlg) + rng.sample(other, min(n - n_dlg, len(other)))
    sample.sort(key=lambda r: (r.chapter_no, r.seq))

    payload = {
        "task": "rendering-mode gold standard — 人工标注（自然段级）",
        "labels": mode.MODE_NAMES,
        "howto": (
            "给每个 item 的 label 填一个标签。判据是「这段是怎么写的」而非「写的是什么事」：\n"
            "对话=引号内的说话；动作=身体动作或事件发生；描写=环境/外貌/氛围；"
            "心理=想法、感受、回忆；叙述=概述、交代背景、时间流逝。\n"
            "拿不准填 '?'，统计时会剔除。"
        ),
        "items": [
            {
                "id": r.id,
                "chapter_no": r.chapter_no,
                "seq": r.seq,
                "text": r.text,
                "label": "",
            }
            for r in sample
        ],
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.abspath(os.path.join(OUT_DIR, "mode_gold.todo.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return path


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--anchor", action="store_true")
    ap.add_argument("--chapters", type=int, default=0,
                    help="limit anchor labelling to the first N chapters (0 = all)")
    ap.add_argument("--export-gold", type=int, default=0)
    ap.add_argument("--llm", action="store_true", help="third labeller (costs credit)")
    ap.add_argument("--limit", type=int, default=0, help="cap for --llm (0 = no cap)")
    ap.add_argument("--llm-chapters", type=int, default=8,
                    help="contiguous chapters to label for the transition matrix")
    ap.add_argument("--reset-llm", action="store_true",
                    help="clear existing mode_llm first (needed after a taxonomy change)")
    ap.add_argument("--seed", type=int, default=20260725)
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(
                select(CorpusParagraph.id).where(CorpusParagraph.work == args.work).limit(1)
            )
        ).first()
        if not existing or args.replace:
            total = await build(db, args.work, args.replace)
            print(f"built {total} paragraphs")

        rows = list(
            (
                await db.execute(
                    select(CorpusParagraph)
                    .where(CorpusParagraph.work == args.work)
                    .order_by(CorpusParagraph.chapter_no, CorpusParagraph.seq)
                )
            ).scalars().all()
        )
        dlg = sum(1 for r in rows if r.is_dialogue)
        print(f"{len(rows)} paragraphs | 规则判为对话 {dlg} ({dlg / len(rows) * 100:.1f}%) "
              f"| 均长 {sum(r.char_len for r in rows) / len(rows):.0f} 字")

        if args.export_gold:
            path = export_gold(rows, args.export_gold, args.seed)
            print(f"gold worksheet → {path}\n  填好 label 后另存为 mode_gold.v1.json")
        if args.anchor:
            await run_anchor(db, args.work, args.chapters)
        if args.reset_llm:
            for r in rows:
                r.mode_llm = None
            await db.commit()
            print("cleared existing mode_llm labels")
        if args.llm:
            await run_llm(db, args.work, args.limit, args.seed, args.llm_chapters)


if __name__ == "__main__":
    asyncio.run(main())
