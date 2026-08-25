# creatoros architecture (M7)

creatoros is an AI content business automation MVP. Responsibilities are
intentionally split so intelligence stays in one place and orchestration stays
external.

```text
User
  ↓
Next.js (App Router)
  ↓ REST + JWT
FastAPI
  ├── Auth / ownership
  ├── Projects, Trends, Content, Analytics
  ├── llm_service → Gemini
  ├── Agents (Research → Planning → Video; Analytics → Coach)
  ├── PostgreSQL
  └── Redis (sessions blacklist, automation jobs, rate limits)

n8n (external)
  ↓ HTTP + X-Automation-Secret
FastAPI /api/v1/automation/*
  ↓ triggers existing services (does not reimplement AI)
```

## Why this split

| Layer | Owns | Does not own |
|-------|------|--------------|
| **FastAPI** | Business logic, AI prompts/agents, scoring, DB, jobs, auth | Cron schedules, Slack/email delivery, third-party fan-out |
| **n8n** | Scheduling, notifications, external connectors | LLM prompts, agent orchestration, scoring |
| **Next.js** | Product UI, charts, workspace | Secrets, authorization decisions |

n8n must call creatoros automation APIs. It must not embed Gemini prompts or
duplicate collectors.

## Content / video lifecycle (actual statuses)

```text
PENDING → GENERATED → REVIEW → APPROVED → EXPORTED
         ↘ FAILED

generation_phase: queued → researching → planning → generating_video
                → processing → ready | failed
publish_status: draft → ready → uploading → published | failed
```

Transitions are enforced in `ContentService` (HTTP 409 on invalid moves).
Review requires a real `video_url`. YouTube publish requires OAuth + upload adapter.

## Data stores

- **PostgreSQL:** `users`, `projects`, `trends` (+ `language`), `content` (video fields),
  `agent_runs`, `analytics_daily`, `youtube_credentials`
- **Redis:** JWT blacklist, generation/automation job state / idempotency, rate-limit counters
- **Object storage:** video files via `storage_service` (not Postgres BLOBs)

## Deployment shape

- Frontend → Vercel (`NEXT_PUBLIC_API_URL`)
- Backend → Railway (or similar) running uvicorn + Alembic migrations
- Managed PostgreSQL + Redis
- Optional n8n Cloud / self-hosted (compose profile `automation` for local only)

See root `README.md` and `docs/n8n-integration.md`.
