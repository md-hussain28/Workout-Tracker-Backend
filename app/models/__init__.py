"""ORM models - import all so Base.metadata is complete for migrations."""

from app.models.body_log import BodyLog
from app.models.exercise import Exercise
from app.models.muscle_group import MuscleGroup
from app.models.template import TemplateExercise, WorkoutTemplate
from app.models.user_bio import UserBio
from app.models.workout import Workout, WorkoutSet

__all__ = [
    "BodyLog",
    "Exercise",
    "MuscleGroup",
    "UserBio",
    "Workout",
    "WorkoutSet",
    "WorkoutTemplate",
    "TemplateExercise",
]
