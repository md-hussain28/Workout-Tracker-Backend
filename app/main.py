"""FastAPI application factory and lifespan."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: ensure DB connectivity; shutdown: cleanup."""
    # Startup: optional create tables (use Alembic in production)
    # async with engine.begin() as conn:
    #     await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    # CORS: allow localhost in dev; in production use CORS_ORIGINS env (comma-separated)
    if settings.debug:
        cors_origins = ["*"]
    elif settings.environment == "development":
        cors_origins = ["http://localhost:3000", "http://127.0.0.1:3000"]
    else:
        # Production: Vercel frontend + any extra from CORS_ORIGINS env
        cors_origins = [
            "https://workout-tracker-frontend-gamma.vercel.app",
            *[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Health paths for Render / load balancers (root and common custom path)
    @app.get("/")
    def root():
        return {"status": "ok", "message": "Workout Tracker API"}

    @app.get("/saquibhealth")
    def health_check():
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_application()
