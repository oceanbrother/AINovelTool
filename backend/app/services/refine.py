# -*- coding: utf-8 -*-
"""精修模式编排 (refine) — 多候选 → 场景计划 → 校验写作 → 重写。

This is the "precision" rung of the planning-strength ladder (exploration =
续写/破壁, standard = plan→write, precision = the full loop here). It turns the
imitation self-check loop from "check the prose's voice" into "check the draft
against an explicit plan" — the plan's must_include / must_not are objectively
verifiable, so the write gate is a program check, not another noisy 1-10 judge.

Stages are separated by the two human-in-the-loop decision points, so this is
not one end-to-end stream but three calls:

  compose_candidates  → author picks / merges a candidate
  expand_plan         → author edits the ScenePlan
  refine_write_stream → the verified generation loop (Phase 2)
"""
from __future__ import annotations

import json
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.core.config import settings
from app.core.embedding import embed_texts
from app.models.chapter import Chapter
from app.models.character import Character
from app.models.story_fact import StoryFact
from app.schemas.refine import (
    ConstraintCheck,
    PlanCandidate,
    RefineAttempt,
    RefineCandidatesResponse,
    RefinePlanResponse,
    ScenePlan,
    VerifyResult,
)
from app.services import (
    cliche,
    generation,
    imitation,
    knowledge,
    retrieval,
    rhythm,
    scene,
)

# Naming a feeling once can be a deliberate beat; doing it repeatedly is the
# scene explaining itself instead of happening.
MAX_DIRECT_EMOTION = 1

# Cosine (bge-m3 vectors are L2-normalised, so a dot product IS the cosine)
# above which a candidate one-liner is flagged as "疑似重复既有桥段". Advisory
# only — the author still decides; set high to avoid false alarms. Tunable.
REPETITION_THRESHOLD = 0.80


def _parse_json(raw: str) -> dict:
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group())
    except json.JSONDecodeError:
        return {}


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _settings_block(chunks: list) -> str:
    return "\n".join(
        f"[设定{i}] ({c.source_type}) {c.content}" for i, c in enumerate(chunks)
    ) or "（无命中；可基于片段本身构思，设定引用留空）"


# --- ① 候选 --------------------------------------------------------------------

_CANDIDATES_SYSTEM = (
    "你是长篇小说的情节策划。作者给你一段正文片段和一组【设定命中】。"
    "请提出 {n} 条**明显不同**的后续走向候选，彼此必须在这些维度上拉开实质差异：\n"
    "· conflict_source：冲突来源（外部威胁 / 人际 / 内心 / 环境…）\n"
    "· agency：主角是主动推进还是被动卷入\n"
    "· reveal_order：关键信息的揭示顺序（先果后因 / 层层递进 / 一开始摊牌…）\n"
    "· emotion_arc：情绪走势（如 紧绷→释然 / 轻松→失控）\n"
    "· turn：转折机制（误会 / 背叛 / 意外发现 / 时间压力…）\n"
    "· open_question：结尾留下的问题（勾住下一段的悬念）\n"
    "另给每条：\n"
    "· summary：一句话走向\n"
    "· refs：这条候选用到的设定编号数组（只能引用给定编号，用于接地，不得虚构设定）\n\n"
    '只输出 JSON：{"candidates":[{"summary":"...","conflict_source":"...",'
    '"agency":"...","reveal_order":"...","emotion_arc":"...","turn":"...",'
    '"open_question":"...","refs":[0,2]}]}\n'
    "规则：候选之间要有实质差异，不能只是措辞不同；每条都要贴合这段正文的具体情境，"
    "不写通用套路；设定引用必须基于给定的设定命中。"
)


async def _chapter_reference_texts(db: AsyncSession, project_id: int) -> list[str]:
    """Existing chapters' one-liners for repetition comparison.

    Prefer the summary (apples-to-apples with a candidate one-liner); fall back
    to a content head when a chapter has no summary yet.
    """
    rows = (
        await db.execute(select(Chapter).where(Chapter.project_id == project_id))
    ).scalars().all()
    texts: list[str] = []
    for ch in rows:
        t = (ch.summary or "").strip() or (ch.content or "")[:300].strip()
        if t:
            texts.append(t)
    return texts


