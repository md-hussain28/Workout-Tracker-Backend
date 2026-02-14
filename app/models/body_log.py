"""BodyLog model — weight + JSONB measurements + pre-computed stats."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class BodyLog(Base):
    """A single body measurement entry.

    Raw data: weight_kg, body_fat_pct (optional manual), measurements (JSONB).
    Pre-computed at POST time: computed_stats (JSONB) — BMR, BF%, FFMI, percentiles, rank.
    """

    __tablename__ = "body_logs"
    __table_args__ = (
        Index("ix_body_logs_user_created", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user_bio.id", ondelete="CASCADE"), nullable=False
    )
    weight_kg: Mapped[float] = mapped_column(Float, nullable=False)
    body_fat_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    # All circumferences stored as a flat dict: {"chest": 102.3, "bicep_l": 38, ...}
    measurements: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Pre-computed stats: {"bmr": 1850, "bf_navy": 14.2, "ffmi": 22.5,
    #   "percentiles": {"chest": 85, ...}, "aesthetic_rank": 15, "symmetry": {...}}
    computed_stats: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    user_bio: Mapped["UserBio"] = relationship("UserBio", back_populates="body_logs")
