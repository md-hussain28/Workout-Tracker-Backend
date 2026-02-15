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
    """Get statistics for a muscle group."""
    from app.models.exercise import Exercise
    from app.models.workout import Workout, WorkoutSet
    from sqlalchemy import func, case, desc

    # Verify existence
    result = await db.execute(select(MuscleGroup).where(MuscleGroup.id == muscle_group_id))
    mg = result.scalar_one_or_none()
    if not mg:
        raise HTTPException(status_code=404, detail="Muscle group not found")

    # Base query: Sets using exercises that involve this muscle group
    stmt = (
        select(WorkoutSet, Exercise, Workout.started_at)
        .join(Exercise, Exercise.id == WorkoutSet.exercise_id)
        .join(Workout, Workout.id == WorkoutSet.workout_id)
        .where(
            (Exercise.primary_muscle_group_id == muscle_group_id)
            | (Exercise.secondary_muscle_group_id == muscle_group_id)
            | (Exercise.tertiary_muscle_group_id == muscle_group_id)
        )
    )
    result = await db.execute(stmt)
    rows = result.all()

    total_workouts = set()
    total_sets = 0
    total_volume = 0.0
    role_dist = {"primary": 0, "secondary": 0, "tertiary": 0}
    volume_by_date = {}
    exercises_stats = {}

    for s, ex, started_at in rows:
        weight = float(s.weight or 0)
        reps = float(s.reps or 0)
        duration = float(s.duration_seconds or 0)
        
        # Calculate volume for this set
        # Using simple weight * reps or duration as volume proxy
        vol = (weight * reps) if weight > 0 else duration

        total_workouts.add(s.workout_id)
        total_sets += 1
        total_volume += vol

        # Role
        if ex.primary_muscle_group_id == muscle_group_id:
            role_dist["primary"] += 1
        elif ex.secondary_muscle_group_id == muscle_group_id:
            role_dist["secondary"] += 1
        elif ex.tertiary_muscle_group_id == muscle_group_id:
            role_dist["tertiary"] += 1

        # History
        date_str = started_at.isoformat().split("T")[0]
        volume_by_date[date_str] = volume_by_date.get(date_str, 0) + vol

        # Top Exercises
        if ex.id not in exercises_stats:
            exercises_stats[ex.id] = {"name": ex.name, "volume": 0.0, "set_count": 0}
        exercises_stats[ex.id]["volume"] += vol
        exercises_stats[ex.id]["set_count"] += 1

    # Format response
    volume_history = [
        {"date": d, "volume": round(v, 2)} 
        for d, v in sorted(volume_by_date.items())
    ]
    
    top_exercises = [
        {"id": eid, "name": stat["name"], "volume": round(stat["volume"], 2), "set_count": stat["set_count"]}
        for eid, stat in exercises_stats.items()
    ]
    top_exercises.sort(key=lambda x: x["volume"], reverse=True)

    return {
        "id": mg.id,
        "name": mg.name,
        "color": mg.color,
        "total_workouts": len(total_workouts),
        "total_sets": total_sets,
        "total_volume": round(total_volume, 2),
        "role_distribution": role_dist,
        "volume_history": volume_history,
        "top_exercises": top_exercises[:10],  # Top 10
    }
