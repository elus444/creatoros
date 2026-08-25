from fastapi import APIRouter
from sqlalchemy import text

from app.api.deps import DBSession
from app.core.redis import ping_redis

router = APIRouter(tags=["health"])


@router.get("/health")
def health(db: DBSession) -> dict:
    """Readiness-style check used by the app and local smoke tests.

    Reports dependency status as ok/error strings only — never connection
    URLs, credentials, or exception details.
    """
    database = "ok"
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        database = "error"

    redis_status = "ok" if ping_redis() else "error"
    overall = "ok" if database == "ok" and redis_status == "ok" else "degraded"
    return {
        "status": overall,
        "service": "creatoros",
        "database": database,
        "redis": redis_status,
    }


@router.get("/health/live")
def liveness() -> dict:
    """Liveness: process is up (no DB/Redis)."""
    return {"status": "ok", "service": "creatoros"}


@router.get("/health/ready")
def readiness(db: DBSession) -> dict:
    """Readiness: dependencies must be healthy for traffic."""
    try:
        db.execute(text("SELECT 1"))
        database = "ok"
    except Exception:
        database = "error"
    redis_status = "ok" if ping_redis() else "error"
    ready = database == "ok" and redis_status == "ok"
    body = {
        "status": "ok" if ready else "unavailable",
        "service": "creatoros",
        "database": database,
        "redis": redis_status,
    }
    if not ready:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=body)
    return body
