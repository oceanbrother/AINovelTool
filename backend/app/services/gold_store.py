# -*- coding: utf-8 -*-
"""File-backed store for the hand-labelling queue and its results.

Files, not a table, for two reasons that both matter more than convenience:

  · The queue embeds corpus prose. `style_data/` is gitignored precisely so
    copyrighted reference text cannot reach the repository, and keeping this
    beside `function_gold.v1.json` means one rule covers all of it. A database
    row is one `pg_dump` away from a place that rule does not protect.
  · The output must be readable by `eval/run_function_agreement.py --gold`
    unchanged. Same schema as v1 — {id, chapter_no, seq, context_before, text,
    label, reason} — so a finished queue is a drop-in gold set.

Design decisions worth stating, because each one is a way the labels could
quietly stop being evidence:

**Blind by construction.** `next_item()` returns the prose and nothing else. No
model guess, no channel that surfaced it, no running tally by class. An author
who can see that they have answered 信息 forty times in a row starts looking for
reasons to answer something else, and the gate then measures that drift.

**Skips are recorded, not dropped.** A scene the author genuinely cannot judge
is not a label — forcing one manufactures the exact noise the gate is meant to
detect. But a silently discarded skip is worse: a 30% skip rate is a finding
about the taxonomy, not an inconvenience, and it has to survive to the report.

**Append-only, with the queue frozen.** The queue is built once with a recorded
seed and never reshuffled; labels append. Re-drawing midway would make "300
random scenes" untrue in a way nothing downstream could detect.
"""
from __future__ import annotations

import json
import os
import random
import tempfile
from typing import Any

# app/services/gold_store.py → backend/ → repo root → style_data/, so the queue
# lands beside function_gold.v1.json and `--gold ../style_data/…` resolves from
# backend/ the way every existing script and eval already expects.
_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "..", "style_data"
    )
)

SKIP = "跳过"


def _path(name: str) -> str:
    return os.path.join(_DIR, name)


def _read(name: str) -> Any:
    try:
        with open(_path(name), encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return None


def _write(name: str, data: Any) -> None:
    """Atomic write: a half-written gold file after 200 labels is unrecoverable."""
    os.makedirs(_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=_DIR, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, _path(name))
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --- queue ------------------------------------------------------------------


def queue_name(work: str) -> str:
    return f"function_queue.{work}.json"


def gold_name(work: str) -> str:
    return f"function_gold.{work}.json"


def build_queue(work: str, rows: list[dict], n: int, seed: int) -> dict:
    """Freeze a random draw of `n` scenes. Refuses to overwrite an existing queue.

    `rows` is the whole ordered corpus as dicts with id/chapter_no/seq/text;
    context_before is taken from the preceding row so the labeller has the same
    120-character window the v1 gold set used.
    """
    existing = _read(queue_name(work))
    if existing:
        return existing

    rng = random.Random(seed)
    idx = sorted(rng.sample(range(len(rows)), min(n, len(rows))))
    items = []
    for i in idx:
        r = rows[i]
        prev = rows[i - 1]["text"] if i > 0 else ""
        items.append(
            {
                "id": r["id"],
                "chapter_no": r["chapter_no"],
                "seq": r["seq"],
                "context_before": prev[-120:],
                "text": r["text"],
            }
        )
    q = {"work": work, "seed": seed, "n": len(items), "items": items}
    _write(queue_name(work), q)
    return q


def get_queue(work: str) -> dict | None:
    return _read(queue_name(work))


# --- labels -----------------------------------------------------------------


def get_labels(work: str) -> dict[int, dict]:
    data = _read(gold_name(work)) or {"items": []}
    return {it["id"]: it for it in data.get("items", [])}


def save_label(work: str, item_id: int, label: str, reason: str = "") -> int:
    """Upsert one label. Returns the number of labelled (non-skipped) items."""
    q = get_queue(work)
    if not q:
        raise ValueError("queue not built")
    src = next((it for it in q["items"] if it["id"] == item_id), None)
    if src is None:
        raise ValueError("item not in queue")

    data = _read(gold_name(work)) or {"work": work, "items": []}
    rest = [it for it in data["items"] if it["id"] != item_id]
    rest.append({**src, "label": label, "reason": reason})
    # Keep corpus order in the file so a human can read it alongside the book.
    rest.sort(key=lambda it: (it["chapter_no"], it["seq"]))
    data["items"] = rest
    _write(gold_name(work), data)
    return sum(1 for it in rest if it["label"] != SKIP)


def next_item(work: str) -> dict | None:
    """The next unlabelled scene — prose only, nothing that hints at an answer."""
    q = get_queue(work)
    if not q:
        return None
    done = get_labels(work)
    for it in q["items"]:
        if it["id"] not in done:
            return {
                "id": it["id"],
                "context_before": it["context_before"],
                "text": it["text"],
            }
    return None


def progress(work: str) -> dict:
    """Totals only. Deliberately no per-class breakdown — see the module docstring."""
    q = get_queue(work)
    if not q:
        return {"built": False}
    done = get_labels(work)
    skipped = sum(1 for it in done.values() if it["label"] == SKIP)
    return {
        "built": True,
        "total": q["n"],
        "seen": len(done),
        "labelled": len(done) - skipped,
        "skipped": skipped,
        "gold_file": f"style_data/{gold_name(work)}",
    }
