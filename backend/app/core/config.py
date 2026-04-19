# config.py
# ---------------------------------------------------------------------------
# Central configuration loaded from environment variables.
# All secrets and connection strings are validated at startup via Pydantic.
# ---------------------------------------------------------------------------

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # ── Supabase ──────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # ── External AI Providers ─────────────────────────────────────────────
    FIRECRAWL_API_KEY: str
    GEMINI_API_KEY: str
    GROQ_API_KEY: str  # Feature 1: Multi-model consensus (Llama 3.1 70B)

    # ── Reddit API (Feature 7 — Social Sentiment) ────────────────────────
    # Empty string = Reddit disabled. Set to your OAuth2 app credentials
    # from https://www.reddit.com/prefs/apps to enable live sentiment.
    REDDIT_CLIENT_ID: str = ""
    REDDIT_CLIENT_SECRET: str = ""
    REDDIT_USER_AGENT: str = "StartupScopeAI/1.0"

    # ── Redis ─────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://localhost:6380/0"

    # ── RabbitMQ / Celery ─────────────────────────────────────────────────
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5673/"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6380/1"

    # ── Celery Beat (RedBeat — Redis-backed schedule store) ───────────────
    # Uses the same Redis instance as the cache layer (DB 0).
    # RedBeat keys are prefixed with `redbeat:` to avoid collisions.
    CELERY_REDBEAT_REDIS_URL: str = "redis://localhost:6380/0"

    # ── Feature 19: AI Cost Control ──────────────────────────────────────
    DAILY_COST_CAP: float = 5.00  # Max daily AI spend per user (USD)

    # ── Feature 20: Outbound Webhooks ────────────────────────────────────
    # Global webhook URL + secret. Per-user config can override these.
    WEBHOOK_URL: str = ""
    WEBHOOK_SECRET: str = ""

    # ── Feature 18: OpenTelemetry Observability ──────────────────────────
    # OTLP gRPC endpoint (e.g., "http://jaeger:4317"). Empty = console.
    OTEL_EXPORTER_OTLP_ENDPOINT: str = ""
    ENVIRONMENT: str = "development"

    # ── Feature 16: SMTP for Smart Alerts ────────────────────────────────
    # Empty = mock mode (prints to stdout). Set to enable real emails.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASS: str = ""
    SMTP_FROM: str = "alerts@startupscope.ai"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()