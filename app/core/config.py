"""Application configuration from environment variables."""

from functools import lru_cache
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings loaded from environment (and .env file)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_name: str = "Workout Tracker API"
    debug: bool = False
    environment: str = "development"

    # API
    api_v1_prefix: str = "/api/v1"

    # Database (Aiven PostgreSQL)
    database_host: str = "pg-2cec4e9f-saquibworkouttracker.k.aivencloud.com"
    database_port: int = 15207
    database_user: str = "avnadmin"
    database_password: str = ""  # Set in .env - never commit
    database_name: str = "defaultdb"
    database_ssl_mode: str = "require"

    # Pool (production tuning)
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # CORS: comma-separated list of allowed origins in production (e.g. https://your-app.vercel.app)
    cors_origins: str = ""

    def _build_db_url(self, scheme: str = "postgresql", ssl_query: str = "sslmode=require") -> str:
        user = quote_plus(self.database_user)
        password = quote_plus(self.database_password)
        return (
            f"{scheme}://{user}:{password}@{self.database_host}:{self.database_port}"
            f"/{self.database_name}?{ssl_query}"
        )

    @property
    def database_url(self) -> str:
        """Synchronous URL for Alembic and tooling."""
        return self._build_db_url(scheme="postgresql", ssl_query=f"sslmode={self.database_ssl_mode}")

    @property
    def async_database_url(self) -> str:
        """Async URL for FastAPI (asyncpg driver)."""
        return self._build_db_url(scheme="postgresql+asyncpg", ssl_query="ssl=require")


@lru_cache
def get_settings() -> Settings:
    """Cached settings instance."""
    return Settings()
