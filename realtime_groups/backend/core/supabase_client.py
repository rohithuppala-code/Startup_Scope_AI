# realtime_groups/backend/core/supabase_client.py
# ---------------------------------------------------------------------------
# Singleton Supabase service-role client.
# Uses the service-role key (bypasses Row Level Security) — NEVER expose to
# the frontend. All row-level ownership checks MUST be enforced at the API
# layer using the authenticated user's UUID.
# ---------------------------------------------------------------------------

from supabase import create_client, Client
from realtime_groups.backend.core.config import social_settings

_client: Client | None = None


def get_supabase() -> Client:
    """
    Returns a lazily-initialized Supabase service-role client.
    Thread-safe for asyncio event loops (single-threaded concurrency model).
    """
    global _client
    if _client is None:
        _client = create_client(
            social_settings.SUPABASE_URL,
            social_settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _client
