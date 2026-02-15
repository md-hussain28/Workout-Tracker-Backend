"""Workout templates - save and reload workout structure."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import MAX_EXERCISES_PER_SESSION
from app.db.session import get_db
from app.models.template import TemplateExercise, WorkoutTemplate
from app.models.workout import Workout, WorkoutSet
from app.schemas.template import (
    TemplateExerciseRead,
    WorkoutTemplateCreate,
    WorkoutTemplateCreateFromWorkout,
    WorkoutTemplateRead,
    WorkoutTemplateUpdate,
)

router = APIRouter()


@router.get("", response_model=list[WorkoutTemplateRead])
async def list_templates(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """List all workout templates."""
    result = await db.execute(
        select(WorkoutTemplate)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(TemplateExercise.exercise))
        .order_by(WorkoutTemplate.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.scalars().all())


@router.post("", response_model=WorkoutTemplateRead, status_code=201)
async def create_template(
    payload: WorkoutTemplateCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create an empty template (add exercises via template exercises)."""
    t = WorkoutTemplate(name=payload.name)
    db.add(t)
    await db.flush()
    await db.refresh(t)
    result = await db.execute(
        select(WorkoutTemplate)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(TemplateExercise.exercise))
        .where(WorkoutTemplate.id == t.id)
    )
    return result.scalar_one()


@router.post("/from-workout", response_model=WorkoutTemplateRead, status_code=201)
async def create_template_from_workout(
    payload: WorkoutTemplateCreateFromWorkout,
    db: AsyncSession = Depends(get_db),
):
    """Save a completed workout as a template (exercise order preserved)."""
    result = await db.execute(
        select(Workout)
        .where(Workout.id == payload.workout_id)
        .options(selectinload(Workout.sets))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    # Unique exercise IDs in set order (first occurrence order)
    seen: set = set()
    order: list = []
    for s in sorted(workout.sets, key=lambda x: (x.set_order, x.id)):
        if s.exercise_id not in seen:
            seen.add(s.exercise_id)
            order.append(s.exercise_id)
    if len(order) > MAX_EXERCISES_PER_SESSION:
        order = order[:MAX_EXERCISES_PER_SESSION]

    t = WorkoutTemplate(name=payload.name)
    db.add(t)
    await db.flush()
    for i, ex_id in enumerate(order):
        te = TemplateExercise(template_id=t.id, exercise_id=ex_id, order_in_template=i)
        db.add(te)
    await db.flush()
    result = await db.execute(
        select(WorkoutTemplate)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(TemplateExercise.exercise))
        .where(WorkoutTemplate.id == t.id)
    )
    return result.scalar_one()


@router.get("/{template_id}", response_model=WorkoutTemplateRead)
async def get_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a template with its exercises."""
    result = await db.execute(
        select(WorkoutTemplate)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(TemplateExercise.exercise))
        .where(WorkoutTemplate.id == template_id)
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    return t


@router.patch("/{template_id}", response_model=WorkoutTemplateRead)
async def update_template(
    template_id: uuid.UUID,
    payload: WorkoutTemplateUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update template name."""
    result = await db.execute(select(WorkoutTemplate).where(WorkoutTemplate.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(t, k, v)
    await db.flush()
    result = await db.execute(
        select(WorkoutTemplate)
        .options(selectinload(WorkoutTemplate.exercises).selectinload(TemplateExercise.exercise))
        .where(WorkoutTemplate.id == template_id)
    )
    return result.scalar_one()


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a template."""
    result = await db.execute(select(WorkoutTemplate).where(WorkoutTemplate.id == template_id))
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")
    await db.delete(t)
    return None


@router.post("/{template_id}/instantiate", status_code=201)
async def instantiate_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Create a new workout from a template (same exercise order; sets added during session)."""
    result = await db.execute(
        select(WorkoutTemplate)
        .options(selectinload(WorkoutTemplate.exercises))
        .where(WorkoutTemplate.id == template_id)
    )
    t = result.scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Template not found")

    workout = Workout(notes=f"From template: {t.name}")
    db.add(workout)
    await db.flush()
    # Optionally pre-create empty set placeholders? No - frontend adds sets. Just return the new workout.
    await db.refresh(workout)
    return {
        "workout_id": workout.id,
        "started_at": workout.started_at.isoformat() if workout.started_at else None,
        "message": "Workout created. Add sets as you go.",
        "exercise_order": [te.exercise_id for te in sorted(t.exercises, key=lambda e: e.order_in_template)],
    }
