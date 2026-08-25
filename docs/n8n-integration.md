# n8n ↔ creatoros integration (Milestone 5)

creatoros keeps **intelligence inside FastAPI** (agents, scoring, DB, auth).
**n8n** owns cron schedules, HTTP triggers, and external notifications.

```text
n8n (cron / notify)  --HTTP + X-Automation-Secret-->  FastAPI automation APIs
                                                      ├── TrendService (M2)
                                                      ├── ContentService agents (M3)
                                                      └── Redis job state
```

Do **not** put prompts, LLM calls, or scoring logic into n8n nodes.

---

## Prerequisites

1. Set a shared secret in the creatoros `.env` (never commit the real value):

```env
N8N_WEBHOOK_SECRET=replace-with-a-long-random-string
```

2. Restart the FastAPI backend so settings reload.

3. Run n8n separately (local Docker example below, or n8n Cloud).

---

## Authentication

All machine automation endpoints require:

| Header | Value |
|--------|--------|
| `X-Automation-Secret` | Same value as `N8N_WEBHOOK_SECRET` |
| `Content-Type` | `application/json` (for POST bodies) |

Optional:

| Header | Value |
|--------|--------|
| `Idempotency-Key` | Stable string per logical run (e.g. `daily-2026-08-10`) |

Missing/wrong secret → **401**.  
Unset `N8N_WEBHOOK_SECRET` on the server → **503**.

Secrets are never logged by creatoros.

---

## Base URL

Local default:

```text
http://localhost:8000/api/v1
```

---

## Endpoint reference

### 1. Collect trends

```http
POST /api/v1/automation/trends/collect
```

**Body**

```json
{
  "project_id": "uuid-of-project",
  "query": "optional override; defaults to project niche"
}
```

**Success (202-style accepted as 200)**

```json
{
  "success": true,
  "job_id": "uuid",
  "status": "queued",
  "idempotent_replay": false
}
```

Reuses Milestone 2 collectors + scoring. Work runs in a background job.

**Errors**

| Status | Meaning |
|--------|---------|
| 401 | Bad/missing automation secret |
| 404 | Unknown `project_id` |
| 400 | No query/niche available |
| 503 | Secret not configured / Redis down |

---

### 2. Generate content

```http
POST /api/v1/automation/content/generate
```

**Body**

```json
{
  "project_id": "uuid-of-project",
  "trend_id": "optional-uuid"
}
```

If `trend_id` is omitted, creatoros picks the project's **highest-scored** trend
and selects it, then runs the existing Research → Strategy → Content pipeline.

**Success**

```json
{
  "success": true,
  "job_id": "uuid",
  "status": "queued",
  "idempotent_replay": false
}
```

---

### 3. Poll job status

```http
GET /api/v1/automation/jobs/{job_id}
```

**Statuses:** `queued` → `running` → `completed` | `failed`

**Completed content job example**

```json
{
  "job_id": "uuid",
  "kind": "content.generate",
  "status": "completed",
  "content_id": "uuid",
  "result": {
    "content_id": "uuid",
    "status": "GENERATED",
    "trend_id": "uuid"
  },
  "error": null
}
```

n8n can notify when `status === "completed"` and use `content_id` in the message.

---

## Suggested n8n workflows

### Workflow 1 — Daily trend collection

```text
Cron (every morning)
  → HTTP Request POST /automation/trends/collect
       Headers: X-Automation-Secret, Idempotency-Key=collect-{{$today}}
       Body: { "project_id": "..." }
  → (optional) Wait / poll GET /automation/jobs/{{job_id}}
```

### Workflow 2 — Content generation + notify

```text
Trigger (after collect, or separate cron)
  → HTTP Request POST /automation/content/generate
       Headers: X-Automation-Secret, Idempotency-Key=generate-{{$today}}
       Body: { "project_id": "..." }
  → Loop / Wait until GET /automation/jobs/{{job_id}} status is completed|failed
  → IF completed → Slack/Email/Discord notification with content_id
  → IF failed → alert with job.error
```

Polling tip: wait 5–15s between status checks; content generation can take 10–60s.

---

## Idempotency / duplicate protection

Pass `Idempotency-Key` on POST requests. creatoros stores the mapping in Redis
(`automation:idempotency:...`, TTL 24h by default).

- First request creates a job and returns its `job_id`.
- Retries with the **same key + same endpoint scope** return the same `job_id`
  with `"idempotent_replay": true` — they do **not** start a second AI run.

Use a daily key in cron workflows (date stamped) so a flaky retry cannot
double-generate content for the same morning run.

---

## Rate limiting (M7)

Automation POSTs are rate-limited with a Redis fixed-window counter (default
60 requests / 60 seconds per automation secret hash). Exceeding the limit
returns **429** with `Retry-After`. Space cron retries accordingly.

---

## Optional local n8n (Docker)

Keep n8n outside the FastAPI process. Example compose service (optional):

```yaml
n8n:
  image: n8nio/n8n:latest
  ports:
    - "5678:5678"
  environment:
    - N8N_HOST=localhost
    - N8N_PORT=5678
    - N8N_PROTOCOL=http
  volumes:
    - n8n_data:/home/node/.n8n
```

Open `http://localhost:5678` and point HTTP nodes at
`http://host.docker.internal:8000/api/v1/...` on Docker Desktop for Windows/Mac
(or your host LAN IP on Linux).

---

## Ownership reminder

| Inside FastAPI | Inside n8n |
|----------------|------------|
| AI prompts & agents | Cron schedules |
| LLM calls | HTTP requests to creatoros |
| Trend scoring | Notifications (Slack/email/…) |
| DB business logic | External SaaS APIs |
| Job processing | Simple IF conditions |
