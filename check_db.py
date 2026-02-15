import sys
import os
import asyncio
from sqlalchemy import text

# Add backend directory to sys.path
sys.path.append(os.getcwd())
# Adjust if running from root
if os.path.basename(os.getcwd()) != 'backend':
    sys.path.append(os.path.join(os.getcwd(), 'backend'))

try:
    from app.db.session import async_session_maker
except ImportError:
    # Try absolute import if running from root
    from backend.app.db.session import async_session_maker

async def check_data():
    async with async_session_maker() as session:
        try:
            tables = ["exercises", "workouts", "workout_templates", "body_logs", "user_bio"]
            print(f"Checking tables: {tables}")
            for table in tables:
                try:
                    result = await session.execute(text(f"SELECT count(*) FROM {table}"))
                    count = result.scalar()
                    print(f"Table '{table}' row count: {count}")
                    
                    if count > 0:
                        # Show sample ID
                        sample = await session.execute(text(f"SELECT id FROM {table} LIMIT 1"))
                        sample_id = sample.scalar()
                        print(f"  Sample ID from {table}: {sample_id} (Type: {type(sample_id)})")
                except Exception as e:
                    print(f"Error querying {table}: {e}")
                    
        except Exception as e:
            print(f"Error checking DB: {e}")

if __name__ == "__main__":
    asyncio.run(check_data())
