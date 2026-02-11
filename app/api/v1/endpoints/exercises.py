"""Exercise CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.exercise import Exercise
from app.schemas.exercise import ExerciseCreate, ExerciseRead, ExerciseUpdate

router = APIRouter()


def _exercise_query():
    return select(Exercise).options(
        selectinload(Exercise.primary_muscle_group),
        selectinload(Exercise.secondary_muscle_group),
        selectinload(Exercise.tertiary_muscle_group),
    )


@router.get("", response_model=list[ExerciseRead])
async def list_exercises(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
):
    """List exercises with optional pagination (includes muscle groups)."""
    result = await db.execute(
        _exercise_query().order_by(Exercise.name).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.post("", response_model=ExerciseRead, status_code=201)
async def create_exercise(
    payload: ExerciseCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new exercise (with optional muscle hierarchy and measurement mode)."""
    exercise = Exercise(**payload.model_dump())
    db.add(exercise)
    await db.flush()
    result = await db.execute(
        _exercise_query().where(Exercise.id == exercise.id)
    )
    return result.scalar_one()


@router.get("/{exercise_id}", response_model=ExerciseRead)
async def get_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a single exercise by id (includes muscle groups)."""
    result = await db.execute(
        _exercise_query().where(Exercise.id == exercise_id)
    )
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise


@router.patch("/{exercise_id}", response_model=ExerciseRead)
async def update_exercise(
    exercise_id: int,
    payload: ExerciseUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an exercise (partial)."""
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(exercise, k, v)
    await db.flush()
    await db.refresh(exercise)
    result = await db.execute(
        _exercise_query().where(Exercise.id == exercise_id)
    )
    return result.scalar_one()


@router.delete("/{exercise_id}", status_code=204)
async def delete_exercise(
    exercise_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete an exercise."""
    result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
    exercise = result.scalar_one_or_none()
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    await db.delete(exercise)
    return None
