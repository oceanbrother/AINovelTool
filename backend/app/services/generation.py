"""Generation service — the two core modes.

  * 续写 (continue): solve slow writing. Assemble a *retrieval-grounded* context
    (rolling summary + recent chapters + RAG-retrieved settings) and stream the
    next passage.
  * 破壁 (breakthrough): solve writer's block. Given the current state, propose N
    divergent next-arc branches as structured JSON.

Both share the same retrieval base, so the prompt only ever contains the
settings relevant *right now* — the whole point of the RAG layer.
"""
from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import llm
from app.core.config import settings
from app.models.chapter import Chapter
from app.schemas.generation import BranchIdea
from app.services import retrieval, summary

_CONTINUE_SYSTEM = (
    "你是一位都市幻想小说的资深代笔作者。依据提供的【滚动摘要】【近期正文】和"
    "【检索到的设定】保持人物、世界观与伏笔一致，自然续写下一段正文。"
    "若提供了【文风样本】，模仿其语感、节奏与用词习惯，但不得复述或改写样本内容。"
    "只输出小说正文，不要解说、不要标题。"
)

# fact sources for the settings block; style rides a separate retrieval path
_FACT_SOURCES = ["character", "world", "foreshadowing"]

_BREAKTHROUGH_SYSTEM = (
    "你是小说剧情策划。基于当前剧情状态，提出若干条【走向不同】的后续分支"
    "（如：冲突升级 / 引入新人物 / 揭露伏笔），每条都要可展开。"
    "严格输出 JSON 数组，每项形如："
    '{"title":"分支标题","direction":"走向类型","outline":"一段剧情梗概"}。'
)


async def build_imitation_context(
    db: AsyncSession, chapter: Chapter, query: str
) -> tuple[str, list, list]:
    """Like _build_context but also returns the style chunks, so the
    imitation self-check loop can run its plagiarism/style gates on them."""
    context, chunks, styles = await _build_context_full(db, chapter, query)
    return context, chunks, styles


async def _build_context(
    db: AsyncSession, chapter: Chapter, query: str
) -> tuple[str, list]:
    context, chunks, _styles = await _build_context_full(db, chapter, query)
    return context, chunks


async def _build_context_full(
    db: AsyncSession, chapter: Chapter, query: str
) -> tuple[str, list, list]:
    roll = await summary.get_or_create_summary(db, chapter.project_id)
    recent = await summary.recent_chapters_text(
        db,
        chapter.project_id,
        settings.recent_chapters_window,
        before_order=chapter.order_index,
    )
    # two retrieval paths: facts for grounding, style samples for voice —
    # separated so prose samples never crowd out the fact slots
    chunks = await retrieval.retrieve_settings(
        db, chapter.project_id, query, source_types=_FACT_SOURCES
    )
    styles = await retrieval.retrieve_settings(
        db,
        chapter.project_id,
        query,
        source_types=["style"],
        top_k=2,
        min_score=0.0,  # any sample beats none for voice consistency
    )
    settings_block = retrieval.format_chunks_for_prompt(chunks)
    context = (
        f"【滚动摘要】\n{roll.content or '（暂无）'}\n\n"
        f"【近期正文】\n{recent or '（暂无）'}\n\n"
        f"【检索到的设定】\n{settings_block}\n\n"
        f"【当前章节正文】{chapter.title or ''}\n{chapter.content}"
    )
    if styles:
        # placed LAST — adjacent to the generation point — so the voice
        # instruction isn't diluted by the long context above it
        style_block = "\n---\n".join(s.content for s in styles)
        context += (
            f"\n\n【文风样本】\n{style_block}\n\n"
            "续写时严格模仿【文风样本】的句长与节奏（样本多短句则多用短句）、"
            "标点密度与用词习惯；只借其语感，不得复述其内容。"
        )
    return context, chunks, styles


async def continue_chapter_stream(
    db: AsyncSession, chapter: Chapter, instruction: str | None
) -> AsyncGenerator[tuple[str, object], None]:
    """Stream the continuation as typed events.

    Yields ("clues", chunks) as soon as retrieval finishes — the UI can light
    up the grounding evidence while the LLM's first token is still in flight
    (~3s on DeepSeek) — then ("token", delta) for each streamed piece.
    Query for retrieval = chapter tail + instruction.
    """
    query = (chapter.content[-500:] + " " + (instruction or "")).strip()
    context, chunks = await _build_context(db, chapter, query or chapter.title or "")
    yield "clues", chunks
    user = context
    if instruction:
        user += f"\n\n【方向指引】{instruction}"
    messages = [
        {"role": "system", "content": _CONTINUE_SYSTEM},
        {"role": "user", "content": user},
    ]
    async for delta in llm.stream_complete(messages):
        yield "token", delta


async def breakthrough(
    db: AsyncSession, chapter: Chapter, state: str, num_branches: int
) -> tuple[list[BranchIdea], list]:
    """Returns (branches, clues) — clues are the retrieved chunks the branches
    were grounded in, so the UI can surface the evidence next to the cards."""
    context, chunks = await _build_context(db, chapter, state)
    messages = [
        {"role": "system", "content": _BREAKTHROUGH_SYSTEM},
        {
            "role": "user",
            "content": (
                f"{context}\n\n【当前剧情状态】{state}\n\n"
                f"请给出 {num_branches} 条走向不同的后续分支。"
            ),
        },
    ]
    raw = await llm.complete(messages, temperature=0.9)
    return _parse_branches(raw), chunks


def _parse_branches(raw: str) -> list[BranchIdea]:
    raw = raw.strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    out: list[BranchIdea] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        out.append(
            BranchIdea(
                title=item.get("title", "未命名分支"),
                direction=item.get("direction", ""),
                outline=item.get("outline", ""),
            )
        )
    return out
