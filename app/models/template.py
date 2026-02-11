"""Workout template - save and reload workout structure."""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class WorkoutTemplate(Base):
    """Saved workout structure (name + list of exercises in order)."""

    __tablename__ = "workout_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
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

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("workout_templates.id", ondelete="CASCADE"), nullable=False
    )
    exercise_id: Mapped[int] = mapped_column(
        ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False
    )
    order_in_template: Mapped[int] = mapped_column(Integer, default=0)

    template: Mapped["WorkoutTemplate"] = relationship("WorkoutTemplate", back_populates="exercises")
    exercise: Mapped["Exercise"] = relationship("Exercise", back_populates="template_entries")