async def compose_candidates(
    db: AsyncSession,
    project_id: int,
    fragment: str,
    num_candidates: int = 4,
    top_k_settings: int = 6,
) -> RefineCandidatesResponse:
    chunks = await retrieval.retrieve_settings(
        db, project_id, fragment, channel="hints", top_k=top_k_settings
    )
    raw = await llm.complete(
        [
            {"role": "system", "content": _CANDIDATES_SYSTEM.replace("{n}", str(num_candidates))},
            {
                "role": "user",
                "content": f"【正文片段】\n{fragment}\n\n【设定命中】\n{_settings_block(chunks)}",
            },
        ],
        temperature=0.75,  # higher than 续写: candidates must diverge
    )
    data = _parse_json(raw)

    candidates: list[PlanCandidate] = []
    for c in data.get("candidates", []):
        summary = str(c.get("summary", "")).strip()
        if not summary:
            continue
        refs = [i for i in c.get("refs", []) if isinstance(i, int) and 0 <= i < len(chunks)]
        candidates.append(
            PlanCandidate(
                summary=summary,
                conflict_source=str(c.get("conflict_source", "")),
                agency=str(c.get("agency", "")),
                reveal_order=str(c.get("reveal_order", "")),
                emotion_arc=str(c.get("emotion_arc", "")),
                turn=str(c.get("turn", "")),
                open_question=str(c.get("open_question", "")),
                refs=refs,
                grounded=[chunks[i].content for i in refs],
            )
        )

    await _flag_repetition(db, project_id, candidates)
    return RefineCandidatesResponse(candidates=candidates, raw_settings=chunks)


async def _flag_repetition(
    db: AsyncSession, project_id: int, candidates: list[PlanCandidate]
) -> None:
    """Program-side check: flag candidates that echo an existing chapter.

    Pure vector work — embed each candidate one-liner and the existing chapters'
    one-liners, take the max cosine. No LLM, ties into the anti-hallucination
    "retrieval-grounded" thesis rather than piling on another judge call.
    """
    refs = await _chapter_reference_texts(db, project_id)
    if not refs or not candidates:
        return
    ref_vecs = await embed_texts(refs)
    cand_vecs = await embed_texts([c.summary for c in candidates])
    for c, cv in zip(candidates, cand_vecs):
        best = max((_cosine(cv, rv) for rv in ref_vecs), default=0.0)
        c.repetition = round(best, 4)
        c.repetition_flag = best >= REPETITION_THRESHOLD


# --- ② 场景计划 ----------------------------------------------------------------

_PLAN_SYSTEM = (
    "你是资深小说编辑。作者选定了一条后续走向，给你正文片段、该走向、以及【设定命中】。"
    "请把它扩写成一份**场景计划**——约束这一场要完成什么，但不替作者写台词和动作。"
    "输出这些字段：\n"
    "· goal：本场目标（这一场要达成的叙事目的）\n"
    "· desire：角色欲望（主要角色这一场想要什么）\n"
    "· conflict：冲突（阻碍欲望的力量）\n"
    "· info_shift：信息变化（读者 / 角色从知道什么到知道什么）\n"
    "· emotion_curve：情绪曲线（如 试探→不安→短暂失控→克制收尾）\n"
    "· must_include：必须出现的具体物象 / 事件数组（越具体越好，"
    "如『柜台下的旧报纸』『停摆的电子钟』）\n"
    "· must_not：不能发生的事数组（如『直接揭示幕后身份』『某角色死亡』）\n"
    "· end_state：结尾状态（这一场结束时的处境，为下一场留口子）\n\n"
    '只输出 JSON：{"goal":"...","desire":"...","conflict":"...","info_shift":"...",'
    '"emotion_curve":"...","must_include":["...","..."],"must_not":["...","..."],'
    '"end_state":"..."}\n'
    "规则：must_include / must_not 必须是能客观判断在不在的具体项，不写抽象要求；"
    "所有内容基于给定设定，不虚构新设定。\n"
    # A model asked for a scene plan will happily stack "establish character +
    # advance relationship + plant a clue + escalate conflict + hint at theme"
    # into one scene. Every scene then strains, and a long book loses its
    # breathing room — so the budget is stated explicitly.
    "本场只承担一个主要目的，附带目的至多两个；"
    "允许存在只用于陪伴、休息或展示生活的缓冲场景，不必每场都推进主线。\n"
    # Crying is a result, not a function. Naming what changed irreversibly is
    # what keeps 目标 from collapsing into a description of the surface events.
    "写 goal 时先自问：这一场结束后，故事发生了什么不可逆的变化？"
    "把那个变化写成目标，而不是把表面发生的事复述一遍。"
)


