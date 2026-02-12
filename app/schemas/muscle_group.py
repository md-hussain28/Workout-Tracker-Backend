"""Muscle group schemas."""

from pydantic import BaseModel, ConfigDict, Field


class MuscleGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    color: str | None = Field(None, max_length=7)


class MuscleGroupCreate(MuscleGroupBase):
    pass


class MuscleGroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    color: str | None = Field(None, max_length=7)


class MuscleGroupRead(MuscleGroupBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


class MuscleGroupChartPoint(BaseModel):
    date: str
    volume: float


class MuscleGroupTopExercise(BaseModel):
    id: int
    name: string
    volume: float
    set_count: int


class MuscleGroupRoleDistribution(BaseModel):
    primary: int
    secondary: int
    tertiary: int


class MuscleGroupStats(BaseModel):
    id: int
    name: str
    color: str | None = None
    total_workouts: int
    total_sets: int
    total_volume: float
    role_distribution: MuscleGroupRoleDistribution
    volume_history: list[MuscleGroupChartPoint]
    top_exercises: list[MuscleGroupTopExercise]
