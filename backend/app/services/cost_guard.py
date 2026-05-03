# cost_guard.py
# ---------------------------------------------------------------------------
# FEATURE 19: AI Cost Control
#
# Atomic per-user daily spend tracking using Redis INCRBYFLOAT.
# Prevents runaway costs by enforcing a configurable daily cap.
#
# DESIGN:
#   1. ESTIMATE: Before any LLM call, use tiktoken to count prompt tokens
#      and compute the estimated cost using the model's pricing table.
#   2. CHECK: Atomically increment the user's daily spend in Redis.
#      If the new total exceeds DAILY_COST_CAP → raise CostLimitExceeded.
#   3. CHARGE: After the LLM call completes, reconcile with actual tokens.
#      If the estimate was wrong, adjust the Redis counter.
#
# ATOMICITY: Redis INCRBYFLOAT is atomic — no race conditions between
# concurrent Celery workers billing the same user.
#
# KEY SCHEMA:
#   cost:{user_id}:{YYYY-MM-DD} → float (daily cumulative spend in USD)
#   Keys auto-expire at midnight UTC (TTL = seconds until end of day).
#
# PRICING TABLE (as of 2025):
#   - Gemini 2.0 Flash:  $0.10 / 1M input, $0.40 / 1M output
#   - Gemini 1.5 Flash:  $0.075 / 1M input, $0.30 / 1M output
#   - Groq Llama 3.1 70B: Free tier (effectively $0)
#   - Gemini embedding:  $0.00 (free tier for text-embedding-004)
# ---------------------------------------------------------------------------

from __future__ import annotations

from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple

import redis
import tiktoken

from app.core.config import settings


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Default daily cost cap per user (in USD).
# Override via DAILY_COST_CAP env var if needed.
DAILY_COST_CAP: float = float(getattr(settings, "DAILY_COST_CAP", 5.00))


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------

class CostLimitExceeded(Exception):
    """
    Raised when a user's daily AI spend exceeds the configured cap.

    FastAPI can catch this and return HTTP 429 Too Many Requests.
    """
    def __init__(self, user_id: str, current_spend: float, cap: float):
        self.user_id = user_id
        self.current_spend = current_spend
        self.cap = cap
        super().__init__(
            f"User {user_id} daily cost limit exceeded: "
            f"${current_spend:.4f} / ${cap:.2f}"
        )


# ---------------------------------------------------------------------------
# Redis client
# ---------------------------------------------------------------------------
_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


# ---------------------------------------------------------------------------
# PRICING TABLE
#
# Exact costs per token for each model. All values in USD.
# Updated for 2025 pricing. Groq free tier is effectively $0.
# ---------------------------------------------------------------------------

PRICING_TABLE: dict[str, dict[str, float]] = {
    # Gemini 2.5 Flash
    "gemini-2.5-flash": {
        "input_cost_per_token": 0.075 / 1_000_000,
        "output_cost_per_token": 0.30 / 1_000_000,
    },
    # Gemini 2.0 Flash
    "gemini-2.0-flash": {
        "input_cost_per_token": 0.10 / 1_000_000,   # $0.10 per 1M input tokens
        "output_cost_per_token": 0.40 / 1_000_000,   # $0.40 per 1M output tokens
    },
    # Gemini 1.5 Flash
    "gemini-1.5-flash": {
        "input_cost_per_token": 0.075 / 1_000_000,
        "output_cost_per_token": 0.30 / 1_000_000,
    },
    # Gemini 1.5 Pro
    "gemini-1.5-pro": {
        "input_cost_per_token": 1.25 / 1_000_000,
        "output_cost_per_token": 5.00 / 1_000_000,
    },
    # Groq Llama 3.1 70B Versatile (free tier)
    "llama-3.1-70b-versatile": {
        "input_cost_per_token": 0.0,
        "output_cost_per_token": 0.0,
    },
    # Gemini embedding (free)
    "gemini-embedding-001": {
        "input_cost_per_token": 0.0,
        "output_cost_per_token": 0.0,
    },
}


def get_model_pricing(model_name: str) -> dict[str, float]:
    """
    Returns the pricing dict for a given model.
    Falls back to Gemini 2.0 Flash pricing if the model is unknown.
    """
    # Normalize model name (handle prefixes like "models/")
    clean_name = model_name.split("/")[-1].lower()

    # Exact match
    if clean_name in PRICING_TABLE:
        return PRICING_TABLE[clean_name]

    # Partial match (e.g., "gemini-2.0-flash-001" → "gemini-2.0-flash")
    for key in PRICING_TABLE:
        if key in clean_name:
            return PRICING_TABLE[key]

    # Default: Gemini 2.5 Flash (most commonly used)
    return PRICING_TABLE["gemini-2.5-flash"]


# ---------------------------------------------------------------------------
# TOKEN COUNTING via tiktoken
#
# tiktoken doesn't have Gemini tokenizers built-in, but cl100k_base
# (GPT-4's tokenizer) produces a close approximation for English text.
# The error margin is typically <10%, which is acceptable for cost
# ESTIMATION (not billing). We reconcile with actual tokens after the call.
# ---------------------------------------------------------------------------

# Module-level encoder — loaded once, reused across all calls
_encoder: tiktoken.Encoding | None = None


def _get_encoder() -> tiktoken.Encoding:
    """Returns a cached tiktoken encoder (cl100k_base)."""
    global _encoder
    if _encoder is None:
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


