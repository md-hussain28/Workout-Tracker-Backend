"""Muscle group model - custom hierarchy for exercises."""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class MuscleGroup(Base):
    """Custom muscle group (e.g. Chest, Quads). Exercises link via Primary/Secondary/Tertiary."""

    __tablename__ = "muscle_groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)

    # Exercises that target this as primary / secondary / tertiary
    exercises_primary: Mapped[list["Exercise"]] = relationship(
        "Exercise",
        foreign_keys="Exercise.primary_muscle_group_id",
        back_populates="primary_muscle_group",
    )
    exercises_secondary: Mapped[list["Exercise"]] = relationship(
        "Exercise",
        foreign_keys="Exercise.secondary_muscle_group_id",
        back_populates="secondary_muscle_group",
    )
    exercises_tertiary: Mapped[list["Exercise"]] = relationship(
        "Exercise",
        foreign_keys="Exercise.tertiary_muscle_group_id",
        back_populates="tertiary_muscle_group",
    )
