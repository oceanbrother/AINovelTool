# -*- coding: utf-8 -*-
"""Observability layer: request IDs, structured logging, and token accounting.

Lightweight by design — stdlib logging with a JSON formatter, no external
dependency beyond what the project already has. The goal is to answer three
questions that are currently unanswerable:

  1. Which request produced that error?          (request ID)
  2. How much did this generation call cost?     (token accounting)
  3. What are the P50/P95 latencies per op?      (/stats endpoint)

Token accounting is kept in-process (a module-level accumulator) because the
project is single-user by design. A multi-tenant deployment would move this to
a time-series store; the interface (record_call / get_stats) would stay the same.
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from collections import defaultdict
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


# --- Request ID ---------------------------------------------------------------

_request_id: ContextVar[str] = ContextVar("request_id", default="")

def get_request_id() -> str:
    return _request_id.get()

def set_request_id(rid: str) -> None:
    _request_id.set(rid)


# --- JSON structured logging --------------------------------------------------

class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "logger": record.name,
        }
        rid = get_request_id()
        if rid:
            payload["rid"] = rid
        if record.exc_info and record.exc_info[1]:
            payload["exc"] = str(record.exc_info[1])
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)


# --- Token accounting ---------------------------------------------------------

@dataclass
class CallRecord:
    operation: str       # "plan" | "draft" | "verify" | "judge" | "idiom" | "brief"
    model: str
    latency_ms: float
    prompt_tokens: int
    completion_tokens: int
    reasoning_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


# In-process accumulators. For a single-user tool this is fine; a multi-tenant
# deployment would push these to a time-series store behind the same interface.
_records: list[CallRecord] = []

# Per-operation latency buckets for percentile computation
_latency_buckets: dict[str, list[float]] = defaultdict(list)


def record_call(
    operation: str,
    model: str,
    latency_ms: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    reasoning_tokens: int = 0,
) -> None:
    rec = CallRecord(
        operation=operation,
        model=model,
        latency_ms=latency_ms,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        reasoning_tokens=reasoning_tokens,
    )
    _records.append(rec)
    _latency_buckets[operation].append(latency_ms)


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    k = (len(sorted_vals) - 1) * p
    f = int(k)
    c = k - f
    if f + 1 < len(sorted_vals):
        return sorted_vals[f] * (1 - c) + sorted_vals[f + 1] * c
    return sorted_vals[f]


def get_stats() -> dict:
    """Aggregated stats since process start. Resets on restart by design."""
    ops: dict[str, dict] = {}
    for op, latencies in _latency_buckets.items():
        op_records = [r for r in _records if r.operation == op]
        total_prompt = sum(r.prompt_tokens for r in op_records)
        total_completion = sum(r.completion_tokens for r in op_records)
        total_reasoning = sum(r.reasoning_tokens for r in op_records)
        ops[op] = {
            "calls": len(latencies),
            "latency_p50_ms": round(_percentile(latencies, 0.50), 1),
            "latency_p95_ms": round(_percentile(latencies, 0.95), 1),
            "latency_p99_ms": round(_percentile(latencies, 0.99), 1),
            "prompt_tokens": total_prompt,
            "completion_tokens": total_completion,
            "reasoning_tokens": total_reasoning,
        }

    total_calls = len(_records)
    return {
        "total_calls": total_calls,
        "total_prompt_tokens": sum(r.prompt_tokens for r in _records),
        "total_completion_tokens": sum(r.completion_tokens for r in _records),
        "total_reasoning_tokens": sum(r.reasoning_tokens for r in _records),
        "operations": ops,
    }
