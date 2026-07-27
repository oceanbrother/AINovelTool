# -*- coding: utf-8 -*-
"""Long-form health report — the questions a chapter-at-a-time view cannot answer.

Writing forward one scene at a time hides the failures that only exist across
chapters: a thread planted twenty chapters ago and quietly abandoned, a payoff
recorded before its own setup, a character who says a thing the timeline says
they have no way of knowing. None of that is visible while drafting, and all of
it is cheap to check once the structure is recorded.

Two tiers, kept apart because their costs differ by orders of magnitude:

  结构层    pure SQL over foreshadowing, chapters and the knowledge timeline.
            Free, deterministic, always runs. Catches bookkeeping errors —
            which are the author's own mistakes, not the model's.
  正文核对层 opt-in (--check-prose). Resolves what must not be revealed as of
            each chapter and checks the written text against exactly those
            constraints, reusing refine.verify_draft. One judge call per
            chapter, so it is a deliberate spend rather than a default.

The second tier is the one that needs saying plainly: knowing what a character
may know became possible only once awareness had a timeline. The constraint was
always derivable; what was missing was "as of when".

    python eval/run_longform_report.py --project-id 7 [--check-prose]

Nothing here is written back to the database — it is a report, and the author
decides what to act on.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.foreshadowing import Foreshadowing
from app.models.knowledge_event import KnowledgeEvent
from app.models.story_fact import StoryFact
from app.schemas.refine import ScenePlan
from app.services import knowledge, refine

# A thread left open this long is worth flagging — not an error, but the kind of
# thing that is invisible while drafting and obvious to a reader.
STALE_AFTER_CHAPTERS = 8


def _rate(part: int, whole: int) -> str:
    return f"{part}/{whole}" + (f" = {part / whole * 100:.0f}%" if whole else "")


async def structural(db, project_id: int) -> None:
    chapters = list((await db.execute(
        select(Chapter).where(Chapter.project_id == project_id)
        .order_by(Chapter.order_index)
    )).scalars().all())
    order_of = {c.id: c.order_index for c in chapters}
    latest = max(order_of.values(), default=0)
    threads = list((await db.execute(
        select(Foreshadowing).where(Foreshadowing.project_id == project_id)
    )).scalars().all())
    facts = list((await db.execute(
        select(StoryFact).where(StoryFact.project_id == project_id)
    )).scalars().all())
    events = list((await db.execute(
        select(KnowledgeEvent).where(KnowledgeEvent.project_id == project_id)
    )).scalars().all())

    print(f"=== 结构层（{len(chapters)} 章 · {len(threads)} 条伏笔 · "
          f"{len(facts)} 条事实 · {len(events)} 条认知变化）===")

    closed = [t for t in threads if t.status == "closed"]
    print(f"\n伏笔回收率: {_rate(len(closed), len(threads))}")

    # Threads whose payoff predates their setup are excluded: they are reported
    # below as errors, and averaging them in would let bad bookkeeping quietly
    # drag the distance negative — a statistic that hides the fault that caused it.
    spans = [
        order_of[t.payoff_chapter_id] - order_of[t.setup_chapter_id]
        for t in closed
        if t.setup_chapter_id in order_of
        and t.payoff_chapter_id in order_of
        and order_of[t.payoff_chapter_id] >= order_of[t.setup_chapter_id]
    ]
    if spans:
        print(f"  平均铺垫距离: {statistics.mean(spans):.1f} 章"
              f"（中位 {statistics.median(spans):.1f}，范围 {min(spans)}–{max(spans)}）")
    else:
        print("  平均铺垫距离: 无可计算样本（回收的伏笔未记录埋设/回收章）")

    stale = [
        t for t in threads
        if t.status == "open"
        and t.setup_chapter_id in order_of
        and latest - order_of[t.setup_chapter_id] >= STALE_AFTER_CHAPTERS
    ]
    if stale:
        print(f"\n⚠ 埋下超过 {STALE_AFTER_CHAPTERS} 章仍未回收: {len(stale)} 条")
        for t in stale[:5]:
            print(f"    · {t.title}（第 {order_of[t.setup_chapter_id]} 章埋下，"
                  f"已过 {latest - order_of[t.setup_chapter_id]} 章）")

    # --- bookkeeping errors: cheap to find, easy to make, invisible while writing
    problems: list[str] = []
    for t in threads:
        if (
            t.setup_chapter_id in order_of
            and t.payoff_chapter_id in order_of
            and order_of[t.payoff_chapter_id] < order_of[t.setup_chapter_id]
        ):
            problems.append(f"伏笔「{t.title}」的回收章早于埋设章")
        if t.status == "closed" and not t.payoff_chapter_id:
            problems.append(f"伏笔「{t.title}」标记为已回收，但没有记录回收章")

    rank = {"unknown": 0, "suspects": 1, "knows": 2, "believes_false": 1}
    by_holder: dict[tuple[int, str, int | None], list[tuple[int, str]]] = {}
    for e in events:
        at = order_of.get(e.chapter_id, -1) if e.chapter_id else -1
        by_holder.setdefault((e.fact_id, e.holder_type, e.holder_id), []).append(
            (at, e.level)
        )
    for (fact_id, holder, hid), seq in by_holder.items():
        seq.sort()
        for (a_at, a), (b_at, b) in zip(seq, seq[1:]):
            # forgetting is a legitimate plot device, but it is worth surfacing
            # rather than assuming — most of the time it is a typo
            if rank.get(b, 0) < rank.get(a, 0):
                who = holder if holder == "reader" else f"角色{hid}"
                problems.append(
                    f"事实 #{fact_id} 的「{who}」认知回退：第 {a_at} 章 {a} → 第 {b_at} 章 {b}"
                )

    orphan_events = [e for e in events if e.chapter_id and e.chapter_id not in order_of]
    if orphan_events:
        problems.append(f"{len(orphan_events)} 条认知变化指向已删除的章节（按开篇起处理）")

    untracked = [
        f for f in facts
        if not any(e.fact_id == f.id for e in events) and f.reader_level == "unknown"
    ]

    print(f"\n结构错误: {len(problems)} 处")
    for p in problems[:8]:
        print(f"  ⚠ {p}")
    if untracked:
        print(f"\n提示: {len(untracked)} 条事实读者始终未知且没有任何时间线 —— "
              "它们会在每一章都产生禁令，考虑补上释放节点")


async def check_prose(db, project_id: int) -> None:
    """Check written chapters against the constraints that applied when they happened.

    Same checklist verification the write loop uses, pointed at finished prose
    instead of a draft. A hit means the text does something the timeline says was
    not yet permissible — usually a reveal that arrived early.
    """
    chapters = list((await db.execute(
        select(Chapter).where(Chapter.project_id == project_id)
        .order_by(Chapter.order_index)
    )).scalars().all())
    names = dict((await db.execute(
        select(Character.id, Character.name).where(Character.project_id == project_id)
    )).all())
    print(f"\n=== 正文核对层（{len(chapters)} 章，每章一次裁判调用）===")
    if not names:
        print("  项目无角色，跳过")
        return

    total_violations = 0
    for ch in chapters:
        text = (ch.content or "").strip()
        if not text:
            continue
        constraints = await refine.derive_constraints(
            db, project_id, chapter_id=ch.id
        )
        if not constraints:
            print(f"  第{ch.order_index}章《{ch.title}》: 该章无适用禁令，跳过")
            continue
        plan = ScenePlan(must_not=constraints)
        # the chapter can be long; the check reads its opening, where a premature
        # reveal is most likely to be planted
        verdict = await refine.verify_draft(text[:3000], plan)
        bad = [c for c in verdict.checks if not c.satisfied]
        total_violations += len(bad)
        status = "✓ 无越界" if not bad else f"⚠ {len(bad)} 处越界"
        print(f"  第{ch.order_index}章《{ch.title}》: {status}（核对 {len(verdict.checks)} 条）")
        for c in bad:
            print(f"      · {c.text}")
            if c.evidence:
                print(f"        依据：{c.evidence[:60]}")
    print(f"\n越界合计: {total_violations} 处")
    if total_violations:
        print("  注意：这不必然是错误——作者可能有意提前揭示。它标出的是"
              "「正文与你登记的时间线不一致」，两者哪个该改由你定。")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--check-prose", action="store_true",
                    help="额外扫描已写章节（每章一次裁判调用，花钱）")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        await structural(db, args.project_id)
        if args.check_prose:
            await check_prose(db, args.project_id)


if __name__ == "__main__":
    asyncio.run(main())
