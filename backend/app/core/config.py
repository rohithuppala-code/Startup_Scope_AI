# config.py

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_SERVICE_ROLE_KEY: str

    # External API keys
    FIRECRAWL_API_KEY: str
    GEMINI_API_KEY: str

    # Redis
    REDIS_URL: str = "redis://localhost:6380/0"

    # RabbitMQ / Celery
    CELERY_BROKER_URL: str = "amqp://guest:guest@localhost:5673/"

    # BUG FIX: Added CELERY_RESULT_BACKEND.
    # Without a result backend Celery logs persistent warnings on every
    # send_task() call, and task state (SUCCESS / FAILURE) cannot be retrieved.
    # We reuse Redis for simplicity; this matches the cache layer already
    # present in the architecture.
    CELERY_RESULT_BACKEND: str = "redis://localhost:6380/1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()