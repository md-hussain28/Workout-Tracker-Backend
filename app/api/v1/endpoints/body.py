"""Body analytics endpoints — UserBio CRUD + BodyLog POST/GET."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.body_log import BodyLog
from app.models.user_bio import UserBio
from app.schemas.body import (
    BodyLogCreate,
    BodyLogRead,
    BodyLogUpdate,
    UserBioCreate,
    UserBioRead,
    UserBioUpdate,
)
from app.services.body_analytics import compute_all_stats

logger = logging.getLogger(__name__)
router = APIRouter()
# Singleton user until auth: one row in user_bio with this UUID as primary key.
# The id in responses (e.g. "00000000-0000-0000-0000-000000000001") is this UUID — not an integer.
USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


async def get_weight_at_date(
    db: AsyncSession,
    user_id: uuid.UUID,
    at_date: datetime,
) -> float | None:
    """
    Return weight_kg from the BodyLog closest to at_date (before or after).
    If no logs exist, return None.
    """
    # Prefer latest log on or before at_date; else earliest after
    before = await db.execute(
        select(BodyLog.weight_kg)
        .where(BodyLog.user_id == user_id, BodyLog.created_at <= at_date)
        .order_by(BodyLog.created_at.desc())
        .limit(1)
    )
    w = before.scalar_one_or_none()
    if w is not None:
        return float(w)
    after = await db.execute(
        select(BodyLog.weight_kg)
        .where(BodyLog.user_id == user_id, BodyLog.created_at > at_date)
        .order_by(BodyLog.created_at.asc())
        .limit(1)
    )
    a = after.scalar_one_or_none()
    return float(a) if a is not None else None


async def get_weights_for_dates(
    db: AsyncSession,
    user_id: uuid.UUID,
    at_dates: list[datetime],
) -> dict[str, float]:
    """
    Return weight_kg for each date: key = date isoformat, value = closest BodyLog weight.
    One query fetches all logs in range; then for each at_date we pick latest on or before, else earliest after.
    """
    if not at_dates:
        return {}
    lo = min(at_dates) - timedelta(days=1)
    hi = max(at_dates) + timedelta(days=1)
    result = await db.execute(
        select(BodyLog.created_at, BodyLog.weight_kg)
        .where(BodyLog.user_id == user_id, BodyLog.created_at >= lo, BodyLog.created_at <= hi)
        .order_by(BodyLog.created_at)
    )
    rows = result.all()
    if not rows:
        return {}
    # For each at_date, find closest: prefer latest <= at_date, else earliest > at_date
    out: dict[str, float] = {}
    for at_date in at_dates:
        before_w = None
        after_w = None
        for created_at, weight_kg in rows:
            if created_at and weight_kg is not None:
                if created_at <= at_date:
                    before_w = float(weight_kg)
                else:
                    after_w = float(weight_kg)
                    break
        w = before_w if before_w is not None else after_w
        if w is not None:
            out[at_date.date().isoformat()] = w
    return out


# ── UserBio ──────────────────────────────────────────────────────────────

@router.get("/bio", response_model=Optional[UserBioRead])
async def get_bio(db: AsyncSession = Depends(get_db)):
    """Get the singleton user bio. Returns null only when no row exists (or on DB error)."""
    try:
        result = await db.execute(select(UserBio).where(UserBio.id == USER_ID))
        bio = result.scalar_one_or_none()
        return bio
    except Exception as e:
        logger.exception("GET /body/bio failed: %s", e)
        return None


@router.put("/bio", response_model=UserBioRead)
async def upsert_bio(payload: UserBioCreate, db: AsyncSession = Depends(get_db)):
    """Create or update the singleton user bio. Session is committed by get_db after this returns."""
    result = await db.execute(select(UserBio).where(UserBio.id == USER_ID))
    bio = result.scalar_one_or_none()

    if bio:
        bio.height_cm = payload.height_cm
        bio.age = payload.age
        bio.sex = payload.sex
        bio.updated_at = datetime.now(timezone.utc)
    else:
        bio = UserBio(
            id=USER_ID,
            height_cm=payload.height_cm,
            age=payload.age,
            sex=payload.sex,
        )
        db.add(bio)

    await db.flush()
    await db.refresh(bio)
    return bio


# ── BodyLog ──────────────────────────────────────────────────────────────

@router.post("/log", response_model=BodyLogRead, status_code=201)
async def create_body_log(payload: BodyLogCreate, db: AsyncSession = Depends(get_db)):
    """Log weight + optional circumferences. Computes all analytics stats on write."""
    # Fetch user bio for height / age / sex
    result = await db.execute(select(UserBio).where(UserBio.id == USER_ID))
    bio = result.scalar_one_or_none()
    if not bio:
        raise HTTPException(
            status_code=400,
            detail="Set up your profile first (PUT /body/bio).",
        )

    # Resolve weight: use provided value, or fall back to most recent log
    weight = payload.weight_kg
    if weight is None:
        latest = await db.execute(
            select(BodyLog.weight_kg)
            .where(BodyLog.user_id == USER_ID)
            .order_by(BodyLog.created_at.desc())
            .limit(1)
        )
        last_weight = latest.scalar_one_or_none()
        if last_weight is None:
            raise HTTPException(
                status_code=400,
                detail="Weight is required for your first entry.",
            )
        weight = last_weight

    # Run all calculations in-memory
    stats = compute_all_stats(
        weight_kg=weight,
        height_cm=bio.height_cm,
        age=bio.age,
        sex=bio.sex,
        measurements=payload.measurements,
        manual_bf=payload.body_fat_pct,
    )

    log = BodyLog(
        user_id=USER_ID,
        weight_kg=weight,
        body_fat_pct=stats.get("bf_navy") or payload.body_fat_pct,
        measurements=payload.measurements,
        computed_stats=stats,
    )
    db.add(log)
    await db.flush()
    await db.refresh(log)
    return log


BF_KEYS = ("bf_army", "bf_cun_bae", "bf_rfm", "bf_multi", "bf_navy")


def _enrich_computed_stats(
    log: BodyLog,
    bio: UserBio | None,
) -> BodyLogRead:
    """Build BodyLogRead from log, recomputing bf_* stats if missing (so old logs show predictions)."""
    read = BodyLogRead.model_validate(log)
    if not bio or not log.weight_kg:
        return read
    existing = (read.computed_stats or {}).copy()
    if all(existing.get(k) is not None for k in BF_KEYS):
        return read
    stats = compute_all_stats(
        weight_kg=log.weight_kg,
        height_cm=bio.height_cm,
        age=bio.age,
        sex=bio.sex,
        measurements=log.measurements,
        manual_bf=log.body_fat_pct,
    )
    read.computed_stats = {**existing, **stats}
    return read


# Max logs to enrich per request (recompute bf_* when missing); rest return as stored.
MAX_ENRICH_PER_LIST = 100


def _needs_bf_enrich(log: BodyLog) -> bool:
    """True if log has no bio or is missing any bf_* key in computed_stats."""
    existing = log.computed_stats or {}
    return not all(existing.get(k) is not None for k in BF_KEYS)


@router.get("/log", response_model=list[BodyLogRead])
async def list_body_logs(
    days: Optional[int] = Query(None, description="Filter to last N days (7, 30, 90). Omit for all."),
    db: AsyncSession = Depends(get_db),
):
    """Get body log history, optionally filtered by recent days. Enriches with bf_* stats when missing (up to MAX_ENRICH_PER_LIST)."""
    stmt = (
        select(BodyLog)
        .where(BodyLog.user_id == USER_ID)
        .order_by(desc(BodyLog.created_at))
    )
    if days is not None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        stmt = stmt.where(BodyLog.created_at >= cutoff)

    result = await db.execute(stmt)
    logs = result.scalars().all()
    bio_result = await db.execute(select(UserBio).where(UserBio.id == USER_ID))
    bio = bio_result.scalar_one_or_none()
    enriched = 0
    out = []
    for log in logs:
        if _needs_bf_enrich(log) and enriched < MAX_ENRICH_PER_LIST and bio and log.weight_kg:
            out.append(_enrich_computed_stats(log, bio))
            enriched += 1
        else:
            out.append(BodyLogRead.model_validate(log))
    return out


@router.get("/log/latest", response_model=Optional[BodyLogRead])
async def get_latest_body_log(db: AsyncSession = Depends(get_db)):
    """Get the most recent body log entry. Enriches with bf_* stats when missing."""
    result = await db.execute(
        select(BodyLog)
        .where(BodyLog.user_id == USER_ID)
        .order_by(desc(BodyLog.created_at))
        .limit(1)
    )
    log = result.scalar_one_or_none()
    if not log:
        return None
    bio_result = await db.execute(select(UserBio).where(UserBio.id == USER_ID))
    bio = bio_result.scalar_one_or_none()
    return _enrich_computed_stats(log, bio)


@router.patch("/log/{log_id}", response_model=BodyLogRead)
async def update_body_log(log_id: uuid.UUID, payload: BodyLogUpdate, db: AsyncSession = Depends(get_db)):
    """Update a body log entry. Re-computes all stats."""
    result = await db.execute(
        select(BodyLog).where(BodyLog.id == log_id, BodyLog.user_id == USER_ID)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Body log not found")

    # Fetch bio for re-calculation
    bio_result = await db.execute(select(UserBio).where(UserBio.id == USER_ID))
    bio = bio_result.scalar_one_or_none()
    if not bio:
        raise HTTPException(status_code=400, detail="Profile not set up.")

    # Apply partial updates
    if payload.weight_kg is not None:
        log.weight_kg = payload.weight_kg
    if payload.body_fat_pct is not None:
        log.body_fat_pct = payload.body_fat_pct
    if payload.measurements is not None:
        # Merge: keep existing keys, overwrite provided ones
        existing = log.measurements or {}
        existing.update(payload.measurements)
        log.measurements = existing
    if payload.created_at is not None:
        log.created_at = payload.created_at

    # Re-compute stats with updated values
    stats = compute_all_stats(
        weight_kg=log.weight_kg,
        height_cm=bio.height_cm,
        age=bio.age,
        sex=bio.sex,
        measurements=log.measurements,
        manual_bf=log.body_fat_pct,
    )
    log.body_fat_pct = stats.get("bf_navy") or log.body_fat_pct
    log.computed_stats = stats

    await db.flush()
    await db.refresh(log)
    return log


@router.delete("/log/{log_id}", status_code=204)
async def delete_body_log(log_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Delete a body log entry."""
    result = await db.execute(
        select(BodyLog).where(BodyLog.id == log_id, BodyLog.user_id == USER_ID)
    )
    log = result.scalar_one_or_none()
    if not log:
        raise HTTPException(status_code=404, detail="Body log not found")
    await db.delete(log)
