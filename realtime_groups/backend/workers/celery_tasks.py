# realtime_groups/backend/workers/celery_tasks.py
# ---------------------------------------------------------------------------
# Celery tasks for the realtime_groups module.
#
# TASK: moderate_content_task
#   - Triggered by the Supabase DB webhook via synthesis_router.py
#   - Calls ai_moderator.moderate_content() to score the content
#   - Auto-hides toxic/spam content and applies karma penalties
#
# To run the social worker:
#   celery -A realtime_groups.backend.workers.celery_tasks worker \
#       --loglevel=info -Q social --concurrency=4
# ---------------------------------------------------------------------------

import logging
from celery import Task

from realtime_groups.backend.workers.celery_app import social_celery
from realtime_groups.backend.services.ai_moderator import moderate_content

logger = logging.getLogger(__name__)


class BaseTask(Task):
    """Base task class with structured error logging."""
    abstract = True

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error(
            "[SocialWorker] Task %s failed | id=%s | error=%s",
            self.name, task_id, exc,
        )


@social_celery.task(
    bind=True,
    base=BaseTask,
    name="social.moderate_content",
    max_retries=3,
    default_retry_delay=10,   # seconds between retries
    autoretry_for=(Exception,),
    retry_backoff=True,
)
def moderate_content_task(
    self,
    content: str,
    table: str,
    record_id: str,
    author_id: str,
) -> dict:
    """
    Async Celery task that runs AI moderation on a message or comment.

    Called by synthesis_router.moderation_webhook() after a Supabase DB event.
    Automatically retries up to 3 times with exponential backoff on any failure.

    Args:
        content:   The raw text content to moderate.
        table:     "messages" or "comments".
        record_id: UUID of the row to potentially hide.
        author_id: UUID of the content author (for karma penalties).

    Returns:
        Moderation result dict with verdict, scores, and action_taken.
    """
    logger.info(
        "[ModerationTask] Processing %s record=%s author=%s",
        table, record_id, author_id,
    )
    result = moderate_content(
        content=content,
        table=table,
        record_id=record_id,
        author_id=author_id,
    )
    logger.info(
        "[ModerationTask] Completed record=%s verdict=%s action=%s",
        record_id, result.get("verdict"), result.get("action_taken"),
    )
    return result
