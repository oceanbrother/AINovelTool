# -*- coding: utf-8 -*-
"""Are the narrative-function labels reliable enough to build retrieval on?

Function-aware retrieval, a second embedding space and a weighted scorer all
rest on these labels being right. If they are noise, everything above them is
confident nonsense — so the labels get measured before anything is built, and
below the gate the taxonomy is fixed rather than shipped.

This is the second time this gate has run. The first taxonomy scored 0.396 and
was rejected; the fault turned out to be that its labels came from two different
axes, which no amount of prompt tuning would have fixed. So the confusion matrix
matters as much as the headline number — it names the pair to merge.

Reported against the author's own hand labels, since the author is the only
authority on what a scene in their reference material is doing. Accuracy alone
would flatter a labeller that always answered 揭示 (14 of 40 gold items), so
Cohen's kappa is reported beside it.

    python eval/run_function_agreement.py --work 龙族 \
        --gold ../style_data/function_gold.v1.json

Gold files hold corpus prose and stay under style_data/ (gitignored); only the
numbers printed here may leave this machine.
"""
from __future__ import annotations

import argparse
import asyncio
import itertools
import json
import os

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.corpus_segment import CorpusSegment
from app.services import function_label

# Accuracy alone cannot decide this. When one label covers most of the data, a
# classifier that always answers it scores well while knowing nothing — so the
# gate demands a real margin over that trivial baseline AND a kappa that shows
# agreement beyond chance.
GATE_KAPPA = 0.40
GATE_MARGIN = 0.10   # accuracy must beat "always answer the commonest label" by this


def majority_baseline(gold: list[str]) -> tuple[str, float]:
    """The score a constant classifier would get — the bar any labeller must clear."""
    counts: dict[str, int] = {}
    for g in gold:
        counts[g] = counts.get(g, 0) + 1
    label, hits = max(counts.items(), key=lambda kv: kv[1])
    return label, hits / len(gold)


def cohen_kappa(a: list[str], b: list[str], labels: list[str]) -> float:
    """Agreement with chance agreement subtracted out."""
    n = len(a)
    if not n:
        return 0.0
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    expected = sum((a.count(k) / n) * (b.count(k) / n) for k in labels)
    return 0.0 if expected >= 1.0 else (observed - expected) / (1 - expected)


def report(name: str, pairs: list[tuple[str, str]], labels: list[str]) -> float:
    """pairs = (predicted, gold). Returns accuracy."""
    if not pairs:
        print(f"\n{name}: 无可比对样本")
        return 0.0
    pred = [p for p, _ in pairs]
    gold = [g for _, g in pairs]
    hits = sum(1 for p, g in zip(pred, gold) if p == g)
    acc = hits / len(pairs)
    print(f"\n{name}: n={len(pairs)}  一致 {hits}  准确率={acc:.3f}  "
          f"kappa={cohen_kappa(pred, gold, labels):.3f}")

    per: dict[str, list[int]] = {}
    for p, g in pairs:
        slot = per.setdefault(g, [0, 0])
        slot[1] += 1
        slot[0] += int(p == g)
    print("  按人工标签: " + ", ".join(
        f"{k} {v[0]}/{v[1]}" for k, v in sorted(per.items(), key=lambda kv: -kv[1][1])))

    confusion: dict[tuple[str, str], int] = {}
    for p, g in pairs:
        if p != g:
            confusion[(g, p)] = confusion.get((g, p), 0) + 1
    if confusion:
        print("  主要混淆（应为→判成）: " + ", ".join(
            f"{g}→{p} ×{c}"
            for (g, p), c in sorted(confusion.items(), key=lambda kv: -kv[1])[:6]))
    return acc


