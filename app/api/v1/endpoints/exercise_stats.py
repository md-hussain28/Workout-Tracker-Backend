"""Exercise statistics endpoint – detailed stats for a single exercise."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutSet

router = APIRouter()

# Brzycki 1RM in SQL: weight * 36/(37-reps), or weight*1.1 for reps>=37
def _brzycki_1rm_expr(weight_col, reps_col):
    return case(
        (reps_col >= 37, weight_col * 1.1),
        else_=weight_col * 36.0 / func.nullif(37 - reps_col, 0),
    )


def _brzycki_1rm(weight: float, reps: int) -> float:
    if reps <= 0:
        return 0.0
    if reps >= 37:
        return weight * 1.1
    return weight * (36 / (37 - reps))


@router.get("/{exercise_id}/stats")
async def exercise_stats(
    exercise_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Detailed stats for a single exercise:
    - total_sets, total_workouts, first/last performed
    - PRs (best weight, best volume, best estimated 1RM)
    - set label distribution
    - 1RM progression points
    - recent history (last 10 workouts with sets)
    """
    try:
        # Verify exercise exists
        ex_result = await db.execute(select(Exercise).where(Exercise.id == exercise_id))
        exercise = ex_result.scalar_one_or_none()
        if not exercise:
            raise HTTPException(status_code=404, detail="Exercise not found")

        # Single combined query: counts, first/last dates, and all PRs (including best_volume, best_1rm in SQL)
        agg = await db.execute(
            select(
                func.count(WorkoutSet.id).label("total_sets"),
                func.count(func.distinct(WorkoutSet.workout_id)).label("total_workouts"),
                func.min(Workout.started_at).label("first"),
                func.max(Workout.started_at).label("last"),
                func.max(WorkoutSet.weight).label("best_weight"),
                func.max(WorkoutSet.reps).label("best_reps"),
                func.max(WorkoutSet.duration_seconds).label("best_duration"),
                func.max(WorkoutSet.weight * WorkoutSet.reps).label("best_volume"),
                func.max(_brzycki_1rm_expr(WorkoutSet.weight, WorkoutSet.reps)).label("best_1rm"),
            )
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(WorkoutSet.exercise_id == exercise_id)
        )
        row = agg.one_or_none()
        total_sets = int(row.total_sets or 0) if row else 0
        total_workouts = int(row.total_workouts or 0) if row else 0
        first_performed = row.first.isoformat() if row and row.first else None
        last_performed = row.last.isoformat() if row and row.last else None
        best_weight = float(row.best_weight) if row and row.best_weight is not None else None
        best_reps = int(row.best_reps) if row and row.best_reps is not None else None
        best_duration = int(row.best_duration) if row and row.best_duration is not None else None
        best_volume = float(row.best_volume) if row and row.best_volume is not None else 0.0
        best_1rm = float(row.best_1rm) if row and row.best_1rm is not None else 0.0

        # Set label distribution
        label_result = await db.execute(
            select(
                WorkoutSet.set_label,
                func.count(WorkoutSet.id).label("cnt"),
            )
            .where(WorkoutSet.exercise_id == exercise_id)
            .group_by(WorkoutSet.set_label)
        )
        set_label_distribution = [
            {"label": row.set_label.value if row.set_label else "unlabeled", "count": row.cnt}
            for row in label_result.all()
        ]

        # Daily progression in one query: group by date, aggregate 1rm/volume/weight/sets/reps
        progression_result = await db.execute(
            select(
                func.date(Workout.started_at).label("d"),
                func.max(_brzycki_1rm_expr(WorkoutSet.weight, WorkoutSet.reps)).label("best_1rm"),
                func.sum(WorkoutSet.weight * WorkoutSet.reps).label("volume"),
                func.max(WorkoutSet.weight).label("max_weight"),
                func.count(WorkoutSet.id).label("sets_count"),
                func.sum(WorkoutSet.reps).label("total_reps"),
            )
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(
                WorkoutSet.exercise_id == exercise_id,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None),
            )
            .group_by(func.date(Workout.started_at))
            .order_by(func.date(Workout.started_at))
        )
        daily_rows = progression_result.all()

        one_rm_progression = [
            {"date": (r.d.isoformat() if hasattr(r.d, "isoformat") else str(r.d)), "estimated_1rm": round(float(r.best_1rm or 0), 2)}
            for r in daily_rows if r.best_1rm and float(r.best_1rm) > 0
        ]
        volume_history = [
            {"date": (r.d.isoformat() if hasattr(r.d, "isoformat") else str(r.d)), "volume": round(float(r.volume or 0), 2)}
            for r in daily_rows if r.volume and float(r.volume) > 0
        ]
        max_weight_history = [
            {"date": (r.d.isoformat() if hasattr(r.d, "isoformat") else str(r.d)), "weight": float(r.max_weight or 0)}
            for r in daily_rows if r.max_weight and float(r.max_weight) > 0
        ]
        sets_reps_history = [
            {
                "date": r.d.isoformat() if hasattr(r.d, "isoformat") else str(r.d),
                "sets": int(r.sets_count or 0),
                "reps": int(r.total_reps or 0),
            }
            for r in daily_rows
        ]

        # Recent history – one query: subquery for last 10 workout IDs, then their sets for this exercise
        recent_ids_subq = (
            select(WorkoutSet.workout_id)
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(WorkoutSet.exercise_id == exercise_id)
            .group_by(WorkoutSet.workout_id)
            .order_by(func.max(Workout.started_at).desc())
            .limit(10)
            .subquery()
        )
        sets_result = await db.execute(
            select(WorkoutSet)
            .where(
                WorkoutSet.workout_id.in_(recent_ids_subq),
                WorkoutSet.exercise_id == exercise_id,
            )
            .options(selectinload(WorkoutSet.workout))
            .order_by(WorkoutSet.set_order)
        )
        sets_list = sets_result.scalars().all()
        by_workout: dict = {}
        for s in sets_list:
            wid = s.workout_id
            if wid not in by_workout:
                by_workout[wid] = {"workout_id": wid, "started_at": s.workout.started_at.isoformat() if s.workout and s.workout.started_at else None, "sets": []}
            by_workout[wid]["sets"].append({
                "set_order": s.set_order,
                "weight": float(s.weight) if s.weight is not None else None,
                "reps": int(s.reps) if s.reps is not None else None,
                "duration_seconds": int(s.duration_seconds) if s.duration_seconds is not None else None,
                "set_label": s.set_label.value if s.set_label else None,
                "is_pr": s.is_pr,
            })
        recent_history = sorted(
            by_workout.values(),
            key=lambda x: x["started_at"] or "",
            reverse=True,
        )

        return {
            "exercise_id": exercise_id,
            "total_sets": total_sets,
            "total_workouts": total_workouts,
            "first_performed": first_performed,
            "last_performed": last_performed,
            "prs": {
                "best_weight": best_weight,
                "best_reps": best_reps,
                "best_volume": round(best_volume, 2) if best_volume else None,
                "best_1rm": round(best_1rm, 2) if best_1rm else None,
                "best_duration": best_duration,
            },
            "set_label_distribution": set_label_distribution,
            "one_rm_progression": one_rm_progression,
            "volume_history": volume_history,
            "max_weight_history": max_weight_history,
            "sets_reps_history": sets_reps_history,
            "recent_history": recent_history,
        }
    except Exception as e:
        # In case of ANY unforeseen error, log it and return 500 but with a message
        print(f"Error in exercise_stats: {e}") 
        raise HTTPException(status_code=500, detail=f"Failed to calculate stats: {str(e)}")
