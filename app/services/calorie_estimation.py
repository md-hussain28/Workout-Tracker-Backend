"""Calorie estimation for workouts using MET-based formula (2024 Compendium)."""

from __future__ import annotations

# MET values from 2024 Adult Compendium of Physical Activities (Conditioning / Resistance).
MET_LIGHT = 3.5    # Resistance training, multiple exercises, 8–15 reps
MET_MODERATE = 5.0  # Health club / gym, squats, deadlift
MET_VIGOROUS = 6.0  # Free weights, powerlifting, bodybuilding

DEFAULT_MET = MET_MODERATE
MINUTES_PER_SET_ESTIMATE = 2.5  # Work + rest per set when duration unknown


def get_met_for_intensity(intensity: str | None) -> float:
    """Map intensity to MET. Default moderate."""
    if not intensity:
        return DEFAULT_MET
    i = (intensity or "").strip().lower()
    if i == "light":
        return MET_LIGHT
    if i == "vigorous":
        return MET_VIGOROUS
    return MET_MODERATE


def estimate_calories(
    weight_kg: float,
    duration_minutes: float,
    intensity: str | None = None,
) -> float:
    """
    Estimate calories burned using MET formula: (MET × 3.5 × weight_kg / 200) × duration_minutes.
    Returns rounded kcal.
    """
    if weight_kg <= 0 or duration_minutes <= 0:
        return 0.0
    met = get_met_for_intensity(intensity)
    kcal_per_min = met * 3.5 * weight_kg / 200
    return round(kcal_per_min * duration_minutes, 1)


def get_active_duration_minutes(
    duration_seconds: int | None,
    sets_count: int,
) -> float:
    """
    Return active duration in minutes.
    Prefer workout.duration_seconds when set; otherwise estimate from number of sets.
    """
    if duration_seconds is not None and duration_seconds > 0:
        return duration_seconds / 60.0
    if sets_count <= 0:
        return 0.0
    return sets_count * MINUTES_PER_SET_ESTIMATE
