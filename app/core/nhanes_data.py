"""NHANES population reference data — hardcoded for O(1) lookups.

Mean and standard deviation values for body circumferences (cm)
by sex. Derived from NHANES 2017-2020 adult population data.
Used to compute population percentiles without any DB queries.
"""

from typing import Tuple, Optional

# ── Population stats: { sex: { measurement_key: (mean_cm, std_cm) } } ──
NHANES_STATS: dict[str, dict[str, Tuple[float, float]]] = {
    "male": {
        "chest":    (103.5, 9.8),
        "waist":    (98.0, 14.2),
        "hips":     (103.8, 9.1),
        "neck":     (39.5, 2.8),
        "shoulder": (119.0, 7.5),
        "bicep":    (33.5, 4.2),
        "forearm":  (28.5, 2.5),
        "thigh":    (56.0, 6.0),
        "calf":     (38.5, 3.5),
        "wrist":    (17.5, 1.2),
        "ankle":    (23.5, 1.8),
    },
    "female": {
        "chest":    (97.0, 11.5),
        "waist":    (92.5, 15.5),
        "hips":     (108.0, 12.0),
        "neck":     (34.5, 2.5),
        "shoulder": (105.0, 7.0),
        "bicep":    (30.0, 4.5),
        "forearm":  (25.0, 2.5),
        "thigh":    (57.5, 7.0),
        "calf":     (37.0, 3.8),
        "wrist":    (15.5, 1.0),
        "ankle":    (22.0, 1.8),
    },
}

# Keys that come in left/right pairs — we average them for percentile lookup
PAIRED_KEYS = {"bicep", "forearm", "thigh", "calf"}


def get_population_stats(sex: str, measurement_key: str) -> Optional[Tuple[float, float]]:
    """Return (mean, std) for a given sex and measurement, or None if unknown."""
    # Normalize: strip _l / _r suffix for paired keys
    base_key = measurement_key.rstrip("_l").rstrip("_r")
    if base_key in PAIRED_KEYS:
        measurement_key = base_key
    return NHANES_STATS.get(sex, {}).get(measurement_key)
