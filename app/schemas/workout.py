"""Workout and WorkoutSet schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import PRType, SetLabel

WorkoutIntensity = Literal["light", "moderate", "vigorous"]


class ExerciseRef(BaseModel):
    """Minimal exercise info for embedding in set responses (id + name only)."""

    id: UUID
    name: str

    model_config = ConfigDict(from_attributes=True)


class WorkoutSetBase(BaseModel):
    exercise_id: UUID
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
    id: UUID
    workout_id: UUID
    is_pr: bool = False
    pr_type: PRType | None = None
    exercise: ExerciseRef | None = None


class WorkoutBase(BaseModel):
    notes: str | None = None


class WorkoutCreate(WorkoutBase):
    pass


class WorkoutUpdate(BaseModel):
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    notes: str | None = None
    intensity: WorkoutIntensity | None = None


class WorkoutRead(WorkoutBase):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    started_at: datetime
    ended_at: datetime | None = None
    duration_seconds: int | None = None
    intensity: str | None = None
    sets: list[WorkoutSetRead] = []


class WorkoutReadWithSets(WorkoutRead):
    """Workout with nested sets (for detail view). Includes estimated_calories when computable."""

    estimated_calories: float | None = None
    sets: list[WorkoutSetRead] = []
