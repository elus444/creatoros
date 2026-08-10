import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import auth, content, health, projects, trends
from app.core.config import get_settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("creatoros")

settings = get_settings()

app = FastAPI(
    title="creatoros API",
    version="0.1.0",
    description="AI content business automation platform",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.api_v1_prefix)
app.include_router(auth.router, prefix=settings.api_v1_prefix)
app.include_router(projects.router, prefix=settings.api_v1_prefix)
app.include_router(trends.router, prefix=settings.api_v1_prefix)
app.include_router(content.router, prefix=settings.api_v1_prefix)


@app.get("/")
def root() -> dict:
    return {"name": "creatoros", "status": "running"}
