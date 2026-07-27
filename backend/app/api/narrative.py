from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.narrative import NarrativePlan, NarrativeUnit
from app.schemas.narrative import (
    LOCKABLE_FIELDS,
    NarrativePlanOut,
    NarrativePlanUpdate,
    NarrativeUnitOut,
)

router = APIRouter(prefix="/projects/{project_id}/narrative", tags=["narrative"])


async def _plan_or_404(db: AsyncSession, project_id: int, plan_id: int) -> NarrativePlan:
    obj = await db.get(NarrativePlan, plan_id)
    if obj is None or obj.project_id != project_id:
        raise HTTPException(404, "narrative plan not found")
    return obj


@router.get("/plans", response_model=list[NarrativePlanOut])
async def list_plans(
    project_id: int,
    chapter_id: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    stmt = select(NarrativePlan).where(NarrativePlan.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(NarrativePlan.chapter_id == chapter_id)
    return (await db.execute(stmt.order_by(NarrativePlan.id.desc()))).scalars().all()


@router.patch("/plans/{plan_id}", response_model=NarrativePlanOut)
async def update_plan(
    project_id: int,
    plan_id: int,
    payload: NarrativePlanUpdate,
    db: AsyncSession = Depends(get_session),
):
    """Save the author's edits, including which fields they froze.

    Unknown lock names are rejected rather than stored: a typo would silently
    protect nothing, and the author would only find out when a regeneration
    quietly overwrote the decision they thought was safe.
    """
    obj = await _plan_or_404(db, project_id, plan_id)
    data = payload.model_dump(exclude_unset=True)

    if (locks := data.get("locked_fields")) is not None:
        unknown = [f for f in locks if f not in LOCKABLE_FIELDS]
        if unknown:
            raise HTTPException(
                422,
                f"不可锁定的字段 {unknown}；可锁定：{'/'.join(LOCKABLE_FIELDS)}",
            )
    if (plan := data.get("plan")) is not None:
        obj.plan = plan  # already a dict after model_dump
    for field in ("locked_fields", "review_status", "generation_status", "unit_id"):
        if field in data:
            setattr(obj, field, data[field])

    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/plans/{plan_id}", status_code=204)
async def delete_plan(
    project_id: int, plan_id: int, db: AsyncSession = Depends(get_session)
):
    obj = await _plan_or_404(db, project_id, plan_id)
    await db.delete(obj)
    await db.commit()


@router.get("/units", response_model=list[NarrativeUnitOut])
async def list_units(
    project_id: int,
    chapter_id: int | None = None,
    db: AsyncSession = Depends(get_session),
):
    stmt = select(NarrativeUnit).where(NarrativeUnit.project_id == project_id)
    if chapter_id is not None:
        stmt = stmt.where(NarrativeUnit.chapter_id == chapter_id)
    return (
        await db.execute(
            stmt.order_by(NarrativeUnit.chapter_id, NarrativeUnit.order_index)
        )
    ).scalars().all()
