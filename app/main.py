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
    # CORS: allow Vercel frontend (any deployment + previews) and localhost
    vercel_origin = "https://workout-tracker-frontend-gamma.vercel.app"
    extra_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    cors_origins = [
        vercel_origin,
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        *extra_origins,
    ]
    # Any *.vercel.app origin (preview deployments, other branches)
    cors_origin_regex = r"^https://[\w-]+\.vercel\.app$"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_origin_regex=cors_origin_regex,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Health paths for Render / load balancers
    @app.get("/")
    def root():
        return {"status": "ok", "message": "Workout Tracker API"}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/saquibhealth")
    def health_saquib():
        return {"status": "ok"}

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_application()
