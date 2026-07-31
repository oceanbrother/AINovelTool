# -*- coding: utf-8 -*-
"""拆书 — hand-label a reference corpus into a gold standard.

Not project-scoped: a corpus is a book the author is learning from, shared
across every project on this machine. Hence a top-level router rather than one
nested under /projects/{id}.

The endpoints exist because the alternative — a CLI that prints 300 scenes and
reads stdin — is a chore nobody finishes, and an unfinished gold set is worth
exactly nothing. The measurement this feeds has failed its gate twice for lack
of minority-class instances; the bottleneck is author minutes, so the interface
is the intervention.

Serving corpus prose over HTTP is safe here and only here: the API binds
localhost and the text never leaves the machine. What must never happen is the
labelled result reaching the repository — it lives under `style_data/`, which
`.gitignore` covers.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import distinct, select

from app.db import AsyncSessionLocal
from app.models.corpus_segment import CorpusSegment
from app.services import gold_store
from app.services.function_label import FUNCTIONS

router = APIRouter(prefix="/deconstruct", tags=["deconstruct"])


class BuildQueueRequest(BaseModel):
    work: str
    n: int = Field(300, ge=10, le=2000)
    # Recorded in the queue file so "300 random scenes" is a reproducible claim
    # rather than a description of one afternoon.
    seed: int = 0


class LabelRequest(BaseModel):
    work: str
    id: int
    label: str
    reason: str = ""


@router.get("/works")
async def list_works():
    """Corpora available to deconstruct, with how far each has got."""
    async with AsyncSessionLocal() as db:
        works = (
            await db.execute(select(distinct(CorpusSegment.work)))
        ).scalars().all()
    return [{"work": w, **gold_store.progress(w)} for w in works]


@router.get("/taxonomy")
async def taxonomy():
    """The label set, with the disambiguating test shown next to each choice.

    Sent to the UI rather than duplicated in the frontend: the taxonomy has been
    revised twice by measurement, and a copy in JSX is a copy that goes stale
    without anything failing.
    """
    return [
        {"name": name, "meaning": meaning, "test": test}
        for name, (meaning, test) in FUNCTIONS.items()
    ]


@router.post("/queue")
async def build_queue(payload: BuildQueueRequest):
    """Freeze a random draw. Idempotent — an existing queue is returned as-is.

    Random, with no stratification, is a deliberate choice recorded in
    `services/deconstruct.py`: both structural channels built to surface
    minority classes scored at or below chance against the only ground truth
    available, so drawing at random is the honest option. It costs more author
    time and buys an accuracy and kappa that can actually be interpreted.
    """
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(CorpusSegment)
                .where(CorpusSegment.work == payload.work)
                .order_by(CorpusSegment.chapter_no, CorpusSegment.seq)
            )
        ).scalars().all()
    if not rows:
        raise HTTPException(404, "no corpus segments for that work")

    q = gold_store.build_queue(
        payload.work,
        [
            {"id": r.id, "chapter_no": r.chapter_no, "seq": r.seq, "text": r.text}
            for r in rows
        ],
        payload.n,
        payload.seed,
    )
    return {"work": q["work"], "n": q["n"], "seed": q["seed"],
            **gold_store.progress(payload.work)}


@router.get("/next")
async def next_item(work: str):
    """One unlabelled scene, blind: prose only, no guess, no running tally."""
    item = gold_store.next_item(work)
    if item is None:
        return {"done": True, **gold_store.progress(work)}
    return {"done": False, "item": item, **gold_store.progress(work)}


@router.post("/label")
async def label(payload: LabelRequest):
    valid = set(FUNCTIONS) | {gold_store.SKIP}
    if payload.label not in valid:
        raise HTTPException(422, f"label must be one of {sorted(valid)}")
    try:
        gold_store.save_label(payload.work, payload.id, payload.label, payload.reason)
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return gold_store.progress(payload.work)
