# -*- coding: utf-8 -*-
"""Judge calibration — can the judge tell real prose from our imitation?

Method: for n rounds, pair a REAL style-library passage with an AI imitation
generated under the same style injection, and ask the judge (blind, both
orders) which one is the human original. High discrimination accuracy means
the judge's style verdicts carry weight; ~50% would mean either the judge is
guessing or the imitation has genuinely closed the gap — disambiguate with
the style scores from the imitate loop.

Prints verdicts and accuracy only — never the passages themselves (the real
ones are private copyrighted material).

    python eval/run_judge_calibration.py --project-id 5 --chapter-id 2 [--runs 6]
"""
from __future__ import annotations

import argparse
import asyncio
import random

import httpx

from app.core.config import settings

BASE = "http://127.0.0.1:8000"

CALIB_PROMPT = (
    "下面两段文字，一段是人类作家的原文，一段是 AI 的仿写。"
    "判断哪一段是人类作家的原文。只回答一个字：甲 或 乙。\n\n"
    "【甲】\n{a}\n\n【乙】\n{b}"
)


async def gen_imitation(client: httpx.AsyncClient, pid: int, cid: int) -> str:
    text = []
    async with client.stream(
        "POST",
        f"{BASE}/projects/{pid}/generate/continue",
        json={"chapter_id": cid, "instruction": "续写一段场景，250字左右"},
    ) as resp:
        resp.raise_for_status()
        event = None
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1].removeprefix(" ")
                if event == "token":
                    text.append(data)
                elif event == "error":
                    raise RuntimeError(data[:200])
                elif event == "done":
                    break
    return "".join(text)


async def ask(client: httpx.AsyncClient, a: str, b: str) -> str:
    resp = await client.post(
        f"{settings.llm_api_base}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_judge_model,
            "messages": [{"role": "user", "content": CALIB_PROMPT.format(a=a, b=b)}],
            "temperature": 0.0,
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--chapter-id", type=int, required=True)
    ap.add_argument("--runs", type=int, default=6)
    args = ap.parse_args()

    async with httpx.AsyncClient(timeout=600) as client:
        samples = (
            await client.get(f"{BASE}/projects/{args.project_id}/style-samples")
        ).json()
        if len(samples) < args.runs:
            raise SystemExit("not enough style samples for calibration")
        real_picks = random.sample(samples, args.runs)

        correct = 0
        for run, real in enumerate(real_picks, 1):
            fake = await gen_imitation(client, args.project_id, args.chapter_id)
            real_text = real["content"]

            # counterbalanced: both orders, count only consistent verdicts
            v1 = await ask(client, real_text, fake)   # real is 甲
            v2 = await ask(client, fake, real_text)   # real is 乙
            got1 = "甲" in v1
            got2 = "乙" in v2
            if got1 and got2:
                correct += 1
                outcome = "correct (both orders)"
            elif not got1 and not got2:
                outcome = "WRONG (both orders — imitation fooled the judge)"
            else:
                outcome = "inconsistent"
            print(f"run {run}: {outcome}")

        print(f"\ndiscrimination accuracy: {correct}/{args.runs}")


if __name__ == "__main__":
    asyncio.run(main())
