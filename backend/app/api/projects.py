from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.project import Project
from app.schemas.project import ProjectCreate, ProjectOut, ProjectUpdate

router = APIRouter(prefix="/projects", tags=["projects"])


async def _get_or_404(db: AsyncSession, project_id: int) -> Project:
    obj = await db.get(Project, project_id)
    if obj is None:
        raise HTTPException(404, "project not found")
    return obj


@router.post("", response_model=ProjectOut, status_code=201)
async def create_project(
    payload: ProjectCreate, db: AsyncSession = Depends(get_session)
):
    obj = Project(**payload.model_dump())
    db.add(obj)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(Project).order_by(Project.id))).scalars().all()
    return rows


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: int, db: AsyncSession = Depends(get_session)):
    return await _get_or_404(db, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
async def update_project(
    project_id: int,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_session),
):
    obj = await _get_or_404(db, project_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, field, value)
    await db.commit()
    await db.refresh(obj)
    return obj


@router.delete("/{project_id}", status_code=204)
async def delete_project(project_id: int, db: AsyncSession = Depends(get_session)):
    obj = await _get_or_404(db, project_id)
    await db.delete(obj)
    await db.commit()
