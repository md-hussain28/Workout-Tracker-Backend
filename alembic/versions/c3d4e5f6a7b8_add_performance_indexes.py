"""Add performance indexes for faster API queries

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-02-19

Indexes added:
- workouts.started_at (list/filter by date, streak, analytics)
- workout_sets.workout_id (join workouts->sets, consistency)
- workout_sets.exercise_id (exercise stats, PR detection, analytics)
No data is modified or deleted.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_workouts_started_at"),
        "workouts",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workout_sets_workout_id"),
        "workout_sets",
        ["workout_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_workout_sets_exercise_id"),
        "workout_sets",
        ["exercise_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workout_sets_exercise_id"), table_name="workout_sets")
    op.drop_index(op.f("ix_workout_sets_workout_id"), table_name="workout_sets")
    op.drop_index(op.f("ix_workouts_started_at"), table_name="workouts")
