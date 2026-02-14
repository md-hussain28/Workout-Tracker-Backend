"""UserBio model — singleton user profile for body analytics."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserBio(Base):
    """One-to-one user profile storing height, age, sex.

    Singleton pattern: single row with id=1 (no auth yet).
    """

    __tablename__ = "user_bio"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    height_cm: Mapped[float] = mapped_column(Float, nullable=False)
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    sex: Mapped[str] = mapped_column(String(10), nullable=False, default="male")  # male / female
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    body_logs: Mapped[list["BodyLog"]] = relationship(
        "BodyLog", back_populates="user_bio", cascade="all, delete-orphan"
    )
