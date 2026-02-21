"""Body analytics calculation service.

All heavy math runs at POST time — results are cached in the DB record.
Uses math.erf for percentile calculation (no scipy dependency).
"""

from __future__ import annotations

import math
from typing import Any, Optional

from app.core.nhanes_data import NHANES_STATS, PAIRED_KEYS, get_population_stats


def _normalize_measurements(measurements: dict[str, float]) -> dict[str, float]:
    """Lowercase keys and map formula aliases so logged data matches equation inputs.
    E.g. abdomen -> waist, hip -> hips (formula uses waist/hips/weight).
    """
    out: dict[str, float] = {}
    for k, v in measurements.items():
        if v is None:
            continue
        try:
            out[k.lower().strip()] = float(v)
        except (TypeError, ValueError):
            continue
    # Map common aliases to canonical keys used by formulas
    if "abdomen" in out and "waist" not in out:
        out["waist"] = out["abdomen"]
    if "hip" in out and "hips" not in out:
        out["hips"] = out["hip"]
    return out


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


# U.S. Navy / Army body fat formulas use INCHES and POUNDS.
CM_TO_IN = 1.0 / 2.54
KG_TO_LB = 2.20462

# Plausible body fat % range; clamp all formulas to avoid unit/input errors.
BF_PCT_MIN = 2.0
BF_PCT_MAX = 60.0


def _clamp_bf(pct: float | None) -> float | None:
    if pct is None:
        return None
    return round(max(BF_PCT_MIN, min(BF_PCT_MAX, pct)), 1)


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
        return _clamp_bf(bf)
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
    """U.S. Army 2024 one-site formula. Uses abdomen (waist) in INCHES and weight in POUNDS."""
    if weight_kg <= 0 or not waist_cm:
        return None
    # 2024 Army: one-site (abdominal circumference) + weight. All in inches and pounds.
    abdomen_in = waist_cm * CM_TO_IN
    weight_lb = weight_kg * KG_TO_LB
    if sex == "male":
        # Males: % = -26.97 - (0.12 × weight_lb) + (1.99 × abdomen_in)
        bf = -26.97 - (0.12 * weight_lb) + (1.99 * abdomen_in)
    else:
        # Females: % = -9.15 - (0.015 × weight_lb) + (1.27 × abdomen_in)
        bf = -9.15 - (0.015 * weight_lb) + (1.27 * abdomen_in)
    return _clamp_bf(bf)


def calc_cun_bae_bf(
    weight_kg: float, height_cm: float, age: int, sex: str
) -> Optional[float]:
    """CUN-BAE body fat equation using BMI, age, and sex. No circumferences."""
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
    return _clamp_bf(bf)


def calc_rfm_bf(
    sex: str, height_cm: float, waist_cm: Optional[float] = None
) -> Optional[float]:
    """Relative Fat Mass (RFM). Height and waist in same units (cm); ratio is unit-invariant."""
    if height_cm <= 0 or not waist_cm or waist_cm <= 0:
        return None
    if sex == "male":
        bf = 64 - (20 * height_cm / waist_cm)
    else:
        bf = 76 - (20 * height_cm / waist_cm)
    return _clamp_bf(bf)


def calc_multi_girth_bf(
    weight_kg: float,
    height_cm: float,
    sex: str,
    waist_cm: Optional[float] = None,
    chest_cm: Optional[float] = None,
    hips_cm: Optional[float] = None,
) -> Optional[float]:
    """Multi-girth proxy: waist/chest/hip in INCHES (formula coefficients expect ~30–40 range)."""
    if height_cm <= 0 or weight_kg <= 0 or not waist_cm or not chest_cm or not hips_cm:
        return None
    height_m = height_cm / 100
    bmi = weight_kg / (height_m**2)
    waist_in = waist_cm * CM_TO_IN
    chest_in = chest_cm * CM_TO_IN
    hips_in = hips_cm * CM_TO_IN
    if sex == "male":
        bf = 0.5 * bmi + 0.4 * waist_in + 0.2 * hips_in - 0.3 * chest_in - 15
    else:
        bf = 0.5 * bmi + 0.3 * waist_in + 0.4 * hips_in - 0.2 * chest_in - 10
    return _clamp_bf(bf)


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
    # Normalize so abdomen->waist, hip->hips, lowercase keys; formulas use waist/hips/chest/neck
    m = _normalize_measurements(measurements) if measurements else {}

    # BMR
    stats["bmr"] = calc_bmr(weight_kg, height_cm, age, sex)

    # Body fat: prefer manual, fallback to Navy formula
    bf = manual_bf
    if bf is None and m:
        waist = m.get("waist")
        neck = m.get("neck")
        hips = m.get("hips")
        bf = calc_navy_bf(sex, height_cm, waist, neck, hips)
    stats["bf_navy"] = bf

    # Other BF equations
    stats["bf_cun_bae"] = calc_cun_bae_bf(weight_kg, height_cm, age, sex)
    stats["bf_army"] = None
    stats["bf_rfm"] = None
    stats["bf_multi"] = None

    if m:
        waist = m.get("waist")
        hips = m.get("hips")
        chest = m.get("chest")
        stats["bf_army"] = calc_army_bf(sex, weight_kg, waist, hips)
        stats["bf_rfm"] = calc_rfm_bf(sex, height_cm, waist)
        stats["bf_multi"] = calc_multi_girth_bf(weight_kg, height_cm, sex, waist, chest, hips)

    # FFMI
    stats["ffmi"] = calc_ffmi(weight_kg, height_cm, bf)

    # Percentiles & rank (use normalized dict so all keys are lowercase/canonical)
    if m:
        stats["percentiles"] = calc_percentiles(sex, m)
        stats["aesthetic_rank"] = calc_aesthetic_rank(stats["percentiles"], m)
        stats["symmetry"] = calc_symmetry(m)
    else:
        stats["percentiles"] = {}
        stats["aesthetic_rank"] = None
        stats["symmetry"] = {}

    return stats
