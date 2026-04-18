# redis_listener.py
from __future__ import annotations

# BUG FIX: `from __future__ import annotations` enables PEP 563 postponed
# evaluation of annotations. This makes `redis.Redis | None` and all other
# union-syntax annotations valid as string literals at parse time, so the
# file runs correctly on Python 3.9 without a TypeError. It is the least-
# invasive fix: no import changes, no Optional[] rewrites needed anywhere.

import json
import asyncio
import redis.asyncio as redis
from app.websockets.manager import ConnectionManager
from app.core.config import settings

_RECONNECT_DELAY = 5.0


async def _cleanup(pubsub: redis.client.PubSub | None, redis_client: redis.Redis | None) -> None:
    """
    Safely tears down a pubsub subscription and Redis connection.
    Called from the finally block and before the reconnect sleep.
    Wrapped in broad try/except so cleanup errors never mask the original error.
    """
    if pubsub is not None:
        try:
            await pubsub.unsubscribe("validation_events")
            await pubsub.aclose()
        except Exception:
            pass
    if redis_client is not None:
        try:
            await redis_client.aclose()
        except Exception:
            pass


async def listen_to_redis(manager: ConnectionManager) -> None:
    """
    Long-running background task that connects to Redis Pub/Sub, listens on
    the 'validation_events' channel, and dispatches events to connected
    WebSocket clients via the ConnectionManager.

    BUGS FIXED IN THIS VERSION:
    1. Python 3.9 compatibility: `redis.Redis | None` union syntax now works
       via `from __future__ import annotations` at the top of this file.

    2. Cleanup-before-sleep: The original slept for _RECONNECT_DELAY inside
       `except Exception` while the broken pubsub/redis_client were still open.
       Those objects stayed unclosed for the full sleep window. We now call
       _cleanup() eagerly before sleeping so resources are freed immediately.

    3. CancelledError-safe finally: During uvicorn shutdown, a second
       CancelledError can be delivered while awaiting cleanup inside `finally`,
       propagating uncaught and producing a messy traceback. The finally block
       now wraps cleanup in `asyncio.shield()` to protect it from cancellation,
       with a broad except as a last-resort guard.
    """
    while True:
        redis_client: redis.Redis | None = None
        pubsub: redis.client.PubSub | None = None
        try:
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            pubsub = redis_client.pubsub()
            await pubsub.subscribe("validation_events")
            print("Redis listener: subscribed to 'validation_events'.")

            async for raw_message in pubsub.listen():
                if raw_message.get("type") != "message":
                    continue

                data_str = raw_message.get("data")
                if not data_str:
                    continue

                try:
                    data = json.loads(data_str)
                except json.JSONDecodeError as exc:
                    print(f"Redis listener: malformed JSON payload skipped: {exc}")
                    continue

                validation_id = data.get("validation_id")
                if validation_id:
                    await manager.send_update(validation_id, data)

        except asyncio.CancelledError:
            print("Redis listener: shutdown signal received. Exiting.")
            # BUG FIX: Clean up immediately before breaking, rather than
            # relying solely on the finally block which may itself be cancelled.
            await _cleanup(pubsub, redis_client)
            pubsub = None
            redis_client = None
            break

        except Exception as e:
            print(f"Redis listener: connection error — {e}. Retrying in {_RECONNECT_DELAY}s.")
            # BUG FIX: Clean up the broken connection BEFORE sleeping so we
            # don't hold open socket/file descriptors during the wait window.
            await _cleanup(pubsub, redis_client)
            pubsub = None
            redis_client = None
            await asyncio.sleep(_RECONNECT_DELAY)

        finally:
            # BUG FIX: Wrap cleanup in asyncio.shield() so a second CancelledError
            # delivered during shutdown (e.g. uvicorn's hard timeout) cannot
            # interrupt the await inside _cleanup() and propagate uncaught from
            # a finally block, which produces an unhandled exception traceback.
            # If pubsub/redis_client are already None (cleaned up above), _cleanup
            # is a cheap no-op.
            try:
                await asyncio.shield(_cleanup(pubsub, redis_client))
            except Exception:
                pass