# -*- coding: utf-8 -*-
"""A/B: does injecting a measured rhythm prior actually change what gets written?

The whole rhythm pipeline is only worth wiring into generation if the profile
changes output in the intended direction. This harness answers that before any
of it touches the product — the plan's rule was verify first, integrate second.

One variable, everything else held fixed:

  arm B (baseline)  style samples + task          — today's behaviour
  arm A (rhythm)    style samples + task + PRIOR  — the measured profile

Both arms get the same samples, the same task, and are judged against the same
held-out reference, so a difference can only come from the prior.

Two metrics, primary first:

  节奏吻合度  program-computed distance between the draft's texture and the
              corpus norms (dialogue share, sentence length, short-sentence
              share, punctuation density). Deterministic and free — and it is
              the thing the prior is actually supposed to move.
  style 分    the existing judge, median of 3, because a single judge call was
              already shown to swing wildly on identical input.

Honest expectation: this project has a precedent — scene-aligned sample recall
looked obviously helpful and measured as noise (5.5 vs 4.7, n=10). A null result
here is a real possibility and gets recorded either way.

    python eval/run_rhythm_ablation.py --work 龙族 [--n 20]

Costs credit: 2 generations + 6 judge calls per probe.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics

import httpx
from sqlalchemy import select

from app.core import llm
from app.db import AsyncSessionLocal
from app.models.corpus_segment import CorpusSegment
from app.services import imitation, rhythm

OUT = os.path.join(os.path.dirname(os.path.dirname(__file__)), "..", "style_data")

# Generic tasks: no private character or plot names, so this harness stays
# repo-safe and the corpus is never echoed back into the prompt.
PROBES = [
    "写一段两人在雨夜街头擦肩而过的场面，约300字",
    "写一段少年独自走进空荡教室时的所见所感，约300字",
    "写一段两个人隔着桌子互相试探的对话，约300字",
    "写一段有人推门而入打断了原本的谈话，约300字",
    "写一段角色在深夜接到一通陌生来电，约300字",
    "写一段两人因误会而起争执，约300字",
    "写一段角色发现房间里有人来过的痕迹，约300字",
    "写一段清晨海边的环境，以及一个人站在那里，约300字",
    "写一段角色回忆起一件很久以前的小事，约300字",
    "写一段两人在走廊里短暂交谈后各自离开，约300字",
    "写一段角色在人群中忽然看见一个熟悉的背影，约300字",
    "写一段有人在雨里等另一个人，最后没等到，约300字",
    "写一段角色被质问却选择沉默，约300字",
    "写一段两人一起吃一顿沉默的晚饭，约300字",
    "写一段角色在旧物里翻出一样意外的东西，约300字",
    "写一段一场对话因为一个突然的消息而中断，约300字",
    "写一段角色走在陌生的城市街道上，约300字",
    "写一段两人告别，谁都没有说出真正想说的话，约300字",
    "写一段角色在镜子前发现自己的变化，约300字",
    "写一段有人敲门，开门后却空无一人，约300字",
]

_GEN_SYSTEM = (
    "你是小说代笔。严格模仿【文风样本】的句长节奏、标点密度与用词习惯，"
    "只借语感、不复述样本内容，完成【任务】。只输出正文。"
)

STYLE_REFS = 3    # samples shown to the generator (identical across arms)
JUDGE_REFS = 3    # held-out samples used as the fixed judging bar
TEXTURE_KEYS = ["dialogue_ratio", "short_sent_ratio", "avg_sent_len", "punct_density"]


async def _retry(factory, attempts: int = 4, delay: float = 4.0):
    for i in range(attempts):
        try:
            return await factory()
        except httpx.HTTPError as exc:
            if i == attempts - 1:
                raise
            print(f"    (retry {i + 1}: {type(exc).__name__})")
            await asyncio.sleep(delay * (i + 1))


def build_prior(profile: dict) -> str:
    """Render the measured profile into a compact writing instruction.

    Only the findings that survived measurement go in: the dialogue inertia and
    pull from the transition matrix, and the intra-chapter acceleration that
    showed up in all three chapter types. Numbers are stated so the model has a
    target rather than an adjective.
    """
    tm = profile["transition"]
    labels = tm["labels"]
    runs = tm["mean_run_length"]
    stat = tm["stationary"]
    lines = ["【节奏参照】以下是目标文风的实测节奏，请照此组织段落："]
    lines.append(
        f"· 模式占比：对话约 {stat.get('对话', 0) * 100:.0f}%，"
        f"描写约 {stat.get('描写', 0) * 100:.0f}%，"
        f"心理约 {stat.get('心理', 0) * 100:.0f}%，"
        f"叙述约 {stat.get('叙述', 0) * 100:.0f}%。对话是主导模式。"
    )
    lines.append(
        f"· 对话有惯性：一旦进入对话，通常连续 {runs.get('对话', 0):.1f} 段左右才切走；"
        f"而描写/心理/叙述都很短促（约 {runs.get('描写', 0):.1f} 段就转开），不要长篇铺陈。"
    )
    top = max(((tm["counts"][i][j], labels[i], labels[j])
               for i in range(len(labels)) for j in range(len(labels))
               if i != j), key=lambda t: t[0])
    lines.append(f"· 最常见的模式切换是「{top[1]}→{top[2]}」，其余模式最终都倾向于回到对话。")
    lines.append("· 越往后节奏越紧：句子逐步变短，收尾处最短促。")
    return "\n".join(lines)


async def generate(refs: list[str], task: str, prior: str | None) -> str:
    block = "\n---\n".join(refs)
    user = f"【文风样本】\n{block}\n\n"
    if prior:
        user += prior + "\n\n"
    user += f"【任务】{task}"
    return await llm.complete(
        [{"role": "system", "content": _GEN_SYSTEM}, {"role": "user", "content": user}],
        temperature=0.8,
    )


def rhythm_fit(text: str, norms: dict[str, tuple[float, float]]) -> float:
    """Mean |z| between a draft's texture and the corpus norms — lower is closer.

    Expressed in corpus standard deviations so the four metrics, which live on
    very different scales, contribute comparably.
    """
    tex = rhythm.texture(text)
    zs = []
    for key in TEXTURE_KEYS:
        mean, sd = norms[key]
        if sd:
            zs.append(abs(tex[key] - mean) / sd)
    return statistics.mean(zs) if zs else 0.0


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--n", type=int, default=20)
    args = ap.parse_args()

    path = os.path.join(OUT, "rhythm_profile.json")
    if not os.path.exists(path):
        raise SystemExit("run eval/run_rhythm_profile.py first")
    with open(path, encoding="utf-8") as fh:
        profile = json.load(fh)
    prior = build_prior(profile)
    print("=== 注入的节奏先验 ===")
    print(prior)

    async with AsyncSessionLocal() as db:
        segs = list((await db.execute(
            select(CorpusSegment).where(CorpusSegment.work == args.work)
            .order_by(CorpusSegment.chapter_no, CorpusSegment.seq)
        )).scalars().all())

    norms = {}
    for key in TEXTURE_KEYS:
        vals = [getattr(s, key) for s in segs if getattr(s, key) is not None]
        norms[key] = (statistics.mean(vals), statistics.pstdev(vals))
    print("\n=== 语料纹理基准（均值 ± sd）===")
    for key in TEXTURE_KEYS:
        print(f"  {key:<18} {norms[key][0]:.3f} ± {norms[key][1]:.3f}")

    # samples shown to the generator and the held-out judging bar are disjoint,
    # and identical across arms — a difference can only come from the prior
    style_refs = [s.text for s in segs[10:10 + STYLE_REFS]]
    judge_refs = [s.text for s in segs[100:100 + JUDGE_REFS]]

    probes = PROBES[: args.n]
    fit_a, fit_b, style_a, style_b = [], [], [], []
    print(f"\n=== A/B（n={len(probes)}）===")
    for i, probe in enumerate(probes, 1):
        draft_a = await _retry(lambda: generate(style_refs, probe, prior))
        draft_b = await _retry(lambda: generate(style_refs, probe, None))
        fa = rhythm_fit(draft_a, norms)
        fb = rhythm_fit(draft_b, norms)
        va = await _retry(lambda: imitation.judge_draft_stable(draft_a, judge_refs))
        vb = await _retry(lambda: imitation.judge_draft_stable(draft_b, judge_refs))
        fit_a.append(fa); fit_b.append(fb)
        style_a.append(va["style_score"]); style_b.append(vb["style_score"])
        print(f"  {i:2d}. 节奏距离 A={fa:.2f} B={fb:.2f} {'A胜' if fa < fb else 'B胜' if fb < fa else '平'}"
              f"   |  style A={va['style_score']} B={vb['style_score']}", flush=True)

    n = len(probes)
    fit_wins = sum(1 for a, b in zip(fit_a, fit_b) if a < b)
    style_wins = sum(1 for a, b in zip(style_a, style_b) if a > b)
    style_ties = sum(1 for a, b in zip(style_a, style_b) if a == b)
    print("\n===== 汇总 =====")
    print(f"n={n}")
    print(f"【主指标】节奏距离（越小越贴近语料，单位=语料 sd）")
    print(f"  A(注入先验)={statistics.mean(fit_a):.3f}   B(基线)={statistics.mean(fit_b):.3f}"
          f"   差={statistics.mean(fit_b) - statistics.mean(fit_a):+.3f}")
    print(f"  A 更贴近的次数: {fit_wins}/{n}")
    print(f"【副指标】style 分（裁判取中位数去噪）")
    print(f"  A={statistics.mean(style_a):.2f}   B={statistics.mean(style_b):.2f}"
          f"   差={statistics.mean(style_a) - statistics.mean(style_b):+.2f}")
    print(f"  A 胜 {style_wins} / 平 {style_ties} / 负 {n - style_wins - style_ties}")


if __name__ == "__main__":
    asyncio.run(main())
