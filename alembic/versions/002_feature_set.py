"""Feature set: muscle groups, measurement mode, set labels, PR, templates.

Revision ID: 002
Revises: 001
Create Date: 2025-02-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types first (PostgreSQL requires them to exist before use)
    op.execute("CREATE TYPE measurementmode AS ENUM ('WEIGHT_REPS', 'TIME', 'BODYWEIGHT_REPS')")
    op.execute("CREATE TYPE setlabel AS ENUM ('WARMUP', 'WORKING', 'FAILURE', 'DROP_SET')")
    op.execute("CREATE TYPE prtype AS ENUM ('WEIGHT', 'VOLUME', 'DURATION')")

    # muscle_groups
    op.create_table(
        "muscle_groups",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_muscle_groups_name"), "muscle_groups", ["name"], unique=True)

    # exercises: add new columns, then drop old muscle_group
    op.add_column("exercises", sa.Column("measurement_mode", sa.Enum("WEIGHT_REPS", "TIME", "BODYWEIGHT_REPS", name="measurementmode", create_type=False), nullable=False, server_default="WEIGHT_REPS"))
    op.add_column("exercises", sa.Column("rest_seconds_preset", sa.Integer(), nullable=True))
    op.add_column("exercises", sa.Column("primary_muscle_group_id", sa.Integer(), nullable=True))
    op.add_column("exercises", sa.Column("secondary_muscle_group_id", sa.Integer(), nullable=True))
    op.add_column("exercises", sa.Column("tertiary_muscle_group_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_exercises_primary_muscle_group", "exercises", "muscle_groups", ["primary_muscle_group_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_exercises_secondary_muscle_group", "exercises", "muscle_groups", ["secondary_muscle_group_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_exercises_tertiary_muscle_group", "exercises", "muscle_groups", ["tertiary_muscle_group_id"], ["id"], ondelete="SET NULL")
    op.create_index(op.f("ix_exercises_primary_muscle_group_id"), "exercises", ["primary_muscle_group_id"], unique=False)
    op.create_index(op.f("ix_exercises_secondary_muscle_group_id"), "exercises", ["secondary_muscle_group_id"], unique=False)
    op.create_index(op.f("ix_exercises_tertiary_muscle_group_id"), "exercises", ["tertiary_muscle_group_id"], unique=False)
    op.drop_index("ix_exercises_muscle_group", table_name="exercises")
    op.drop_column("exercises", "muscle_group")

    # workouts: duration_seconds
    op.add_column("workouts", sa.Column("duration_seconds", sa.Integer(), nullable=True))

    # workout_sets: set_label, is_pr, pr_type
    op.add_column("workout_sets", sa.Column("set_label", sa.Enum("WARMUP", "WORKING", "FAILURE", "DROP_SET", name="setlabel", create_type=False), nullable=True))
    op.add_column("workout_sets", sa.Column("is_pr", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("workout_sets", sa.Column("pr_type", sa.Enum("WEIGHT", "VOLUME", "DURATION", name="prtype", create_type=False), nullable=True))

    # workout_templates
    op.create_table(
        "workout_templates",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workout_templates_name"), "workout_templates", ["name"], unique=False)

    # template_exercises
    op.create_table(
        "template_exercises",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("exercise_id", sa.Integer(), nullable=False),
        sa.Column("order_in_template", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["exercise_id"], ["exercises.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["workout_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("template_exercises")
    op.drop_index(op.f("ix_workout_templates_name"), table_name="workout_templates")
    op.drop_table("workout_templates")
    op.drop_column("workout_sets", "pr_type")
    op.drop_column("workout_sets", "is_pr")
    op.drop_column("workout_sets", "set_label")
    op.drop_column("workouts", "duration_seconds")
    op.add_column("exercises", sa.Column("muscle_group", sa.String(length=100), nullable=True))
    op.create_index("ix_exercises_muscle_group", "exercises", ["muscle_group"], unique=False)
    op.drop_index(op.f("ix_exercises_tertiary_muscle_group_id"), table_name="exercises")
    op.drop_index(op.f("ix_exercises_secondary_muscle_group_id"), table_name="exercises")
    op.drop_index(op.f("ix_exercises_primary_muscle_group_id"), table_name="exercises")
    op.drop_constraint("fk_exercises_tertiary_muscle_group", "exercises", type_="foreignkey")
    op.drop_constraint("fk_exercises_secondary_muscle_group", "exercises", type_="foreignkey")
    op.drop_constraint("fk_exercises_primary_muscle_group", "exercises", type_="foreignkey")
    op.drop_column("exercises", "tertiary_muscle_group_id")
    op.drop_column("exercises", "secondary_muscle_group_id")
    op.drop_column("exercises", "primary_muscle_group_id")
    op.drop_column("exercises", "rest_seconds_preset")
    op.drop_column("exercises", "measurement_mode")
    op.drop_index(op.f("ix_muscle_groups_name"), table_name="muscle_groups")
    op.drop_table("muscle_groups")
    op.execute("DROP TYPE IF EXISTS prtype")
    op.execute("DROP TYPE IF EXISTS setlabel")
    op.execute("DROP TYPE IF EXISTS measurementmode")
