"""Muscle group CRUD - custom hierarchy for exercise targeting."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.muscle_group import MuscleGroup
from app.schemas.muscle_group import MuscleGroupCreate, MuscleGroupRead, MuscleGroupUpdate, MuscleGroupStats

router = APIRouter()


@router.get("", response_model=list[MuscleGroupRead])
async def list_muscle_groups(
    db: AsyncSession = Depends(get_db),
    skip: int = 0,
    limit: int = 200,
):
    """List all muscle groups (for Primary/Secondary/Tertiary linking)."""
    result = await db.execute(
        select(MuscleGroup).order_by(MuscleGroup.name).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


@router.post("", response_model=MuscleGroupRead, status_code=201)
async def create_muscle_group(
    payload: MuscleGroupCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a custom muscle group."""
    existing = await db.execute(select(MuscleGroup).where(MuscleGroup.name == payload.name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Muscle group with this name already exists")
    mg = MuscleGroup(**payload.model_dump())
    db.add(mg)
    await db.flush()
    await db.refresh(mg)
    return mg


@router.get("/{muscle_group_id}", response_model=MuscleGroupRead)
async def get_muscle_group(
    muscle_group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get a single muscle group."""
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")
    return mg


@router.patch("/{muscle_group_id}", response_model=MuscleGroupRead)
async def update_muscle_group(
    muscle_group_id: uuid.UUID,
    payload: MuscleGroupUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a muscle group."""
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(mg, k, v)
    await db.flush()
    await db.refresh(mg)
    return mg


@router.delete("/{muscle_group_id}", status_code=204)
async def delete_muscle_group(
    muscle_group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete a muscle group (exercises' FKs set to NULL)."""
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")
    await db.delete(mg)
    return None


@router.get("/{muscle_group_id}/stats", response_model=MuscleGroupStats)
async def get_muscle_group_stats(
    muscle_group_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Get statistics for a muscle group. Aggregations done in SQL."""
    from app.models.exercise import Exercise
    from app.models.workout import Workout, WorkoutSet
    from sqlalchemy import case, func

    # Verify existence
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")

    # Volume expression: weight*reps if weight > 0 else duration_seconds
    vol_expr = case(
        (WorkoutSet.weight > 0, WorkoutSet.weight * func.coalesce(WorkoutSet.reps, 0)),
        else_=func.coalesce(WorkoutSet.duration_seconds, 0),
    )
    mg_filter = (
        (Exercise.primary_muscle_group_id == muscle_group_id)
        | (Exercise.secondary_muscle_group_id == muscle_group_id)
        | (Exercise.tertiary_muscle_group_id == muscle_group_id)
    )

    # 1) Totals and role distribution in one query
    totals_stmt = (
        select(
            func.count(func.distinct(WorkoutSet.workout_id)).label("total_workouts"),
            func.count(WorkoutSet.id).label("total_sets"),
            func.coalesce(func.sum(vol_expr), 0).label("total_volume"),
            func.sum(case((Exercise.primary_muscle_group_id == muscle_group_id, 1), else_=0)).label("primary_count"),
            func.sum(case((Exercise.secondary_muscle_group_id == muscle_group_id, 1), else_=0)).label("secondary_count"),
            func.sum(case((Exercise.tertiary_muscle_group_id == muscle_group_id, 1), else_=0)).label("tertiary_count"),
        )
        .select_from(WorkoutSet)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(mg_filter)
    )
    tot_row = (await db.execute(totals_stmt)).one_or_none()
    total_workouts = int(tot_row.total_workouts or 0) if tot_row else 0
    total_sets = int(tot_row.total_sets or 0) if tot_row else 0
    total_volume = float(tot_row.total_volume or 0) if tot_row else 0.0
    role_dist = {
        "primary": int(tot_row.primary_count or 0) if tot_row else 0,
        "secondary": int(tot_row.secondary_count or 0) if tot_row else 0,
        "tertiary": int(tot_row.tertiary_count or 0) if tot_row else 0,
    }

    # 2) Volume by date
    history_stmt = (
        select(
            func.date(Workout.started_at).label("d"),
            func.sum(vol_expr).label("vol"),
        )
        .select_from(WorkoutSet)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(mg_filter, Workout.started_at.isnot(None))
        .group_by(func.date(Workout.started_at))
        .order_by(func.date(Workout.started_at))
    )
    history_rows = (await db.execute(history_stmt)).all()
    volume_history = [
        {"date": (r.d.isoformat() if hasattr(r.d, "isoformat") else str(r.d)), "volume": round(float(r.vol or 0), 2)}
        for r in history_rows
    ]

    # 3) Top 10 exercises by volume
    top_stmt = (
        select(
            Exercise.id,
            Exercise.name,
            func.sum(vol_expr).label("vol"),
            func.count(WorkoutSet.id).label("set_count"),
        )
        .select_from(WorkoutSet)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(mg_filter)
        .group_by(Exercise.id, Exercise.name)
        .order_by(func.sum(vol_expr).desc())
        .limit(10)
    )
    top_rows = (await db.execute(top_stmt)).all()
    top_exercises = [
        {"id": r.id, "name": r.name or "", "volume": round(float(r.vol or 0), 2), "set_count": int(r.set_count or 0)}
        for r in top_rows
    ]

    return {
        "id": mg.id,
        "name": mg.name,
        "color": mg.color,
        "total_workouts": total_workouts,
        "total_sets": total_sets,
        "total_volume": round(total_volume, 2),
        "role_distribution": role_dist,
        "volume_history": volume_history,
        "top_exercises": top_exercises,
    }
