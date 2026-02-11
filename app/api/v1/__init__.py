"""API v1 router aggregation."""

from fastapi import APIRouter

from app.api.v1.endpoints import (
    analytics,
    exercises,
    health,
    muscle_groups,
    previous_session,
    pr,
    templates,
    tools,
    workouts,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(exercises.router, prefix="/exercises", tags=["exercises"])
api_router.include_router(workouts.router, prefix="/workouts", tags=["workouts"])
api_router.include_router(muscle_groups.router, prefix="/muscle-groups", tags=["muscle-groups"])
api_router.include_router(previous_session.router, prefix="/previous-session", tags=["previous-session"])
api_router.include_router(pr.router, prefix="/pr", tags=["pr"])
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])
api_router.include_router(templates.router, prefix="/templates", tags=["templates"])
api_router.include_router(tools.router, prefix="/tools", tags=["tools"])
