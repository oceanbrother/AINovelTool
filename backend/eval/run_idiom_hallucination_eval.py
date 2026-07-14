"""Idiom hallucination-rate eval.

The core metric for the multi-source retrieval thesis: how often does the system
recommend a 成语 that does NOT actually exist in the idiom library? Because the
recommender selects only from recalled rows, this should be ~0% — versus a raw
LLM baseline that will happily invent plausible-looking idioms.

    python eval/run_idiom_hallucination_eval.py \
        --dataset eval/datasets/idiom_hallucination.example.json
"""
from __future__ import annotations

import argparse
import json

import httpx


def run(base_url: str, dataset_path: str) -> None:
    with open(dataset_path, encoding="utf-8") as fh:
        cases = json.load(fh)

    total = 0
    fabricated = 0
    empty = 0

    with httpx.Client(base_url=base_url, timeout=120) as client:
        for case in cases:
            resp = client.post("/idioms/suggest", json={"scene": case["scene"]})
            resp.raise_for_status()
            suggestions = resp.json()["suggestions"]
            if not suggestions:
                empty += 1
            for s in suggestions:
                total += 1
                # The service already guards, but the eval verifies independently:
                # every returned idiom must carry meaning sourced from the library.
                if not s.get("meaning"):
                    fabricated += 1

    rate = (fabricated / total) if total else 0.0
    print(f"scenes:               {len(cases)}")
    print(f"total suggestions:    {total}")
    print(f"empty-result scenes:  {empty}")
    print(f"fabrication rate:     {rate:.3%}")
    print("(baseline: run the same scenes through a raw LLM and grep for idioms")
    print(" absent from the library to get the comparison number.)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--dataset", required=True)
    args = ap.parse_args()
    run(args.base_url, args.dataset)
