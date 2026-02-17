"""Calorie estimation for workouts.

Current approach: MET-based formula (2024 Compendium). When the user does not
report intensity (light/moderate/vigorous), we infer it from workout volume
(tonnage) and duration so no extra input is required.

Other approaches and data needed (for reference):
- Work-based (tonnage): Use total weight×reps + duration + body weight.
  Data: already have it (sets, duration, body weight). Implemented as inferred intensity.
- Heart rate: HR during workout + age, sex, weight, resting/max HR.
  Data: HR device or manual entry, user profile (age, sex, weight, optional HR stats).
- VO2 / wearables: Device-estimated EE (e.g. Apple Watch, Garmin).
  Data: Integration with wearable API or manual entry.
"""

from __future__ import annotations

# MET values from 2024 Adult Compendium of Physical Activities (Conditioning / Resistance).
MET_LIGHT = 3.5    # Resistance training, multiple exercises, 8–15 reps
MET_MODERATE = 5.0  # Health club / gym, squats, deadlift
MET_VIGOROUS = 6.0  # Free weights, powerlifting, bodybuilding

DEFAULT_MET = MET_MODERATE
MINUTES_PER_SET_ESTIMATE = 2.5  # Work + rest per set when duration unknown

# Tonnage (kg per minute) thresholds to infer intensity when user doesn't report it.
# Below low = light; between low and high = moderate; above high = vigorous.
TONNAGE_PER_MIN_LIGHT_MAX = 80.0   # < 80 kg/min → light
TONNAGE_PER_MIN_VIGOROUS_MIN = 200.0  # >= 200 kg/min → vigorous

# When TUT + rest are provided: MET for time-under-tension (active lifting) and for rest between sets.
MET_ACTIVE_LIFTING = 5.5   # Actual work phase (between moderate and vigorous)
MET_REST_BETWEEN_SETS = 2.0  # Light standing / recovery between sets


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


def infer_intensity_from_tonnage(tonnage_kg: float, duration_minutes: float) -> str:
    """
    Infer light/moderate/vigorous from work density (tonnage per minute).
    Uses no user input; only workout data.
    """
    if duration_minutes <= 0 or tonnage_kg <= 0:
        return "moderate"
    kg_per_min = tonnage_kg / duration_minutes
    if kg_per_min < TONNAGE_PER_MIN_LIGHT_MAX:
        return "light"
    if kg_per_min >= TONNAGE_PER_MIN_VIGOROUS_MIN:
        return "vigorous"
    return "moderate"


def estimate_calories(
    weight_kg: float,
    duration_minutes: float,
    intensity: str | None = None,
    tonnage_kg: float | None = None,
    active_seconds: float | None = None,
    rest_seconds: float | None = None,
) -> float:
    """
    Estimate calories burned.

    Best accuracy when time-under-tension and rest are provided per set:
    - active_seconds: sum of TUT for all sets (actual work time).
    - rest_seconds: sum of rest_seconds_after for all sets.
    Uses MET_ACTIVE_LIFTING for active time and MET_REST_BETWEEN_SETS for rest.

    Otherwise uses MET formula with duration: (MET × 3.5 × weight_kg / 200) × duration_minutes.
    If intensity is not provided, it is inferred from tonnage and duration.
    """
    if weight_kg <= 0:
        return 0.0
    base = 3.5 * weight_kg / 200

    # Prefer TUT + rest when both are present and positive (better estimate)
    if (
        active_seconds is not None
        and rest_seconds is not None
        and (active_seconds > 0 or rest_seconds > 0)
    ):
        active_min = max(0.0, active_seconds) / 60.0
        rest_min = max(0.0, rest_seconds) / 60.0
        kcal_active = MET_ACTIVE_LIFTING * base * active_min
        kcal_rest = MET_REST_BETWEEN_SETS * base * rest_min
        return round(kcal_active + kcal_rest, 1)

    if duration_minutes <= 0:
        return 0.0
    if intensity is None and tonnage_kg is not None and tonnage_kg > 0:
        intensity = infer_intensity_from_tonnage(tonnage_kg, duration_minutes)
    met = get_met_for_intensity(intensity)
    return round(met * base * duration_minutes, 1)


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
