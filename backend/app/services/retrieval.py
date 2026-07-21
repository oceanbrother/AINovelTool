"""RAG retrieval layer — the project's technical core.

Naive approach: stuff every setting + character into the prompt. For a
multi-character, long-running 都市幻想 novel that burns tokens, blows context
windows, and degrades quality.

Here we embed the query and pull only the *currently relevant* setting chunks
via pgvector cosine similarity, optionally filtered by source_type. Smaller
prompt -> faster, cheaper, more focused — one mechanism that addresses both the
"stuck" and the "quality" pain at once.

The same primitive (`_vector_search`) backs the literary and idiom features in
services/literary.py and services/idiom.py — one embedding + pgvector base, many
retrieval sources (multi-source hybrid retrieval).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.embedding import embed_text
from app.models.setting_chunk import SettingChunk
from app.schemas.retrieval import RetrievedChunk

# --- 检索通道矩阵 ---------------------------------------------------------------
# Every feature reads through a named channel; the channel decides which sources
# may answer. ONE table governs the whole system — add a source here and every
# consumer updates together; a feature that needs different rules gets its own
# row instead of an ad-hoc filter (that ad-hoc path is exactly how style samples
# once leaked into the clue pane).
#
#   hints    线索/剧情参谋：找灵感 —— 只看事实设定，文风与金句不得介入
#   generate 续写/破壁/仿写 的事实通道
#   style    生成链路的文风参照通道（独立检索，紧邻生成点注入）
#   debug    调试视图：不过滤
CHANNELS: dict[str, list[str] | None] = {
    "hints": ["character", "world", "foreshadowing"],
    "generate": ["character", "world", "foreshadowing"],
    "style": ["style"],
    "debug": None,  # all sources
}


async def retrieve_settings(
    db: AsyncSession,
    project_id: int,
    query: str,
    *,
    channel: str = "hints",
    top_k: int | None = None,
    source_types: list[str] | None = None,
    source_labels: list[str] | None = None,
    min_score: float | None = None,
) -> list[RetrievedChunk]:
    """Return the top setting chunks most relevant to `query` for a project.

    Score is cosine similarity in [0, 1] (1 - cosine_distance). Results below
    `min_score` are dropped so an irrelevant query returns nothing rather than
    noise.
    """
    top_k = top_k or settings.retrieval_top_k
    min_score = settings.retrieval_min_score if min_score is None else min_score
    if source_types is None:  # explicit source_types (debug/tests) overrides
        source_types = CHANNELS[channel]

    query_vec = await embed_text(query)
    # pgvector `<=>` is cosine distance; similarity = 1 - distance.
    distance = SettingChunk.embedding.cosine_distance(query_vec)
    stmt = (
        select(SettingChunk, distance.label("distance"))
        .where(SettingChunk.project_id == project_id)
        .where(SettingChunk.embedding.isnot(None))
    )
    if source_types:
        stmt = stmt.where(SettingChunk.source_type.in_(source_types))
    if source_labels:
        stmt = stmt.where(SettingChunk.source_label.in_(source_labels))
    stmt = stmt.order_by(distance).limit(top_k)

    rows = (await db.execute(stmt)).all()
    out: list[RetrievedChunk] = []
    for chunk, dist in rows:
        score = 1.0 - float(dist)
        if score < min_score:
            continue
        out.append(
            RetrievedChunk(
                id=chunk.id,
                source_type=chunk.source_type,
                source_id=chunk.source_id,
                content=chunk.content,
                score=round(score, 4),
            )
        )
    return out


def format_chunks_for_prompt(chunks: list[RetrievedChunk]) -> str:
    """Render retrieved chunks into a compact, labeled context block."""
    if not chunks:
        return "（无相关设定被检索到）"
    label = {
        "character": "角色",
        "world": "世界观",
        "foreshadowing": "伏笔",
        "style": "文风",
    }
    lines = []
    for c in chunks:
        tag = label.get(c.source_type, c.source_type)
        lines.append(f"[{tag}] {c.content}")
    return "\n".join(lines)
