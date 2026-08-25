# creatoros

AI-powered content business automation for creators.

**Problem:** Creators juggle trend research, video planning, generation, review,
YouTube publishing, and performance learning across disconnected tools.

**Solution:** One product loop — discover English trends → research → plan →
generate real videos → review → YouTube publish → measure → coach → improve —
with FastAPI owning intelligence and n8n (optional, external) owning schedules
and notifications.

## Core workflow

```text
Authenticate → Project → English Trends → Select
→ Research / Planning / Video agents (+ content memory)
→ Replicate (minimax/video-01) 9:16 Short → Video workspace review/approve → YouTube
→ Analytics ingest → Analytics + Coach agents
```

## Status

- M1 Auth — PASS
- M2 Trends (Google Trends + YouTube; no Reddit; English filter) — PASS
- M3 Multi-agent generation (Research / Planning / Video) — PASS
- M4 Video workspace — PASS
- M5 Hybrid automation APIs (n8n-ready) — PASS
- M6 Analytics + Coach — PASS
- M7 Production hardening + polish — PASS
- **Video-first product correction** — architecture + async generation shipped;
  live video provider + YouTube resumable upload require external credentials

## Features (implemented)

- JWT register/login/logout with Redis token blacklist
- Projects with niche / audience / brand voice
- English-only trend collect + score + select (Google Trends + YouTube)
- Research → Planning → Video agents (Gemini via `llm_service`)
- Content memory + duplicate-trend guards for future planning
- Narrated Shorts: Replicate motion clips + JSON2Video voiceover (no on-screen text)
- Supabase Storage for generated `.mp4` files (Postgres stores path/URL only)
- Async Redis-backed generation jobs (default) with phase polling
- Video-first workspace (preview, review, approve, YouTube publish path)
- YouTube OAuth connect scaffold (tokens stay server-side)
- Automation job APIs for n8n triggers
- Analytics ingest/dashboard + Analytics/Coach agents
- Basic Redis rate limiting on expensive routes

## Architecture

See [`docs/architecture.md`](docs/architecture.md) and
[`docs/n8n-integration.md`](docs/n8n-integration.md).

```text
Next.js → FastAPI → PostgreSQL / Redis / Gemini agents
n8n (external) → FastAPI /automation/* (no prompts in n8n)
```

## Tech stack

- **Frontend:** Next.js App Router, Tailwind, Framer Motion, Recharts
- **Backend:** FastAPI, SQLAlchemy, Alembic, PostgreSQL, Redis
- **AI:** Gemini through a single `llm_service`
- **Automation:** n8n-ready HTTP APIs (n8n not bundled as an app dependency)

## Project structure

```text
backend/app/          FastAPI app (routes, services, agents, models)
backend/alembic/      Migrations
backend/tests/        pytest
frontend/src/app/     Next.js routes
docs/                 Architecture + n8n integration
docker-compose.yml    Postgres, Redis, backend, frontend (+ optional n8n)
```

## Local setup

### 1. Environment

Copy `.env.example` → `.env` at the repo root (never commit real secrets).
Copy `NEXT_PUBLIC_API_URL` into `frontend/.env.local`.

Important variables: `DATABASE_URL`, `REDIS_URL`, `JWT_SECRET`, `CORS_ORIGINS`,
`GEMINI_API_KEY`, `YOUTUBE_API_KEY`, `VIDEO_GENERATION_PROVIDER`,
`YOUTUBE_OAUTH_CLIENT_ID` / `SECRET` / `REDIRECT_URI`, `N8N_WEBHOOK_SECRET`,
`NEXT_PUBLIC_API_URL`, `ENVIRONMENT` (`development` locally; `production`
enforces strong JWT + explicit CORS).

### 2. Infrastructure

```bash
docker compose up -d --build
docker compose ps   # postgres, redis, backend, frontend
```

- App: `http://localhost:3000`
- API: `http://localhost:8000/api/v1`
- Postgres is on host port **5434** (container still uses 5432).

Infra only (if you run uvicorn / Next on the host): `docker compose up -d postgres redis`.

Optional local n8n: `docker compose --profile automation up -d` (port 5678).

### 3. Backend (host, optional)

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --reload --port 8000
```

API: `http://127.0.0.1:8000/api/v1` — OpenAPI at `/docs`.

Health:

- `GET /health` — process liveness
- `GET /api/v1/health/live` — liveness
- `GET /api/v1/health/ready` — DB + Redis readiness
- `GET /api/v1/health` — dependency summary (`ok` / `degraded`)

### 4. Frontend

```bash
cd frontend
npm install
npm run dev
```

App: `http://localhost:3000`.

> Do not run `npm run build` while `npm run dev` is active in the same folder.

## Tests

```bash
cd backend
python -m pytest -q
```

Frontend Playwright smoke (mocked API journey):

```bash
cd frontend
npx playwright install chromium
npm run test:e2e
```

## AI architecture

Agents only call `llm_service`. Structured Pydantic outputs are validated with
retries; attempts are logged to `agent_runs`. Agents:

1. Research 2. Strategy 3. Content 4. Analytics 5. Coach

## Automation architecture

FastAPI owns AI + jobs. n8n only schedules HTTP calls and notifications.
Configure workflows later using `docs/n8n-integration.md` — do not put prompts
in n8n.

Rate limiting (M7): Redis fixed-window counters on trend collect, content
generate/suggest/regenerate, analytics coach/ingest, and automation triggers.
Fails open if Redis is unavailable for the counter (auth still requires Redis).

## Deployment (prepare — not auto-deployed)

| Piece | Target |
|-------|--------|
| Frontend | Vercel — set `NEXT_PUBLIC_API_URL` to the public API |
| Backend | Railway (or similar) — run Alembic then uvicorn |
| DB | Managed PostgreSQL |
| Redis | Managed Redis |
| Secrets | Platform secret store (`JWT_SECRET`, `GEMINI_API_KEY`, `N8N_WEBHOOK_SECRET`, …) |
| CORS | Set `CORS_ORIGINS` to the exact Vercel origin; set `ENVIRONMENT=production` |

Backend container: see `backend/Dockerfile`. Compose only runs local data stores
(+ optional n8n), not the full production stack.

## Conventions

- UUIDs via `sa.Uuid`; register models in `app/models/__init__.py`
- Ownership checks return **404** (not 403) for cross-user resources
- Content statuses: `PENDING` → `GENERATED` → `REVIEW` → `APPROVED` → `EXPORTED` (or `FAILED`)
- Never invent analytics or AI output when providers fail
