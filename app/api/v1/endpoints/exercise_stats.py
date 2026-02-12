"""Exercise statistics endpoint – detailed stats for a single exercise."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select, case
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.session import get_db
from app.models.exercise import Exercise
from app.models.workout import Workout, WorkoutSet

router = APIRouter()


def _brzycki_1rm(weight: float, reps: int) -> float:
    if reps <= 0:
        return 0.0
    if reps >= 37:
        return weight * 1.1
    return weight * (36 / (37 - reps))


@router.get("/{exercise_id}/stats")
async def exercise_stats(
    exercise_id: int,
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

        # Basic counts
        count_result = await db.execute(
            select(
                func.count(WorkoutSet.id).label("total_sets"),
                func.count(func.distinct(WorkoutSet.workout_id)).label("total_workouts"),
            ).where(WorkoutSet.exercise_id == exercise_id)
        )
        counts = count_result.first()
        total_sets = (counts.total_sets if counts else 0) or 0
        total_workouts = (counts.total_workouts if counts else 0) or 0

        # First and last performed dates
        date_result = await db.execute(
            select(
                func.min(Workout.started_at).label("first"),
                func.max(Workout.started_at).label("last"),
            )
            .join(WorkoutSet, WorkoutSet.workout_id == Workout.id)
            .where(WorkoutSet.exercise_id == exercise_id)
        )
        dates = date_result.first()
        first_performed = dates.first.isoformat() if dates and dates.first else None
        last_performed = dates.last.isoformat() if dates and dates.last else None

        # PRs
        pr_result = await db.execute(
            select(
                func.max(WorkoutSet.weight).label("best_weight"),
                func.max(WorkoutSet.reps).label("best_reps"),
                func.max(WorkoutSet.duration_seconds).label("best_duration"),
            ).where(WorkoutSet.exercise_id == exercise_id)
        )
        prs = pr_result.first()
        best_weight = float(prs.best_weight) if prs and prs.best_weight is not None else None
        best_reps = int(prs.best_reps) if prs and prs.best_reps is not None else None
        best_duration = int(prs.best_duration) if prs and prs.best_duration is not None else None

        # Best volume (weight * reps) and best estimated 1RM
        vol_result = await db.execute(
            select(WorkoutSet.weight, WorkoutSet.reps)
            .where(
                WorkoutSet.exercise_id == exercise_id,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None),
            )
        )
        best_volume = 0.0
        best_1rm = 0.0
        for row in vol_result.all():
            w = float(row.weight) if row.weight is not None else 0.0
            r = int(row.reps) if row.reps is not None else 0
            # Safety check for crazy values
            if w < 0: w = 0
            if r < 0: r = 0

            vol = w * r
            if vol > best_volume:
                best_volume = vol
            
            est = _brzycki_1rm(w, r)
            if est > best_1rm:
                best_1rm = est

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

        # 1RM progression (per workout, best set)
        progression_result = await db.execute(
            select(Workout.started_at, WorkoutSet.weight, WorkoutSet.reps)
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .where(
                WorkoutSet.exercise_id == exercise_id,
                WorkoutSet.weight.isnot(None),
                WorkoutSet.reps.isnot(None),
            )
            .order_by(Workout.started_at)
        )
        
        progression_by_date: dict[str, float] = {}
        for row in progression_result.all():
            if not row.started_at:
                continue
            d = row.started_at.date().isoformat()
            w = float(row.weight) if row.weight is not None else 0.0
            r = int(row.reps) if row.reps is not None else 0
            
            est = _brzycki_1rm(w, r)
            if est > 0 and (d not in progression_by_date or est > progression_by_date[d]):
                progression_by_date[d] = est
                
        one_rm_progression = [
            {"date": d, "estimated_1rm": round(v, 2)}
            for d, v in progression_by_date.items()
        ]

        # Recent history – last 10 workouts with sets
        recent_workout_ids_result = await db.execute(
            select(func.distinct(WorkoutSet.workout_id))
            .where(WorkoutSet.exercise_id == exercise_id)
            .join(Workout, Workout.id == WorkoutSet.workout_id)
            .order_by(Workout.started_at.desc())
            .limit(10)
        )
        recent_ids = [r[0] for r in recent_workout_ids_result.all() if r[0] is not None]
        recent_history = []
        if recent_ids:
            history_result = await db.execute(
                select(Workout)
                .where(Workout.id.in_(recent_ids))
                .options(selectinload(Workout.sets))
                .order_by(Workout.started_at.desc())
            )
            for workout in history_result.scalars().all():
                ex_sets = [s for s in workout.sets if s.exercise_id == exercise_id]
                recent_history.append({
                    "workout_id": workout.id,
                    "started_at": workout.started_at.isoformat() if workout.started_at else None,
                    "sets": [
                        {
                            "set_order": s.set_order,
                            "weight": float(s.weight) if s.weight is not None else None,
                            "reps": int(s.reps) if s.reps is not None else None,
                            "duration_seconds": int(s.duration_seconds) if s.duration_seconds is not None else None,
                            "set_label": s.set_label.value if s.set_label else None,
                            "is_pr": s.is_pr,
                        }
                        for s in sorted(ex_sets, key=lambda x: x.set_order or 0)
                    ],
                })

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
            "recent_history": recent_history,
        }
    except Exception as e:
        # In case of ANY unforeseen error, log it and return 500 but with a message
        print(f"Error in exercise_stats: {e}") 
        raise HTTPException(status_code=500, detail=f"Failed to calculate stats: {str(e)}")
