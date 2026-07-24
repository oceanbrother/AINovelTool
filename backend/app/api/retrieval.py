from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.schemas.compose import ComposeOutlineRequest, ComposeOutlineResponse
from app.schemas.retrieval import RetrieveRequest, RetrieveResponse
from app.services import compose, retrieval

router = APIRouter(prefix="/projects/{project_id}/retrieve", tags=["retrieval"])


@router.post("", response_model=RetrieveResponse)
async def retrieve(
    project_id: int,
    payload: RetrieveRequest,
    db: AsyncSession = Depends(get_session),
):
    """Inspect what the RAG layer would feed the generator for a query.

    Useful on its own and for the retrieval-recall eval harness."""
    chunks = await retrieval.retrieve_settings(
        db,
        project_id,
        payload.query,
        top_k=payload.top_k,
        source_types=payload.source_types,  # None -> "hints" channel (no style)
    )
    return RetrieveResponse(query=payload.query, chunks=chunks)


@router.post("/compose-outline", response_model=ComposeOutlineResponse)
async def compose_outline(
    project_id: int,
    payload: ComposeOutlineRequest,
    db: AsyncSession = Depends(get_session),
):
    """细纲生成 — 正文片段进，几条可编辑的执行细纲出（走向/视角/入场/设定引出/节拍）。"""
    return await compose.compose_outline(
        db,
        project_id,
        payload.fragment,
        payload.num_outlines,
        payload.top_k_settings,
    )
