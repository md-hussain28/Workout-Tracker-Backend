import asyncio
import sys
import os

# Add backend to path
sys.path.append(os.getcwd())

from app.db.session import engine
from app.db.base import Base
# Import all models
from app.models import *

async def drop_tables():
    print("Dropping all tables...")
    async with engine.begin() as conn:
        from sqlalchemy import text
        await conn.execute(text("DROP TABLE IF EXISTS alembic_version"))
        await conn.run_sync(Base.metadata.drop_all)
    print("Tables dropped.")
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(drop_tables())
