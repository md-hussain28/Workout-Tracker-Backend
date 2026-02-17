"""Data insights & analytics: muscle volume, 1RM, tonnage, consistency."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from math import exp
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.v1.endpoints.body import USER_ID, get_weight_at_date
from app.db.session import get_db
from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutSet
from app.services.calorie_estimation import (
    estimate_calories,
    get_active_duration_minutes,
)

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
    exercise_id: uuid.UUID,
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


@router.get("/volume-history-by-muscle")
async def volume_history_by_muscle(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Daily volume grouped by Primary Muscle Group.
    Returns: { date: string, muscles: { [muscle_name]: volume } }[]
    """
    conditions = []
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)
        
    stmt = (
        select(
            Workout.started_at,
            Exercise.primary_muscle_group_id,
            func.sum(WorkoutSet.weight * WorkoutSet.reps).label("volume")
        )
        .join(WorkoutSet, Workout.id == WorkoutSet.workout_id)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .where(
            WorkoutSet.weight.isnot(None),
            WorkoutSet.reps.isnot(None),
            Exercise.primary_muscle_group_id.isnot(None),
            *conditions
        )
        .group_by(Workout.started_at, Exercise.primary_muscle_group_id)
        .order_by(Workout.started_at)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    # We also need muscle names
    from app.models.muscle_group import MuscleGroup
    mg_result = await db.execute(select(MuscleGroup.id, MuscleGroup.name))
    mg_map = {row.id: row.name for row in mg_result.all()}
    
    # Process into Date -> { muscle: vol }
    data_by_date: dict[str, dict[str, float]] = {}
    
    for r in rows:
        d = r.started_at.date().isoformat()
        mg_name = mg_map.get(r.primary_muscle_group_id, "Unknown")
        vol = float(r.volume or 0)
        
        if d not in data_by_date:
            data_by_date[d] = {"date": d}
        
        data_by_date[d][mg_name] = data_by_date[d].get(mg_name, 0.0) + vol
        
    return list(data_by_date.values())


@router.get("/muscle-distribution")
async def muscle_distribution(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Total SETS count per muscle group (Primary Only for now).
    """
    conditions = []
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)

    stmt = (
        select(
            Exercise.primary_muscle_group_id,
            func.count(WorkoutSet.id).label("set_count")
        )
        .join(WorkoutSet, Exercise.id == WorkoutSet.exercise_id)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(
            Exercise.primary_muscle_group_id.isnot(None),
            *conditions
        )
        .group_by(Exercise.primary_muscle_group_id)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    from app.models.muscle_group import MuscleGroup
    mg_result = await db.execute(select(MuscleGroup.id, MuscleGroup.name))
    mg_map = {row.id: row.name for row in mg_result.all()}
    
    return [
        {"name": mg_map.get(r.primary_muscle_group_id, "Unknown"), "value": r.set_count}
        for r in rows
    ]


@router.get("/workout-density")
async def workout_density(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Sets per workout, stacked by Exercise.
    """
    conditions = []
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)

    stmt = (
        select(
            Workout.started_at,
            Exercise.name,
            func.count(WorkoutSet.id).label("set_count")
        )
        .join(WorkoutSet, Workout.id == WorkoutSet.workout_id)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .where(*conditions)
        .group_by(Workout.started_at, Exercise.name)
        .order_by(Workout.started_at)
    )
    
    result = await db.execute(stmt)
    rows = result.all()
    
    data_by_date: dict[str, dict[str, Any]] = {}
    
    for r in rows:
        d = r.started_at.date().isoformat()
        if d not in data_by_date:
            data_by_date[d] = {"date": d}
            
        data_by_date[d][r.name] = r.set_count
        
    return list(data_by_date.values())


@router.get("/plateau-radar")
async def plateau_radar(
    db: AsyncSession = Depends(get_db),
):
    """
    Radar chart data: Top 6 exercises by volume.
    Compare: "All Time Best Volume" vs "Average of Last 3 Workouts Volume".
    """
    # 1. Find top 6 exercises by total all-time sets (most practiced)
    top_ex_stmt = (
        select(Exercise.id, Exercise.name)
        .join(WorkoutSet, Exercise.id == WorkoutSet.exercise_id)
        .group_by(Exercise.id)
        .order_by(func.count(WorkoutSet.id).desc())
        .limit(6)
    )
    top_ex_res = await db.execute(top_ex_stmt)
    top_exercises = top_ex_res.all()
    
    valid_data = []
    
    for ex_id, ex_name in top_exercises:
        # Get all workouts for this exercise with computed volume
        hist_stmt = (
            select(
                Workout.started_at,
                func.sum(WorkoutSet.weight * WorkoutSet.reps).label("vol")
            )
            .join(WorkoutSet, Workout.id == WorkoutSet.workout_id)
            .where(
                WorkoutSet.exercise_id == ex_id,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None)
            )
            .group_by(Workout.id, Workout.started_at)
            .order_by(Workout.started_at.desc())
        )
        hist_res = await db.execute(hist_stmt)
        history = hist_res.all()
        
        if not history:
            continue
            
        # All time best (vol can be Decimal from DB; convert to float for JSON and arithmetic)
        all_time_best = float(max(h.vol for h in history))
        
        # Recent average (last 3 sessions)
        recent_sessions = history[:3]
        recent_avg = float(sum(h.vol for h in recent_sessions)) / len(recent_sessions)
        
        valid_data.append({
            "subject": ex_name,
            "A": round(all_time_best, 1),  # Full
            "B": round(recent_avg, 1),     # Recent
            "fullMark": round(all_time_best * 1.1, 1),  # Scale max
        })
        
    return valid_data


