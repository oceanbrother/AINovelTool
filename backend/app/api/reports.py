# -*- coding: utf-8 -*-
"""Long-form health report + information timeline APIs.

  GET /projects/{id}/longform-report  — structural health + optional prose check
  GET /projects/{id}/timeline         — per-fact knowledge timeline for each entity
"""
from __future__ import annotations

import statistics

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.foreshadowing import Foreshadowing
from app.models.knowledge_event import KnowledgeEvent
from app.models.story_fact import StoryFact

router = APIRouter(prefix="/projects", tags=["reports"])

STALE_AFTER_CHAPTERS = 8


@router.get("/{project_id}/longform-report")
async def longform_report(
    project_id: int,
    check_prose: bool = Query(False, description="逐章核对正文是否越界（消耗裁判调用）"),
    db: AsyncSession = Depends(get_session),
):
    """Structural health of a long-form project.

    Returns metrics invisible at chapter-at-a-time drafting:
    foreshadowing payoff rate, stale threads, timeline violations,
    and optionally prose-level knowledge-boundary checks.
    """
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

    # --- Foreshadowing ---
    closed = [t for t in threads if t.status == "closed"]
    spans = [
        order_of[t.payoff_chapter_id] - order_of[t.setup_chapter_id]
        for t in closed
        if t.setup_chapter_id in order_of
        and t.payoff_chapter_id in order_of
        and order_of[t.payoff_chapter_id] >= order_of[t.setup_chapter_id]
    ]
    stale = [
        {
            "title": t.title,
            "setup_chapter": order_of.get(t.setup_chapter_id),
            "chapters_ago": latest - order_of.get(t.setup_chapter_id, latest),
        }
        for t in threads
        if t.status == "open"
        and t.setup_chapter_id in order_of
        and latest - order_of[t.setup_chapter_id] >= STALE_AFTER_CHAPTERS
    ]

    # --- Bookkeeping errors ---
    problems: list[str] = []
    for t in threads:
        if (
            t.setup_chapter_id in order_of and t.payoff_chapter_id in order_of
            and order_of[t.payoff_chapter_id] < order_of[t.setup_chapter_id]
        ):
            problems.append(f"伏笔「{t.title}」回收章早于埋设章")
        if t.status == "closed" and not t.payoff_chapter_id:
            problems.append(f"伏笔「{t.title}」已回收但未记录回收章")

    # Knowledge regressions
    rank = {"unknown": 0, "suspects": 1, "knows": 2, "believes_false": 1}
    by_holder: dict[tuple, list[tuple[int, str]]] = {}
    for e in events:
        at = order_of.get(e.chapter_id, -1) if e.chapter_id else -1
        by_holder.setdefault((e.fact_id, e.holder_type, e.holder_id), []).append(
            (at, e.level)
        )
    for (fact_id, holder, hid), seq in by_holder.items():
        seq.sort()
        for (a_at, a), (b_at, b) in zip(seq, seq[1:]):
            if rank.get(b, 0) < rank.get(a, 0):
                who = "读者" if holder == "reader" else f"角色{hid}"
                problems.append(
                    f"事实#{fact_id}「{who}」认知回退: 第{a_at}章 {a} → 第{b_at}章 {b}"
                )

    # --- Prose check (opt-in, costs LLM) ---
    prose_violations: list[dict] = []
    if check_prose:
        from app.schemas.refine import ScenePlan
        from app.services import refine
        names = dict((await db.execute(
            select(Character.id, Character.name).where(Character.project_id == project_id)
        )).all())
        for ch in chapters:
            text = (ch.content or "").strip()
            if not text:
                continue
            constraints = await refine.derive_constraints(db, project_id, chapter_id=ch.id)
            if not constraints:
                continue
            plan = ScenePlan(must_not=constraints)
            verdict = await refine.verify_draft(text[:3000], plan)
            bad = [c for c in verdict.checks if not c.satisfied]
            for c in bad:
                prose_violations.append({
                    "chapter": ch.order_index,
                    "title": ch.title,
                    "constraint": c.text,
                    "evidence": c.evidence[:100] if c.evidence else "",
                })

    return {
        "chapters": len(chapters),
        "threads_total": len(threads),
        "threads_closed": len(closed),
        "threads_payoff_rate": round(len(closed) / max(len(threads), 1), 3),
        "avg_span_chapters": round(statistics.mean(spans), 1) if spans else None,
        "median_span_chapters": round(statistics.median(spans), 1) if spans else None,
        "stale_threads": stale,
        "stale_count": len(stale),
        "problems": problems,
        "problem_count": len(problems),
        "facts_total": len(facts),
        "events_total": len(events),
        "prose_violations": prose_violations if check_prose else None,
    }


@router.get("/{project_id}/timeline")
async def fact_timeline(
    project_id: int,
    db: AsyncSession = Depends(get_session),
):
    """Per-fact knowledge timeline — who knows what, and when.

    Returns for each fact a list of knowledge events ordered by chapter,
    showing how awareness propagates across characters and the reader.
    """
    facts = list((await db.execute(
        select(StoryFact).where(StoryFact.project_id == project_id)
    )).scalars().all())
    events = list((await db.execute(
        select(KnowledgeEvent).where(KnowledgeEvent.project_id == project_id)
    )).scalars().all())
    chapters = list((await db.execute(
        select(Chapter).where(Chapter.project_id == project_id)
        .order_by(Chapter.order_index)
    )).scalars().all())
    order_of = {c.id: c.order_index for c in chapters}
    names = dict((await db.execute(
        select(Character.id, Character.name).where(Character.project_id == project_id)
    )).all())

    # Group events by fact
    by_fact: dict[int, list[dict]] = {}
    for e in events:
        ch = order_of.get(e.chapter_id) if e.chapter_id else None
        who = "读者" if e.holder_type == "reader" else names.get(e.holder_id, f"角色{e.holder_id}")
        by_fact.setdefault(e.fact_id, []).append({
            "chapter": ch,
            "holder": who,
            "holder_type": e.holder_type,
            "level": e.level,
        })

    timeline = []
    for f in facts:
        entries = sorted(by_fact.get(f.id, []), key=lambda x: x["chapter"] or 0)
        timeline.append({
            "fact_id": f.id,
            "statement": f.statement,
            "reader_level": f.reader_level,
            "is_true": f.is_true,
            "foreshadowing_id": f.foreshadowing_id,
            "events": entries,
            "reveal_chapter": next(
                (e["chapter"] for e in entries
                 if e["holder"] == "读者" and e["level"] == "knows"),
                None,
            ),
        })

    return {
        "project_id": project_id,
        "chapters": len(chapters),
        "facts": timeline,
    }
