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
    # Single query for all-time max weight, max volume, max duration
    r = await db.execute(
        select(
            func.max(WorkoutSet.weight).label("max_weight"),
            func.max(WorkoutSet.weight * WorkoutSet.reps).label("max_volume"),
            func.max(WorkoutSet.duration_seconds).label("max_duration"),
        ).where(WorkoutSet.exercise_id == exercise_id)
    )
    row = r.one_or_none()
    max_weight = float(row.max_weight or 0) if row else 0
    max_volume = float(row.max_volume or 0) if row else 0
    max_duration = int(row.max_duration or 0) if row else 0

    if weight is not None and float(weight) > max_weight:
        return True, PRType.WEIGHT
    if weight is not None and reps is not None and (float(weight) * int(reps)) > max_volume:
        return True, PRType.VOLUME
    if duration_seconds is not None and int(duration_seconds) > max_duration:
        return True, PRType.DURATION
    return False, None