@router.get("/recovery")
async def muscle_recovery(
    db: AsyncSession = Depends(get_db),
):
    """
    Muscle-group fatigue/readiness scan for anatomy heatmap.
    Returns per-muscle fatigue_score (0.0-1.0) and overstrained flag.

    Logic:
    - Calculate weighted volume (primary 100%, secondary 50%, tertiary 25%)
      for the last 48 hours and the last 28 days.
    - fatigue_score = recent_volume / max(avg_volume, 1) clamped to 0-1,
      with exponential decay based on hours since last trained.
    - overstrained = true if 48h volume exceeds 4-week session average by >30%.
    """
    from app.models.muscle_group import MuscleGroup

    now = datetime.now(timezone.utc)
    cutoff_48h = now - timedelta(hours=48)
    cutoff_28d = now - timedelta(days=28)

    # ── Fetch all muscle groups ──
    mg_result = await db.execute(select(MuscleGroup.id, MuscleGroup.name))
    all_muscles = {row.id: row.name for row in mg_result.all()}

    # ── Fetch all sets from last 28 days with exercise + workout ──
    stmt = (
        select(WorkoutSet, Exercise, Workout.started_at)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(Workout.started_at >= cutoff_28d)
    )
    result = await db.execute(stmt)
    rows = result.all()

    # ── Accumulate per-muscle volumes ──
    # recent_vol = volume in last 48h
    # total_vol_28d = total volume in 28 days
    # workout_dates_28d = set of workout dates per muscle (to count sessions)
    # last_trained = most recent workout timestamp per muscle
    recent_vol: dict[int, float] = {}
    total_vol_28d: dict[int, float] = {}
    session_count_28d: dict[int, int] = {}  # approximate via distinct workout dates
    workout_ids_28d: dict[int, set[int]] = {}
    last_trained: dict[int, datetime] = {}

    for (s, ex, started_at) in rows:
        weight = float(s.weight or 0)
        reps = int(s.reps or 0)
        duration = int(s.duration_seconds or 0)

        for mg_id, is_p, is_s, is_t in [
            (ex.primary_muscle_group_id, True, False, False),
            (ex.secondary_muscle_group_id, False, True, False),
            (ex.tertiary_muscle_group_id, False, False, True),
        ]:
            if mg_id is None:
                continue
            factor = _volume_weight(is_p, is_s, is_t)
            vol = (duration * factor) if duration else ((weight * reps) * factor)

            # 28-day totals
            total_vol_28d[mg_id] = total_vol_28d.get(mg_id, 0) + vol
            if mg_id not in workout_ids_28d:
                workout_ids_28d[mg_id] = set()
            workout_ids_28d[mg_id].add(s.workout_id)

            # 48h window
            if started_at and started_at >= cutoff_48h:
                recent_vol[mg_id] = recent_vol.get(mg_id, 0) + vol

            # Last trained
            if started_at:
                if mg_id not in last_trained or started_at > last_trained[mg_id]:
                    last_trained[mg_id] = started_at

    # ── Compute per-muscle scores ──
    muscles = []
    for mg_id, mg_name in all_muscles.items():
        sessions = len(workout_ids_28d.get(mg_id, set()))
        avg_session_vol = (total_vol_28d.get(mg_id, 0) / max(sessions, 1))
        recent = recent_vol.get(mg_id, 0)
        lt = last_trained.get(mg_id)

        # Time-based decay: exponential decay over 72 hours
        if lt:
            hours_since = max((now - lt).total_seconds() / 3600, 0)
            decay = exp(-hours_since / 24)  # half-life ~17h, near-zero at 72h
        else:
            decay = 0.0  # never trained = fully recovered

        # Raw fatigue: ratio of recent volume to average, scaled by decay
        if avg_session_vol > 0:
            raw_fatigue = (recent / avg_session_vol) * decay
        else:
            raw_fatigue = (1.0 if recent > 0 else 0.0) * decay

        fatigue_score = round(min(max(raw_fatigue, 0.0), 1.0), 2)

        # Overstrained: 48h volume > 130% of session average
        overstrained = recent > avg_session_vol * 1.3 if avg_session_vol > 0 else False

        # Normalised key for SVG mapping
        muscle_key = mg_name.lower().replace(" ", "_")

        muscles.append({
            "key": muscle_key,
            "name": mg_name,
            "fatigue_score": fatigue_score,
            "overstrained": overstrained,
        })

    # Sort by fatigue descending
    muscles.sort(key=lambda m: -m["fatigue_score"])

    return {"muscles": muscles}


