# -*- coding: utf-8 -*-
"""三臂对照：同一场、同一份约束，比"给什么"和"跑什么机器"。

问的是作者的问题：**项目里这一堆参数和约束，比直接把设定喂进提示词好多少？**

  A 只给文风样本        —— 地板。它不知道这个故事，约束几乎必然不达标。
                           它回答的是另一个问题：光靠模仿笔法能拿到什么。
  B 设定全量塞进提示词  —— 诚实的基线。任何人拿着同一批材料写一个好提示词
                           就能做到这个程度，不需要这个项目。
  C 现有管线            —— 检索 + 场景计划 + 校验重写循环。

**三臂必须同模型同温度**，否则差异里混着"换了个模型"，谁赢都解释不了。
子 agent 跑在另一个模型上，所以这里不用子 agent——它只是手段，要的是对照。

不对称是设计的一部分，不是缺陷：C 拿到了显式约束，A/B 没有。这正是计划层
存在的意义，所以约束兑现率天然偏向 C。因此同时报几项**不偏向 C** 的程序指标：

  与参考样本的 n-gram 重叠   模仿得越像越可能是在复述，低者胜
  俗套命中                    services/cliche.py，零 LLM
  直接情绪句                  services/rhythm.py，零 LLM
  纹理距离                    与**参考作品**的距离，低者更像它。第一版拿项目自己的
                              章节当基准，实测那 84,566 字里作者亲笔只占 6%，其余是工具
                              生成的——自我参照，作废。

    python eval/run_three_arm.py --plan <ab_plan.json> --materials <ab3_materials.json> \
        --out-dir <仓库外目录>

稿件与材料都内嵌正文，一律走仓库外路径。
"""
from __future__ import annotations

import argparse
import asyncio
import io
import json
import os

from sqlalchemy import select

from app.core import llm
from app.core.config import settings
from app.db import AsyncSessionLocal
from app.models.chapter import Chapter
from app.models.corpus_segment import CorpusSegment
from app.schemas.refine import PlanCandidate, ScenePlan
from app.services import cliche, imitation, refine, rhythm

# A 臂：只有笔法，没有故事。
_A_SYSTEM = (
    "你是中文小说写作者。模仿【文风样本】的语感与节奏，写一个场景，2000-2500 字。\n"
    "只借语感，**不得复述样本里的任何句子、人名、地名、专有名词**。\n"
    "不要写设定说明，直接写场景。只输出正文。"
)

# B 臂：设定全给，但没有场景计划、没有检索、没有校验循环。
_B_SYSTEM = (
    "你是中文小说写作者。依据【世界观】【人物】【前文】接着往下写一场，2000-2500 字。\n"
    "人物与世界观规则必须与给定设定一致，不得自造设定。\n"
    "模仿【文风样本】的语感与节奏，但**不得复述样本里的任何句子、人名、地名、专有名词**。\n"
    "不要写设定说明，直接写场景。只输出正文。"
)


def _mats_block(m: dict, *, with_settings: bool) -> str:
    styles = "\n---\n".join(m["style_samples"])
    if not with_settings:
        return f"【文风样本】\n{styles}"
    world = "\n".join(f"·（{w['category']}）{w['title']}：{w['content']}" for w in m["world"])
    chars = "\n".join(f"·{c['name']}：{c['summary']}" for c in m["characters"])
    return (
        f"【世界观】\n{world}\n\n【人物】\n{chars}\n\n"
        f"【前文】\n{m['fragment']}\n\n【文风样本】\n{styles}"
    )


async def _write_arm(system: str, user: str) -> str:
    return await llm.complete(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=settings.llm_temperature,
        max_tokens=llm.PROSE_MAX_TOKENS,
        **llm.NO_REASONING,
    )


