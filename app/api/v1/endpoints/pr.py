"""PR Trophy Room - records broken this month or year."""

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.workout import Workout, WorkoutSet

router = APIRouter()


@router.get("/trophy-room")
async def pr_trophy_room(
    period: Literal["month", "year"] = "month",
    db: AsyncSession = Depends(get_db),
):
    """
    Lists sets marked as PR (personal record) in the given period.
    period=month: this calendar month; period=year: this calendar year.
    """
    now = datetime.utcnow()
    if period == "month":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now.replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)

    result = await db.execute(
        select(WorkoutSet)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(WorkoutSet.is_pr.is_(True), Workout.started_at >= start)
        .options(
            selectinload(WorkoutSet.exercise),
            selectinload(WorkoutSet.workout),
        )
        .order_by(Workout.started_at.desc())
    )
    sets = result.scalars().all()

    return {
        "period": period,
        "from": start.isoformat(),
        "to": now.isoformat(),
        "count": len(sets),
        "records": [
            {
                "set_id": s.id,
                "workout_id": s.workout_id,
                "workout_started_at": s.workout.started_at.isoformat() if s.workout and s.workout.started_at else None,
                "exercise_id": s.exercise_id,
                "exercise_name": s.exercise.name if s.exercise else None,
                "pr_type": s.pr_type.value if s.pr_type else None,
                "weight": float(s.weight) if s.weight is not None else None,
                "reps": s.reps,
                "duration_seconds": s.duration_seconds,
            }
            for s in sets
        ],
    }
