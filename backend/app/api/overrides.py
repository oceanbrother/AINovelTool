from __future__ import annotations

import difflib

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.embedding import embed_text
from app.db import get_session
from app.models.setting_chunk import SettingChunk
from app.models.style_override import StyleOverride
from app.schemas.style import StyleOverrideCreate, StyleOverrideOut
from app.services import rhythm, scene

router = APIRouter(prefix="/projects/{project_id}/style-overrides", tags=["style"])

# An edit at least this large counts as the author reshaping the prose rather
# than fixing a typo — a single wrong character in a 300-char passage scores
# about 0.003, so 0.02 (~6 chars) sits clearly above correction noise.
MIN_EDIT_TO_INTERNALIZE = 0.02


def edit_ratio(suggested: str, accepted: str) -> float:
    """How much of the suggestion the author rewrote: 0 = verbatim, 1 = all new.

    difflib's ratio counts matching characters in both directions, so this stays
    symmetric and is not fooled by pure insertions or deletions.
    """
    if not suggested and not accepted:
        return 0.0
    return 1.0 - difflib.SequenceMatcher(None, suggested, accepted).ratio()


def texture_deltas(suggested: str, accepted: str) -> dict[str, float]:
    """accepted − suggested, per metric. The sign is the author's preference."""
    before = rhythm.texture(suggested)
    after = rhythm.texture(accepted)
    return {f"d_{key}": round(after[key] - before[key], 4) for key in before}


def should_internalize(ratio: float, passed_check: bool | None) -> bool:
    """Does this accepted text belong in the style library?

    A passage the author reworked is theirs by definition, so it goes in
    regardless of what any judge thought of the draft it came from. Text merged
    untouched only qualifies if a check vouched for it — otherwise the author
    merely tolerated it, which is not the same as endorsing the voice.
    """
    if ratio >= MIN_EDIT_TO_INTERNALIZE:
        return True
    return bool(passed_check)


@router.post("", response_model=StyleOverrideOut, status_code=201)
async def record_override(
    project_id: int,
    payload: StyleOverrideCreate,
    db: AsyncSession = Depends(get_session),
):
    """Record a (suggested, accepted) pair at merge time — the only moment the
    two versions are still separable.

    Internalisation happens here rather than in the client so the rule has one
    home: the frontend cannot drift from it, and it can be tested directly.
    """
    ratio = round(edit_ratio(payload.suggested_text, payload.accepted_text), 4)
    obj = StyleOverride(
        project_id=project_id,
        chapter_id=payload.chapter_id,
        source=payload.source,
        suggested_text=payload.suggested_text,
        accepted_text=payload.accepted_text,
        edit_ratio=ratio,
        **texture_deltas(payload.suggested_text, payload.accepted_text),
    )
    db.add(obj)

    internalized = should_internalize(ratio, payload.passed_check)
    if internalized:
        # the ACCEPTED text, not the model's — the whole point of the change.
        # generation._build_context_full prefers source_label='内化' when
        # recalling voice, so this feeds straight back into later writing.
        vec = await embed_text(payload.accepted_text)
        anchors = await scene.anchor_vectors_public()
        db.add(
            SettingChunk(
                project_id=project_id,
                source_type="style",
                source_id=None,
                source_label="内化",
                scene_tag=scene.classify_vector(vec, anchors),
                content=payload.accepted_text,
                embedding=vec,
            )
        )

    await db.commit()
    await db.refresh(obj)
    return StyleOverrideOut(
        id=obj.id,
        source=obj.source,
        edit_ratio=obj.edit_ratio,
        internalized=internalized,
        created_at=obj.created_at,
    )
