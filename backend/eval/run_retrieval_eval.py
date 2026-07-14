"""Retrieval recall eval.

For each labeled case, ask the running API to retrieve setting chunks for a
query, then check whether the expected substrings show up in the returned
chunks. Reports recall@k, average chunks returned, and average latency.

    python eval/run_retrieval_eval.py --project-id 1 \
        --dataset eval/datasets/retrieval_recall.example.json
"""
from __future__ import annotations

import argparse
import json
import statistics
import time

import httpx


def run(base_url: str, project_id: int, dataset_path: str) -> None:
    with open(dataset_path, encoding="utf-8") as fh:
        cases = json.load(fh)

    recalls: list[float] = []
    chunk_counts: list[int] = []
    latencies: list[float] = []

    with httpx.Client(base_url=base_url, timeout=60) as client:
        for case in cases:
            body = {"query": case["query"]}
            if case.get("source_types"):
                body["source_types"] = case["source_types"]

            t0 = time.perf_counter()
            resp = client.post(f"/projects/{project_id}/retrieve", json=body)
            latencies.append(time.perf_counter() - t0)
            resp.raise_for_status()
            chunks = resp.json()["chunks"]
            chunk_counts.append(len(chunks))

            blob = "\n".join(c["content"] for c in chunks)
            expected = case.get("expected_substrings", [])
            hit = sum(1 for sub in expected if sub in blob)
            recalls.append(hit / len(expected) if expected else 0.0)

    print(f"cases:            {len(cases)}")
    print(f"recall@k (mean):  {statistics.mean(recalls):.3f}")
    print(f"avg chunks:       {statistics.mean(chunk_counts):.2f}")
    print(f"avg latency (s):  {statistics.mean(latencies):.3f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--dataset", required=True)
    args = ap.parse_args()
    run(args.base_url, args.project_id, args.dataset)
