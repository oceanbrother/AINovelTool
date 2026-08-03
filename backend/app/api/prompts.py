from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.prompt_version import PromptVersion
from app.services import prompts

router = APIRouter(prefix="/prompts", tags=["prompts"])


class PromptBody(BaseModel):
    body: str


@router.get("")
async def list_prompts(db: AsyncSession = Depends(get_session)):
    """Every prompt slot: default, current body, whether it is overridden.

    Not project-scoped on purpose — these are the tool's instructions, not one
    book's content. An author who fixes a bad plan prompt wants that fix on
    every project.
    """
    items = await prompts.list_all(db)
    for it in items:
        it["diff"] = prompts.diff_summary(it["default_body"], it["body"])
        it["rules"] = prompts.rule_count(it["body"])
        it["default_rules"] = prompts.rule_count(it["default_body"])
    return items


@router.get("/{key}/versions")
async def list_versions(key: str, db: AsyncSession = Depends(get_session)):
    """Version history for a prompt slot. Current version first, then archived."""
    try:
        prompts.slot(key)
    except KeyError:
        raise HTTPException(404, "unknown prompt slot")
    archived = (
        await db.execute(
            select(PromptVersion)
            .where(PromptVersion.key == key)
            .order_by(PromptVersion.revision.desc())
        )
    ).scalars().all()
    return [
        {
            "revision": v.revision,
            "body": v.body,
            "based_on": v.based_on,
            "created_at": v.created_at.isoformat(),
        }
        for v in archived
    ]


@router.patch("/{key}")
async def update_prompt(
    key: str, payload: PromptBody, db: AsyncSession = Depends(get_session)
):
    """Save an override. Rejects edits that would silently change behaviour."""
    try:
        prompts.slot(key)
    except KeyError:
        raise HTTPException(404, "unknown prompt slot")
    try:
        row = await prompts.save(db, key, payload.body)
    except ValueError as exc:  # validation, not a server fault
        raise HTTPException(422, str(exc))
    return {"key": row.key, "revision": row.revision}


@router.post("/{key}/reset")
async def reset_prompt(key: str, db: AsyncSession = Depends(get_session)):
    """Drop the override and go back to the code default."""
    try:
        prompts.slot(key)
    except KeyError:
        raise HTTPException(404, "unknown prompt slot")
    await prompts.reset(db, key)
    return {"key": key, "body": prompts.default(key)}
