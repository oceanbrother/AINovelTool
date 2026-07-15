# -*- coding: utf-8 -*-
"""Idiom hallucination A/B eval — raw LLM baseline vs retrieval-grounded API.

The headline metric for the retrieval-grounded-generation thesis. Both arms
answer the same scenes; every suggested idiom is checked against an
authoritative dictionary (the full chinese-xinhua vocabulary, ~31k entries).

  baseline arm: ask the configured LLM directly for idioms (no retrieval)
  grounded arm: POST /idioms/suggest (recall from pgvector, LLM selects
                only from the recalled candidates)

Fairness note: the truth set is the FULL dictionary, not our imported subset,
so the baseline is not penalised for real idioms we happened not to import.

    python eval/run_idiom_hallucination_eval.py \
        --dataset eval/datasets/idiom_scenes.v1.json \
        --truth path/to/idiom.json [--skip-baseline]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re

import httpx

from app.core.config import settings

BASELINE_PROMPT = (
    "你是写作助手。作者描述了一个画面，请推荐 5 个贴切的成语帮助他形容。\n"
    "画面：{scene}\n\n"
    '只输出 JSON 数组，格式：[{{"text": "成语", "meaning": "释义"}}]'
)


def load_truth(path: str) -> set[str]:
    with open(path, encoding="utf-8") as fh:
        return {d["word"] for d in json.load(fh)}


async def load_library_terms() -> set[str]:
    """Curated library entries are human-verified, so they belong in the truth
    set even when the external dictionary lacks them (e.g. 灯火阑珊)."""
    from sqlalchemy import select

    from app.db import AsyncSessionLocal
    from app.models.idiom import Idiom

    async with AsyncSessionLocal() as db:
        return set((await db.execute(select(Idiom.text))).scalars().all())


def extract_json_array(text: str) -> list[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if not match:
        return []
    try:
        parsed = json.loads(match.group())
        return [d for d in parsed if isinstance(d, dict) and d.get("text")]
    except json.JSONDecodeError:
        return []


async def with_retry(fn, attempts: int = 3, delay: float = 3.0):
    """LLM/network calls flake; one transient failure shouldn't kill the run."""
    for i in range(attempts):
        try:
            return await fn()
        except (httpx.HTTPError, httpx.HTTPStatusError):
            if i == attempts - 1:
                raise
            await asyncio.sleep(delay * (i + 1))


async def baseline_suggest(client: httpx.AsyncClient, scene: str) -> list[str]:
    resp = await client.post(
        f"{settings.llm_api_base}/chat/completions",
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        json={
            "model": settings.llm_model,
            "messages": [
                {"role": "user", "content": BASELINE_PROMPT.format(scene=scene)}
            ],
            "temperature": 0.8,
        },
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"]["content"]
    return [d["text"].strip() for d in extract_json_array(content)]


async def grounded_suggest(client: httpx.AsyncClient, base_url: str, scene: str) -> list[str]:
    resp = await client.post(f"{base_url}/idioms/suggest", json={"scene": scene})
    resp.raise_for_status()
    return [s["text"].strip() for s in resp.json()["suggestions"]]


def score(name: str, per_scene: list[list[str]], truth: set[str]) -> None:
    suggestions = [t for scene in per_scene for t in scene]
    fabricated = sorted({t for t in suggestions if t not in truth})
    rate = len([t for t in suggestions if t not in truth]) / len(suggestions) if suggestions else 0.0
    print(f"\n[{name}]")
    print(f"  total suggestions:  {len(suggestions)}")
    print(f"  fabricated:         {len([t for t in suggestions if t not in truth])}")
    print(f"  fabrication rate:   {rate:.1%}")
    if fabricated:
        print(f"  fabricated terms:   {'、'.join(fabricated[:20])}")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--truth", required=True, help="chinese-xinhua idiom.json")
    ap.add_argument("--skip-baseline", action="store_true")
    args = ap.parse_args()

    with open(args.dataset, encoding="utf-8") as fh:
        scenes = [c["scene"] for c in json.load(fh)]
    truth = load_truth(args.truth) | await load_library_terms()
    print(f"scenes: {len(scenes)}   truth-set size: {len(truth)} (dictionary ∪ curated library)")

    async with httpx.AsyncClient(timeout=300) as client:
        grounded = []
        for i, scene in enumerate(scenes, 1):
            grounded.append(
                await with_retry(lambda s=scene: grounded_suggest(client, args.base_url, s))
            )
            print(f"  grounded {i}/{len(scenes)}", flush=True)
        score("grounded /idioms/suggest", grounded, truth)

        if not args.skip_baseline:
            baseline = []
            for i, scene in enumerate(scenes, 1):
                baseline.append(
                    await with_retry(lambda s=scene: baseline_suggest(client, s))
                )
                print(f"  baseline {i}/{len(scenes)}", flush=True)
            score("raw LLM baseline", baseline, truth)


if __name__ == "__main__":
    asyncio.run(main())
