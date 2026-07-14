"""LLM provider abstraction (OpenAI-compatible chat completions).

A thin provider so the model/endpoint can be swapped via config without the
generation services knowing the difference. Exposes:

  * complete()        -> full string response
  * stream_complete() -> async generator of token deltas (for SSE)
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator

import httpx

from app.core.config import settings

Message = dict[str, str]  # {"role": "system|user|assistant", "content": "..."}


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.llm_api_key}",
        "Content-Type": "application/json",
    }


def _payload(messages: list[Message], *, stream: bool, **overrides) -> dict:
    return {
        "model": overrides.get("model", settings.llm_model),
        "messages": messages,
        "temperature": overrides.get("temperature", settings.llm_temperature),
        "max_tokens": overrides.get("max_tokens", settings.llm_max_tokens),
        "stream": stream,
    }


async def complete(messages: list[Message], **overrides) -> str:
    """Non-streaming completion -> the assistant message content."""
    async with httpx.AsyncClient(timeout=120) as client:
        resp = await client.post(
            f"{settings.llm_api_base}/chat/completions",
            json=_payload(messages, stream=False, **overrides),
            headers=_headers(),
        )
        resp.raise_for_status()
        data = resp.json()
    return data["choices"][0]["message"]["content"]


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
