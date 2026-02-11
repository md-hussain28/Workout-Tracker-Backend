"""QoL tools: plate calculator, plateau alerts."""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import PLATEAU_SESSIONS_THRESHOLD
from app.db.session import get_db
from app.models.workout import Workout, WorkoutSet

router = APIRouter()


# ---- Plate calculator (pure logic, no DB) ----


class PlateCalculatorRequest(BaseModel):
    bar_weight: float = Field(ge=0, description="Bar weight (e.g. 20 kg)")
    target_weight: float = Field(gt=0, description="Total weight to load")
    available_plates: str = Field(
        default="20,15,10,5,2.5,1.25",
        description="Comma-separated plate weights (each side); e.g. 20,15,10,5,2.5,1.25",
    )


class PlateCalculatorResponse(BaseModel):
    weight_to_load: float
    per_side: float
    plates_per_side: list[float]
    total_weight: float  # bar + plates


def _plate_calc(bar: float, target: float, plates: list[float]) -> tuple[float, list[float]]:
    """Return (weight_per_side, sorted list of plates per side)."""
    load = target - bar
    if load <= 0:
        return 0.0, []
    per_side = load / 2.0
    sorted_plates = sorted(plates, reverse=True)
    result: list[float] = []
    remaining = per_side
    for p in sorted_plates:
        while remaining >= p - 0.001:  # float tolerance
            result.append(p)
            remaining -= p
    return per_side, result


@router.get("/plate-calculator", response_model=PlateCalculatorResponse)
async def plate_calculator(
    bar_weight: float = 20.0,
    target_weight: float = 100.0,
    available_plates: str = "20,15,10,5,2.5,1.25",
):
    """
    Returns which plates to put on each side of the bar to reach the target weight.
    Plates are in kg (or lb); same logic applies.
    """
    plates = [float(x.strip()) for x in available_plates.split(",") if x.strip()]
    per_side, plates_per_side = _plate_calc(bar_weight, target_weight, plates)
    total = bar_weight + 2 * sum(plates_per_side)
    return PlateCalculatorResponse(
        weight_to_load=total - bar_weight,
        per_side=per_side,
        plates_per_side=plates_per_side,
        total_weight=total,
    )


# ---- Plateau alerts (no progress for 3+ consecutive sessions) ----


@router.get("/plateau-alerts")
async def plateau_alerts(
    db: AsyncSession = Depends(get_db),
):
    """
    Exercises where weight or reps have not increased for 3+ consecutive sessions.
    Returns list of { exercise_id, exercise_name, sessions_without_improvement, last_* }.
    """
    # For each exercise, get workouts that contain it, ordered by started_at.
    # Compare last 3 (or more) sessions: if max weight and max volume and max duration
    # are all <= previous session, count as no improvement.
    # "Plateau" = 3+ consecutive sessions with no improvement.

    # Subquery: workouts per exercise, ordered by date, with session number
    # Then for each exercise, find where we have 3+ consecutive "no improvement" sessions.

    # Simpler approach: for each exercise, get last 4 workouts that have it.
    # Compare workout 4 to 3, 3 to 2, 2 to 1. If in all three comparisons we have
    # (max weight didn't increase AND max volume didn't increase AND max duration didn't increase),
    # then plateau.

    from app.models.exercise import Exercise

    # All exercises that have at least one set
    ex_with_sets = await db.execute(
        select(distinct(WorkoutSet.exercise_id))
    )
    exercise_ids = [r[0] for r in ex_with_sets.all()]

    alerts = []
    for exercise_id in exercise_ids:
        # Last N workouts for this exercise (by started_at desc)
        n = PLATEAU_SESSIONS_THRESHOLD + 1  # need 4 workouts to compare 3 gaps
        stmt = (
            select(Workout.id, Workout.started_at)
            .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
            .where(WorkoutSet.exercise_id == exercise_id)
            .order_by(Workout.started_at.desc())
            .limit(n)
        )
        result = await db.execute(stmt)
        workouts = result.all()
        if len(workouts) < n:
            continue

        workout_ids = [w.id for w in workouts]
        # For each workout, get max weight, max volume, max duration for this exercise
        session_stats: list[tuple[int, float, float, int]] = []  # workout_id, max_w, max_vol, max_dur
        for wid in workout_ids:
            r = await db.execute(
                select(
                    func.max(WorkoutSet.weight),
                    func.max(WorkoutSet.weight * func.coalesce(WorkoutSet.reps, 0)),
                    func.max(WorkoutSet.duration_seconds),
                ).where(WorkoutSet.workout_id == wid, WorkoutSet.exercise_id == exercise_id)
            )
            row = r.one()
            session_stats.append((
                wid,
                float(row[0] or 0),
                float(row[1] or 0),
                int(row[2] or 0),
            ))

        # session_stats ordered by workout desc, so [0]=most recent, [1]=previous, ...
        consecutive_no_improve = 0
        for i in range(len(session_stats) - 1):
            cur_w, cur_vol, cur_dur = session_stats[i][1], session_stats[i][2], session_stats[i][3]
            prev_w, prev_vol, prev_dur = session_stats[i + 1][1], session_stats[i + 1][2], session_stats[i + 1][3]
            if cur_w <= prev_w and cur_vol <= prev_vol and cur_dur <= prev_dur:
                consecutive_no_improve += 1
            else:
                break

        if consecutive_no_improve >= PLATEAU_SESSIONS_THRESHOLD:
            ex_row = await db.execute(select(Exercise.name).where(Exercise.id == exercise_id))
            ex_name = ex_row.scalar_one_or_none() or f"Exercise {exercise_id}"
            alerts.append({
                "exercise_id": exercise_id,
                "exercise_name": ex_name,
                "sessions_without_improvement": consecutive_no_improve,
                "last_workout_id": session_stats[0][0] if session_stats else None,
            })

    return {"plateau_alerts": alerts}
