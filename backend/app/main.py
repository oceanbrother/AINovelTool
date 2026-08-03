"""FastAPI entrypoint — wires routers, CORS, and observability middleware.

Run:  uvicorn app.main:app --reload
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    agent,
    chapters,
    characters,
    deconstruct,
    facts,
    foreshadowing,
    generate,
    idioms,
    literary,
    narrative,
    overrides,
    projects,
    prompts,
    reports,
    retrieval,
    style,
    world,
)
from app.core.config import settings
from app.core.observability import get_request_id, get_stats, set_request_id, setup_logging

# JSON structured logging from process start
setup_logging()

app = FastAPI(title=settings.app_name, version="1.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request-ID middleware ---
@app.middleware("http")
async def add_request_id(request: Request, call_next):
    rid = request.headers.get("X-Request-ID", uuid.uuid4().hex[:12])
    set_request_id(rid)
    t0 = time.monotonic()
    response = await call_next(request)
    elapsed_ms = (time.monotonic() - t0) * 1000
    response.headers["X-Request-ID"] = rid
    response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"
    return response

# Core MVP
app.include_router(projects.router)
app.include_router(characters.router)
app.include_router(world.router)
app.include_router(chapters.router)
app.include_router(foreshadowing.router)
app.include_router(facts.router)
app.include_router(narrative.router)
app.include_router(retrieval.router)
app.include_router(style.router)
app.include_router(overrides.router)
app.include_router(generate.router)
# v1.1 multi-source retrieval features
app.include_router(literary.router)
app.include_router(idioms.router)
app.include_router(prompts.router)
app.include_router(deconstruct.router)
app.include_router(reports.router)
app.include_router(agent.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}


@app.get("/stats", tags=["meta"])
async def stats():
    """Per-operation latency and token accounting since process start.

    Resets on restart by design — in-process accumulators, no external store.
    For a single-user tool this is the right trade-off.
    """
    return get_stats()
