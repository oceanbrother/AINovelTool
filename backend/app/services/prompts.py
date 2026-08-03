"""One place to see every prompt this tool sends, and to edit the ones that are
safe to edit.

Why this exists
---------------
Five rounds of work produced corrections that are *only* expressible as prompt
text — cap the number of functions per scene, ask what changed irreversibly,
forbid the voice pass from touching information boundaries. All of them were
compiled into string literals the author cannot reach. When a generated plan
comes back wrong, the author's only recourse was to regenerate and hope.

The borrowed reference project (MuMuAINovel) answers this differently: it never
asks the model to score subjective qualities, it makes the *instruction* the
editable artifact. That sidesteps a problem this project hit four times — a
model asked to rate 主观量 cannot do it reliably enough to drive anything
(function labels twice, rhythm prior, and the 5-level state scales).

Two classes of prompt, and the difference matters
-------------------------------------------------
**创作类** (editable): they shape what gets written. If the author makes one
worse, they see worse drafts and can undo. Cheap to be wrong.

**量具类** (locked): constraint verification, style judging, function
labelling. These are instruments. Every recorded number came out of these exact
strings; editing one silently invalidates comparisons against every earlier
run. The lock is structural — `verify_draft`, `judge_draft` and the labellers
take no `AsyncSession`, so no code path can read an override for them. They are
listed here read-only so the author can *see* them, because hiding a measuring
device is its own kind of dishonesty.

Defaults stay in their own modules
----------------------------------
`default()` reads the live literal by import. Nothing is duplicated here, so a
default cannot drift out of sync with the code that uses it, and an upgrade that
improves a default reaches everyone who has not overridden that slot.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import import_module

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.prompt_template import PromptTemplate


@dataclass(frozen=True)
class Slot:
    key: str
    label: str
    module: str  # under app.services
    attr: str
    editable: bool
    note: str
    # substrings the body must still contain after an edit. Losing one does not
    # raise at generation time — it silently changes behaviour, which is worse.
    required: tuple[str, ...] = ()


SLOTS: tuple[Slot, ...] = (
    # --- 创作类：可编辑 ---
    Slot(
        "refine.candidates", "精修 ① 候选走向", "refine", "_CANDIDATES_SYSTEM", True,
        "要求候选之间在六个维度上拉开实质差异。{n} 会被替换成候选条数。",
        required=("{n}",),
    ),
    Slot(
        "refine.plan", "精修 ② 场景计划", "refine", "_PLAN_SYSTEM", True,
        "产出 must_include / must_not 等可校验约束。R1 的两条纠偏就在这里："
        "限制本场功能数量、goal 要写不可逆变化。",
    ),
    Slot(
        "refine.draft", "精修 ③ 内容通道", "refine", "_DRAFT_SYSTEM", True,
        "两阶段写作的第一段：只管把事情写对，不给文风样本——"
        "没东西可模仿就不会为句子好听而含糊事件。",
    ),
    Slot(
        "refine.voice", "精修 ③ 声音通道", "refine", "_VOICE_SYSTEM", True,
        "两阶段写作的第二段：只换讲法。禁止改动事件与信息边界那几句是这个设计"
        "能用的前提——实测 1/5 概率破坏已达成约束，靠复核挡下。",
    ),
    Slot(
        "generation.continue", "续写", "generation", "_CONTINUE_SYSTEM", True,
        "检索增强的顺序续写。",
    ),
    Slot(
        "generation.breakthrough", "破壁分支", "generation", "_BREAKTHROUGH_SYSTEM", True,
        "N 条发散走向。前端已不再调用，端点仍在。",
    ),
    Slot(
        "compose.outline", "细纲", "compose", "_SYSTEM", True,
        "{n} 会被替换成条数。前端已不再调用，端点仍在。",
        required=("{n}",),
    ),
    Slot(
        "idiom.select", "找词挑选", "idiom", "_SELECT_SYSTEM", True,
        "从召回的成语/词条里挑合用的。",
    ),
    Slot(
        "summary.rolling", "滚动摘要", "summary", "_SUMMARY_SYSTEM", True,
        "把已写章节折叠成长期记忆。改坏了会影响所有依赖前文的生成。",
    ),
    # --- 量具类：只读 ---
    Slot(
        "refine.verify", "约束核对（量具）", "refine", "_VERIFY_SYSTEM", False,
        "只判断在不在，不评文笔。约束兑现率 59%→93% 是用这个字符串测出来的。"
        "改动会让新旧数字不可比。",
    ),
    Slot(
        "imitation.judge", "风格评分（量具）", "imitation", "_JUDGE_SYSTEM", False,
        "仿写自检环与所有 A/B 的裁判。中位数取 3 次是因为同输入会摆动。",
    ),
    Slot(
        "function_label.llm", "功能标注（量具）", "function_label", "LLM_SYSTEM", False,
        "两次未过闸门（6 类 kappa 0.089；4 类 0.800 但等于平凡基线）。"
        "留在这里是为了让那两次失败可复现。",
    ),
)

_BY_KEY = {s.key: s for s in SLOTS}


def slot(key: str) -> Slot:
    if key not in _BY_KEY:
        raise KeyError(f"unknown prompt slot: {key}")
    return _BY_KEY[key]


def default(key: str) -> str:
    """The literal currently in the source, read live (never duplicated here)."""
    s = slot(key)
    return getattr(import_module(f"app.services.{s.module}"), s.attr)


def validate(key: str, body: str) -> list[str]:
    """Reasons this body must not be saved. Empty list = fine.

    A missing placeholder does not crash — `.replace("{n}", ...)` on a body that
    lost `{n}` just leaves the model to invent how many candidates to produce.
    Silent behaviour change is exactly what a save-time check is for.
    """
    s = slot(key)
    problems: list[str] = []
    if not s.editable:
        problems.append("这条是量具，只读：改动会让已记录的评测数字不可比")
    if not body.strip():
        problems.append("不能为空")
    for token in s.required:
        if token not in body:
            problems.append(f"必须保留占位符 {token}，否则该参数会静默失效")
    if len(body) > 8000:
        problems.append("超过 8000 字符")
    return problems


async def resolve(db: AsyncSession, key: str) -> str:
    """The body to actually send: the author's override, else the code default.

    Locked slots never reach here — their callers hold no session — but the
    guard is kept so a future refactor cannot quietly open the door.
    """
    s = slot(key)
    if not s.editable:
        return default(key)
    row = (
        await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    ).scalar_one_or_none()
    return row.body if row else default(key)


async def list_all(db: AsyncSession) -> list[dict]:
    """Every slot with its default, override and drift state, for the UI."""
    rows = {
        r.key: r
        for r in (await db.execute(select(PromptTemplate))).scalars().all()
    }
    out: list[dict] = []
    for s in SLOTS:
        d = default(s.key)
        row = rows.get(s.key)
        out.append(
            {
                "key": s.key,
                "label": s.label,
                "editable": s.editable,
                "note": s.note,
                "required": list(s.required),
                "default_body": d,
                "body": row.body if row else d,
                "overridden": row is not None,
                "revision": row.revision if row else 0,
                # the author edited an older default and the code has since
                # moved on: their text is kept, but they deserve to know
                "stale_base": bool(row and row.based_on and row.based_on != d),
            }
        )
    return out


async def save(db: AsyncSession, key: str, body: str) -> PromptTemplate:
    problems = validate(key, body)
    if problems:
        raise ValueError("；".join(problems))
    row = (
        await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    ).scalar_one_or_none()
    if row is None:
        row = PromptTemplate(
            key=key, body=body, revision=1, based_on=default(key)
        )
        db.add(row)
    else:
        # Archive the current version before overwriting
        from app.models.prompt_version import PromptVersion
        db.add(PromptVersion(
            key=row.key,
            body=row.body,
            revision=row.revision,
            based_on=row.based_on,
        ))
        row.body = body
        row.revision += 1
        row.based_on = default(key)
    await db.commit()
    await db.refresh(row)
    return row


async def reset(db: AsyncSession, key: str) -> None:
    """Drop the override; the slot goes back to the code default."""
    row = (
        await db.execute(select(PromptTemplate).where(PromptTemplate.key == key))
    ).scalar_one_or_none()
    if row is not None:
        await db.delete(row)
        await db.commit()


def diff_summary(default_body: str, body: str) -> dict:
    """Cheap line-level shape of an edit, for the list view."""
    a = [l for l in default_body.splitlines() if l.strip()]
    b = [l for l in body.splitlines() if l.strip()]
    sa, sb = set(a), set(b)
    return {
        "added": len(sb - sa),
        "removed": len(sa - sb),
        "chars": len(body) - len(default_body),
    }


_SENTENCE = re.compile(r"[。；\n]")


def rule_count(body: str) -> int:
    """Roughly how many instructions a body carries — shown so the author can
    see a prompt growing without bound, which is how prompts quietly stop
    working."""
    return sum(1 for p in _SENTENCE.split(body) if len(p.strip()) > 4)
