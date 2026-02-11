"""Shared enums for models and API."""

from enum import Enum


class MeasurementMode(str, Enum):
    """How an exercise is measured."""

    WEIGHT_REPS = "weight_reps"  # Weight & Reps
    TIME = "time"  # Time-based (e.g. Planks)
    BODYWEIGHT_REPS = "bodyweight_reps"  # Bodyweight/Reps only


class SetLabel(str, Enum):
    """Smart set labeling."""

    WARMUP = "warmup"
    WORKING = "working"
    FAILURE = "failure"
    DROP_SET = "drop_set"


class PRType(str, Enum):
    """Type of personal record."""

    WEIGHT = "weight"  # Heaviest weight
    VOLUME = "volume"  # Highest volume (weight × reps)
    DURATION = "duration"  # Longest duration
