# creatoros

AI-powered content business automation platform. Discover trends, research
and plan with a multi-agent AI pipeline, generate content, review/approve,
automate with n8n, and learn from analytics.

Built milestone-by-milestone. See `docs/` (or the project chat history) for
the full Project Constitution and Master Development Plan.

## Status

- **M1 — Foundation + Authentication: PASS.** Repo structure, Docker
  (Postgres + Redis), FastAPI backend, Next.js frontend, JWT auth
  (register/login/logout/me), protected app shell, initial design system.
- M2–M7: not started yet.

## Stack

- **Frontend:** Next.js (App Router, JavaScript), Tailwind CSS, shadcn/ui,
  Framer Motion, React Query, Recharts (added when needed).
- **Backend:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis.
- **Automation:** n8n (added in M5).
- **Deployment target:** Vercel (frontend) + Railway (backend/DB), see M7.

## Repository layout

```text
backend/
  app/
    api/routes/   FastAPI routers (one module per resource)
    api/deps.py   Shared dependencies (CurrentUser, DBSession, ...)
    core/         config, database, redis, security
    models/       SQLAlchemy models — register every new model in
                  models/__init__.py so Alembic autogenerate picks it up
    schemas/      Pydantic request/response schemas
    services/     Business logic, one service per domain concept
  alembic/        Migrations (never edit the DB schema by hand)
  tests/          pytest; shared fixtures live in tests/conftest.py
frontend/
  src/app/        Next.js routes (App Router)
  src/components/ UI components, grouped by feature (auth/, layout/, marketing/, ui/)
  src/context/    React context providers (auth-context, ...)
  src/lib/        api.js (backend client), auth-storage.js, utils.js
docker-compose.yml   Postgres + Redis for local dev
```

## Local setup

### 1. Environment variables

Copy `.env.example` to `.env` at the repo root and adjust as needed. The
frontend also reads `frontend/.env.local` (points `NEXT_PUBLIC_API_URL` at
the backend).

### 2. Start Postgres + Redis (Docker)

```bash
docker compose up -d
docker compose ps   # both should show "healthy"
```

> **Windows note:** Postgres is mapped to host port **5434** (not 5432).
> A native/system PostgreSQL service commonly already occupies 5432 on
> Windows dev machines, and Docker's port-forwarder silently loses that
> conflict rather than erroring — connections to 5432 would silently hit
> the wrong Postgres instance. Redis has no such conflict and uses the
> default 6379. If you're on macOS/Linux without a conflicting local
> Postgres, you can remap to 5432 in `docker-compose.yml`, just keep
> `DATABASE_URL` in `.env` in sync.

### 3. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

Backend runs at `http://127.0.0.1:8000`, API prefix `/api/v1`, docs at
`/docs`.

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:3000`.

> Do not run `npm run build` while `npm run dev` is active in the same
> directory — both write to `.next/` and will corrupt each other's build
> cache, producing spurious 500s. Stop the dev server first, or use a
> separate checkout/CI job for production builds.

## Testing

```bash
cd backend
python -m pytest -v
```

Tests use an in-memory SQLite DB and a fake Redis (see
`backend/tests/conftest.py`) — no live Postgres/Redis required to run them.
Reuse the `client` fixture from `conftest.py` in new test modules rather
than redefining the DB/Redis setup.

## Conventions to keep consistent across milestones

- **IDs:** `users.id` is a UUID (`sa.Uuid`, not `postgresql.UUID`, for
  dialect portability — SQLite-backed tests rely on this). Use the same
  type for all new primary keys and foreign keys referencing them.
- **New models:** add to `app/models/__init__.py` — `alembic/env.py`
  imports the package, not individual model modules, so anything missing
  from `__init__.py` won't be picked up by autogenerate.
- **New API clients (frontend):** add a new `xApi` object in
  `src/lib/api.js` next to `authApi`, reusing `apiRequest`.
- **New protected routes (backend):** depend on `CurrentUser` /
  `DBSession` from `app/api/deps.py` rather than re-deriving auth logic.
- **Redis keys:** namespace with a prefix like `auth:blacklist:*` (see
  `app/core/redis.py`) to avoid collisions once M5 adds job/queue state.
- **Sidebar nav:** `frontend/src/components/layout/sidebar.jsx` already
  has placeholder (disabled) links for Trends/Content/Analytics/Automation/
  Projects/Settings — flip `disabled` off and point at the real route as
  each milestone ships it, instead of adding new nav items ad hoc.
