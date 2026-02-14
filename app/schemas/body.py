"""Body analytics Pydantic schemas — UserBio and BodyLog."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── UserBio ──────────────────────────────────────────────────────────────

class UserBioCreate(BaseModel):
    height_cm: float = Field(..., gt=50, lt=300, description="Height in centimetres")
    age: int = Field(..., ge=10, le=120, description="Age in years")
    sex: str = Field(..., pattern="^(male|female)$", description="Biological sex")


class UserBioUpdate(BaseModel):
    height_cm: Optional[float] = Field(None, gt=50, lt=300)
    age: Optional[int] = Field(None, ge=10, le=120)
    sex: Optional[str] = Field(None, pattern="^(male|female)$")


class UserBioRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    height_cm: float
    age: int
    sex: str
    created_at: datetime
    updated_at: datetime


# ── BodyLog ──────────────────────────────────────────────────────────────

class BodyLogCreate(BaseModel):
    weight_kg: Optional[float] = Field(None, gt=20, lt=400, description="Body weight in kg. If omitted, uses last known weight.")
    body_fat_pct: Optional[float] = Field(None, ge=2, le=60, description="Manual body fat %")
    measurements: Optional[dict[str, float]] = Field(
        None,
        description=(
            "Body circumferences in cm. Keys: chest, waist, hips, neck, shoulder, "
            "bicep_l, bicep_r, forearm_l, forearm_r, thigh_l, thigh_r, calf_l, calf_r, wrist, ankle"
        ),
    )


class BodyLogUpdate(BaseModel):
    weight_kg: Optional[float] = Field(None, gt=20, lt=400)
    body_fat_pct: Optional[float] = Field(None, ge=2, le=60)
    measurements: Optional[dict[str, float]] = None
    created_at: Optional[datetime] = Field(None, description="Override the entry date")


class BodyLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    weight_kg: float
    body_fat_pct: Optional[float] = None
    measurements: Optional[dict[str, float]] = None
    computed_stats: Optional[dict[str, Any]] = None
    created_at: datetime
