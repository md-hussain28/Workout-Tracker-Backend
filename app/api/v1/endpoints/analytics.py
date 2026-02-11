"""Data insights & analytics: muscle volume, 1RM, tonnage, consistency."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutSet

router = APIRouter()


def _volume_weight(primary: bool, secondary: bool, tertiary: bool) -> float:
    """Primary 100%, Secondary 50%, Tertiary 25%."""
    if primary:
        return 1.0
    if secondary:
        return 0.5
    if tertiary:
        return 0.25
    return 0.0


@router.get("/muscle-volume")
async def muscle_volume_heatmap(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Volume per muscle group for heatmap/body map.
    Primary target = 100%, Secondary = 50%, Tertiary = 25%.
    Volume = sum over sets of (weight * reps * factor) or duration * factor for time-based.
    """
    # Build per-muscle-group volume from sets joined to exercises
    conditions = []
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)
    stmt = (
        select(WorkoutSet, Exercise)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
    )
    if conditions:
        stmt = stmt.where(*conditions)
    sets_with_ex = await db.execute(stmt)
    rows = sets_with_ex.all()

    volume_by_muscle: dict[int | None, float] = {}
    name_by_muscle: dict[int | None, str] = {}

    for (s, ex) in rows:
        weight = float(s.weight or 0)
        reps = int(s.reps or 0)
        duration = int(s.duration_seconds or 0)
        for mg_id, name_attr, is_primary, is_secondary, is_tertiary in [
            (ex.primary_muscle_group_id, "primary_muscle_group", True, False, False),
            (ex.secondary_muscle_group_id, "secondary_muscle_group", False, True, False),
            (ex.tertiary_muscle_group_id, "tertiary_muscle_group", False, False, True),
        ]:
            if mg_id is None:
                continue
            factor = _volume_weight(is_primary, is_secondary, is_tertiary)
            if duration:
                vol = duration * factor
            else:
                vol = (weight * reps) * factor
            volume_by_muscle[mg_id] = volume_by_muscle.get(mg_id, 0) + vol
            rel = getattr(ex, name_attr, None)
            if mg_id not in name_by_muscle and rel is not None:
                name_by_muscle[mg_id] = rel.name

    # Resolve names from DB for any we didn't get from loaded relation
    from app.models.muscle_group import MuscleGroup
    for mg_id in volume_by_muscle:
        if mg_id not in name_by_muscle:
            r = await db.execute(select(MuscleGroup.name).where(MuscleGroup.id == mg_id))
            name_by_muscle[mg_id] = r.scalar_one_or_none() or f"MuscleGroup_{mg_id}"

    return {
        "from": from_date.isoformat() if from_date else None,
        "to": to_date.isoformat() if to_date else None,
        "muscle_groups": [
            {"muscle_group_id": mg_id, "name": name_by_muscle.get(mg_id), "volume": round(v, 2)}
            for mg_id, v in sorted(volume_by_muscle.items(), key=lambda x: -x[1])
        ],
    }


def _brzycki_1rm(weight: float, reps: int) -> float:
    """1RM = weight * (36 / (37 - reps))."""
    if reps <= 0:
        return 0.0
    if reps >= 37:
        return weight * 1.1  # extrapolate
    return weight * (36 / (37 - reps))


def _epley_1rm(weight: float, reps: int) -> float:
    """1RM = weight * (1 + reps/30)."""
    if reps <= 0:
        return 0.0
    return weight * (1 + reps / 30)


@router.get("/one-rm/{exercise_id}")
async def one_rm_prediction(
    exercise_id: int,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    formula: str = "brzycki",
    db: AsyncSession = Depends(get_db),
):
    """
    Estimated 1-Rep Max over time for an exercise (weight+reps sets only).
    formula: brzycki | epley.
    """
    fn = _brzycki_1rm if formula == "brzycki" else _epley_1rm
    conditions = [
        WorkoutSet.exercise_id == exercise_id,
        WorkoutSet.weight.isnot(None),
        WorkoutSet.reps.isnot(None),
    ]
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)
    stmt = (
        select(Workout.started_at, WorkoutSet.weight, WorkoutSet.reps)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(*conditions)
        .order_by(Workout.started_at)
    )
    result = await db.execute(stmt)
    rows = result.all()
    points = []
    for started_at, weight, reps in rows:
        if weight and reps:
            est = fn(float(weight), int(reps))
            points.append({"date": started_at.isoformat() if started_at else None, "estimated_1rm": round(est, 2)})
    return {"exercise_id": exercise_id, "formula": formula, "points": points}


@router.get("/tonnage")
async def workout_tonnage(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Total tonnage (sum of weight * reps) per workout for intensity radar."""
    conditions = []
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)
    stmt = (
        select(
            Workout.id,
            Workout.started_at,
            func.coalesce(func.sum(WorkoutSet.weight * func.coalesce(WorkoutSet.reps, 0)), 0).label("tonnage"),
        )
        .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
    )
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.group_by(Workout.id, Workout.started_at).order_by(Workout.started_at)
    result = await db.execute(stmt)
    rows = result.all()
    return {
        "from": from_date.isoformat() if from_date else None,
        "to": to_date.isoformat() if to_date else None,
        "workouts": [
            {"workout_id": r.id, "started_at": r.started_at.isoformat() if r.started_at else None, "tonnage": float(r.tonnage)}
            for r in rows
        ],
    }


@router.get("/consistency")
async def consistency_calendar(
    year: int,
    month: int | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Calendar view: days with workouts. Optional month for one month; else full year.
    Returns list of { date, duration_seconds, tonnage } for color intensity.
    """
    start = datetime(year, month or 1, 1)
    if month:
        if month == 12:
            end = datetime(year + 1, 1, 1)
        else:
            end = datetime(year, month + 1, 1)
    else:
        end = datetime(year + 1, 1, 1)

    stmt = (
        select(
            Workout.started_at,
            Workout.duration_seconds,
            func.coalesce(func.sum(WorkoutSet.weight * func.coalesce(WorkoutSet.reps, 0)), 0).label("tonnage"),
        )
        .outerjoin(WorkoutSet, WorkoutSet.workout_id == Workout.id)
        .where(Workout.started_at >= start, Workout.started_at < end)
        .group_by(Workout.id, Workout.started_at, Workout.duration_seconds)
    )
    result = await db.execute(stmt)
    rows = result.all()
    days: list[dict[str, Any]] = []
    for r in rows:
        d = r.started_at.date() if r.started_at else None
        if not d:
            continue
        days.append({
            "date": d.isoformat(),
            "duration_seconds": r.duration_seconds,
            "tonnage": float(r.tonnage),
        })
    return {"year": year, "month": month, "days": days}
