# celery_beat.py
# ---------------------------------------------------------------------------
# FEATURE 4: Celery Beat Schedule Configuration (RedBeat)
#
# Uses RedBeat — a Redis-backed scheduler for Celery Beat — so that
# schedules persist across container restarts (no file-based schedule).
#
# SCHEDULED TASKS:
#   - `rerun_validations`: Runs weekly. Finds all completed validations
#     that are due for a re-run and dispatches them for temporal tracking.
#
# HOW IT WORKS:
#   RedBeat stores the schedule in Redis under `redbeat:` prefixed keys.
#   When Celery Beat starts with `--scheduler=redbeat.RedBeatScheduler`,
#   it reads the schedule from Redis instead of a local file. This means:
#   - Container restarts don't wipe the schedule.
#   - Multiple Beat instances won't conflict (RedBeat uses Redis locks).
#   - Schedule state (last_run_at, total_run_count) is persisted.
#
# CONFIGURATION: This module is imported by the Celery worker at startup
# via the `celery_app.conf.beat_schedule` setting.
# ---------------------------------------------------------------------------

from __future__ import annotations

from celery.schedules import crontab

from app.core.config import settings


# =====================================================================
# BEAT SCHEDULE CONFIGURATION
#
# Imported and applied in celery_tasks.py via:
#   celery_app.conf.update(beat_schedule=BEAT_SCHEDULE, ...)
# =====================================================================

BEAT_SCHEDULE = {
    # ── Weekly validation re-run for temporal tracking ────────────────
    # Runs every Sunday at 2:00 AM UTC.
    # Finds all completed validations that haven't been re-run in 7+ days
    # and dispatches them through the full pipeline again.
    "rerun-validations-weekly": {
        "task": "app.worker.celery_tasks.rerun_due_validations",
        "schedule": crontab(
            hour=2,
            minute=0,
            day_of_week="sunday",
        ),
        "options": {
            "queue": "default",
            "priority": 3,  # Low priority — batch re-runs shouldn't block live requests
        },
    },
}


# =====================================================================
# REDBEAT CONFIGURATION
#
# Applied to the Celery app in celery_tasks.py.
# =====================================================================

REDBEAT_CONFIG = {
    # RedBeat uses this Redis URL for schedule persistence
    "redbeat_redis_url": settings.CELERY_REDBEAT_REDIS_URL,

    # Lock timeout: how long a Beat instance holds the leader lock.
    # Only one Beat process runs tasks at a time (leader election).
    "redbeat_lock_timeout": 300,  # 5 minutes

    # Key prefix in Redis — avoids collisions with application keys
    "redbeat_key_prefix": "redbeat:",
}
