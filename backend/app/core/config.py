from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "creatoros"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"

    # Default matches docker-compose.yml's host port remap (5434) used to
    # avoid colliding with a native Windows Postgres on 5432.
    database_url: str = (
        "postgresql+psycopg://creatoros:creatoros_dev_password@localhost:5434/creatoros"
    )
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me-to-a-long-random-secret-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    cors_origins: str = "http://localhost:3000"

    # Trend collectors (M2). Google Trends has no official keyword-scoped
    # API and needs no credentials — it uses the public daily-trends RSS
    # feed (see services/collectors/google_trends_collector.py). YouTube
    # requires a real Data API v3 key; if unset, that collector is skipped
    # with a warning rather than faking data.
    google_trends_geo: str = "US"
    youtube_api_key: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
