"""LLM provider abstraction (OpenAI-compatible chat completions).

A thin provider so the model/endpoint can be swapped via config without the
generation services knowing the difference. Exposes:

  * complete()        -> full string response
  * stream_complete() -> async generator of token deltas (for SSE)
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings
from app.core.observability import record_call

Message = dict[str, str]  # {"role": "system|user|assistant", "content": "..."}

# Reasoning models spend `max_tokens` on hidden reasoning BEFORE emitting a
# single visible character, and this provider returns `content: ""` rather than
# an error when the budget runs out. Measured on deepseek-v4-flash with a
# deliberately trivial planning prompt:
#
#     completion_tokens 2911 = reasoning_tokens 2733 + visible 356
#
# So any call that must come back with a COMPLETE JSON object — a scene plan, a
# constraint verdict, a style scorecard — needs headroom for the reasoning plus
# the object. The global default (2048) is sized for a prose continuation and
# silently produces empty structured output on every one of them.
#
STRUCTURED_MAX_TOKENS = 8192

# Prose calls need the same headroom for the same reason. Measured: the draft
# call returned "" once in three runs at the 2048 default, with no error —
# and an empty draft satisfies every must_not, so the write loop scored it as
# its best attempt. Prose is longer than a plan, so this is not smaller.
PROSE_MAX_TOKENS = 8192


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }


# Turns the model's hidden reasoning off for one call.
#
# Not a micro-optimisation. Measured on the scene-planning prompt, same input,
# max_tokens=8192:
#
#     default              visible 1131 chars, reasoning 7466 tokens
#     reasoning_effort=none visible  882 chars, reasoning 0
#
# 91% of the budget went to tokens nobody can read, and when the prompt got a
# little longer the reasoning consumed all of it and the API returned empty.
#
# Applied ONLY to generation-side structured calls (plan, candidates, outline,
# branches, idiom picks). NOT to the instruments — every number in the README
# came out of those, and changing how they think breaks comparability with no
# way to notice. NOT to prose either: reasoning there measures 21 tokens, so
# there is nothing to save, and any effect on the writing would need its own
# A/B rather than riding along with a cost fix.
NO_REASONING: dict = {"reasoning_effort": "none"}


def _payload(messages: list[Message], *, stream: bool, **overrides) -> dict:
    # Pass unknown keys straight through. They used to be dropped silently, so
    # a caller could ask for `reasoning_effort` and get the default behaviour
    # with nothing to indicate the request never left the process — the same
    # class of failure as the empty completion this module now raises on.
    extra = {
        k: v for k, v in overrides.items()
        if k not in {"model", "temperature", "max_tokens"}
    }
    return {
        "model": overrides.get("model", settings.llm_model),
        "messages": messages,
        "temperature": overrides.get("temperature", settings.llm_temperature),
        "max_tokens": overrides.get("max_tokens", settings.llm_max_tokens),
        "stream": stream,
        **extra,
    }


class EmptyCompletion(RuntimeError):
    """The provider returned a 200 with no assistant content.

    Never a useful result, and never previously visible: callers took the empty
    string and carried on. A planner produced a plan with zero constraints; a
    verifier marked every constraint failed; a draft loop scored a blank page as
    its best attempt, because a blank page violates none of the must_nots. Each
    of those looked like a working feature returning a poor result.

    Raised rather than returned so the failure has to be handled somewhere.
    """


async def complete(messages: list[Message], **overrides) -> str:
    """Non-streaming completion -> the assistant message content.

    Token usage is recorded as a side effect (observability.record_call).
    The return type is unchanged — callers don't need to be aware of telemetry.
    """
    t0 = time.monotonic()
    model = overrides.get("model", settings.llm_model)
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.llm_api_base}/chat/completions",
            json=_payload(messages, stream=False, **overrides),
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    elapsed = (time.monotonic() - t0) * 1000
    choice = data["choices"][0]
    content = choice.get("message", {}).get("content") or ""

    # Record token usage — the API returns it for free; we were discarding it
    usage = data.get("usage", {}) or {}
    details = usage.get("completion_tokens_details", {}) or {}
    record_call(
        operation=overrides.get("_op", "llm"),
        model=model,
        latency_ms=elapsed,
        prompt_tokens=usage.get("prompt_tokens", 0),
        completion_tokens=usage.get("completion_tokens", 0),
        reasoning_tokens=details.get("reasoning_tokens", 0),
    )

    if not content.strip():
        raise EmptyCompletion(
            f"empty completion (finish_reason={choice.get('finish_reason')!r}, "
            f"completion_tokens={usage.get('completion_tokens')}, "
            f"reasoning_tokens={details.get('reasoning_tokens')}, "
            f"max_tokens={_payload(messages, stream=False, **overrides)['max_tokens']}) "
            "— on a reasoning model the budget covers hidden reasoning too"
        )
    return content


async def stream_complete(
    messages: list[Message], **overrides
) -> AsyncGenerator[str, None]:
    """Streaming completion -> yields content deltas as they arrive.

    Parses the OpenAI SSE wire format (`data: {json}\n\n`, terminated by
    `data: [DONE]`).
    """
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{settings.llm_api_base}/chat/completions",
            json=_payload(messages, stream=True, **overrides),
            headers=_headers(),
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[len("data:") :].strip()
                if chunk == "[DONE]":
                    break
                try:
                    obj = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                delta = obj["choices"][0].get("delta", {}).get("content")
                if delta:
                    yield delta
