# Rate Limiting

Creator OS implements rate limiting on expensive operations to prevent abuse.

## Configuration

Set in `.env`:

```
RATE_LIMIT_ENABLED=true
RATE_LIMIT_WINDOW_SECONDS=60
RATE_LIMIT_USER_MAX=20           # Per-user limit per window
RATE_LIMIT_AUTOMATION_MAX=60     # Per-automation-secret limit
TRUSTED_PROXY_HOPS=0              # Adjust if behind a reverse proxy
```

Rate limiting fails open: if Redis is unreachable, requests are allowed
through and a warning is logged, rather than taking the API down.

## Limited Endpoints

- `POST /api/v1/content/generate` — 20 per minute
- `POST /api/v1/content/suggest` — 20 per minute
- `POST /api/v1/content/regenerate` — 20 per minute
- `POST /api/v1/projects/{id}/trends/collect` — 20 per minute
- `POST /api/v1/analytics/{id}/coach` — 20 per minute
- `POST /automation/jobs/{id}` — 60 per minute (automation secret)

## Response Headers

When rate-limited, the API includes:

- `RateLimit-Limit` — Maximum requests in window
- `RateLimit-Remaining` — Requests left in current window
- `RateLimit-Reset` — Unix timestamp when limit resets
- `Retry-After` — Seconds to wait before retrying (on 429)

The `X-RateLimit-*` aliases are also sent for compatibility with older
clients and automation tools (e.g. n8n) that only look for the `X-`
prefixed headers.

## Example: Rate Limited Response

```
HTTP/1.1 429 Too Many Requests
RateLimit-Limit: 20
RateLimit-Remaining: 0
RateLimit-Reset: 1693000660
Retry-After: 45

{
  "detail": "Rate limit exceeded for content.generate. Try again shortly."
}
```

## Behavior When Rate Limited

1. The caller receives `429 Too Many Requests`.
2. The response includes a `Retry-After` header with seconds to wait.
3. Further requests within the same window also fail with `429`.
4. The counter resets after `RATE_LIMIT_WINDOW_SECONDS`.

## Identity

- Authenticated (JWT) routes are limited per user ID.
- Automation routes are limited per hashed `X-Automation-Secret`.
- Unauthenticated/machine routes without a secret fall back to client IP,
  resolved via `X-Forwarded-For` only as far as `TRUSTED_PROXY_HOPS`
  indicates the deployment's own reverse-proxy chain is trusted.
