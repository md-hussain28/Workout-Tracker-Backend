"""Workout CRUD endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.constants import (
    MAX_EXERCISES_PER_SESSION,
    MAX_SETS_PER_EXERCISE_PER_SESSION,
)
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
from app.services.pr_detection import detect_pr

router = APIRouter()


@router.get("", response_model=list[WorkoutRead])
async def list_workouts(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 50,
):
    """List workouts (without sets)."""
    result = await db.execute(
        select(Workout).order_by(Workout.started_at.desc()).offset(skip).limit(limit)
    )
    workouts = result.scalars().all()
    return [
        WorkoutRead(
            id=w.id,
            started_at=w.started_at,
            ended_at=w.ended_at,
            duration_seconds=w.duration_seconds,
            notes=w.notes,
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
        sets=[],
    )


@router.get("/{workout_id}", response_model=WorkoutReadWithSets)
async def get_workout(
    workout_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Get a workout with all sets (and exercise info)."""
    result = await db.execute(
        select(Workout)
        .where(Workout.id == workout_id)
        .options(selectinload(Workout.sets).selectinload(WorkoutSet.exercise))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")
    return workout


@router.patch("/{workout_id}", response_model=WorkoutRead)
async def update_workout(
    workout_id: int,
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
        sets=[],
    )


@router.delete("/{workout_id}", status_code=204)
async def delete_workout(
    workout_id: int,
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
    workout_id: int,
    payload: WorkoutSetCreate,
    db: AsyncSession = Depends(get_db),
):
    """Add a set (max 20 exercises per session, 10 sets per exercise). Auto-flags PRs."""
    result = await db.execute(select(Workout).where(Workout.id == workout_id))
    workout = result.scalar_one_or_none()
    if not workout:
        raise HTTPException(status_code=404, detail="Workout not found")

    # Distinct exercise count in this workout
    distinct_ex = await db.execute(
        select(func.count(func.distinct(WorkoutSet.exercise_id))).where(
            WorkoutSet.workout_id == workout_id
        )
    )
    n_exercises = distinct_ex.scalar() or 0
    sets_for_exercise = await db.execute(
        select(func.count(WorkoutSet.id)).where(
            WorkoutSet.workout_id == workout_id,
            WorkoutSet.exercise_id == payload.exercise_id,
        )
    )
    n_sets_this_ex = sets_for_exercise.scalar() or 0

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
    return set_


@router.patch("/{workout_id}/sets/{set_id}", response_model=WorkoutSetRead)
async def update_set(
    workout_id: int,
    set_id: int,
    payload: WorkoutSetUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update an existing set (weight, reps, duration, notes, label)."""
    result = await db.execute(
        select(WorkoutSet).where(WorkoutSet.id == set_id, WorkoutSet.workout_id == workout_id)
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
    workout_id: int,
    set_id: int,
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
