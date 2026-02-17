"""Add time_under_tension_seconds and rest_seconds_after to workout_sets

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-02-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b2c3d4e5f6a7"
down_revision: Union[str, None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "workout_sets",
        sa.Column("time_under_tension_seconds", sa.Integer(), nullable=True),
    )
    op.add_column(
        "workout_sets",
        sa.Column("rest_seconds_after", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("workout_sets", "rest_seconds_after")
    op.drop_column("workout_sets", "time_under_tension_seconds")
