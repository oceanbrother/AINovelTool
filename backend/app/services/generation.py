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
    "只输出小说正文，不要解说、不要标题。"
)

_BREAKTHROUGH_SYSTEM = (
    "你是小说剧情策划。基于当前剧情状态，提出若干条【走向不同】的后续分支"
    "（如：冲突升级 / 引入新人物 / 揭露伏笔），每条都要可展开。"
    "严格输出 JSON 数组，每项形如："
    '{"title":"分支标题","direction":"走向类型","outline":"一段剧情梗概"}。'
)


async def _build_context(
    db: AsyncSession, chapter: Chapter, query: str
) -> tuple[str, list]:
    roll = await summary.get_or_create_summary(db, chapter.project_id)
    recent = await summary.recent_chapters_text(
        db,
        chapter.project_id,
        settings.recent_chapters_window,
        before_order=chapter.order_index,
    )
    chunks = await retrieval.retrieve_settings(db, chapter.project_id, query)
    settings_block = retrieval.format_chunks_for_prompt(chunks)
    context = (
        f"【滚动摘要】\n{roll.content or '（暂无）'}\n\n"
        f"【近期正文】\n{recent or '（暂无）'}\n\n"
        f"【检索到的设定】\n{settings_block}\n\n"
        f"【当前章节正文】{chapter.title or ''}\n{chapter.content}"
    )
    return context, chunks


async def continue_chapter_stream(
    db: AsyncSession, chapter: Chapter, instruction: str | None
) -> AsyncGenerator[str, None]:
    """Stream the continuation. Query for retrieval = chapter tail + instruction."""
    query = (chapter.content[-500:] + " " + (instruction or "")).strip()
    context, _chunks = await _build_context(db, chapter, query or chapter.title or "")
    user = context
    if instruction:
        user += f"\n\n【方向指引】{instruction}"
    messages = [
        {"role": "system", "content": _CONTINUE_SYSTEM},
        {"role": "user", "content": user},
    ]
    async for delta in llm.stream_complete(messages):
        yield delta


async def breakthrough(
    db: AsyncSession, chapter: Chapter, state: str, num_branches: int
) -> list[BranchIdea]:
    context, _chunks = await _build_context(db, chapter, state)
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
    return _parse_branches(raw)


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