def _candidate_brief(c: PlanCandidate) -> str:
    parts = [f"走向：{c.summary}"]
    for label, val in (
        ("冲突来源", c.conflict_source),
        ("主动/被动", c.agency),
        ("信息揭示顺序", c.reveal_order),
        ("情绪走势", c.emotion_arc),
        ("转折机制", c.turn),
        ("结尾悬念", c.open_question),
    ):
        if val:
            parts.append(f"{label}：{val}")
    return "\n".join(parts)


async def expand_plan(
    db: AsyncSession,
    project_id: int,
    fragment: str,
    candidate: PlanCandidate,
    top_k_settings: int = 6,
) -> RefinePlanResponse:
    # re-ground on the chosen direction (not just the fragment) so the plan's
    # settings are relevant to where the author decided to go
    query = f"{fragment}\n{candidate.summary}"
    chunks = await retrieval.retrieve_settings(
        db, project_id, query, channel="hints", top_k=top_k_settings
    )
    raw = await llm.complete(
        [
            {"role": "system", "content": _PLAN_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"【正文片段】\n{fragment}\n\n【选定走向】\n{_candidate_brief(candidate)}"
                    f"\n\n【设定命中】\n{_settings_block(chunks)}"
                ),
            },
        ],
        temperature=0.4,  # planning is convergent — keep it grounded
    )
    data = _parse_json(raw)

    def _strlist(key: str) -> list[str]:
        return [str(x).strip() for x in data.get(key, []) if str(x).strip()]

    plan = ScenePlan(
        goal=str(data.get("goal", "")),
        desire=str(data.get("desire", "")),
        conflict=str(data.get("conflict", "")),
        info_shift=str(data.get("info_shift", "")),
        emotion_curve=str(data.get("emotion_curve", "")),
        must_include=_strlist("must_include"),
        must_not=_strlist("must_not"),
        end_state=str(data.get("end_state", "")),
        grounded=[c.content for c in chunks],
    )
    # scene tag via the anchor-vector classifier (zero LLM) — reused at write
    # time to pull same-scene style samples
    tag_seed = " ".join(filter(None, [plan.goal, plan.conflict, plan.emotion_curve]))
    if tag_seed.strip():
        plan.scene_tag = await scene.classify_text(tag_seed)

    # Continuity rules compiled from the knowledge table, appended by PROGRAM
    # rather than asked of the planner: a character who cannot know something
    # must not say it, and that guarantee should not depend on whether the model
    # remembered to write the line. Kept in their own field so the UI can show
    # where they came from and editing the plan cannot drop them.
    plan.derived_must_not = await derive_constraints(
        db, project_id, existing=plan.must_not
    )

    return RefinePlanResponse(plan=plan, raw_settings=chunks)


async def derive_constraints(
    db: AsyncSession, project_id: int, existing: list[str] | None = None
) -> list[str]:
    """Load the project's knowledge state and compile it into must_not lines."""
    facts = list((await db.execute(
        select(StoryFact).where(StoryFact.project_id == project_id)
    )).scalars().all())
    if not facts:
        return []
    names = dict((await db.execute(
        select(Character.id, Character.name).where(Character.project_id == project_id)
    )).all())
    return knowledge.derive_must_not(facts, names, existing or [])


# --- ③ 校验写作 + 重写 ---------------------------------------------------------

_VERIFY_SYSTEM = (
    "你是严格的稿件核对员。给你【必须出现】和【不能发生】两组约束，以及一段【待核对稿件】。"
    "逐条客观判断（只看在不在，不评价文笔）：\n"
    "· 必须出现的每一项：稿件里是否真的出现了。\n"
    "· 不能发生的每一项：稿件里是否触犯了。\n"
    '只输出 JSON：{"include":[{"ok":true,"evidence":"稿中依据"}],'
    '"exclude":[{"ok":true,"evidence":"说明"}]}\n'
    "include[i].ok = 该必须项出现了为 true；exclude[i].ok = 成功规避（未触犯）为 true。"
    "两个数组的顺序与长度必须与给定约束一一对应。"
)


