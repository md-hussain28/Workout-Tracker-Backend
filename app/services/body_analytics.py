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


# U.S. Navy body fat formula uses INCHES. 1 in = 2.54 cm.
CM_TO_IN = 1.0 / 2.54


def calc_navy_bf(
    sex: str,
    height_cm: float,
    waist_cm: float,
    neck_cm: float,
    hips_cm: Optional[float] = None,
) -> Optional[float]:
    """U.S. Navy body fat % formula. Inputs in cm; converted to inches for formula."""
    if waist_cm is None or neck_cm is None or waist_cm <= neck_cm or height_cm <= 0:
        return None
    try:
        waist_in = waist_cm * CM_TO_IN
        neck_in = neck_cm * CM_TO_IN
        height_in = height_cm * CM_TO_IN
        if sex == "male":
            # Male: 86.010×log10(abdomen−neck) − 70.041×log10(height) + 36.76 (inches)
            bf = (
                86.010 * math.log10(waist_in - neck_in)
                - 70.041 * math.log10(height_in)
                + 36.76
            )
        else:
            if hips_cm is None:
                return None
            hips_in = hips_cm * CM_TO_IN
            # Female: 163.205×log10(waist+hip−neck) − 97.684×log10(height) − 78.387 (inches)
            bf = (
                163.205 * math.log10(waist_in + hips_in - neck_in)
                - 97.684 * math.log10(height_in)
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


def calc_army_bf(
    sex: str,
    weight_kg: float,
    waist_cm: Optional[float] = None,
    hips_cm: Optional[float] = None,
) -> Optional[float]:
    """U.S. Army 2024 body fat formula (validated). Inputs in cm/kg."""
    if sex != "male" or weight_kg <= 0 or not waist_cm or not hips_cm:
        return None
    
    # 2024 Army equation For men: %BF ≈ -38.32 + 2.23×abdomen + 0.68×hip -0.43×waist -0.16×weight
    # Assumes abdomen approx equals waist if only waist is given.
    abdomen = waist_cm
    bf = -38.32 + 2.23 * abdomen + 0.68 * hips_cm - 0.43 * waist_cm - 0.16 * weight_kg
    return round(max(bf, 2.0), 1)


def calc_cun_bae_bf(
    weight_kg: float, height_cm: float, age: int, sex: str
) -> Optional[float]:
    """CUN-BAE body fat equation using BMI, age, and sex."""
    if height_cm <= 0 or weight_kg <= 0:
        return None
    height_m = height_cm / 100
    bmi = weight_kg / (height_m**2)
    s = 0 if sex == "male" else 1
    bf = (
        -44.988
        + (0.503 * age)
        + (10.689 * s)
        + (3.172 * bmi)
        - (0.026 * bmi**2)
        + (0.181 * bmi * s)
        - (0.02 * bmi * age)
        - (0.005 * bmi**2 * s)
        + (0.00021 * bmi**2 * age)
    )
    return round(max(bf, 2.0), 1)


def calc_rfm_bf(
    sex: str, height_cm: float, waist_cm: Optional[float] = None
) -> Optional[float]:
    """Relative Fat Mass (RFM) body fat equation."""
    if height_cm <= 0 or not waist_cm or waist_cm <= 0:
        return None
    if sex == "male":
        # Men: 64 - (20 × height/waist)
        bf = 64 - (20 * height_cm / waist_cm)
    else:
        # Women: 76 - (20 × height/waist)
        bf = 76 - (20 * height_cm / waist_cm)
    return round(max(bf, 2.0), 1)


def calc_multi_girth_bf(
    weight_kg: float,
    height_cm: float,
    sex: str,
    waist_cm: Optional[float] = None,
    chest_cm: Optional[float] = None,
    hips_cm: Optional[float] = None,
) -> Optional[float]:
    """Multi-Girth Regression body fat estimate using Waist/chest/hip + BMI proxy."""
    if height_cm <= 0 or weight_kg <= 0 or not waist_cm or not chest_cm or not hips_cm:
        return None
    height_m = height_cm / 100
    bmi = weight_kg / (height_m**2)
    
    if sex == "male":
        bf = 0.5 * bmi + 0.4 * waist_cm + 0.2 * hips_cm - 0.3 * chest_cm - 15
    else:
        bf = 0.5 * bmi + 0.3 * waist_cm + 0.4 * hips_cm - 0.2 * chest_cm - 10
    
    return round(max(bf, 2.0), 1)


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

    # Other BF equations
    stats["bf_cun_bae"] = calc_cun_bae_bf(weight_kg, height_cm, age, sex)
    stats["bf_army"] = None
    stats["bf_rfm"] = None
    stats["bf_multi"] = None

    if measurements:
        waist = measurements.get("waist")
        hips = measurements.get("hips")
        chest = measurements.get("chest")
        
        stats["bf_army"] = calc_army_bf(sex, weight_kg, waist, hips)
        stats["bf_rfm"] = calc_rfm_bf(sex, height_cm, waist)
        stats["bf_multi"] = calc_multi_girth_bf(weight_kg, height_cm, sex, waist, chest, hips)

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
