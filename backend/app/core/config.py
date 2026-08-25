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
    access_token_expire_minutes: int = 60 * 24 * 30  # 30 days; /auth/me also slides the JWT

    cors_origins: str = "http://localhost:3000"

    # Trend collectors (M2). Google Trends has no official keyword-scoped
    # API and needs no credentials — it uses the public daily-trends RSS
    # feed (see services/collectors/google_trends_collector.py). YouTube
    # requires a real Data API v3 key; if unset, that collector is skipped
    # with a warning rather than faking data.
    google_trends_geo: str = "US"
    youtube_api_key: str | None = None

    # LLM (M3). All agents call Gemini's generateContent REST API through
    # llm_service — never directly. If unset, generation fails clearly via
    # LLMNotConfiguredError rather than faking a response.
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash-lite-latest"

    # Automation (M5). Shared secret for n8n -> FastAPI webhook calls.
    # If unset, automation endpoints fail clearly with 503 rather than
    # running open. Sent as header X-Automation-Secret.
    n8n_webhook_secret: str | None = None
    # How long Redis keeps job records / idempotency keys (seconds).
    automation_job_ttl_seconds: int = 60 * 60 * 24
    # A job stuck in "running" for longer than this (no update) is assumed
    # to have lost its worker (process restart/crash) and is auto-reaped to
    # "failed" the next time it is read, rather than staying "running"
    # forever with nothing able to retry it.
    automation_job_stale_seconds: int = 60 * 30
    # Optional outbound webhook n8n can listen on for job-completion
    # notifications (generation done, publish done, coach done, trend
    # collect done — success or failure). Sent as a signed POST using the
    # same N8N_WEBHOOK_SECRET as the X-Automation-Secret header, so n8n can
    # verify the call actually came from this backend. If unset, no
    # outbound notifications are sent — inbound polling via
    # GET /automation/jobs/{id} still works either way.
    n8n_notify_webhook_url: str | None = None
    n8n_notify_timeout_seconds: float = 10.0

    # Video generation. Default none — never fake videos.
    # json2video (recommended free tier): narrated Shorts with Azure TTS audio.
    #   VIDEO_GENERATION_PROVIDER=json2video + JSON2VIDEO_API_KEY
    # Replicate: silent diffusion clips (paid credits).
    #   VIDEO_GENERATION_PROVIDER=replicate + REPLICATE_API_TOKEN
    # Keys stay on the backend only — never expose to the frontend.
    video_generation_provider: str = "none"
    video_generation_api_key: str | None = None
    video_generation_api_url: str | None = None
    replicate_api_token: str | None = None
    json2video_api_key: str | None = None
    json2video_voice: str = "en-US-AnaNeural"  # child-friendly Azure voice
    json2video_image_model: str = "flux-schnell"  # unused for Shorts; kept for compat
    json2video_video_model: str = "seedance-v1.5-pro"  # JSON2Video text-to-video fallback
    video_content_style: str = "kids"  # kids | general — drives visual + narration style

    # Storage for video assets (not Postgres). Use supabase for hosted videos.
    storage_backend: str = "local"
    storage_local_path: str = "storage"
    storage_public_base_url: str = "http://127.0.0.1:8000/media"
    supabase_url: str | None = None
    # Secret/service key for Storage admin + private uploads (backend only).
    supabase_secret_key: str | None = None
    # Back-compat alias; prefer SUPABASE_SECRET_KEY.
    supabase_key: str | None = None
    supabase_publishable_key: str | None = None

    # YouTube OAuth (publishing). Separate from YOUTUBE_API_KEY (trends).
    youtube_oauth_client_id: str | None = None
    youtube_oauth_client_secret: str | None = None
    youtube_oauth_redirect_uri: str | None = None
    # Where the OAuth callback sends the browser after Google (never include tokens).
    frontend_url: str = "http://localhost:3000"

    # Rate limiting (M7). Fixed-window counters in Redis for expensive routes.
    rate_limit_enabled: bool = True
    rate_limit_window_seconds: int = 60
    rate_limit_user_max: int = 20
    rate_limit_automation_max: int = 60
    # Number of trusted reverse-proxy hops in front of this app (e.g. 1 for
    # a single nginx/ALB in front of uvicorn). X-Forwarded-For is a
    # client-settable header — an app that blindly trusts it lets any
    # client spoof their rate-limit identity and dodge limits entirely.
    # Default 0 means "no trusted proxy": always rate-limit by the actual
    # TCP peer address and ignore X-Forwarded-For. Only raise this above 0
    # if your proxy is configured to strip/overwrite any client-supplied
    # X-Forwarded-For before appending its own hop.
    trusted_proxy_hops: int = 0

    # List query caps to avoid unbounded responses (M7).
    max_list_items: int = 200

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [
            origin.strip()
            for origin in self.cors_origins.split(",")
            if origin.strip()
        ]
        if self.is_production and ("*" in origins or not origins):
            raise ValueError(
                "CORS_ORIGINS must list explicit frontend origin(s) in production "
                "(wildcard '*' is not allowed for authenticated APIs)."
            )
        return origins

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}

    def validate_for_runtime(self) -> None:
        """Fail fast on unsafe production defaults (M7)."""
        if not self.is_production:
            return
        weak = {
            "",
            "change-me-to-a-long-random-secret-in-production",
            "changeme",
            "secret",
        }
        if self.jwt_secret.strip().lower() in weak or len(self.jwt_secret) < 32:
            raise ValueError(
                "JWT_SECRET must be a strong secret (>=32 chars) in production."
            )
        # Touch CORS validation
        _ = self.cors_origin_list
        if self.storage_backend.strip().lower() == "local":
            raise ValueError(
                "STORAGE_BACKEND=local is not allowed in production. The "
                "local backend serves every generated video from an "
                "unauthenticated /media static mount — any user's video URL "
                "is publicly guessable with no per-user access control. Set "
                "STORAGE_BACKEND=supabase (which serves videos via signed, "
                "owner-scoped URLs) and configure SUPABASE_URL / "
                "SUPABASE_SECRET_KEY before deploying."
            )


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.validate_for_runtime()
    return settings
