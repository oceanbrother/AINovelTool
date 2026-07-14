"""Token-cost eval: full-context dump vs RAG-selected retrieval.

Quantifies the headline efficiency claim. For each query we compare:
  * baseline: concatenate ALL setting chunks for the project (the naive
    "stuff everything into the prompt" approach)
  * rag:      only the chunks the retriever selected

Char count is used as a model-agnostic proxy for tokens (≈1 token / 1.5 Chinese
chars); pass --tiktoken to use real token counts if tiktoken is installed.

    python eval/run_token_eval.py --project-id 1 \
        --dataset eval/datasets/retrieval_recall.example.json
"""
from __future__ import annotations

import argparse
import json
import statistics

import httpx


def _count(text: str, encoder) -> int:
    if encoder is not None:
        return len(encoder.encode(text))
    return len(text)


def run(base_url: str, project_id: int, dataset_path: str, use_tiktoken: bool) -> None:
    encoder = None
    if use_tiktoken:
        import tiktoken

        encoder = tiktoken.get_encoding("cl100k_base")

    with open(dataset_path, encoding="utf-8") as fh:
        cases = json.load(fh)

    reductions: list[float] = []
    with httpx.Client(base_url=base_url, timeout=60) as client:
        # Baseline corpus = every chunk in the project (retrieve with a huge top_k
        # and no score floor via a broad query is approximated by a big top_k).
        full = client.post(
            f"/projects/{project_id}/retrieve",
            json={"query": "全部设定", "top_k": 1000},
        )
        full.raise_for_status()
        full_chars = _count(
            "\n".join(c["content"] for c in full.json()["chunks"]), encoder
        )

        for case in cases:
            resp = client.post(
                f"/projects/{project_id}/retrieve", json={"query": case["query"]}
            )
            resp.raise_for_status()
            rag_chars = _count(
                "\n".join(c["content"] for c in resp.json()["chunks"]), encoder
            )
            if full_chars:
                reductions.append(1.0 - rag_chars / full_chars)

    unit = "tokens" if encoder else "chars"
    print(f"baseline context ({unit}): {full_chars}")
    print(f"mean reduction:           {statistics.mean(reductions):.1%}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--tiktoken", action="store_true", help="use real token counts")
    args = ap.parse_args()
    run(args.base_url, args.project_id, args.dataset, args.tiktoken)
