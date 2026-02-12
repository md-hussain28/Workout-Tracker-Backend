"""Workout and WorkoutSet schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import PRType, SetLabel


class WorkoutSetBase(BaseModel):
    exercise_id: int
    set_order: int = 0
    weight: float | None = None
    reps: int | None = None
    duration_seconds: int | None = None
    notes: str | None = None
    set_label: SetLabel | None = None


class WorkoutSetCreate(WorkoutSetBase):
    pass


class WorkoutSetUpdate(BaseModel):
    weight: float | None = None
    reps: int | None = None
    duration_seconds: int | None = None
    notes: str | None = None
    set_label: SetLabel | None = None


class WorkoutSetRead(WorkoutSetBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    workout_id: int
    is_pr: bool = False
    pr_type: PRType | None = None


class WorkoutBase(BaseModel):
    notes: str | None = None


class WorkoutCreate(WorkoutBase):
    pass


class WorkoutUpdate(BaseModel):
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    notes: str | None = None


class WorkoutRead(WorkoutBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    sets: list[WorkoutSetRead] = []


class WorkoutReadWithSets(WorkoutRead):
    """Workout with nested sets (for detail view)."""

    sets: list[WorkoutSetRead] = []
