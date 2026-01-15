from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DBSession
from app.core.redis import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: DBSession) -> dict:
    db.execute(text("SELECT 1"))
    redis_ok = ping_redis()
    return {
        "status": "ok",
        "service": "creatoros",
        "database": "ok",
        "redis": "ok" if redis_ok else "error",
    }