def _program_metrics(draft: str, refs: list[str], target: dict | None) -> dict:
    """零 LLM 的指标。它们不知道场景计划，所以不偏向任何一臂。

    纹理的参照系是**参考作品**（龙族），不是作者自己的正文。第一版拿项目里
    全部章节当基准，实测那 84,566 字里作者亲笔只占 6%，其余是本会话生成的
    ——那个"距离"量的是"像不像我写的续篇"，自我参照，任何结论都不成立。

    参考作品是外部的，且正是文风样本的来源，所以"像不像它"这个问题本身成立。
    """
    tex = rhythm.texture(draft)
    dist = (
        sum(abs(tex[k] - target[k]) / max(abs(target[k]), 1e-6) for k in tex) / len(tex)
        if target else None
    )
    return {
        "字数": len(draft),
        "n-gram重叠": round(imitation.ngram_overlap(draft, refs), 4) if refs else None,
        "俗套命中": len(cliche.find_cliches(draft)),
        "直接情绪句": rhythm.direct_emotion_sentences(draft)
        if hasattr(rhythm, "direct_emotion_sentences") else None,
        "纹理距离": round(dist, 3) if dist is not None else None,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", required=True, help="ab_plan.json —— 三臂共用的约束")
    ap.add_argument("--materials", required=True)
    ap.add_argument("--out-dir", required=True, help="仓库外目录：稿件内嵌正文")
    ap.add_argument("--project-id", type=int, default=7)
    ap.add_argument("--corpus", default="龙族", help="纹理参照的参考作品")
    args = ap.parse_args()

    p = json.load(io.open(args.plan, encoding="utf-8"))
    m = json.load(io.open(args.materials, encoding="utf-8"))
    plan = ScenePlan(
        goal=p["goal"], desire=p["desire"], conflict=p["conflict"],
        info_shift=p["info_shift"], emotion_curve=p["emotion_curve"],
        must_include=p["must_include"], must_not=p["must_not"],
        end_state=p["end_state"], grounded=p.get("grounded", []),
    )
    os.makedirs(args.out_dir, exist_ok=True)
    print(f"共用约束：{len(plan.must_include)} 必须 / {len(plan.must_not)} 禁止")
    print(f"三臂同模型 {settings.llm_model} · 温度 {settings.llm_temperature}\n", flush=True)

    direction = p["goal"].split("；")[0][:60]
    drafts: dict[str, str] = {}

    drafts["A 只给文风"] = await _write_arm(
        _A_SYSTEM, _mats_block(m, with_settings=False) + f"\n\n【场景】\n{direction}"
    )
    print(f"A 完成 {len(drafts['A 只给文风'])} 字", flush=True)

    drafts["B 设定全塞"] = await _write_arm(
        _B_SYSTEM, _mats_block(m, with_settings=True) + f"\n\n【场景】\n{direction}"
    )
    print(f"B 完成 {len(drafts['B 设定全塞'])} 字", flush=True)

    async with AsyncSessionLocal() as db:
        chapter = await db.get(Chapter, p["chapter_id"])
        attempts = []
        # two_stage=True：内容通道不给文风样本 → 声音通道按样本重述且禁改事件。
        # 这是本项目唯一专门管文风的机制。第一版没开，等于关着风格功能比文风。
        # 它上一轮实测是分裂的：约束兑现 88.0% vs 72.6% 更好，但 style 3.20 vs
        # 3.80 更差，且 1/5 概率破坏已达成约束被复核挡下。
        async for kind, data in refine.refine_write_stream(
            db, chapter, plan, None, max_attempts=2, two_stage=True
        ):
            if kind == "result":
                drafts["C 现有管线"], attempts, _ = data
        print(f"C 完成 {len(drafts['C 现有管线'])} 字（{len(attempts)} 稿）", flush=True)

        # 参照系 = 参考作品本身。抽样而非全量：纹理在几万字上已经稳定。
        segs = (await db.execute(
            select(CorpusSegment).where(CorpusSegment.work == args.corpus)
            .order_by(CorpusSegment.chapter_no, CorpusSegment.seq).limit(120)
        )).scalars().all()
        target = rhythm.texture("\n".join(s.text for s in segs)) if segs else None
        print(f"纹理参照系：《{args.corpus}》{len(segs)} 段" if segs
              else "纹理参照系：无（语料未入库）", flush=True)
        rows = []
        for name, d in drafts.items():
            v = await refine.verify_draft(d, plan)
            inc = [c for c in v.checks if c.kind == "include"]
            exc = [c for c in v.checks if c.kind == "exclude"]
            rows.append((name, d, v, {
                "兑现": sum(c.satisfied for c in v.checks) / max(len(v.checks), 1),
                "必须出现": sum(c.satisfied for c in inc) / max(len(inc), 1),
                "规避": sum(c.satisfied for c in exc) / max(len(exc), 1),
                **_program_metrics(d, m["style_samples"], target),
            }))

    print("\n===== 结果 =====")
    hdr = ["兑现", "必须出现", "规避", "字数", "n-gram重叠", "俗套命中", "纹理距离"]
    print(f"{'臂':<12}" + "".join(f"{h:>11}" for h in hdr))
    for name, _d, _v, r in rows:
        cells = []
        for h in hdr:
            v = r.get(h)
            cells.append("—" if v is None else
                         (f"{v:>10.0%}" if h in ("兑现", "必须出现", "规避") else f"{v:>10}"))
        print(f"{name:<12}" + "".join(f"{c:>11}" for c in cells))

    # 稿件落盘：作者要审的是文字。比率抹掉、只留代号，便于盲读后再对照。
    for i, (name, d, v, r) in enumerate(rows):
        io.open(os.path.join(args.out_dir, f"arm_{'ABC'[i]}.md"), "w", encoding="utf-8").write(d)
    with io.open(os.path.join(args.out_dir, "three_arm_report.md"), "w", encoding="utf-8") as fh:
        fh.write("# 三臂对照\n\n共用约束\n\n**必须出现**\n"
                 + "\n".join(f"{k}. {x}" for k, x in enumerate(plan.must_include))
                 + "\n\n**不能发生**\n"
                 + "\n".join(f"{k}. {x}" for k, x in enumerate(plan.must_not)))
        for i, (name, d, v, r) in enumerate(rows):
            fh.write(f"\n\n---\n\n## {'ABC'[i]} · {name}\n\n")
            fh.write(" · ".join(f"{k} {v2:.0%}" if isinstance(v2, float) and k in
                                ("兑现", "必须出现", "规避") else f"{k} {v2}"
                                for k, v2 in r.items() if v2 is not None))
            fails = [c for c in v.checks if not c.satisfied]
            if fails:
                fh.write("\n\n未达标：\n" + "\n".join(
                    f"- ({c.kind}) {c.text} — {c.evidence or '（无证据）'}" for c in fails))
            fh.write(f"\n\n### 正文\n\n{d}\n")
    print(f"\n稿件与报告 → {args.out_dir}")


if __name__ == "__main__":
    asyncio.run(main())
