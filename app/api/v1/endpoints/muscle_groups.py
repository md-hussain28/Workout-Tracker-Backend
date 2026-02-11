"""Muscle group CRUD - custom hierarchy for exercise targeting."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.muscle_group import MuscleGroup
from app.schemas.muscle_group import MuscleGroupCreate, MuscleGroupRead, MuscleGroupUpdate

router = APIRouter()


@router.get("", response_model=list[MuscleGroupRead])
async def list_muscle_groups(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 200,
):
    """List all muscle groups (for Primary/Secondary/Tertiary linking)."""
    result = await db.execute(
        select(MuscleGroup).order_by(MuscleGroup.name).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.post("", response_model=MuscleGroupRead, status_code=201)
async def create_muscle_group(
    payload: MuscleGroupCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a custom muscle group."""
    existing = await db.execute(select(MuscleGroup).where(MuscleGroup.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Muscle group with this name already exists")
    mg = MuscleGroup(**payload.model_dump())
    db.add(mg)
    await db.flush()
    await db.refresh(mg)
    return mg


@router.get("/{muscle_group_id}", response_model=MuscleGroupRead)
async def get_muscle_group(
    muscle_group_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single muscle group."""
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")
    return mg


@router.patch("/{muscle_group_id}", response_model=MuscleGroupRead)
async def update_muscle_group(
    muscle_group_id: int,
    payload: MuscleGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a muscle group."""
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(mg, k, v)
    await db.flush()
    await db.refresh(mg)
    return mg


@router.delete("/{muscle_group_id}", status_code=204)
async def delete_muscle_group(
    muscle_group_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a muscle group (exercises' FKs set to NULL)."""
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")
    await db.delete(mg)
    return None
