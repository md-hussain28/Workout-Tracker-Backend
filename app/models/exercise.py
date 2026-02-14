"""Exercise model - trackable exercise types with muscle hierarchy and measurement mode."""

from __future__ import annotations

import uuid

from sqlalchemy import Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import MeasurementMode
from app.db.base import Base


class Exercise(Base):
    """Exercise definition with Primary/Secondary/Tertiary muscle groups and measurement mode."""

    __tablename__ = "exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="kg")
    measurement_mode: Mapped[MeasurementMode] = mapped_column(
        Enum(MeasurementMode), default=MeasurementMode.WEIGHT_REPS, nullable=False
    )
    rest_seconds_preset: Mapped[int | None] = mapped_column(nullable=True)  # Rest timer preset

    primary_muscle_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("muscle_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    secondary_muscle_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("muscle_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )
    tertiary_muscle_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("muscle_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )

    primary_muscle_group: Mapped["MuscleGroup | None"] = relationship(
        "MuscleGroup", foreign_keys=[primary_muscle_group_id], back_populates="exercises_primary"
    )
    secondary_muscle_group: Mapped["MuscleGroup | None"] = relationship(
        "MuscleGroup", foreign_keys=[secondary_muscle_group_id], back_populates="exercises_secondary"
    )
    tertiary_muscle_group: Mapped["MuscleGroup | None"] = relationship(
        "MuscleGroup", foreign_keys=[tertiary_muscle_group_id], back_populates="exercises_tertiary"
    )

    workout_sets: Mapped[list["WorkoutSet"]] = relationship(
        "WorkoutSet", back_populates="exercise", cascade="all, delete-orphan"
    )
    template_entries: Mapped[list["TemplateExercise"]] = relationship(
        "TemplateExercise", back_populates="exercise", cascade="all, delete-orphan"
    )
