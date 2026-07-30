"""FastAPI entrypoint — wires routers and CORS.

Run:  uvicorn app.main:app --reload
Docs: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    chapters,
    characters,
    facts,
    foreshadowing,
    generate,
    idioms,
    literary,
    narrative,
    overrides,
    projects,
    prompts,
    retrieval,
    style,
    world,
)
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="1.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

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


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name}