def merge_scan(pairs: list[tuple[str, str]], labels: list[str]) -> None:
    """If two labels were treated as one, how much would agreement improve?

    This is the question the previous failure turned on: merging 动作 into 描写
    lifted agreement more than any prompt change could have. Rather than guess
    which pair is redundant, measure every pair and let the numbers name it.
    """
    base = sum(1 for p, g in pairs if p == g) / len(pairs)
    rows = []
    for a, b in itertools.combinations(labels, 2):
        merged = [
            (a if p == b else p, a if g == b else g) for p, g in pairs
        ]
        acc = sum(1 for p, g in merged if p == g) / len(merged)
        rows.append((acc - base, a, b, acc))
    rows.sort(reverse=True)
    print(f"\n=== 合并扫描（当前 {len(labels)} 类，基线 {base:.3f}）===")
    print("  把两类当成一类后准确率会变成多少 —— 提升最大的那对就是重叠最严重的：")
    for delta, a, b, acc in rows[:5]:
        flag = "  ← 值得合并" if delta >= 0.08 else ""
        print(f"    {a} + {b:<4} → {acc:.3f}  ({delta:+.3f}){flag}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--gold", required=True)
    args = ap.parse_args()

    labels = function_label.FUNCTION_NAMES

    def fold(tag: str | None) -> str | None:
        """Map a pre-merge label onto the current taxonomy.

        Both the gold sheet and any labels stored before the merge speak the old
        six-label vocabulary. Folding them here means the earlier annotation
        stays usable instead of having to be redone — the author's 40 hand
        labels are the most expensive artefact in this round.
        """
        if tag in function_label.MERGED_INTO_INFO:
            return "信息"
        return tag
    async with AsyncSessionLocal() as db:
        rows = list((await db.execute(
            select(CorpusSegment).where(CorpusSegment.work == args.work)
        )).scalars().all())
    by_id = {r.id: r for r in rows}
    print(f"{len(rows)} segments | llm 已标 {sum(1 for r in rows if r.func_tag)}")

    if not os.path.exists(args.gold):
        raise SystemExit(f"gold not found: {args.gold}")
    with open(args.gold, encoding="utf-8") as fh:
        data = json.load(fh)
    known = set(labels) | set(function_label.MERGED_INTO_INFO)
    gold = {
        int(i["id"]): fold(i["label"].strip())
        for i in data.get("items", [])
        if i.get("label", "").strip() in known
    }
    print(f"gold: {len(gold)}/{len(data.get('items', []))} 段有效标注")

    pairs = [
        (fold(by_id[i].func_tag), g)
        for i, g in gold.items()
        if i in by_id and by_id[i].func_tag
    ]
    acc = report("llm vs gold（决定性）", pairs, labels)
    if not pairs:
        return
    merge_scan(pairs, labels)

    gold_labels = [g for _, g in pairs]
    top, base = majority_baseline(gold_labels)
    kappa = cohen_kappa([p for p, _ in pairs], gold_labels, labels)
    margin = acc - base

    print(f"\n=== 平凡基线对照 ===")
    print(f"  「一律答『{top}』」的准确率 = {base:.3f}（{top} 占 {base * 100:.0f}% 的人工标注）")
    print(f"  实际准确率 {acc:.3f}，相对基线 {margin:+.3f}")
    if margin < GATE_MARGIN:
        print("  ⚠ 准确率主要来自多数类，不代表分类器学到了区分")

    print("\n" + "=" * 62)
    if kappa >= GATE_KAPPA and margin >= GATE_MARGIN:
        print(f"闸门通过：kappa {kappa:.3f} ≥ {GATE_KAPPA}，且超基线 {margin:+.3f}")
        print("→ 可用功能标签建检索（C2/C4）。")
    else:
        print(f"闸门未过：kappa {kappa:.3f}（需 ≥{GATE_KAPPA}）、"
              f"超基线 {margin:+.3f}（需 ≥{GATE_MARGIN}）")
        print("→ 不得在未验证的标签上继续建 function_embedding 或功能感知检索。")
        minority = sorted(
            ((sum(1 for _, g in pairs if g == k), k) for k in labels if k != top)
        )
        thin = [f"{k} n={n}" for n, k in minority if n < 8]
        if thin:
            print(f"  注意：少数类样本过少（{', '.join(thin)}），"
                  "当前数据无法判定模型能否识别它们 —— 需要**分层抽样**补足金标准，"
                  "而不是继续加大随机采样。")


if __name__ == "__main__":
    asyncio.run(main())
