# circuit_breaker.py
# ---------------------------------------------------------------------------
# REFINEMENT 2: Circuit Breaker pattern for external API calls.
#
# When chaining Firecrawl → Gemini → Groq, a slow/dead upstream can
# cascade into task queue pile-up. The circuit breaker:
#
#   CLOSED  → Requests flow normally (tracking failures)
#   OPEN    → Requests fail-fast immediately (no waiting for timeout)
#   HALF    → One probe request allowed; success → CLOSED, fail → OPEN
#
# State is stored in Redis so it's shared across Celery workers.
# Each external service gets its own breaker instance.
# ---------------------------------------------------------------------------

from __future__ import annotations

import logging
import time
from typing import Any, Callable, TypeVar, Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default thresholds
DEFAULT_FAILURE_THRESHOLD = 3    # Consecutive failures to trip
DEFAULT_RECOVERY_TIMEOUT = 60    # Seconds before half-open probe
DEFAULT_CALL_TIMEOUT = 30        # Seconds per external call


class CircuitOpenError(Exception):
    """Raised when the circuit is OPEN and calls are being rejected."""
    def __init__(self, service: str, retry_after: float):
        self.service = service
        self.retry_after = retry_after
        super().__init__(
            f"Circuit breaker OPEN for '{service}'. "
            f"Retry after {retry_after:.0f}s."
        )


class CircuitBreaker:
    """
    Thread-safe, Redis-backed circuit breaker.

    Usage:
        breaker = CircuitBreaker("firecrawl_scrape")
        result = breaker.call(lambda: app.scrape_url(...))
    """

    def __init__(
        self,
        service_name: str,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        recovery_timeout: int = DEFAULT_RECOVERY_TIMEOUT,
        redis_url: str | None = None,
    ):
        self.service = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self._redis_url = redis_url or settings.REDIS_URL
        self._redis: redis.Redis | None = None

    def _get_redis(self) -> redis.Redis:
        if self._redis is None:
            self._redis = redis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    @property
    def _state_key(self) -> str:
        return f"cb:{self.service}:state"

    @property
    def _failures_key(self) -> str:
        return f"cb:{self.service}:failures"

    @property
    def _last_failure_key(self) -> str:
        return f"cb:{self.service}:last_failure"

    def _get_state(self) -> str:
        """Returns 'closed', 'open', or 'half_open'."""
        try:
            r = self._get_redis()
            state = r.get(self._state_key)
            if state == "open":
                # Check if recovery timeout elapsed → half-open
                last_fail = float(r.get(self._last_failure_key) or 0)
                if time.time() - last_fail >= self.recovery_timeout:
                    return "half_open"
                return "open"
            return state or "closed"
        except Exception:
            return "closed"  # Redis down → fail-open (allow calls)

    def _record_success(self) -> None:
        """Resets the breaker to CLOSED on success."""
        try:
            r = self._get_redis()
            pipe = r.pipeline()
            pipe.set(self._state_key, "closed")
            pipe.set(self._failures_key, "0")
            pipe.execute()
        except Exception:
            pass

    def _record_failure(self) -> None:
        """Increments failure count. Trips to OPEN if threshold reached."""
        try:
            r = self._get_redis()
            failures = r.incr(self._failures_key)
            r.set(self._last_failure_key, str(time.time()))

            if failures >= self.failure_threshold:
                r.set(self._state_key, "open")
                logger.warning(
                    "[CircuitBreaker] 🔴 OPEN: '%s' after %d consecutive failures.",
                    self.service, failures,
                )
        except Exception:
            pass

    def call(self, fn: Callable[[], T], fallback: Optional[Callable[[], T]] = None) -> T:
        """
        Executes fn() through the circuit breaker.

        Args:
            fn: The function to call (should be a lambda/closure).
            fallback: Optional fallback function if circuit is OPEN.

        Returns:
            Result of fn() or fallback().

        Raises:
            CircuitOpenError: If circuit is OPEN and no fallback provided.
        """
        state = self._get_state()

        if state == "open":
            last_fail = 0.0
            try:
                last_fail = float(self._get_redis().get(self._last_failure_key) or 0)
            except Exception:
                pass
            retry_after = max(0, self.recovery_timeout - (time.time() - last_fail))

            logger.info("[CircuitBreaker] ⏭️ Fast-fail for '%s' (OPEN).", self.service)
            if fallback:
                return fallback()
            raise CircuitOpenError(self.service, retry_after)

        # CLOSED or HALF_OPEN → try the call
        try:
            result = fn()
            self._record_success()
            if state == "half_open":
                logger.info("[CircuitBreaker] 🟢 CLOSED: '%s' recovered.", self.service)
            return result

        except Exception as e:
            self._record_failure()
            if state == "half_open":
                logger.warning("[CircuitBreaker] 🔴 '%s' still failing in half-open.", self.service)

            if fallback:
                logger.info("[CircuitBreaker] Using fallback for '%s'.", self.service)
                return fallback()
            raise

    def reset(self) -> None:
        """Manually resets the circuit to CLOSED."""
        try:
            r = self._get_redis()
            r.delete(self._state_key, self._failures_key, self._last_failure_key)
        except Exception:
            pass


# =====================================================================
# PRE-CONFIGURED BREAKERS for each external service
# =====================================================================

firecrawl_breaker = CircuitBreaker(
    "firecrawl",
    failure_threshold=3,
    recovery_timeout=120,  # 2 min cooldown for Firecrawl
)

gemini_breaker = CircuitBreaker(
    "gemini",
    failure_threshold=3,
    recovery_timeout=60,
)

groq_breaker = CircuitBreaker(
    "groq",
    failure_threshold=5,    # Groq has generous free tier, higher threshold
    recovery_timeout=30,
)
