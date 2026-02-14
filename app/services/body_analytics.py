"""Body analytics calculation service.

All heavy math runs at POST time — results are cached in the DB record.
Uses math.erf for percentile calculation (no scipy dependency).
"""

from __future__ import annotations

import math
from typing import Any, Optional

from app.core.nhanes_data import NHANES_STATS, PAIRED_KEYS, get_population_stats


# ── Percentile helpers (scipy-free) ──────────────────────────────────────

def _z_to_percentile(z: float) -> float:
    """Convert a Z-score to a percentile using the error function."""
    return round(0.5 * (1 + math.erf(z / math.sqrt(2))) * 100, 1)


def _compute_percentile(value: float, mean: float, std: float) -> float:
    """Compute the population percentile for a single measurement."""
    if std <= 0:
        return 50.0
    z = (value - mean) / std
    return _z_to_percentile(z)


# ── Core formulas ────────────────────────────────────────────────────────

def calc_bmr(weight_kg: float, height_cm: float, age: int, sex: str) -> float:
    """Mifflin-St Jeor BMR equation (kcal/day)."""
    base = 10 * weight_kg + 6.25 * height_cm - 5 * age
    return round(base + 5 if sex == "male" else base - 161, 1)


def calc_navy_bf(
    sex: str,
    height_cm: float,
    waist_cm: float,
    neck_cm: float,
    hips_cm: Optional[float] = None,
) -> Optional[float]:
    """U.S. Navy body fat % formula. Returns None if inputs missing."""
    if waist_cm is None or neck_cm is None or waist_cm <= neck_cm:
        return None
    try:
        if sex == "male":
            bf = (
                86.010 * math.log10(waist_cm - neck_cm)
                - 70.041 * math.log10(height_cm)
                + 36.76
            )
        else:
            if hips_cm is None:
                return None
            bf = (
                163.205 * math.log10(waist_cm + hips_cm - neck_cm)
                - 97.684 * math.log10(height_cm)
                - 78.387
            )
        return round(max(bf, 2.0), 1)  # clamp floor at 2%
    except (ValueError, ZeroDivisionError):
        return None


def calc_ffmi(weight_kg: float, height_cm: float, body_fat_pct: Optional[float]) -> Optional[float]:
    """Fat-Free Mass Index = lean_mass / height_m^2 + 6.1*(1.8 - height_m)."""
    if body_fat_pct is None or height_cm <= 0:
        return None
    height_m = height_cm / 100
    lean_mass = weight_kg * (1 - body_fat_pct / 100)
    raw_ffmi = lean_mass / (height_m ** 2)
    # Normalized FFMI adjusts for height
    adjusted = raw_ffmi + 6.1 * (1.8 - height_m)
    return round(adjusted, 1)


# ── Symmetry ─────────────────────────────────────────────────────────────

def calc_symmetry(measurements: dict[str, float]) -> dict[str, Any]:
    """Compare left/right pairs. Returns ratio and delta for each pair."""
    result: dict[str, Any] = {}
    for key in PAIRED_KEYS:
        left = measurements.get(f"{key}_l")
        right = measurements.get(f"{key}_r")
        if left is not None and right is not None and max(left, right) > 0:
            ratio = round(min(left, right) / max(left, right) * 100, 1)
            result[key] = {
                "left": left,
                "right": right,
                "ratio": ratio,
                "delta": round(abs(left - right), 1),
            }
    return result


# ── Percentiles ──────────────────────────────────────────────────────────

def calc_percentiles(
    sex: str, measurements: dict[str, float]
) -> dict[str, float]:
    """Compute population percentile for each measurement.

    For paired keys (bicep_l, bicep_r), average them and look up the base key.
    """
    percentiles: dict[str, float] = {}
    processed_pairs: set[str] = set()

    for key, value in measurements.items():
        # Determine the base key for lookup
        base = key
        for pair_key in PAIRED_KEYS:
            if key.startswith(pair_key):
                base = pair_key
                break

        if base in PAIRED_KEYS:
            if base in processed_pairs:
                continue
            # Average left + right if both present
            left = measurements.get(f"{base}_l")
            right = measurements.get(f"{base}_r")
            if left is not None and right is not None:
                avg_val = (left + right) / 2
            else:
                avg_val = left or right or value
            processed_pairs.add(base)
            stats = get_population_stats(sex, base)
            if stats:
                percentiles[base] = _compute_percentile(avg_val, *stats)
        else:
            stats = get_population_stats(sex, key)
            if stats:
                percentiles[key] = _compute_percentile(value, *stats)

    return percentiles


def calc_aesthetic_rank(percentiles: dict[str, float], measurements: dict[str, float]) -> Optional[float]:
    """Composite aesthetic ranking based on key proportions.

    Factors: shoulder-to-waist ratio, chest percentile, V-taper.
    Returns a "Top X%" value (lower is better).
    """
    if not percentiles:
        return None

    scores: list[float] = []

    # Shoulder / waist ratio bonus
    shoulder = measurements.get("shoulder")
    waist = measurements.get("waist")
    if shoulder and waist and waist > 0:
        sw_ratio = shoulder / waist
        # Ideal male ~1.618 (golden ratio); score as percentile
        ratio_score = min(sw_ratio / 1.618 * 100, 100)
        scores.append(ratio_score)

    # Key muscle percentiles (higher = better)
    for key in ("chest", "shoulder", "bicep", "thigh", "calf"):
        if key in percentiles:
            scores.append(percentiles[key])

    # Waist — lower percentile is better aesthetically
    if "waist" in percentiles:
        scores.append(100 - percentiles["waist"])

    if not scores:
        return None

    avg_score = sum(scores) / len(scores)
    # Convert to "Top X%" — 100th percentile = Top 0%
    rank = round(max(100 - avg_score, 1), 0)
    return rank


# ── Master compute function ─────────────────────────────────────────────

def compute_all_stats(
    weight_kg: float,
    height_cm: float,
    age: int,
    sex: str,
    measurements: Optional[dict[str, float]] = None,
    manual_bf: Optional[float] = None,
) -> dict[str, Any]:
    """Run ALL calculations and return a flat dict ready for JSONB storage."""
    stats: dict[str, Any] = {}

    # BMR
    stats["bmr"] = calc_bmr(weight_kg, height_cm, age, sex)

    # Body fat: prefer manual, fallback to Navy formula
    bf = manual_bf
    if bf is None and measurements:
        waist = measurements.get("waist")
        neck = measurements.get("neck")
        hips = measurements.get("hips")
        bf = calc_navy_bf(sex, height_cm, waist, neck, hips)
    stats["bf_navy"] = bf

    # FFMI
    stats["ffmi"] = calc_ffmi(weight_kg, height_cm, bf)

    # Percentiles & rank
    if measurements:
        stats["percentiles"] = calc_percentiles(sex, measurements)
        stats["aesthetic_rank"] = calc_aesthetic_rank(stats["percentiles"], measurements)
        stats["symmetry"] = calc_symmetry(measurements)
    else:
        stats["percentiles"] = {}
        stats["aesthetic_rank"] = None
        stats["symmetry"] = {}

    return stats
