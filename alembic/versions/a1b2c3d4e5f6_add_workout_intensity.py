"""Add workout intensity for calorie estimation

Revision ID: a1b2c3d4e5f6
Revises: 107d3ff34357
Create Date: 2026-02-16

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, None] = "107d3ff34357"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("workouts", sa.Column("intensity", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("workouts", "intensity")
