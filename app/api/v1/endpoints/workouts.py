"""Workout CRUD endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    MAX_EXERCISES_PER_SESSION,
    MAX_SETS_PER_EXERCISE_PER_SESSION,
)
from app.api.v1.endpoints.body import USER_ID, get_weight_at_date
from app.db.session import get_db
from app.models.workout import Workout, WorkoutSet
from app.schemas.workout import (
    WorkoutCreate,
    WorkoutRead,
    WorkoutReadWithSets,
    WorkoutSetCreate,
    WorkoutSetRead,
    WorkoutSetUpdate,
    WorkoutUpdate,
)
from app.services.calorie_estimation import (
    estimate_calories,
    get_active_duration_minutes,
)
from app.services.pr_detection import detect_pr

router = APIRouter()


@router.get("", response_model=list[WorkoutRead])
async def list_workouts(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
):
    """List workouts (without sets), optionally filtered by date range."""
    stmt = select(Workout)
    if from_date:
        stmt = stmt.where(Workout.started_at >= from_date)
    if to_date:
        stmt = stmt.where(Workout.started_at <= to_date)
    stmt = stmt.order_by(Workout.started_at.desc()).offset(skip).limit(limit)
    result = await db.execute(stmt)
    workouts = result.scalars().all()
    return [
        WorkoutRead(
            id=w.id,
            started_at=w.started_at,
            ended_at=w.ended_at,
            duration_seconds=w.duration_seconds,
            notes=w.notes,
            intensity=w.intensity,
            sets=[],
        )
        for w in workouts
    ]


@router.post("", response_model=WorkoutRead, status_code=201)
async def create_workout(
    payload: WorkoutCreate,
    db: AsyncSession = Depends(get_db),
):
    """Start a new workout."""
    workout = Workout(**payload.model_dump())
    db.add(workout)
    await db.flush()
    await db.refresh(workout)
    # Return a plain dict so we never touch workout.sets (avoids async lazy-load error)
    return WorkoutRead(
        id=workout.id,
        started_at=workout.started_at,
        ended_at=workout.ended_at,
        duration_seconds=workout.duration_seconds,
        notes=workout.notes,
        intensity=workout.intensity,
        sets=[],
    )


@router.get("/{workout_id}", response_model=WorkoutReadWithSets)
async def get_workout(
    workout_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a workout with all sets (and exercise info). Includes estimated_calories when computable."""
    result = await db.execute(
        select(Workout)
        .where(Workout.id == workout_id)
        .options(selectinload(Workout.sets).selectinload(WorkoutSet.exercise))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    estimated_calories = None
    weight_kg = await get_weight_at_date(db, USER_ID, workout.started_at)
    if weight_kg is not None:
        duration_min = get_active_duration_minutes(
            workout.duration_seconds,
            len(workout.sets),
        )
        if duration_min > 0:
            tonnage = sum(
                float(s.weight or 0) * float(s.reps or 0)
                for s in workout.sets
                if s.weight is not None and s.reps is not None
            )
            active_sec = sum(
                (s.time_under_tension_seconds if s.time_under_tension_seconds is not None else 45) 
                for s in workout.sets
            )
            rest_sec = sum(
                (s.rest_seconds_after if s.rest_seconds_after is not None else 90) 
                for s in workout.sets
            )
            cal = estimate_calories(
                weight_kg,
                duration_min,
                workout.intensity,
                tonnage_kg=tonnage if tonnage > 0 else None,
                active_seconds=active_sec if active_sec > 0 else None,
                rest_seconds=rest_sec if rest_sec > 0 else None,
            )
            estimated_calories = round(cal)

    # Order sets by set_order then id (stable order per exercise).
    sorted_sets = sorted(workout.sets, key=lambda s: (s.set_order, str(s.id)))

    return WorkoutReadWithSets(
        id=workout.id,
        started_at=workout.started_at,
        ended_at=workout.ended_at,
        duration_seconds=workout.duration_seconds,
        notes=workout.notes,
        intensity=workout.intensity,
        estimated_calories=estimated_calories,
        sets=[WorkoutSetRead.model_validate(s) for s in sorted_sets],
    )


@router.patch("/{workout_id}", response_model=WorkoutRead)
async def update_workout(
    workout_id: uuid.UUID,
    payload: WorkoutUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update workout (e.g. end time, notes). Sets duration_seconds from started_at/ended_at if not provided."""
    result = await db.execute(select(Workout).where(Workout.id == workout_id))
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    data = payload.model_dump(exclude_unset=True)
    if "ended_at" in data and data["ended_at"] and workout.started_at and "duration_seconds" not in data:
        from datetime import timezone as tz
        ended = data["ended_at"]
        started = workout.started_at
        # Normalize both to tz-aware UTC for safe subtraction
        if ended.tzinfo is None:
            ended = ended.replace(tzinfo=tz.utc)
        if started.tzinfo is None:
            started = started.replace(tzinfo=tz.utc)
        delta = ended - started
        data["duration_seconds"] = max(0, int(delta.total_seconds()))
    for k, v in data.items():
        setattr(workout, k, v)
    await db.flush()
    await db.refresh(workout)
    return WorkoutRead(
        id=workout.id,
        started_at=workout.started_at,
        ended_at=workout.ended_at,
        duration_seconds=workout.duration_seconds,
        notes=workout.notes,
        intensity=workout.intensity,
        sets=[],
    )


@router.delete("/{workout_id}", status_code=204)
async def delete_workout(
    workout_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a workout and its sets."""
    result = await db.execute(select(Workout).where(Workout.id == workout_id))
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    await db.delete(workout)
    return None


@router.post("/{workout_id}/sets", response_model=WorkoutSetRead, status_code=201)
async def add_set_to_workout(
    workout_id: uuid.UUID,
    payload: WorkoutSetCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a set (max 20 exercises per session, 10 sets per exercise). Auto-flags PRs."""
    result = await db.execute(select(Workout).where(Workout.id == workout_id))
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    # One query: distinct exercise count and sets count for this exercise
    from sqlalchemy import case
    counts_row = await db.execute(
        select(
            func.count(func.distinct(WorkoutSet.exercise_id)).label("n_exercises"),
            func.count(case((WorkoutSet.exercise_id == payload.exercise_id, 1))).label("n_sets_this_ex"),
        ).where(WorkoutSet.workout_id == workout_id)
    )
    row = counts_row.one_or_none()
    n_exercises = int(row.n_exercises or 0) if row else 0
    n_sets_this_ex = int(row.n_sets_this_ex or 0) if row else 0

    if n_sets_this_ex >= MAX_SETS_PER_EXERCISE_PER_SESSION:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_SETS_PER_EXERCISE_PER_SESSION} sets per exercise per session.",
        )
    if n_exercises >= MAX_EXERCISES_PER_SESSION and n_sets_this_ex == 0:
        raise HTTPException(
            status_code=400,
            detail=f"Maximum {MAX_EXERCISES_PER_SESSION} exercises per session.",
        )

    is_pr, pr_type = await detect_pr(
        db,
        payload.exercise_id,
        payload.weight,
        payload.reps,
        payload.duration_seconds,
    )
    data = payload.model_dump()
    set_ = WorkoutSet(
        workout_id=workout_id,
        is_pr=is_pr,
        pr_type=pr_type,
        **data,
    )
    db.add(set_)
    await db.flush()
    await db.refresh(set_)
    
    # Reload with exercise for frontend display
    result = await db.execute(
        select(WorkoutSet)
        .where(WorkoutSet.id == set_.id)
        .options(selectinload(WorkoutSet.exercise))
    )
    set_ = result.scalar_one()

    return set_


@router.patch("/{workout_id}/sets/{set_id}", response_model=WorkoutSetRead)
async def update_set(
    workout_id: uuid.UUID,
    set_id: uuid.UUID,
    payload: WorkoutSetUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing set (weight, reps, duration, notes, label)."""
    result = await db.execute(
        select(WorkoutSet)
        .where(WorkoutSet.id == set_id, WorkoutSet.workout_id == workout_id)
        .options(selectinload(WorkoutSet.exercise))
    )
    set_ = result.scalar_one_or_none()
    if not set_:
        raise HTTPException(status_code=404, detail="Set not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(set_, k, v)
    await db.flush()
    await db.refresh(set_)
    return set_


@router.delete("/{workout_id}/sets/{set_id}", status_code=204)
async def delete_set(
    workout_id: uuid.UUID,
    set_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a set from a workout."""
    result = await db.execute(
        select(WorkoutSet).where(WorkoutSet.id == set_id, WorkoutSet.workout_id == workout_id)
    )
    set_ = result.scalar_one_or_none()
    if not set_:
        raise HTTPException(status_code=404, detail="Set not found")
    await db.delete(set_)
    return None
