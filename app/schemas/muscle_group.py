"""Muscle group schemas."""

from pydantic import BaseModel, ConfigDict, Field


class MuscleGroupBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class MuscleGroupCreate(MuscleGroupBase):
    pass


class MuscleGroupUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)


class MuscleGroupRead(MuscleGroupBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
