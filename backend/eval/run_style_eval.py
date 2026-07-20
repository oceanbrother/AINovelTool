# -*- coding: utf-8 -*-
"""Style imitation A/B eval — blind pairwise judging.

For each run: generate a continuation WITH style samples in the project vs
WITHOUT (samples temporarily removed), then ask an LLM judge which passage
better matches the reference style sample. Passage order is shuffled per
round so the judge can't learn a position bias.

    python eval/run_style_eval.py --project-id 5 --chapter-id 2 [--runs 4]

Costs LLM credit: 2 generations + 1 judge call per run.
"""
from __future__ import annotations

import argparse
import asyncio

import httpx

from app.core.config import settings

BASE = "http://127.0.0.1:8000"

JUDGE_PROMPT = (
    "下面是一段【参考文风样本】和两段续写【甲】【乙】。判断哪一段的文风"
    "（句长节奏、用词习惯、修辞密度、叙述口吻）更接近参考样本。\n"
    "只回答一个字：甲 或 乙。\n\n"
    "【参考文风样本】\n{sample}\n\n【甲】\n{a}\n\n【乙】\n{b}"
)


async def generate_once(client: httpx.AsyncClient, pid: int, cid: int) -> str:
    text = []
    async with client.stream(
        "POST",
        f"{BASE}/projects/{pid}/generate/continue",
        json={"chapter_id": cid, "instruction": "续写一段，150字左右"},
    ) as resp:
        resp.raise_for_status()
        event = None
        async for line in resp.aiter_lines():
            if line.startswith("event:"):
                event = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data = line.split(":", 1)[1]
                if data.startswith(" "):
                    data = data[1:]
                if event == "token":
                    text.append(data)
                elif event == "error":
                    raise RuntimeError(f"SSE error: {data[:200]}")
                elif event == "done":
                    break
    return "".join(text)


async def judge(client: httpx.AsyncClient, sample: str, a: str, b: str) -> str:
    resp = await client.post(
        f"{settings.llm_api_base}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "user", "content": JUDGE_PROMPT.format(sample=sample, a=a, b=b)}
            ],
            "temperature": 0.0,
        },
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--chapter-id", type=int, required=True)
    ap.add_argument("--runs", type=int, default=4)
    args = ap.parse_args()

    async with httpx.AsyncClient(timeout=300) as client:
        samples = (
            await client.get(f"{BASE}/projects/{args.project_id}/style-samples")
        ).json()
        if not samples:
            raise SystemExit("no style samples in project; add some first")
        reference = samples[0]["content"]

        styled_wins = 0
        for run in range(args.runs):
            # arm A: with style samples present
            with_style = await generate_once(client, args.project_id, args.chapter_id)

            # arm B: remove samples, generate, restore
            for s in samples:
                await client.delete(
                    f"{BASE}/projects/{args.project_id}/style-samples/{s['id']}"
                )
            without_style = await generate_once(client, args.project_id, args.chapter_id)
            restored = []
            for s in samples:
                r = await client.post(
                    f"{BASE}/projects/{args.project_id}/style-samples",
                    json={"content": s["content"]},
                )
                restored.append(r.json())
            samples = restored  # ids changed after restore

            # counterbalanced judging: each pair is judged in BOTH orders; a
            # win only counts if the verdict is consistent across orders,
            # which cancels any position bias in the judge
            v1 = await judge(client, reference, with_style, without_style)
            v2 = await judge(client, reference, without_style, with_style)
            pick1 = "styled" if "甲" in v1 else "raw"
            pick2 = "styled" if "乙" in v2 else "raw"
            if pick1 == pick2 == "styled":
                outcome = "WIN"
                styled_wins += 1
            elif pick1 == pick2 == "raw":
                outcome = "lose"
            else:
                outcome = "tie (order-dependent)"
            print(f"run {run + 1}: order1={v1!r} order2={v2!r} -> {outcome}")

        print(f"\nstyled arm consistent wins: {styled_wins}/{args.runs}")


if __name__ == "__main__":
    asyncio.run(main())
