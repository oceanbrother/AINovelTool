# -*- coding: utf-8 -*-
"""Deterministic checks for the editable-prompt layer. No LLM, no credit.

Three properties worth failing a build over:

1. **Every declared slot resolves.** `SLOTS` names a module attribute by string;
   a rename in a service would otherwise break generation at request time
   instead of here.
2. **The measurement prompts cannot be overridden.** Not by policy — by
   signature. `verify_draft` / `judge_draft` take no session, so no code path
   can read a row for them. If a refactor ever threads a session through one of
   them, this fails, because at that moment every recorded number in the README
   silently becomes incomparable with the next run.
3. **Edits that would change behaviour without erroring are rejected.**
   Dropping `{n}` does not raise at generation time; it just leaves the model to
   decide how many candidates to write.

    python eval/check_prompts.py            # 只跑不碰库的检查
    python eval/check_prompts.py --live     # 额外做一次 改→生效→恢复 往返
"""
from __future__ import annotations

import argparse
import asyncio
import inspect

from app.services import function_label, imitation, prompts, refine

INSTRUMENTS = (refine.verify_draft, imitation.judge_draft, imitation.judge_draft_stable)


def check_slots_resolve() -> list[str]:
    bad = []
    for s in prompts.SLOTS:
        try:
            body = prompts.default(s.key)
        except (AttributeError, ModuleNotFoundError) as exc:
            bad.append(f"{s.key}: 取不到默认值 ({exc})")
            continue
        if not body.strip():
            bad.append(f"{s.key}: 默认值为空")
        for token in s.required:
            if token not in body:
                bad.append(f"{s.key}: 默认值里缺占位符 {token}")
    return bad


def check_instruments_have_no_session() -> list[str]:
    bad = []
    for fn in INSTRUMENTS:
        params = list(inspect.signature(fn).parameters)
        if any(p in ("db", "session") for p in params):
            bad.append(
                f"{fn.__name__} 现在接收 session —— 量具可被覆盖，"
                f"已记录的评测数字将不可比"
            )
    # the labellers live on a module-level literal too
    if not isinstance(getattr(function_label, "LLM_SYSTEM", None), str):
        bad.append("function_label.LLM_SYSTEM 不再是模块级字符串")
    return bad


def check_validation_rejects() -> list[str]:
    """Each case must be refused; a silent accept is the failure."""
    cases = [
        ("refine.candidates", prompts.default("refine.candidates").replace("{n}", "四"),
         "删掉 {n} 占位符"),
        ("refine.verify", "改写量具", "编辑只读量具"),
        ("refine.plan", "   ", "留空"),
        ("refine.plan", "x" * 9000, "超长"),
    ]
    bad = []
    for key, body, why in cases:
        if not prompts.validate(key, body):
            bad.append(f"validate 放过了「{why}」")
    # and a legitimate edit must pass
    ok_body = prompts.default("refine.plan") + "\n【作者附加】一条新规则。"
    if prompts.validate("refine.plan", ok_body):
        bad.append("validate 误拒了一次合法编辑")
    return bad


async def check_live_roundtrip() -> list[str]:
    from app.db import AsyncSessionLocal

    key = "refine.plan"
    bad = []
    async with AsyncSessionLocal() as db:
        d = prompts.default(key)
        pre_overridden = any(
            i["key"] == key and i["overridden"] for i in await prompts.list_all(db)
        )
        if pre_overridden:
            return ["该槽位已有作者覆盖，跳过往返测试以免覆写作者的编辑"]
        if await prompts.resolve(db, key) != d:
            bad.append("无覆盖时 resolve 没有返回默认值")
        new = d + "\n【往返测试】"
        await prompts.save(db, key, new)
        if await prompts.resolve(db, key) != new:
            bad.append("保存后 resolve 没有返回覆盖值")
        await prompts.reset(db, key)
        if await prompts.resolve(db, key) != d:
            bad.append("reset 后 resolve 没有回到默认值")
    return bad


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="额外做一次数据库往返")
    args = ap.parse_args()

    checks = [
        ("槽位全部可解析", check_slots_resolve()),
        ("量具取不到 session", check_instruments_have_no_session()),
        ("校验拒绝静默改行为的编辑", check_validation_rejects()),
    ]
    if args.live:
        checks.append(("改→生效→恢复 往返", asyncio.run(check_live_roundtrip())))

    n_ed = sum(s.editable for s in prompts.SLOTS)
    print(f"=== 提示词层检查（{len(prompts.SLOTS)} 槽位：可编辑 {n_ed} / 量具 "
          f"{len(prompts.SLOTS) - n_ed}）===\n")
    failed = 0
    for name, problems in checks:
        if problems:
            failed += 1
            print(f"✗ {name}")
            for p in problems:
                print(f"    · {p}")
        else:
            print(f"✓ {name}")
    print()
    if failed:
        raise SystemExit(f"{failed} 项未通过")
    print("全部通过")


if __name__ == "__main__":
    main()
