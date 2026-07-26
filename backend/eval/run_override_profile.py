# -*- coding: utf-8 -*-
"""Do the author's edits carry a consistent stylistic preference — or nothing?

Every (suggested, accepted) pair is a small statement about the author's voice.
This harness asks whether those statements agree with each other well enough to
be worth acting on. It is built to be able to say NO.

Two things are reported:

  偏好方向    median delta per texture metric. Median, not mean, because one
              wholesale rewrite would otherwise drag the estimate around — the
              same reason the imitation judge is denoised by median-of-3.
  方向一致率  the honest test. Fit the direction on a training split, then check
              how often held-out edits move the SAME way. Around 50% means the
              edits are unrelated to texture and there is no signal here, no
              matter how tidy the medians look. Well above 50% means a real,
              reusable preference.

Trivial edits are separated out with difflib (typo fixes say nothing about
voice), and below a minimum sample size nothing is concluded at all.

    python eval/run_override_profile.py --project-id 7

Reminder for whoever extends this: these numbers must NOT be written into a
generation prompt. Injecting measured statistics as instructions was tested on
the rhythm profile and made output measurably worse (distance 1.219 vs 0.619,
style 3.25 vs 4.65). Legitimate uses are post-hoc candidate selection and
surfacing the author's own accepted prose as examples.
"""
from __future__ import annotations

import argparse
import asyncio
import statistics

from sqlalchemy import select

from app.db import AsyncSessionLocal
from app.models.style_override import StyleOverride

MIN_PAIRS = 20          # below this, report coverage and stop
MIN_EDIT_FOR_SIGNAL = 0.05   # a rewrite, not a typo fix
TRAIN_SHARE = 0.7

METRICS = [
    ("d_dialogue_ratio", "对话率"),
    ("d_avg_sent_len", "平均句长"),
    ("d_short_sent_ratio", "短句率"),
    ("d_punct_density", "标点密度"),
    ("d_avg_para_len", "平均段长"),
]


def direction_agreement(train: list[float], test: list[float]) -> tuple[float, int]:
    """Share of held-out edits moving the same way as the training median.

    Zero deltas are dropped rather than counted as agreement — an edit that
    left a metric untouched is evidence of nothing, and counting it either way
    would quietly inflate or deflate the result.
    """
    train = [x for x in train if x]
    test = [x for x in test if x]
    if not train or not test:
        return 0.0, 0
    direction = 1 if statistics.median(train) > 0 else -1
    hits = sum(1 for x in test if (1 if x > 0 else -1) == direction)
    return hits / len(test), len(test)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--min-edit", type=float, default=MIN_EDIT_FOR_SIGNAL)
    args = ap.parse_args()

    async with AsyncSessionLocal() as db:
        rows = list((await db.execute(
            select(StyleOverride)
            .where(StyleOverride.project_id == args.project_id)
            .order_by(StyleOverride.id)
        )).scalars().all())

    if not rows:
        print(f"项目 {args.project_id} 还没有 override 记录。")
        print("先在稿纸/仿写/精修里生成 → 在稿件框改几个字 → 并入正文。")
        return

    by_source: dict[str, int] = {}
    for r in rows:
        by_source[r.source] = by_source.get(r.source, 0) + 1
    untouched = sum(1 for r in rows if r.edit_ratio < 0.001)
    trivial = sum(1 for r in rows if 0.001 <= r.edit_ratio < args.min_edit)
    real = [r for r in rows if r.edit_ratio >= args.min_edit]

    print(f"=== 覆盖情况（项目 {args.project_id}）===")
    print(f"  记录总数 {len(rows)}   来源分布 {by_source}")
    print(f"  一字未改 {untouched}   微小修改(<{args.min_edit}) {trivial}   "
          f"**实质改写 {len(real)}**")
    if real:
        ratios = sorted(r.edit_ratio for r in real)
        print(f"  实质改写的改动幅度 中位 {statistics.median(ratios):.3f}  "
              f"范围 {ratios[0]:.3f}–{ratios[-1]:.3f}")

    if len(real) < MIN_PAIRS:
        print(f"\n样本不足：实质改写只有 {len(real)} 对，低于 {MIN_PAIRS}。")
        print("**不下任何结论。** 继续正常写作攒数据后再跑。")
        return

    print(f"\n=== 偏好方向（n={len(real)}，中位数聚合）===")
    print("  正号 = 你倾向于比模型写得更多/更长；负号 = 更少/更短")
    for field, name in METRICS:
        vals = [getattr(r, field) for r in real if getattr(r, field) is not None]
        if not vals:
            continue
        med = statistics.median(vals)
        share = sum(1 for v in vals if v != 0 and (v > 0) == (med > 0)) / len(vals)
        print(f"  {name:<6} 中位 {med:+8.3f}   同向占比 {share * 100:4.0f}%  (n={len(vals)})")

    split = int(len(real) * TRAIN_SHARE)
    train_rows, test_rows = real[:split], real[split:]
    print(f"\n=== 方向一致率（训练 {len(train_rows)} → 留出 {len(test_rows)}）===")
    print("  ≈50% 表示修改与该指标无关（无信号）；显著高于 50% 才算存在稳定偏好")
    agreements = []
    for field, name in METRICS:
        tr = [getattr(r, field) for r in train_rows if getattr(r, field) is not None]
        te = [getattr(r, field) for r in test_rows if getattr(r, field) is not None]
        rate, n = direction_agreement(tr, te)
        if n:
            agreements.append(rate)
            flag = "有信号" if rate >= 0.70 else "偏弱" if rate >= 0.60 else "无信号"
            print(f"  {name:<6} {rate * 100:5.1f}%  (留出 n={n})   {flag}")

    print("\n" + "=" * 58)
    if agreements and max(agreements) >= 0.70:
        strong = [n for (f, n), a in zip(METRICS, agreements) if a >= 0.70]
        print(f"存在可用信号：{', '.join(strong)}。")
        print("→ 正当用法：best-of-N 事后选稿 / 把你改过的段落作少样本示例。")
        print("→ 禁止：把这些数字写进 prompt（已被节奏建模实验证伪）。")
    else:
        print("未发现稳定信号：各指标的方向一致率都接近随机。")
        print("→ 说明你的修改与这些纹理指标无关，不该据此建打分器。")
        print("→ 可考虑换信号：用词偏好、句式模板、或直接用少样本示例（不依赖统计）。")


if __name__ == "__main__":
    asyncio.run(main())
