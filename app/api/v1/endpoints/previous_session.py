"""Previous session context - what you did last time for an exercise (progressive overload)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.workout import Workout, WorkoutSet

router = APIRouter()


@router.get("/exercises/{exercise_id}/previous-session")
async def get_previous_session_sets(
    exercise_id: uuid.UUID,
    exclude_workout_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Returns the sets for this exercise from the most recent workout that included it.
    Use when adding a set to show "last time you did X". Pass exclude_workout_id
    (e.g. current workout) to get the *previous* session instead of the current one.
    """
    # Workout IDs that have this exercise, ordered by workout started_at desc
    stmt = (
        select(Workout.id)
        .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
        .where(WorkoutSet.exercise_id == exercise_id)
        .order_by(Workout.started_at.desc())
    )
    if exclude_workout_id is not None:
        stmt = stmt.where(Workout.id != exclude_workout_id)
    stmt = stmt.limit(1)
    workout_id_row = await db.execute(stmt)
    workout_id = workout_id_row.scalar_one_or_none()
    if not workout_id:
        return {"workout_id": None, "sets": [], "message": "No previous session for this exercise."}

    result = await db.execute(
        select(Workout)
        .where(Workout.id == workout_id)
        .options(selectinload(Workout.sets).selectinload(WorkoutSet.exercise))
    )
    workout = result.scalar_one_or_none()
    if not workout:
        return {"workout_id": None, "sets": []}

    sets_for_exercise = [s for s in workout.sets if s.exercise_id == exercise_id]
    sets_for_exercise.sort(key=lambda s: (s.set_order, s.id))
    return {
        "workout_id": workout.id,
        "workout_started_at": workout.started_at.isoformat() if workout.started_at else None,
        "sets": [
            {
                "id": s.id,
                "set_order": s.set_order,
                "weight": float(s.weight) if s.weight is not None else None,
                "reps": s.reps,
                "duration_seconds": s.duration_seconds,
                "set_label": s.set_label.value if s.set_label else None,
            }
            for s in sets_for_exercise
        ],
    }
