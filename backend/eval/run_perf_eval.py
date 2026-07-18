# -*- coding: utf-8 -*-
"""Performance eval — latency & throughput numbers for the README.

Cases
  P1  retrieval latency        /retrieve P50/P95 over varied queries
  P2  time-to-first-token      SSE continue: request -> first token event
  P3  streaming throughput     SSE continue: events/sec over the stream
  P4  concurrent retrieval     P95 degradation at 1 / 5 / 10 in-flight
  P5  write+index latency      character create incl. sync embedding

Usage
  python eval/run_perf_eval.py --project-id 5 [--skip-llm]

P1/P4/P5 are local-only (embedding + pgvector). P2/P3 call the configured
LLM provider and cost a (tiny) amount of credit; skip with --skip-llm.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time

import httpx

BASE = "http://127.0.0.1:8000"

RETRIEVAL_QUERIES = [
    "主角在雨夜使用超能力",
    "去黑市买情报",
    "在普通人面前暴露异能的后果",
    "深夜的废弃码头",
    "两个角色在酒吧密谈",
    "守夜人组织的规矩",
    "火焰系能力者出手",
    "大学讲师的双重身份",
    "违禁品交易现场",
    "追踪神秘能量波动",
    "新月之夜的集会",
    "情报贩子的消息网",
    "言灵能力的等级",
    "隐藏身份被识破的危机",
    "城市上空的异象",
    "旧仓库里的线索",
    "被雨水冲刷的痕迹",
    "凡人卷入超自然事件",
    "裁决违规者的场面",
    "黎明前的对峙",
]


def pct(values: list[float], p: float) -> float:
    values = sorted(values)
    idx = min(int(len(values) * p / 100), len(values) - 1)
    return values[idx]


def report(name: str, ms: list[float]) -> dict:
    row = {
        "case": name,
        "n": len(ms),
        "mean_ms": round(statistics.mean(ms), 1),
        "p50_ms": round(pct(ms, 50), 1),
        "p95_ms": round(pct(ms, 95), 1),
        "max_ms": round(max(ms), 1),
    }
    print(
        f"  {name:<28} n={row['n']:<4} mean={row['mean_ms']:>8}ms"
        f"  p50={row['p50_ms']:>8}ms  p95={row['p95_ms']:>8}ms"
    )
    return row


async def timed_retrieve(client: httpx.AsyncClient, pid: int, query: str) -> float:
    t0 = time.perf_counter()
    r = await client.post(
        f"{BASE}/projects/{pid}/retrieve", json={"query": query, "top_k": 5}
    )
    r.raise_for_status()
    return (time.perf_counter() - t0) * 1000


async def p1_retrieval(client: httpx.AsyncClient, pid: int, rounds: int = 3) -> list[dict]:
    # warm-up: first call may pay one-off model/list initialisation costs
    await timed_retrieve(client, pid, "预热")
    cold = [await timed_retrieve(client, pid, q) for q in RETRIEVAL_QUERIES]
    warm = [
        await timed_retrieve(client, pid, q)
        for _ in range(rounds - 1)
        for q in RETRIEVAL_QUERIES
    ]
    # cold = unseen queries (embedding computed); warm = repeats (cache-eligible)
    return [
        report("P1 retrieval (cold)", cold),
        report("P1 retrieval (warm)", warm),
    ]


async def p2_p3_sse(client: httpx.AsyncClient, pid: int, chapter_id: int, runs: int = 5) -> list[dict]:
    ttft_ms: list[float] = []
    rates: list[float] = []
    for i in range(runs):
        t0 = time.perf_counter()
        first: float | None = None
        events = 0
        async with client.stream(
            "POST",
            f"{BASE}/projects/{pid}/generate/continue",
            json={"chapter_id": chapter_id, "instruction": "续写一小段，100字以内"},
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if line.startswith("event: token"):
                    events += 1
                    if first is None:
                        first = (time.perf_counter() - t0) * 1000
                elif line.startswith("event: error"):
                    raise RuntimeError("SSE error event during perf run")
        total_s = time.perf_counter() - t0
        if first is None:
            raise RuntimeError("stream produced no tokens")
        ttft_ms.append(first)
        stream_s = total_s - first / 1000
        if stream_s > 0:
            rates.append(events / stream_s)
    rows = [report("P2 SSE time-to-first-token", ttft_ms)]
    rate_row = {
        "case": "P3 SSE throughput",
        "n": len(rates),
        "mean_events_per_s": round(statistics.mean(rates), 1),
        "min_events_per_s": round(min(rates), 1),
    }
    print(
        f"  {'P3 SSE throughput':<28} n={rate_row['n']:<4} "
        f"mean={rate_row['mean_events_per_s']} events/s  min={rate_row['min_events_per_s']} events/s"
    )
    rows.append(rate_row)
    return rows


async def p4_concurrency(client: httpx.AsyncClient, pid: int) -> list[dict]:
    rows = []
    for level in (1, 5, 10):
        ms: list[float] = []
        # 3 waves per level so each wave is exactly `level` in-flight requests.
        # Queries carry a unique suffix so every request is a cache MISS —
        # this measures true concurrent encoding, not the query cache.
        for wave in range(3):
            batch = [
                f"{RETRIEVAL_QUERIES[(wave * level + i) % len(RETRIEVAL_QUERIES)]}"
                f"（并发样本{level}-{wave}-{i}）"
                for i in range(level)
            ]
            results = await asyncio.gather(
                *(timed_retrieve(client, pid, q) for q in batch)
            )
            ms.extend(results)
        rows.append(report(f"P4 retrieval x{level} in-flight", ms))
    return rows


async def p5_write_index(client: httpx.AsyncClient, pid: int, runs: int = 10) -> dict:
    ms: list[float] = []
    created: list[int] = []
    for i in range(runs):
        t0 = time.perf_counter()
        r = await client.post(
            f"{BASE}/projects/{pid}/characters",
            json={
                "name": f"perf-临时角色-{i}",
                "persona": {"性格": "谨慎", "能力": "潜行"},
                "summary": "性能测试用临时角色，测完即删。",
            },
        )
        r.raise_for_status()
        ms.append((time.perf_counter() - t0) * 1000)
        created.append(r.json()["id"])
    row = report("P5 create+embed character", ms)
    for cid in created:  # clean up
        await client.delete(f"{BASE}/projects/{pid}/characters/{cid}")
    return row


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-id", type=int, required=True)
    ap.add_argument("--chapter-id", type=int, default=None,
                    help="chapter for SSE runs; defaults to the project's first")
    ap.add_argument("--skip-llm", action="store_true",
                    help="skip P2/P3 (no LLM credit spent)")
    ap.add_argument("--json-out", default=None, help="also dump rows as JSON")
    args = ap.parse_args()

    rows: list[dict] = []
    async with httpx.AsyncClient(timeout=300) as client:
        health = await client.get(f"{BASE}/health")
        health.raise_for_status()

        chapter_id = args.chapter_id
        if chapter_id is None and not args.skip_llm:
            chapters = (
                await client.get(f"{BASE}/projects/{args.project_id}/chapters")
            ).json()
            if not chapters:
                raise SystemExit("project has no chapters; pass --chapter-id")
            chapter_id = chapters[0]["id"]

        print("perf eval —", time.strftime("%Y-%m-%d %H:%M:%S"))
        rows.extend(await p1_retrieval(client, args.project_id))
        rows.extend(await p4_concurrency(client, args.project_id))
        rows.append(await p5_write_index(client, args.project_id))
        if not args.skip_llm:
            rows.extend(await p2_p3_sse(client, args.project_id, chapter_id))

    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        print(f"\nrows written to {args.json_out}")


if __name__ == "__main__":
    asyncio.run(main())