@router.get("/calories-history")
async def calories_history(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Time series of estimated calories burned per day (sum of workouts per day).
    Requires body weight (BodyLog) for the user; returns empty list if no weight.
    """
    conditions = []
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)
    stmt = select(Workout)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.options(selectinload(Workout.sets)).order_by(Workout.started_at)
    result = await db.execute(stmt)
    workouts = result.scalars().unique().all()

    daily_calories: dict[str, float] = {}
    for w in workouts:
        weight_kg = await get_weight_at_date(db, USER_ID, w.started_at)
        if weight_kg is None:
            continue
        duration_min = get_active_duration_minutes(w.duration_seconds, len(w.sets))
        if duration_min <= 0:
            continue
        tonnage = sum(
            float(s.weight or 0) * float(s.reps or 0)
            for s in w.sets
            if s.weight is not None and s.reps is not None
        )
        active_sec = sum(s.time_under_tension_seconds or 0 for s in w.sets)
        rest_sec = sum(s.rest_seconds_after or 0 for s in w.sets)
        cal = estimate_calories(
            weight_kg,
            duration_min,
            w.intensity,
            tonnage_kg=tonnage if tonnage > 0 else None,
            active_seconds=active_sec if active_sec > 0 else None,
            rest_seconds=rest_sec if rest_sec > 0 else None,
        )
        date_key = w.started_at.date().isoformat()
        daily_calories[date_key] = daily_calories.get(date_key, 0) + round(cal)

    return [
        {"date": d, "calories": c}
        for d, c in sorted(daily_calories.items())
    ]


@router.get("/calories-summary")
async def calories_summary(
    from_date: datetime | None = None,
    to_date: datetime | None = None,
    db: AsyncSession = Depends(get_db),
):
    """
    Total and average estimated calories in the date range.
    """
    conditions = []
    if from_date:
        conditions.append(Workout.started_at >= from_date)
    if to_date:
        conditions.append(Workout.started_at <= to_date)
    stmt = select(Workout)
    if conditions:
        stmt = stmt.where(*conditions)
    stmt = stmt.options(selectinload(Workout.sets)).order_by(Workout.started_at)
    result = await db.execute(stmt)
    workouts = result.scalars().unique().all()

    total_calories = 0.0
    for w in workouts:
        weight_kg = await get_weight_at_date(db, USER_ID, w.started_at)
        if weight_kg is None:
            continue
        duration_min = get_active_duration_minutes(w.duration_seconds, len(w.sets))
        if duration_min <= 0:
            continue
        tonnage = sum(
            float(s.weight or 0) * float(s.reps or 0)
            for s in w.sets
            if s.weight is not None and s.reps is not None
        )
        active_sec = sum(s.time_under_tension_seconds or 0 for s in w.sets)
        rest_sec = sum(s.rest_seconds_after or 0 for s in w.sets)
        total_calories += estimate_calories(
            weight_kg,
            duration_min,
            w.intensity,
            tonnage_kg=tonnage if tonnage > 0 else None,
            active_seconds=active_sec if active_sec > 0 else None,
            rest_seconds=rest_sec if rest_sec > 0 else None,
        )

    workout_count = len(workouts)
    days_in_range = 1
    if from_date and to_date and to_date > from_date:
        days_in_range = max(1, (to_date - from_date).days + 1)
    daily_average = round(total_calories / days_in_range, 1) if days_in_range else 0

    return {
        "total_calories": round(total_calories),
        "workout_count": workout_count,
        "daily_average": daily_average,
    }

