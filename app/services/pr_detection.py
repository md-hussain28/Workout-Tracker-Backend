"""PR detection: flag a set as PR if it exceeds all-time best for that exercise."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import PRType
from app.models.workout import WorkoutSet


async def detect_pr(
    db: AsyncSession,
    exercise_id: int,
    weight: float | None,
    reps: int | None,
    duration_seconds: int | None,
) -> tuple[bool, PRType | None]:
    """
    Compare this set's weight/volume/duration to all-time bests for the exercise.
    Returns (is_pr, pr_type). pr_type is weight, volume, or duration if it's a PR.
    (Current DB max is the previous best since the new set isn't saved yet.)
    """
    # All-time max weight
    r = await db.execute(
        select(func.max(WorkoutSet.weight)).where(WorkoutSet.exercise_id == exercise_id)
    )
    max_weight = r.scalar() or 0

    # All-time max volume (weight * reps), only where both present
    r = await db.execute(
        select(func.max(WorkoutSet.weight * WorkoutSet.reps)).where(
            WorkoutSet.exercise_id == exercise_id,
            WorkoutSet.weight.isnot(None),
            WorkoutSet.reps.isnot(None),
        )
    )
    max_volume = float(r.scalar() or 0)

    # All-time max duration
    r = await db.execute(
        select(func.max(WorkoutSet.duration_seconds)).where(
            WorkoutSet.exercise_id == exercise_id
        )
    )
    max_duration = r.scalar() or 0

    if weight is not None and float(weight) > float(max_weight):
        return True, PRType.WEIGHT
    if weight is not None and reps is not None and (float(weight) * int(reps)) > max_volume:
        return True, PRType.VOLUME
    if duration_seconds is not None and int(duration_seconds) > int(max_duration):
        return True, PRType.DURATION
    return False, None
