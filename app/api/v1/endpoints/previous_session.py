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
    # Subquery: single most recent workout id that has this exercise
    subq = (
        select(Workout.id)
        .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
        .where(WorkoutSet.exercise_id == exercise_id)
        .order_by(Workout.started_at.desc())
        .limit(1)
    )
    if exclude_workout_id is not None:
        subq = subq.where(Workout.id != exclude_workout_id)
    subq = subq.subquery()

    # One query: sets for this exercise in that workout, with workout started_at
    result = await db.execute(
        select(WorkoutSet, Workout.started_at)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(
            WorkoutSet.exercise_id == exercise_id,
            WorkoutSet.workout_id.in_(subq),
        )
        .order_by(WorkoutSet.set_order, WorkoutSet.id)
    )
    rows = result.all()
    if not rows:
        return {"workout_id": None, "sets": [], "message": "No previous session for this exercise."}

    first = rows[0]
    workout_id = first[0].workout_id
    started_at = first[1]
    return {
        "workout_id": workout_id,
        "workout_started_at": started_at.isoformat() if started_at else None,
        "sets": [
            {
                "id": s.id,
                "set_order": s.set_order,
                "weight": float(s.weight) if s.weight is not None else None,
                "reps": s.reps,
                "duration_seconds": s.duration_seconds,
                "set_label": s.set_label.value if s.set_label else None,
            }
            for s, _ in rows
        ],
    }
