"""Workout and WorkoutSet models."""

from __future__ import annotations

from datetime import datetime, timezone
from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
import uuid

from app.core.enums import PRType, SetLabel
from app.db.base import Base


class Workout(Base):
    """A single workout session with optional duration (logged on completion)."""

    __tablename__ = "workouts"
    __table_args__ = (Index("ix_workouts_started_at", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # Total session duration
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    intensity: Mapped[str | None] = mapped_column(String(20), nullable=True)  # light, moderate, vigorous

    sets: Mapped[list["WorkoutSet"]] = relationship(
        "WorkoutSet", back_populates="workout", cascade="all, delete-orphan"
    )


class WorkoutSet(Base):
    """One set: weight/reps/duration, optional label (warmup/failure/drop_set) and PR flags.
    Optional time under tension and rest after set for better calorie estimation."""

    __tablename__ = "workout_sets"
    __table_args__ = (
        Index("ix_workout_sets_workout_id", "workout_id"),
        Index("ix_workout_sets_exercise_id", "exercise_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workout_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workouts.id", ondelete="CASCADE"), nullable=False)
    exercise_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("exercises.id", ondelete="CASCADE"), nullable=False)
    set_order: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    reps: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Optional: for better calorie estimation (seconds)
    time_under_tension_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)  # TUT per set
    rest_seconds_after: Mapped[int | None] = mapped_column(Integer, nullable=True)  # rest after this set

    set_label: Mapped[SetLabel | None] = mapped_column(Enum(SetLabel), nullable=True)  # warmup, working, failure, drop_set
    is_pr: Mapped[bool] = mapped_column(default=False, nullable=False)
    pr_type: Mapped[PRType | None] = mapped_column(Enum(PRType), nullable=True)  # weight, volume, duration

    workout: Mapped["Workout"] = relationship("Workout", back_populates="sets")
    exercise: Mapped["Exercise"] = relationship("Exercise", back_populates="workout_sets")
