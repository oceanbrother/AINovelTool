# -*- coding: utf-8 -*-
"""Turn knowledge state into constraints a draft can be checked against.

Suspense is a bookkeeping problem before it is an art problem: a scene goes
wrong when someone says a thing they have no way of knowing, or when the reader
is handed an answer that was supposed to stay out of reach for another six
chapters. Nothing in the generator prevents either — the author has been
rewriting the same `must_not` lines by hand for every scene, and forgetting some.

So the awareness table is compiled into `must_not` lines. That target is chosen
because it is already proven: plan constraints lifted fulfilment from 58.9% to
93.0%, and `refine.verify_draft` already checks every `must_not` item and
rewrites on a violation. Knowledge state gets verification for free by speaking
the language the pipeline already verifies.

Two deliberate properties:

  * derivation is PROGRAM logic, never a model call. The rules are simple enough
    to state exactly ("a character who does not know it cannot say it"), so a
    model would add labelling error and latency while removing the guarantee
    that the constraint appears at all.
  * derived lines are handed back separately from the author's own, so the UI
    can show where each came from and an edit to the plan cannot silently drop
    a continuity rule.

The constraints are concrete and checkable, which is the side of the line this
project has evidence for: abstract statistics injected into a prompt measured
*worse* than no guidance at all (rhythm ablation, distance 1.219 vs 0.619).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Protocol

MAX_CONSTRAINTS = 6  # each one costs a check at verification time


class _Fact(Protocol):
    """The shape consumed here — models.StoryFact satisfies it, as do stubs."""

    id: int
    statement: str
    reader_level: str
    character_levels: dict
    foreshadowing_id: int | None


class _Event(Protocol):
    """models.KnowledgeEvent's shape, or a stub in tests."""

    fact_id: int
    holder_type: str
    holder_id: int | None
    level: str
    chapter_id: int | None


@dataclass
class FactState:
    """A fact's awareness levels as they stand at one point in the story."""

    id: int
    statement: str
    foreshadowing_id: int | None
    reader_level: str
    character_levels: dict[int, str]


def resolve_states(
    facts: Iterable[_Fact],
    events: Iterable[_Event],
    chapter_order: int | None,
    order_of: dict[int, int],
) -> list[FactState]:
    """Awareness as of `chapter_order`, applying events up to that point.

    What a character may say depends on when the scene happens: a secret that
    must not be spoken in chapter three is ordinary conversation by chapter
    twelve. The columns on `story_facts` are the opening state, and each event
    overrides it from its chapter onward — so a project that has entered no
    events behaves exactly as it did before the timeline existed.

    `chapter_order` of None means "latest": every event applies. That is the
    right default for questions about the present rather than a past scene.
    """
    per_fact: dict[int, list[tuple[int, _Event]]] = {}
    for event in events:
        # an event with no chapter takes effect from the beginning; unknown
        # chapter ids are treated the same way rather than silently dropped
        at = order_of.get(event.chapter_id, -1) if event.chapter_id else -1
        if chapter_order is not None and at > chapter_order:
            continue  # hasn't happened yet from where we are standing
        per_fact.setdefault(event.fact_id, []).append((at, event))

    states: list[FactState] = []
    for fact in facts:
        reader = fact.reader_level
        characters = {
            int(k): v for k, v in (fact.character_levels or {}).items()
            if str(k).lstrip("-").isdigit()
        }
        # stable order so two events on the same chapter resolve predictably:
        # the later-inserted one wins, which matches how a log reads
        for _at, event in sorted(per_fact.get(fact.id, []), key=lambda pair: pair[0]):
            if event.holder_type == "reader":
                reader = event.level
            elif event.holder_id is not None:
                characters[int(event.holder_id)] = event.level
        states.append(
            FactState(
                id=fact.id,
                statement=fact.statement,
                foreshadowing_id=fact.foreshadowing_id,
                reader_level=reader,
                character_levels=characters,
            )
        )
    return states


def _priority(fact: FactState) -> tuple:
    """Sort key: most spoiler-sensitive first, ties broken deterministically.

    A fact attached to an unpaid-off thread is live tension, so protecting it
    matters most; after that, anything the reader does not know yet, since
    revealing it early is the costliest mistake. This ordering is a heuristic —
    there is no measure here of whether a fact is even relevant to the scene
    being written (that would need an extra embedding pass, deliberately out of
    scope), so an unrelated constraint can survive the cap.
    """
    return (
        0 if fact.foreshadowing_id else 1,
        0 if fact.reader_level == "unknown" else 1,
        -fact.id,
    )


def derive_must_not(
    facts: Iterable[FactState],
    character_names: dict[int, str],
    existing: Iterable[str] = (),
    limit: int = MAX_CONSTRAINTS,
) -> list[str]:
    """Compile awareness state into 'do not do this' lines for a ScenePlan.

    `character_names` maps character id -> name; a character with no entry is
    skipped rather than referred to by a bare id, which would be meaningless in
    a constraint the model has to honour and a human has to read.

    `existing` are constraints the author or the planner already wrote — a line
    that repeats one of those is dropped, so the same rule is never checked twice.
    """
    seen = {line.strip() for line in existing if line and line.strip()}
    out: list[str] = []

    for fact in sorted(facts, key=_priority):
        statement = (fact.statement or "").strip()
        if not statement:
            continue
        lines: list[str] = []

        # the reader is not ready for this yet, so nothing may confirm it
        if fact.reader_level == "unknown":
            lines.append(f"直接揭示「{statement}」")

        for raw_id, level in (fact.character_levels or {}).items():
            try:
                name = character_names[int(raw_id)]
            except (KeyError, TypeError, ValueError):
                continue  # unregistered or deleted character — say nothing
            if level == "believes_false":
                lines.append(f"让{name}表现得已经识破「{statement}」")
            elif level in ("unknown", "suspects"):
                # 'suspects' still cannot state it as fact — that is the whole
                # difference between a suspicion and knowledge
                lines.append(f"让{name}说破「{statement}」")

        for line in lines:
            if line not in seen:
                seen.add(line)
                out.append(line)
            if len(out) >= limit:
                return out
    return out
