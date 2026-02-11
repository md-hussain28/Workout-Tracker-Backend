# What to do after adding your database password

You’ve set `DATABASE_PASSWORD` in `.env`. Follow these steps in order.

## 1. Create a virtual environment (one-time)

From the **backend** folder in a terminal:

```bash
cd "/Users/msh/Documents/Personal Projects/WorkoutTracker/backend"
python3 -m venv .venv
```

## 2. Activate the virtual environment and install dependencies

**On macOS/Linux:**

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

**On Windows (PowerShell):**

```bash
.venv\Scripts\activate
pip install -r requirements.txt
```

Keep the virtual environment activated for the next steps.

## 3. Run database migrations

This creates/updates the tables in your Aiven PostgreSQL database:

```bash
alembic upgrade head
```

You should see output like:

- `Running upgrade  -> 001, Initial schema...`
- `Running upgrade 001 -> 002, Feature set...`

## 4. Start the API server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Then open in your browser:

- **API docs (Swagger):** http://localhost:8000/docs  
- **Health check:** http://localhost:8000/api/v1/health  
- **DB readiness:** http://localhost:8000/api/v1/health/ready  

---

## Quick reference

| Step | Command |
|------|---------|
| Activate venv (Mac/Linux) | `source .venv/bin/activate` |
| Install deps | `pip install -r requirements.txt` |
| Migrate DB | `alembic upgrade head` |
| Run server | `uvicorn app.main:app --reload --port 8000` |

If `alembic upgrade head` fails, double-check that `DATABASE_PASSWORD` in `.env` is correct and that the database is reachable (host/port/SSL from Aiven).
