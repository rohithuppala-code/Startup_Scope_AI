# conftest.py
# ---------------------------------------------------------------------------
# Shared pytest fixtures for the StartupScope AI test suite.
# The auth fixture dynamically logs into Supabase and injects real
# Authorization + x-user-id headers into every live-fire test.
# ---------------------------------------------------------------------------

import os
import pytest
import pytest_asyncio
from dotenv import load_dotenv

load_dotenv()

from supabase import create_client, Client
from app.core.config import settings

# Service-role client for DB assertions (bypasses RLS)
supabase_admin: Client = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_ROLE_KEY,
)


@pytest_asyncio.fixture(scope="module")
async def supabase_auth():
    """
    Authenticates with Supabase using TEST_EMAIL / TEST_PASSWORD from .env.

    Yields a dict containing:
      - headers:  {"Authorization": "Bearer <jwt>", "x-user-id": "<uuid>"}
      - user_id:  the raw UUID string
      - token:    the raw JWT access_token

    Teardown: signs out the session so we don't leave ghost sessions
    in Supabase's auth.sessions table.
    """
    email = os.environ.get("TEST_EMAIL")
    password = os.environ.get("TEST_PASSWORD")

    if not email or not password:
        pytest.skip(
            "TEST_EMAIL and TEST_PASSWORD must be set in .env for live auth tests."
        )

    # Sign in via the admin client (service-role) — this bypasses any
    # email-confirmation requirements and always succeeds for real users.
    response = supabase_admin.auth.sign_in_with_password(
        {"email": email, "password": password}
    )

    session = response.session
    user = response.user

    assert session is not None, (
        f"Supabase sign-in returned no session for {email}. "
        "Check that the user exists and the password is correct."
    )
    assert user is not None, "Supabase sign-in returned no user object."

    user_id = str(user.id)
    access_token = session.access_token

    auth_data = {
        "headers": {
            "Authorization": f"Bearer {access_token}",
            "x-user-id": user_id,
        },
        "user_id": user_id,
        "token": access_token,
    }

    yield auth_data

    # ── Teardown: sign out gracefully ─────────────────────────────────
    try:
        supabase_admin.auth.sign_out()
    except Exception:
        pass  # Non-fatal — session will expire naturally via JWT TTL
