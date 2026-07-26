# -*- coding: utf-8 -*-
"""Are the mode labels trustworthy enough to build rhythm statistics on?

The anchor classifier was written for style-sample recall, where a wrong tag
costs one mediocre example. Rhythm modelling leans on it far harder: a
transition matrix over noisy labels yields confident-looking numbers about
nothing. So the labellers get measured before anything is built on them.

Three comparisons, most to least authoritative:

  anchor vs gold   the decisive number; gold is hand-labelled by the author
  llm    vs gold   is the judge model a usable stand-in for a human?
  anchor vs llm    agreement at a scale hand labelling cannot reach

Reported as accuracy AND Cohen's kappa. Kappa matters because the distribution
is severely skewed — 63% of paragraphs are dialogue, so a labeller that answered
对话 every time would post a flattering accuracy and a kappa near zero.

    python eval/run_mode_agreement.py --work 龙族 \
        --gold ../style_data/mode_gold.v1.json

Gold files hold corpus prose and live under style_data/ (gitignored). Only the
agreement numbers printed here are safe to quote elsewhere.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.corpus_paragraph import CorpusParagraph
from app.services import mode

GATE = 0.60  # below this, fix classification before building rhythm on it


def cohen_kappa(a: list[str], b: list[str], labels: list[str]) -> float:
    """Agreement corrected for what chance alone would have produced."""
    n = len(a)
    if not n:
        return 0.0
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    expected = sum((a.count(lab) / n) * (b.count(lab) / n) for lab in labels)
    if expected >= 1.0:
        return 0.0
    return (observed - expected) / (1 - expected)


def report(name: str, pairs: list[tuple[str, str]], labels: list[str]) -> float:
    """pairs = (predicted, reference). Returns accuracy."""
    if not pairs:
        print(f"\n{name}: 无可比对样本")
        return 0.0
    pred = [p for p, _ in pairs]
    ref = [r for _, r in pairs]
    hits = sum(1 for p, r in zip(pred, ref) if p == r)
    acc = hits / len(pairs)
    kappa = cohen_kappa(pred, ref, labels)
    print(f"\n{name}: n={len(pairs)}  一致 {hits}  准确率={acc:.3f}  kappa={kappa:.3f}")

    per: dict[str, list[int]] = {}
    for p, r in pairs:
        slot = per.setdefault(r, [0, 0])
        slot[1] += 1
        if p == r:
            slot[0] += 1
    print("  按参照标签: " + ", ".join(
        f"{lab} {v[0]}/{v[1]}" for lab, v in sorted(per.items(), key=lambda kv: -kv[1][1])))

    confusion: dict[tuple[str, str], int] = {}
    for p, r in pairs:
        if p != r:
            confusion[(r, p)] = confusion.get((r, p), 0) + 1
    if confusion:
        worst = sorted(confusion.items(), key=lambda kv: -kv[1])[:5]
        print("  主要混淆（应为→判成）: " + ", ".join(
            f"{r}→{p} ×{c}" for (r, p), c in worst))
    return acc


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--gold", default="")
    ap.add_argument("--primary", choices=["llm", "anchor"], default="llm",
                    help="the labeller the statistics will use — the gate judges THIS one")
    args = ap.parse_args()

    labels = mode.MODE_NAMES
    async with AsyncSessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(CorpusParagraph).where(CorpusParagraph.work == args.work)
                )
            ).scalars().all()
        )
    by_id = {r.id: r for r in rows}
    print(f"{len(rows)} paragraphs | anchor 已标 "
          f"{sum(1 for r in rows if r.mode_anchor)} | llm 已标 "
          f"{sum(1 for r in rows if r.mode_llm)}")

    gold: dict[int, str] = {}
    if args.gold and os.path.exists(args.gold):
        with open(args.gold, encoding="utf-8") as fh:
            data = json.load(fh)
        items = data.get("items", [])
        for item in items:
            lab = str(item.get("label", "")).strip()
            if lab in labels:  # '?' and blanks are excluded, as the sheet says
                gold[int(item["id"])] = lab
        print(f"gold: {len(gold)}/{len(items)} 段有效标注")
    else:
        print(f"gold: 未提供（{args.gold or '无路径'}）—— 跳过与人工基准的比对")

    accs: dict[str, float] = {}
    if gold:
        for field, name in (("mode_llm", "llm"), ("mode_anchor", "anchor")):
            mark = "（决定性）" if name == args.primary else "（参考）"
            accs[name] = report(
                f"① {name} vs gold{mark}",
                [(getattr(by_id[i], field), g) for i, g in gold.items()
                 if i in by_id and getattr(by_id[i], field)],
                labels,
            )
        # the quotation-mark rule is free and near-certain — verify that claim
        rule_pairs = [
            ("对话" if by_id[i].is_dialogue else "非对话",
             "对话" if g == "对话" else "非对话")
            for i, g in gold.items() if i in by_id
        ]
        report("③ 引号规则 vs gold（只判对话/非对话）", rule_pairs, ["对话", "非对话"])

    report(
        "④ anchor vs llm（规模化交叉验证）",
        [(r.mode_anchor, r.mode_llm) for r in rows if r.mode_anchor and r.mode_llm],
        labels,
    )

    print("\n" + "=" * 62)
    primary_acc = accs.get(args.primary, 0.0)
    if not gold:
        print("闸门未评估：缺少人工金标准。")
    elif primary_acc >= GATE:
        print(f"闸门通过：主标注者 {args.primary} 准确率 {primary_acc:.3f} >= {GATE}")
        print(f"→ 可用 {args.primary} 标签做节奏统计（Phase 3）。")
    else:
        print(f"闸门未过：主标注者 {args.primary} 准确率 {primary_acc:.3f} < {GATE}")
        print("→ 按计划停工修分类：改进提示词 / 换标注者 / 再降粒度。")
        print("  不得在未验证的标签上继续建节奏模型。")


if __name__ == "__main__":
    asyncio.run(main())
