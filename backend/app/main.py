import logging

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import (
    analytics,
    auth,
    automation,
    content,
    health,
    integrations,
    projects,
    trends,
    youtube,
)
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("creatoros")

settings = get_settings()

app = FastAPI(
    title="creatoros API",
    version="0.7.0",
    description=(
        "AI content business automation platform. "
        "Authenticate with Bearer JWT for user APIs; "
        "automation routes use header X-Automation-Secret. "
        "See /docs and docs/n8n-integration.md."
    ),
)

# Serve locally stored generated videos at STORAGE_PUBLIC_BASE_URL path (/media).
_media_root = Path(settings.storage_local_path)
_media_root.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(_media_root)), name="media")

# Never use allow_origins=["*"] with credentials for production APIs.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Automation-Secret", "Idempotency-Key"],
)

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(projects.router, prefix=settings.api_v1_prefix)
app.include_router(trends.router, prefix=settings.api_v1_prefix)
app.include_router(content.router, prefix=settings.api_v1_prefix)
app.include_router(automation.router, prefix=settings.api_v1_prefix)
app.include_router(analytics.router, prefix=settings.api_v1_prefix)
app.include_router(integrations.router, prefix=settings.api_v1_prefix)
app.include_router(youtube.router, prefix=settings.api_v1_prefix)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    # Keep 422 for malformed input — never promote validation issues to 500.
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        # Pydantic error contexts can include exception instances (for
        # example from a field_validator). JSONResponse cannot serialize
        # those directly; use FastAPI's encoder so invalid input remains a
        # valid 422 response rather than becoming an unrelated 500.
        content={"detail": jsonable_encoder(exc.errors())},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # HTTPException must keep its status/detail — do not collapse to 500.
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )
    # Do not leak stack traces, paths, or secrets to clients.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected error occurred. Please try again."},
    )


@app.get("/")
def root() -> dict:
    return {"name": "creatoros", "status": "running"}


@app.get("/health")
def root_liveness() -> dict:
    """Platform liveness probe (no dependency checks)."""
    return {"status": "ok"}
