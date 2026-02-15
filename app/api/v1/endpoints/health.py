"""Health check endpoint for load balancers and monitoring."""

import os
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db

router = APIRouter()


@router.get("")
async def health():
    """Simple liveness check. Optionally includes built_at if BACKEND_BUILT_AT env is set."""
    payload: dict = {"status": "ok"}
    built_at = os.environ.get("BACKEND_BUILT_AT") or os.environ.get("RENDER_GIT_COMMIT_TIMESTAMP")
    if built_at:
        payload["built_at"] = built_at
    return payload


@router.get("/ready")
async def readiness(db: AsyncSession = Depends(get_db)):
    """Readiness: app + DB connectivity."""
    try:
        await db.execute(text("SELECT 1"))
        return {"status": "ok", "database": "connected"}
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"status": "error", "database": str(e)},
        )
