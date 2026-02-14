"""Workout template - save and reload workout structure."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.db.base import Base


class WorkoutTemplate(Base):
    """Saved workout structure (name + list of exercises in order)."""

    __tablename__ = "workout_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)

    exercises: Mapped[list["TemplateExercise"]] = relationship(
        "TemplateExercise",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="TemplateExercise.order_in_template",
    )


class TemplateExercise(Base):
    """Exercise in a template (order only; sets are added during the live workout)."""

    __tablename__ = "template_exercises"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workout_templates.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )
    order_in_template: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped["WorkoutTemplate"] = relationship("WorkoutTemplate", back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship("Exercise", back_populates="template_entries")
