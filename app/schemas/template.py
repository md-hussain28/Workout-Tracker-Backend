"""Workout template schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.exercise import ExerciseRead


class TemplateExerciseBase(BaseModel):
    exercise_id: int
    order_in_template: int = 0


class TemplateExerciseCreate(TemplateExerciseBase):
    pass


class TemplateExerciseRead(TemplateExerciseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    template_id: int
    exercise: ExerciseRead | None = None


class WorkoutTemplateBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class WorkoutTemplateCreate(WorkoutTemplateBase):
    pass


class WorkoutTemplateUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)


class WorkoutTemplateRead(WorkoutTemplateBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime
    exercises: list[TemplateExerciseRead] = []


class WorkoutTemplateCreateFromWorkout(BaseModel):
    """Create a template from an existing workout (workout_id + name)."""
    name: str = Field(..., min_length=1, max_length=255)
    workout_id: int
