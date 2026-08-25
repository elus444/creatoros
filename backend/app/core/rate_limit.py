"""Simple Redis-backed rate limiting for expensive MVP endpoints (M7).

Approach: fixed-window counter per identity key.
  ratelimit:{scope}:{identity}  INCR + EXPIRE on first hit

Identity is typically user UUID (JWT routes) or a hashed automation
credential / client IP for machine routes. Fail-open if Redis is down
so a Redis outage does not take down the whole API — but log a warning.
"""

from __future__ import annotations

import hashlib
import logging
import time

from fastapi import HTTPException, Request, status

from app.core.config import get_settings
from app.core.redis import redis_client
from app.models.user import User

logger = logging.getLogger("creatoros.ratelimit")


def check_rate_limit(scope: str, identity: str, *, limit: int, window_seconds: int) -> None:
    settings = get_settings()
    if not settings.rate_limit_enabled:
        return
    key = f"ratelimit:{scope}:{identity}"
    try:
        count = int(redis_client.incr(key))
        if count == 1:
            redis_client.expire(key, window_seconds)
        try:
            ttl = redis_client.ttl(key)
        except AttributeError:
            ttl = None
        reset_in = ttl if isinstance(ttl, int) and ttl > 0 else window_seconds
        if count > limit:
            # RFC 6585 style headers, plus the widely-supported X-* aliases,
            # so clients (and n8n) can back off intelligently instead of
            # just retrying blind.
            headers = {
                "Retry-After": str(reset_in),
                "RateLimit-Limit": str(limit),
                "RateLimit-Remaining": "0",
                "RateLimit-Reset": str(int(time.time()) + reset_in),
                "X-RateLimit-Limit": str(limit),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(int(time.time()) + reset_in),
            }
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for {scope}. Try again shortly.",
                headers=headers,
            )
    except HTTPException:
        raise
    except Exception:
        logger.warning(
            "Rate limit check failed for scope=%s (fail-open)", scope, exc_info=True
        )


def identity_for_user(user: User) -> str:
    return f"user:{user.id}"


def _client_ip(request: Request) -> str:
    """Resolve the request's IP for rate-limit identity.

    X-Forwarded-For is attacker-controlled input: any client can send
    `X-Forwarded-For: 1.2.3.4` and, if trusted blindly, get a fresh
    rate-limit bucket on every request. We only trust it as far as
    TRUSTED_PROXY_HOPS says our own reverse-proxy chain is deep, and even
    then we take the hop *our* proxy actually appended (the Nth-from-the-
    right entry), never whatever the client put at the front.
    """
    hops = get_settings().trusted_proxy_hops
    if hops > 0:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            chain = [part.strip() for part in forwarded.split(",") if part.strip()]
            if len(chain) >= hops:
                return chain[-hops]
    return request.client.host if request.client else "unknown"


def identity_for_request(request: Request) -> str:
    secret = request.headers.get("X-Automation-Secret")
    if secret:
        digest = hashlib.sha256(secret.encode("utf-8")).hexdigest()[:24]
        return f"auto:{digest}"
    return f"ip:{_client_ip(request)}"


def enforce_user_limit(scope: str, user: User) -> None:
    settings = get_settings()
    check_rate_limit(
        scope,
        identity_for_user(user),
        limit=settings.rate_limit_user_max,
        window_seconds=settings.rate_limit_window_seconds,
    )


def enforce_request_limit(scope: str, request: Request) -> None:
    settings = get_settings()
    check_rate_limit(
        scope,
        identity_for_request(request),
        limit=settings.rate_limit_automation_max,
        window_seconds=settings.rate_limit_window_seconds,
    )
