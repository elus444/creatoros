from collections.abc import Generator

import redis
from redis import Redis

from app.core.config import get_settings

settings = get_settings()

redis_client = redis.Redis.from_url(
    settings.redis_url,
    decode_responses=True,
)


def get_redis() -> Generator[Redis, None, None]:
    yield redis_client


def ping_redis() -> bool:
    return bool(redis_client.ping())


def blacklist_token(jti: str, expires_in_seconds: int) -> None:
    if expires_in_seconds <= 0:
        expires_in_seconds = 1
    redis_client.setex(f"auth:blacklist:{jti}", expires_in_seconds, "1")


def is_token_blacklisted(jti: str) -> bool:
    return redis_client.exists(f"auth:blacklist:{jti}") == 1
