"""Add composite index (exercise_id, workout_id) on workout_sets for analytics.

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-02-21

Index added for exercise stats, 1RM, progression, previous-session.
No data is modified or deleted.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        op.f("ix_workout_sets_exercise_workout"),
        "workout_sets",
        ["exercise_id", "workout_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_workout_sets_exercise_workout"), table_name="workout_sets")
