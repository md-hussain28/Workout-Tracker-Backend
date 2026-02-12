"""Streak calculation endpoint."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.workout import Workout

router = APIRouter()


@router.get("")
async def get_streak(db: AsyncSession = Depends(get_db)):
    """
    Returns current workout streak (consecutive days with at least 1 workout),
    longest ever streak, and the date of the last workout.
    """
    # Get all distinct workout dates, ordered descending
    result = await db.execute(
        select(func.date(Workout.started_at).label("d"))
        .group_by(func.date(Workout.started_at))
        .order_by(func.date(Workout.started_at).desc())
    )
    workout_dates: list[date] = []
    for row in result.all():
        d = row.d
        if isinstance(d, str):
            d = date.fromisoformat(d)
        workout_dates.append(d)

    if not workout_dates:
        return {
            "current_streak": 0,
            "longest_streak": 0,
            "last_workout_date": None,
        }

    today = date.today()
    last_workout = workout_dates[0]

    # Calculate current streak (must include today or yesterday to be "current")
    current_streak = 0
    if last_workout >= today - timedelta(days=1):
        current_streak = 1
        for i in range(1, len(workout_dates)):
            if workout_dates[i] == workout_dates[i - 1] - timedelta(days=1):
                current_streak += 1
            else:
                break

    # Calculate longest streak
    longest = 1
    run = 1
    for i in range(1, len(workout_dates)):
        if workout_dates[i] == workout_dates[i - 1] - timedelta(days=1):
            run += 1
            longest = max(longest, run)
        else:
            run = 1

    return {
        "current_streak": current_streak,
        "longest_streak": longest,
        "last_workout_date": last_workout.isoformat(),
    }
