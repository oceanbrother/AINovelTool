# -*- coding: utf-8 -*-
"""The three rhythm statistics — what follows what, how a chapter swells, how it lands.

Each answers a different question and needs a different kind of data:

  transition matrix   what follows what      ordered, TAGGED paragraphs
  density curves      how a chapter swells   texture only — no tags, no model
  chapter-end profile how a chapter lands    the last paragraph of every chapter

A vector store can produce none of these: retrieval is order-blind, and rhythm
is a property of sequence.

Labels come from the composite labeller the gate validated:
  dialogue  → the quotation-mark rule   (.875 against hand-labelled gold)
  the rest  → the judge model, 4 modes  (.789 against the same gold)
Dialogue is never sent to a model — a free rule already beats it there.

Deliberate statistical choices, so the numbers aren't oversold:
  * first-order Markov only. 4x4 = 16 cells; a second-order model needs 64 and
    would be noise at this sample size.
  * Laplace α=0.5, so a cell that merely went unobserved doesn't harden into
    "the author never does this".
  * transitions never cross a chapter boundary — the last beat of one chapter
    does not "lead to" the first beat of the next.
  * the matrix is restricted to chapters with COMPLETE label coverage; a
    partially-labelled chapter would silently drop transitions and bias it.
  * chapters are grouped before curves are averaged; pooling a dialogue-heavy
    chapter with an action chapter yields a mean curve resembling neither.
  * chapter-end counts are raw (n = chapter count, which is small).

    python eval/run_rhythm_profile.py --work 龙族

Writes style_data/rhythm_profile.json (gitignored — derived from private corpus).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.corpus_paragraph import CorpusParagraph
from app.models.corpus_segment import CorpusSegment
from app.services import mode, rhythm

ALPHA = 0.5   # Laplace smoothing for unseen transitions
BINS = 10     # position buckets across a chapter
OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "style_data")

TEXTURE_FIELDS = [
    ("dialogue_ratio", "对话率"),
    ("short_sent_ratio", "短句率"),
    ("avg_sent_len", "平均句长"),
    ("punct_density", "标点密度"),
]


def tag_of(p: CorpusParagraph, source: str) -> str | None:
    """Composite label: the rule owns dialogue, the model owns everything else."""
    if p.is_dialogue:
        return "对话"
    return p.mode_llm if source == "llm" else p.mode_anchor


# --- ① transition matrix -------------------------------------------------------

def transition_matrix(paras: list[CorpusParagraph], source: str) -> dict:
    labels = mode.MODE_NAMES
    idx = {lab: i for i, lab in enumerate(labels)}
    counts = [[0] * len(labels) for _ in labels]
    prev, prev_chapter = None, None
    for p in paras:
        tag = tag_of(p, source)
        if tag not in idx:
            prev, prev_chapter = None, p.chapter_no
            continue
        if prev is not None and prev_chapter == p.chapter_no:
            counts[idx[prev]][idx[tag]] += 1
        prev, prev_chapter = tag, p.chapter_no

    total = sum(sum(r) for r in counts)
    probs, runs, entropy = [], {}, {}
    for i, lab in enumerate(labels):
        denom = sum(counts[i]) + ALPHA * len(labels)
        row = [(c + ALPHA) / denom for c in counts[i]]
        probs.append(row)
        runs[lab] = 1 / (1 - row[i]) if row[i] < 1 else float("inf")
        entropy[lab] = -sum(x * math.log2(x) for x in row if x > 0)

    pi = [1 / len(labels)] * len(labels)
    for _ in range(500):
        nxt = [sum(pi[i] * probs[i][j] for i in range(len(labels))) for j in range(len(labels))]
        s = sum(nxt) or 1.0
        nxt = [x / s for x in nxt]
        if max(abs(a - b) for a, b in zip(pi, nxt)) < 1e-12:
            pi = nxt
            break
        pi = nxt

    return {"labels": labels, "counts": counts, "probs": probs,
            "total_transitions": total, "mean_run_length": runs,
            "row_entropy": entropy, "stationary": dict(zip(labels, pi))}


def print_transition(tm: dict, scope: str) -> None:
    labels = tm["labels"]
    n = len(labels)
    print(f"\n=== ① 模式转移矩阵（一阶，Laplace α={ALPHA}，不跨章）===")
    print(f"范围: {scope}")
    print(f"总转移数 {tm['total_transitions']}（{n}×{n}={n * n} 格，"
          f"平均每格 {tm['total_transitions'] / (n * n):.0f}）")
    print("\n  当前\\下一".ljust(12) + "".join(f"{l:>13}" for l in labels))
    for i, lab in enumerate(labels):
        cells = "".join(f"{tm['probs'][i][j] * 100:7.1f}%({tm['counts'][i][j]:>4})"
                        for j in range(n))
        print(f"  {lab:<9}" + cells)
    print("\n  游程均值（连续停留几段）:",
          "  ".join(f"{k}={v:.2f}" for k, v in tm["mean_run_length"].items()))
    print(f"  行熵 bit（越低越套路，max={math.log2(n):.2f}）:",
          "  ".join(f"{k}={v:.2f}" for k, v in tm["row_entropy"].items()))
    print("  稳态分布:", "  ".join(f"{k}={v * 100:.1f}%" for k, v in tm["stationary"].items()))

    flat = sorted(((tm["counts"][i][j], labels[i], labels[j])
                   for i in range(n) for j in range(n)), reverse=True)
    print("  最高频接法: " + ", ".join(f"{a}→{b} {c}次" for c, a, b in flat[:3]))
    print("  最罕见接法: " + ", ".join(f"{a}→{b} {c}次" for c, a, b in flat[-3:]))


# --- ② density curves ----------------------------------------------------------

def chapter_groups(segs: list[CorpusSegment]) -> dict[int, str]:
    """Split chapters into three interpretable types by dialogue share.

    Terciles rather than k-means: the boundaries stay explainable ("the most
    dialogue-driven third of chapters") and the result is deterministic.
    """
    per: dict[int, list[float]] = {}
    for s in segs:
        if s.dialogue_ratio is not None:
            per.setdefault(s.chapter_no, []).append(s.dialogue_ratio)
    means = {c: statistics.mean(v) for c, v in per.items() if v}
    if not means:
        return {}
    ordered = sorted(means, key=lambda c: means[c])
    third = max(1, len(ordered) // 3)
    return {c: ("叙述主导" if k < third else "均衡" if k < 2 * third else "对话主导")
            for k, c in enumerate(ordered)}


def density_curves(segs: list[CorpusSegment], groups: dict[int, str]) -> dict:
    by_chapter: dict[int, list[CorpusSegment]] = {}
    for s in segs:
        by_chapter.setdefault(s.chapter_no, []).append(s)

    per_group: dict[str, dict[str, list[list[float]]]] = {}
    for chapter, items in by_chapter.items():
        items.sort(key=lambda s: s.seq)
        if len(items) < BINS // 2:
            continue
        group = groups.get(chapter, "均衡")
        bucket = per_group.setdefault(
            group, {f: [[] for _ in range(BINS)] for f, _ in TEXTURE_FIELDS})
        for k, seg in enumerate(items):
            b = min(int(((k + 0.5) / len(items)) * BINS), BINS - 1)
            for field, _ in TEXTURE_FIELDS:
                val = getattr(seg, field)
                if val is not None:
                    bucket[field][b].append(val)

    out: dict = {"_chapter_types": {}}
    for group, fields in per_group.items():
        out[group] = {
            field: [{"mean": round(statistics.mean(v), 4) if v else None,
                     "sd": round(statistics.pstdev(v), 4) if len(v) > 1 else 0.0,
                     "n": len(v)} for v in fields[field]]
            for field, _ in TEXTURE_FIELDS
        }
    for g in set(groups.values()):
        out["_chapter_types"][g] = sum(1 for v in groups.values() if v == g)
    return out


def print_curves(curves: dict) -> None:
    print(f"\n=== ② 密度曲线（章内位置归一化 → {BINS} 桶，先按章型分组）===")
    print("  章型分布:", curves.get("_chapter_types", {}))
    for group, fields in curves.items():
        if group.startswith("_"):
            continue
        print(f"\n  ── {group} ──   章首 " + "→" * 4 + " 章末")
        for field, name in TEXTURE_FIELDS:
            vals = [b["mean"] for b in fields[field]]
            if not any(v is not None for v in vals):
                continue
            line = " ".join(f"{v:6.3f}" if v is not None else "   -  " for v in vals)
            head = next((v for v in vals if v is not None), None)
            tail = next((v for v in reversed(vals) if v is not None), None)
            trend = f"  首→末 {(tail - head) / head * 100:+5.0f}%" if head else ""
            print(f"    {name:<5}{line}{trend}")


# --- ③ chapter-end profile -----------------------------------------------------

def chapter_end(paras: list[CorpusParagraph], source: str) -> dict:
    by_chapter: dict[int, list[CorpusParagraph]] = {}
    for p in paras:
        by_chapter.setdefault(p.chapter_no, []).append(p)

    tail_tags: dict[str, int] = {}
    open_tags: dict[str, int] = {}
    stop_ratios: list[float] = []
    tagged = 0
    for items in by_chapter.values():
        items.sort(key=lambda p: p.seq)
        tail, head = items[-1], items[0]
        tag = tag_of(tail, source)
        if tag:
            tail_tags[tag] = tail_tags.get(tag, 0) + 1
            tagged += 1
        htag = tag_of(head, source)
        if htag:
            open_tags[htag] = open_tags.get(htag, 0) + 1
        # 急停系数: the final paragraph's sentences vs the chapter's own average
        lens = [rhythm.avg_sentence_len(p.text) for p in items]
        lens = [x for x in lens if x]
        tail_len = rhythm.avg_sentence_len(tail.text)
        if lens and tail_len:
            mean_len = statistics.mean(lens)
            if mean_len:
                stop_ratios.append(tail_len / mean_len)

    return {"n_chapters": len(by_chapter), "n_tagged_tails": tagged,
            "tail_tag_counts": tail_tags, "opening_tag_counts": open_tags,
            "stop_ratio_mean": round(statistics.mean(stop_ratios), 3) if stop_ratios else None,
            "stop_ratio_median": round(statistics.median(stop_ratios), 3) if stop_ratios else None,
            "stop_ratio_below_1": sum(1 for r in stop_ratios if r < 1.0),
            "stop_ratio_n": len(stop_ratios)}


def print_end(end: dict) -> None:
    print(f"\n=== ③ 章末分布（n = 章数 = {end['n_chapters']}，样本量小，只报原始计数）===")
    if end["n_tagged_tails"]:
        items = sorted(end["tail_tag_counts"].items(), key=lambda kv: -kv[1])
        print("  收势（末段模式）: " + ", ".join(
            f"{k} {v}/{end['n_tagged_tails']}章" for k, v in items))
        op = sorted(end["opening_tag_counts"].items(), key=lambda kv: -kv[1])
        print("  起手（首段模式）: " + ", ".join(f"{k} {v}章" for k, v in op))
    if end["stop_ratio_n"]:
        print(f"\n  急停系数 = 末段句长 / 全章均句长   (n={end['stop_ratio_n']})")
        print(f"    均值 {end['stop_ratio_mean']}   中位 {end['stop_ratio_median']}")
        print(f"    收紧句子的章: {end['stop_ratio_below_1']}/{end['stop_ratio_n']}"
              f"   ← 连续量，比上面的标签分布更可信")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--tag-source", choices=["llm", "anchor"], default="llm")
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        paras = list((await db.execute(
            select(CorpusParagraph)
            .where(CorpusParagraph.work == args.work)
            .order_by(CorpusParagraph.chapter_no, CorpusParagraph.seq)
        )).scalars().all())
        segs = list((await db.execute(
            select(CorpusSegment)
            .where(CorpusSegment.work == args.work)
            .order_by(CorpusSegment.chapter_no, CorpusSegment.seq)
        )).scalars().all())
    if not paras:
        raise SystemExit(f"no paragraphs for '{args.work}'")

    chapters = max(p.chapter_no for p in paras)
    print(f"语料: {args.work} | {len(paras)} 自然段 / {len(segs)} 段 / {chapters} 章 "
          f"| 标签源=规则(对话)+{args.tag_source}(其余)")

    # the matrix may only use chapters whose labels are COMPLETE — a partially
    # labelled chapter would silently drop transitions and skew the counts
    by_chapter: dict[int, list[CorpusParagraph]] = {}
    for p in paras:
        by_chapter.setdefault(p.chapter_no, []).append(p)
    full = sorted(c for c, items in by_chapter.items()
                  if all(tag_of(p, args.tag_source) for p in items))
    covered = [p for p in paras if p.chapter_no in full]
    scope = (f"第 {full[0]}–{full[-1]} 章（标签完整的连续区间），"
             f"{len(covered)} 段" if full else "无完整覆盖的章")
    if not covered:
        raise SystemExit("no fully-labelled chapter — run build_paragraphs.py --llm first")

    tm = transition_matrix(covered, args.tag_source)
    print_transition(tm, scope)

    groups = chapter_groups(segs)
    curves = density_curves(segs, groups)
    print_curves(curves)

    end = chapter_end(paras, args.tag_source)
    print_end(end)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.abspath(os.path.join(OUT, "rhythm_profile.json"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"work": args.work, "tag_source": args.tag_source,
                   "matrix_scope_chapters": full, "transition": tm,
                   "density": curves, "chapter_end": end},
                  fh, ensure_ascii=False, indent=2)
    print(f"\n→ {path}")


if __name__ == "__main__":
    asyncio.run(main())
