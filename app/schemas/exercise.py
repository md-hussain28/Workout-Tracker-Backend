"""Exercise schemas."""

from pydantic import BaseModel, ConfigDict, Field

from app.core.enums import MeasurementMode
from app.schemas.muscle_group import MuscleGroupRead


class ExerciseBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    unit: str = Field(default="kg", max_length=20)
    measurement_mode: MeasurementMode = MeasurementMode.WEIGHT_REPS
    rest_seconds_preset: int | None = None
    primary_muscle_group_id: int | None = None
    secondary_muscle_group_id: int | None = None
    tertiary_muscle_group_id: int | None = None


class ExerciseCreate(ExerciseBase):
    pass


class ExerciseUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    unit: str | None = None
    measurement_mode: MeasurementMode | None = None
    rest_seconds_preset: int | None = None
    primary_muscle_group_id: int | None = None
    secondary_muscle_group_id: int | None = None
    tertiary_muscle_group_id: int | None = None


class ExerciseRead(ExerciseBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    primary_muscle_group: MuscleGroupRead | None = None
    secondary_muscle_group: MuscleGroupRead | None = None
    tertiary_muscle_group: MuscleGroupRead | None = None
