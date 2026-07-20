from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.retrieval import RetrievedChunk


class ContinueRequest(BaseModel):
    """续写模式 — solve the 'stuck' / slow-writing pain.

    Given the current chapter, retrieve relevant settings and continue writing.
    """

    chapter_id: int
    instruction: str | None = Field(
        default=None, description="可选的方向指引，如'让主角识破伪装'"
    )
    stream: bool = True


class BreakthroughRequest(BaseModel):
    """破壁模式 — solve writer's block.

    Given the current plot state, propose N divergent next-arc branches.
    """

    chapter_id: int
    state: str = Field(description="当前剧情状态描述")
    num_branches: int = 3
    stream: bool = False


class BranchIdea(BaseModel):
    title: str
    direction: str  # 冲突升级 / 引入新人物 / 揭露伏笔 ...
    outline: str


class BreakthroughResponse(BaseModel):
    branches: list[BranchIdea]
    # the retrieval evidence the branches were grounded in — the UI can show
    # these alongside the cards (同「续写」的 clues 事件)
    clues: list[RetrievedChunk] = []
