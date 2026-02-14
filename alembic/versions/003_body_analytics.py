"""Body analytics: user_bio + body_logs tables.

Revision ID: 003
Revises: 002
Create Date: 2026-02-14

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # user_bio — singleton profile table
    op.create_table(
        "user_bio",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("height_cm", sa.Float(), nullable=False),
        sa.Column("age", sa.Integer(), nullable=False),
        sa.Column("sex", sa.String(length=10), nullable=False, server_default="male"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    # body_logs — weight + JSONB measurements + pre-computed stats
    op.create_table(
        "body_logs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("weight_kg", sa.Float(), nullable=False),
        sa.Column("body_fat_pct", sa.Float(), nullable=True),
        sa.Column("measurements", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("computed_stats", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user_bio.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Composite index for fast history queries
    op.create_index("ix_body_logs_user_created", "body_logs", ["user_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_body_logs_user_created", table_name="body_logs")
    op.drop_table("body_logs")
    op.drop_table("user_bio")
