import asyncio
import os
import sys

# Add parent directory to path so we can import app modules
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

async def main():
    settings = get_settings()
    # Use the async database URL
    database_url = settings.async_database_url
    
    print(f"Connecting to database...")
    # Create engine (echo=True to see output)
    engine = create_async_engine(database_url, echo=True)

    async with engine.begin() as conn:
        print("Checking if 'color' column exists in 'muscle_groups'...")
        # Check if column exists
        try:
            # PostgreSQL specific check
            result = await conn.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='muscle_groups' AND column_name='color';"
            ))
            if result.scalar():
                print("Column 'color' already exists.")
            else:
                print("Adding 'color' column...")
                await conn.execute(text("ALTER TABLE muscle_groups ADD COLUMN color VARCHAR(7);"))
                print("Column added successfully.")
        except Exception as e:
            print(f"Error checking/adding column: {e}")
            # Fallback for SQLite? User seems to use Postgres.
            # If sqlite, information_schema doesn't exist.
            # But config.py implies Postgres.

    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(main())
