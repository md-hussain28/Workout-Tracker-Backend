# Workout Tracker API (Backend)

Production-grade FastAPI backend for the Workout Tracker app. Uses PostgreSQL (Aiven) with async SQLAlchemy.

## Setup

1. **Clone and enter the project**
   ```bash
   cd backend
   ```

2. **Create a virtual environment and install dependencies**
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment**
   - Copy `.env.example` to `.env` if you haven’t already.
   - Set `DATABASE_PASSWORD` in `.env` to your Aiven PostgreSQL password.

4. **Run database migrations**
   ```bash
   alembic upgrade head
   ```

5. **Start the server**
   ```bash
   uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
   ```

- API: http://localhost:8000  
- Swagger: http://localhost:8000/docs  
- ReDoc: http://localhost:8000/redoc  

## Project structure

```
app/
  main.py           # App factory, lifespan
  core/             # Config, security
  api/v1/           # API routes (health, exercises, workouts)
  db/               # Async engine, session
  models/           # SQLAlchemy models
  schemas/          # Pydantic request/response
alembic/            # Migrations
.env                # Local config (do not commit)
requirements.txt
```

## Database

PostgreSQL on Aiven. Connection is configured via `.env`; SSL is required. Use Alembic for schema changes:

- Create migration: `alembic revision --autogenerate -m "description"`
- Apply: `alembic upgrade head`

## Endpoints

- `GET /api/v1/health` — Liveness
- `GET /api/v1/health/ready` — Readiness (checks DB)
- `GET/POST /api/v1/exercises` — List / create exercises
- `GET/PATCH/DELETE /api/v1/exercises/{id}` — Exercise by id
- `GET/POST /api/v1/workouts` — List / create workouts
- `GET/PATCH/DELETE /api/v1/workouts/{id}` — Workout by id
- `POST /api/v1/workouts/{id}/sets` — Add set to workout
# Workout-Tracker-Backend