async def verify_draft(draft: str, plan: ScenePlan) -> VerifyResult:
    """Checklist verification of a draft against the plan's constraints.

    We control the check list (built from the plan), so the judge only fills
    booleans — no reliance on it echoing the constraint text, and a missing
    entry defaults to *unsatisfied* (conservative: retry rather than pass a
    silent violation). This is an objective present/absent call, far more
    reliable than a 1-10 style score — which is exactly why the gate can be a
    program check instead of another noisy judge.
    """
    # the author's prohibitions and the ones compiled from knowledge state are
    # checked together — the judge has no reason to treat them differently, and
    # provenance is preserved on each check for the UI rather than in the prompt
    exclusions = list(plan.must_not) + [
        t for t in plan.derived_must_not if t not in plan.must_not
    ]
    derived_from = len(plan.must_not)
    if not plan.must_include and not exclusions:
        return VerifyResult(satisfied=True, checks=[])

    inc = "\n".join(f"{i}. {t}" for i, t in enumerate(plan.must_include)) or "（无）"
    exc = "\n".join(f"{i}. {t}" for i, t in enumerate(exclusions)) or "（无）"
    raw = await llm.complete(
        [
            {"role": "system", "content": _VERIFY_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"【必须出现】\n{inc}\n\n【不能发生】\n{exc}\n\n【待核对稿件】\n{draft}"
                ),
            },
        ],
        model=settings.llm_judge_model,  # careful checking on the reasoner model
        temperature=0.0,
    )
    data = _parse_json(raw)
    inc_res = data.get("include", []) if isinstance(data.get("include"), list) else []
    exc_res = data.get("exclude", []) if isinstance(data.get("exclude"), list) else []

    checks: list[ConstraintCheck] = []
    for i, t in enumerate(plan.must_include):
        r = inc_res[i] if i < len(inc_res) and isinstance(inc_res[i], dict) else {}
        checks.append(
            ConstraintCheck(
                text=t, kind="include",
                satisfied=bool(r.get("ok", False)),
                evidence=str(r.get("evidence", "")),
            )
        )
    for i, t in enumerate(exclusions):
        r = exc_res[i] if i < len(exc_res) and isinstance(exc_res[i], dict) else {}
        checks.append(
            ConstraintCheck(
                text=t, kind="exclude",
                satisfied=bool(r.get("ok", False)),
                evidence=str(r.get("evidence", "")),
                source="knowledge" if i >= derived_from else "author",
            )
        )
    checks.extend(program_checks(draft))
    satisfied = all(c.satisfied for c in checks) if checks else True
    return VerifyResult(satisfied=satisfied, checks=checks)


def program_checks(draft: str) -> list[ConstraintCheck]:
    """Checks that need counting, not judgement — so no model is consulted.

    Stock phrases and named feelings are decidable by looking at the characters,
    which makes these the only checks in the loop with no variance at all. They
    also come back with the offending text quoted, so the rewrite instruction
    can say which line to cut rather than asking vaguely for better prose.
    """
    checks: list[ConstraintCheck] = []

    found = cliche.find_cliches(draft)
    checks.append(
        ConstraintCheck(
            text="不使用套话",
            kind="exclude",
            satisfied=not found,
            evidence="、".join(found[:4]) if found else "",
            source="program",
        )
    )

    named = rhythm.direct_emotion_sentences(draft)
    checks.append(
        ConstraintCheck(
            text=f"直接点破情绪的句子不超过 {MAX_DIRECT_EMOTION} 句",
            kind="exclude",
            satisfied=len(named) <= MAX_DIRECT_EMOTION,
            evidence="；".join(s[:20] for s in named[:3]) if named else "",
            source="program",
        )
    )
    return checks


def _feedback_from_checks(checks: list[ConstraintCheck]) -> str:
    """Turn failed constraints into concrete rewrite instructions."""
    lines = []
    for c in checks:
        if c.satisfied:
            continue
        if c.kind == "include":
            lines.append(f"必须出现但缺失：{c.text}")
        else:
            lines.append(f"不能发生却触犯：{c.text}")
    return "；".join(lines)