def count_tokens(text: str) -> int:
    """
    Counts the approximate number of tokens in a text string.

    Uses cl100k_base (GPT-4 tokenizer) as a cross-model approximation.
    Accuracy: ±10% for English text across Gemini/Llama models.
    """
    if not text:
        return 0
    enc = _get_encoder()
    return len(enc.encode(text))


def estimate_cost(
    prompt_text: str,
    model_name: str,
    estimated_output_tokens: int = 2000,
) -> float:
    """
    Estimates the cost of an LLM call BEFORE making it.

    Args:
        prompt_text: The full prompt text (system + user).
        model_name: The model to be called.
        estimated_output_tokens: Expected output length (default 2000).

    Returns:
        Estimated cost in USD.
    """
    pricing = get_model_pricing(model_name)
    input_tokens = count_tokens(prompt_text)

    input_cost = input_tokens * pricing["input_cost_per_token"]
    output_cost = estimated_output_tokens * pricing["output_cost_per_token"]

    return input_cost + output_cost


def compute_actual_cost(
    model_name: str,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """
    Computes the actual cost after an LLM call completes.

    Args:
        model_name: The model that was used.
        input_tokens: Actual input tokens from the API response.
        output_tokens: Actual output tokens from the API response.

    Returns:
        Actual cost in USD.
    """
    pricing = get_model_pricing(model_name)
    return (
        input_tokens * pricing["input_cost_per_token"]
        + output_tokens * pricing["output_cost_per_token"]
    )


# ---------------------------------------------------------------------------
# ATOMIC SPEND TRACKING
#
# Uses Redis INCRBYFLOAT for lock-free atomic increments.
# Key: cost:{user_id}:{YYYY-MM-DD}
# TTL: auto-expires at midnight UTC (seconds remaining in the day).
# ---------------------------------------------------------------------------

def _get_cost_key(user_id: str) -> str:
    """Returns the Redis key for today's cost counter for this user."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"cost:{user_id}:{today}"


def _seconds_until_midnight() -> int:
    """Returns the number of seconds until midnight UTC."""
    now = datetime.now(timezone.utc)
    midnight = (now + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    return int((midnight - now).total_seconds())


def get_daily_spend(user_id: str) -> float:
    """
    Returns the user's current daily spend in USD.
    Returns 0.0 if no spend has been recorded today.
    """
    r = _get_redis()
    key = _get_cost_key(user_id)
    value = r.get(key)
    return float(value) if value else 0.0


def check_and_charge_limit(
    user_id: str,
    estimated_cost: float,
    cap: Optional[float] = None,
) -> float:
    """
    Atomically checks + increments the user's daily spend.

    ATOMIC OPERATION:
      1. INCRBYFLOAT the cost key by estimated_cost.
      2. If the new total exceeds the cap → DECREMENT back and raise.
      3. Set TTL to midnight UTC if this is the first charge today.

    Args:
        user_id: The user to charge.
        estimated_cost: The estimated cost of the upcoming LLM call.
        cap: Daily spend cap in USD. Defaults to DAILY_COST_CAP.

    Returns:
        The new total daily spend after the charge.

    Raises:
        CostLimitExceeded: If the charge would exceed the daily cap.
    """
    if estimated_cost <= 0:
        return get_daily_spend(user_id)

    effective_cap = cap or DAILY_COST_CAP
    r = _get_redis()
    key = _get_cost_key(user_id)

    # Atomic increment
    new_total = r.incrbyfloat(key, estimated_cost)

    # Set TTL if this is the first charge (key was just created)
    ttl = r.ttl(key)
    if ttl == -1:  # Key exists but has no TTL → first charge today
        r.expire(key, _seconds_until_midnight())

    # Check against cap
    if new_total > effective_cap:
        # Roll back the charge — user can't afford it
        r.incrbyfloat(key, -estimated_cost)
        print(
            f"[CostGuard] 🚫 User {user_id} blocked: "
            f"${new_total:.4f} would exceed ${effective_cap:.2f} daily cap.",
            flush=True,
        )
        raise CostLimitExceeded(
            user_id=user_id,
            current_spend=new_total - estimated_cost,
            cap=effective_cap,
        )

    print(
        f"[CostGuard] ✅ Charged ${estimated_cost:.4f} to {user_id}. "
        f"Daily total: ${new_total:.4f} / ${effective_cap:.2f}.",
        flush=True,
    )
    return new_total


def reconcile_cost(
    user_id: str,
    estimated_cost: float,
    actual_cost: float,
) -> None:
    """
    Reconciles the difference between estimated and actual cost.

    Called AFTER the LLM call completes with actual token counts.
    Adjusts the Redis counter so billing is accurate.

    Args:
        user_id: The user to adjust.
        estimated_cost: What was pre-charged via check_and_charge_limit.
        actual_cost: The real cost computed from API response usage data.
    """
    delta = actual_cost - estimated_cost
    if abs(delta) < 0.000001:
        return  # No meaningful difference

    r = _get_redis()
    key = _get_cost_key(user_id)

    r.incrbyfloat(key, delta)
    print(
        f"[CostGuard] 📊 Reconciled {user_id}: "
        f"estimated=${estimated_cost:.4f}, actual=${actual_cost:.4f}, "
        f"adjustment=${delta:+.4f}.",
        flush=True,
    )
