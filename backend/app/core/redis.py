from collections.abc import Generator

import redis
from fastapi import HTTPException, status
from redis import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

settings = get_settings()

redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


class RedisUnavailableError(HTTPException):
    """Raised when Redis is required for an auth operation but unreachable.

    Auth depends on Redis for token blacklist checks — fail clearly with 503
    rather than crashing as an unhandled 500 (Constitution §22).
    """

    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session store unavailable. Please try again shortly.",
        )


def get_redis() -> Generator[Redis, None, None]:
    yield redis_client


def ping_redis() -> bool:
    try:
        return bool(redis_client.ping())
    except RedisError:
        return False


def blacklist_token(jti: str, expires_in_seconds: int) -> None:
    if expires_in_seconds <= 0:
        expires_in_seconds = 1
    try:
        redis_client.setex(f"auth:blacklist:{jti}", expires_in_seconds, "1")
    except RedisError as exc:
        raise RedisUnavailableError() from exc


def is_token_blacklisted(jti: str) -> bool:
    try:
        return redis_client.exists(f"auth:blacklist:{jti}") == 1
    except RedisError as exc:
        raise RedisUnavailableError() from exc