def _plan_block(plan: ScenePlan) -> str:
    """Render the ScenePlan into a generation directive.

    Goal/desire/conflict/emotion are soft conditions; must_include is soft-supply
    to land in the prose; must_not is an outright prohibition. Not a line-by-line
    script — the plan constrains *what the scene must accomplish*, not the words.
    """
    lines = ["【场景计划】依此写出这一场（不要逐条点名，要化在正文里）："]
    for label, val in (
        ("本场目标", plan.goal),
        ("角色欲望", plan.desire),
        ("冲突", plan.conflict),
        ("信息变化", plan.info_shift),
        ("情绪曲线", plan.emotion_curve),
        ("结尾状态", plan.end_state),
    ):
        if val:
            lines.append(f"· {label}：{val}")
    if plan.must_include:
        lines.append("· 必须出现（务必在正文里落实）：" + "；".join(plan.must_include))
    # the author's prohibitions and the continuity rules compiled from knowledge
    # state read the same way to the model, so they go in one list; only the UI
    # needs to know which is which
    prohibitions = list(plan.must_not) + [
        t for t in plan.derived_must_not if t not in plan.must_not
    ]
    # the stock-phrase ban is concrete enough to state up front — and it is
    # also counted afterwards, so saying it here only saves a rewrite pass
    prohibitions.append(cliche.prohibition_line())
    prohibitions.append(
        f"直接点破情绪（如「他感到孤独」）超过 {MAX_DIRECT_EMOTION} 句——"
        "情绪要靠动作、物件与停顿泄露"
    )
    lines.append("· 不能发生（务必回避）：" + "；".join(prohibitions))
    return "\n".join(lines)


async def refine_write_stream(
    db: AsyncSession,
    chapter: Chapter,
    plan: ScenePlan,
    instruction: str | None = None,
    max_attempts: int = 2,
):
    """Plan-conditioned generation with a constraint-verified rewrite loop.

    The agentic core: generate → verify against the plan's must_include /
    must_not → decide (pass / rewrite with the failed constraints as feedback).
    Reuses build_imitation_context (scene-aware style recall) and the imitate
    loop's stage/attempt/result shape so the frontend can share rendering.
    Yields ("stage", str) / ("attempt", RefineAttempt) / ("result", (draft, attempts, clues)).
    """
    yield "stage", "检索设定与文风样本"
    query = " ".join(
        filter(None, [plan.goal, plan.conflict, *plan.must_include])
    ).strip() or chapter.title or ""
    context, chunks, styles = await generation.build_imitation_context(db, chapter, query)
    style_refs = [s.content for s in styles]

    base_user = context + "\n\n" + _plan_block(plan)
    if instruction:
        base_user += f"\n\n【方向指引】{instruction}"

    attempts: list[RefineAttempt] = []
    best_draft = ""
    best_key = -999.0
    notes: str | None = None
    for i in range(max_attempts):
        yield "stage", (
            f"生成第 {i + 1} 稿" if notes is None
            else f"按未达标约束重写第 {i + 1} 稿"
        )
        user = base_user if notes is None else (
            base_user + f"\n\n【上一稿未达标】\n{notes}\n依据以上修正重写，其余约束不变。"
        )
        draft = await llm.complete(
            [
                {"role": "system", "content": generation._CONTINUE_SYSTEM},
                {"role": "user", "content": user},
            ]
        )
        yield "stage", f"第 {i + 1} 稿校验中（核对必须出现/不能发生 + 复述检测）"
        overlap = imitation.ngram_overlap(draft, style_refs) if style_refs else 0.0
        verdict = await verify_draft(draft, plan)
        passed = verdict.satisfied and overlap <= imitation.NGRAM_MAX_OVERLAP
        attempt = RefineAttempt(
            attempt=i + 1,
            satisfied=verdict.satisfied,
            checks=verdict.checks,
            ngram_overlap=round(overlap, 4),
            notes=_feedback_from_checks(verdict.checks),
        )
        attempts.append(attempt)
        yield "attempt", attempt
        # best = most constraints satisfied; plagiarism failures ranked last
        key = (
            float(sum(c.satisfied for c in verdict.checks))
            if overlap <= imitation.NGRAM_MAX_OVERLAP
            else -100.0
        )
        if key > best_key:
            best_key, best_draft = key, draft
        if passed:
            break
        notes = attempt.notes or "约束未完全达标，请对照场景计划修正。"

    yield "result", (best_draft, attempts, chunks)
