# realtime_groups/backend/workers/celery_app.py
# ---------------------------------------------------------------------------
# Celery application instance for the realtime_groups module.
# Shares the same RabbitMQ broker and Redis backend as the main app.
# ---------------------------------------------------------------------------

from celery import Celery
from realtime_groups.backend.core.config import social_settings

social_celery = Celery(
    "social_worker",
    broker=social_settings.CELERY_BROKER_URL,
    backend=social_settings.CELERY_RESULT_BACKEND,
    include=["realtime_groups.backend.workers.celery_tasks"],
)

import os

social_celery.conf.update(
    task_always_eager=os.environ.get("CELERY_TASK_ALWAYS_EAGER", "0") == "1",
    broker_connection_retry_on_startup=True,
    task_queues={
        "social": {
            "exchange": "social",
            "routing_key": "social",
        },
    },
    task_default_queue="social",
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)
