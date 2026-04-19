# realtime_groups/backend/core/config.py
# ---------------------------------------------------------------------------
# Extends the base StartupScope settings with social/realtime-specific
# environment variables. Both modules share the same .env file.
# ---------------------------------------------------------------------------

from pydantic_settings import BaseSettings, SettingsConfigDict


class SocialSettings(BaseSettings):
    """
    All configuration required by the realtime_groups backend module.
    Reads from the same .env file as the main StartupScope app.
    """
    # ── Supabase ─────────────────────────────────────────────────────────────
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # ── AI Providers ──────────────────────────────────────────────────────────
    GEMINI_API_KEY: str       # Gemini 2.0 Flash — Thread Synthesis
    GROQ_API_KEY: str         # Groq llama-3.3-70b — AI Moderation

    # ── Celery / Redis (shared infrastructure) ─────────────────────────────
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5673/"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6380/1"
    REDIS_URL: str = "redis://localhost:6380/0"

    # ── Reputation Tuning ────────────────────────────────────────────────────
    KARMA_UPVOTE: int = 5          # Karma awarded to author when their idea is upvoted
    KARMA_COMMENT: int = 2         # Karma awarded for leaving a helpful comment
    KARMA_POST: int = 3            # Karma awarded for publishing to the Arena
    SERIAL_BUILDER_THRESHOLD: int = 5  # # of public posts to earn "Serial Builder" badge

    # ── AI Moderation ────────────────────────────────────────────────────────
    MODERATION_TOXICITY_THRESHOLD: float = 0.80  # 0.0–1.0 score above which auto-hide fires
    MODERATION_KARMA_PENALTY: int = -10          # Karma deducted on confirmed toxic content

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


social_settings = SocialSettings()
