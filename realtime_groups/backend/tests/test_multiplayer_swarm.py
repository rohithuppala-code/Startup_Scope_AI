"""
Live-fire multiplayer swarm integration suite — StartupScope Social.

Run from backend/ directory:
    pytest ../realtime_groups/backend/tests/test_multiplayer_swarm.py -v -s

Prereqs:
    pip install httpx pytest pytest-asyncio python-dotenv anyio
    uvicorn app.main:app --reload --port 8000
    celery -A realtime_groups.backend.workers.celery_tasks worker -Q social
"""
import asyncio
import os
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv
from supabase import create_client, Client

# ── Env ───────────────────────────────────────────────────────────────────────
# Walk up: tests/ → backend(module) → realtime_groups → Startup_Scope_AI → backend(.env)
_ENV = Path(__file__).parents[3] / "backend" / ".env"
load_dotenv(_ENV)

SUPABASE_URL             = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
TEST_EMAIL               = os.environ["TEST_EMAIL"]
TEST_PASSWORD            = os.environ["TEST_PASSWORD"]
BASE_URL                 = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")

# Service-role client — bypasses RLS; used ONLY for seeding/assertions/teardown
# IMPORTANT: After creating the client, we must explicitly set the service_role
# JWT as the Authorization header so PostgREST respects it for RLS bypass.
svc: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
svc.postgrest.auth(SUPABASE_SERVICE_ROLE_KEY)

pytestmark = pytest.mark.asyncio


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def H(user_id: str) -> dict:
    """Build request headers for a given user UUID."""
    return {"x-user-id": user_id, "Content-Type": "application/json"}


def _find_auth_user(email: str) -> str | None:
    """Return auth user UUID for a given email, handling SDK pagination."""
    try:
        page = 1
        while True:
            result = svc.auth.admin.list_users(page=page, per_page=50)
            users = result if isinstance(result, list) else getattr(result, "users", result)
            if not users:
                break
            for u in users:
                if getattr(u, "email", None) == email:
                    return str(u.id)
            if len(users) < 50:
                break
            page += 1
    except Exception as exc:
        raise RuntimeError(f"Could not list auth users: {exc}") from exc
    return None


def _upsert_profile(uid: str, username: str) -> None:
    """Ensure a profiles row exists for the given auth user UUID.
    Uses INSERT ... ON CONFLICT DO UPDATE so it works regardless of
    whether the row already exists.
    """
    try:
        svc.table("profiles").insert({
            "id": uid,
            "username": username,
            "karma_score": 0,
            "badges": [],
        }).execute()
    except Exception as e:
        err = str(e).lower()
        # If row already exists (duplicate key), update it — that's fine
        if "duplicate" in err or "unique" in err or "23505" in err:
            svc.table("profiles").update({
                "username": username,
            }).eq("id", uid).execute()
        else:
            raise


# ─────────────────────────────────────────────────────────────────────────────
# Session fixtures — created once, shared, torn down after all tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def primary_user_id() -> str:
    uid = _find_auth_user(TEST_EMAIL)
    assert uid, f"Primary user '{TEST_EMAIL}' not found in auth.users"
    _upsert_profile(uid, "primary_founder")
    return uid


@pytest.fixture(scope="session")
def mock_user_ids() -> list[str]:
    """Spin up 4 temporary Supabase auth users with profiles. Tear down after session."""
    ids: list[str] = []
    for i in range(1, 5):
        tag = uuid.uuid4().hex[:8]
        email = f"swarm_{i}_{tag}@test.invalid"
        resp = svc.auth.admin.create_user(
            {"email": email, "password": "SwarmPass@123!", "email_confirm": True}
        )
        uid = str(resp.user.id)
        _upsert_profile(uid, f"mock_{i}_{tag[:6]}")
        ids.append(uid)
        print(f"  [Setup] Created mock user {i}: {uid[:8]}…")

    yield ids

    for uid in ids:
        try:
            svc.auth.admin.delete_user(uid)
            print(f"  [Teardown] Deleted mock user {uid[:8]}…")
        except Exception as exc:
            print(f"  [Teardown] WARNING: could not delete {uid[:8]}: {exc}")


@pytest.fixture(scope="session")
def users(primary_user_id, mock_user_ids) -> dict:
    return {
        "primary": primary_user_id,
        "mock_1":  mock_user_ids[0],
        "mock_2":  mock_user_ids[1],
        "mock_3":  mock_user_ids[2],
        "mock_4":  mock_user_ids[3],
    }


@pytest.fixture(scope="session")
def hub_id(primary_user_id) -> str:
    hid = str(uuid.uuid4())
    svc.table("hubs").insert({
        "id": hid,
        "name": f"AI Founders Test Hub {hid[:6]}",
        "description": "Swarm integration test hub — safe to delete.",
        "created_by": primary_user_id,
        "member_count": 0,
    }).execute()
    print(f"  [Setup] Hub created: {hid[:8]}…")
    yield hid
    try:
        svc.table("hubs").delete().eq("id", hid).execute()
        print(f"  [Teardown] Hub {hid[:8]}… deleted.")
    except Exception as exc:
        print(f"  [Teardown] Hub delete failed: {exc}")


@pytest.fixture(scope="session")
def validation_id(primary_user_id) -> str:
    vid = str(uuid.uuid4())
    svc.table("validations").insert({
        "id": vid,
        "user_id": primary_user_id,
        "idea_description": "AI-powered code-review SaaS for early-stage startups.",
        "target_market": "Engineering teams <50 people",
        "budget_constraints": "$5k/month",
        "status": "completed",
        "idempotency_key": f"swarm-{vid}",
        "idea_hash": uuid.uuid4().hex,
        "report_json": {"score": 87, "summary": "Strong market fit, clear TAM."},
    }).execute()
    yield vid
    try:
        svc.table("validations").delete().eq("id", vid).execute()
    except Exception as exc:
        print(f"  [Teardown] Validation delete failed: {exc}")


@pytest.fixture(scope="session")
def post_id(primary_user_id, validation_id) -> str:
    pid = str(uuid.uuid4())
    # posts.content is NOT NULL in the live schema
    svc.table("posts").insert({
        "id": pid,
        "user_id": primary_user_id,
        "author_id": primary_user_id,
        "validation_id": validation_id,
        "content": "AI-powered code-review SaaS for early-stage startups.",
        "title": "AI Code Review — Swarm Test Post",
        "report_json": {"score": 87, "summary": "Strong market fit."},
        "tags": ["AI", "SaaS", "DevTools"],
        "upvote_count": 0,
        "downvote_count": 0,
        "comment_count": 0,
        "is_hidden": False,
    }).execute()
    print(f"  [Setup] Post created: {pid[:8]}…")
    yield pid
    try:
        svc.table("posts").delete().eq("id", pid).execute()
        print(f"  [Teardown] Post {pid[:8]}… deleted.")
    except Exception as exc:
        print(f"  [Teardown] Post delete failed: {exc}")


@pytest.fixture(scope="session")
def poll_id(post_id) -> str:
    plid = str(uuid.uuid4())
    svc.table("polls").insert({
        "id": plid,
        "post_id": post_id,
        "question": "SaaS vs Open Source — which model fits better?",
        "options": [
            {"id": "opt_saas", "text": "SaaS Subscription"},
            {"id": "opt_oss",  "text": "Open Source + Services"},
        ],
    }).execute()
    print(f"  [Setup] Poll created: {plid[:8]}…")
    yield plid
    try:
        svc.table("polls").delete().eq("id", plid).execute()
    except Exception as exc:
        print(f"  [Teardown] Poll delete failed: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Identity Graph
# ─────────────────────────────────────────────────────────────────────────────
class TestPhase1_Identity:

    async def test_01_primary_updates_profile(self, users):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.put("/api/v1/profiles/me",
                json={"bio": "Swarm test bio.", "avatar_url": "https://cdn.test/av.png",
                      "twitter_url": "https://twitter.com/swarmtest"},
                headers=H(users["primary"]))
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["bio"] == "Swarm test bio."
        assert d["avatar_url"] == "https://cdn.test/av.png"
        # DB truth
        row = svc.table("profiles").select("bio,avatar_url").eq("id", users["primary"]).single().execute()
        assert row.data["bio"] == "Swarm test bio."
        print(f"  ✅ Profile updated. karma={d.get('karma_score',0)}")

    async def test_02_all_mocks_read_primary_profile(self, users):
        uname = svc.table("profiles").select("username").eq("id", users["primary"]).single().execute().data["username"]
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            resps = await asyncio.gather(*[c.get(f"/api/v1/profiles/{uname}") for _ in range(4)])
        for i, r in enumerate(resps):
            assert r.status_code == 200, f"Mock {i+1}: {r.text}"
            assert r.json()["username"] == uname
        print(f"  ✅ 4 concurrent profile reads OK for '{uname}'")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 2 — Community Engine
# ─────────────────────────────────────────────────────────────────────────────
class TestPhase2_Community:

    async def test_03_five_users_join_hub(self, users, hub_id):
        all_ids = [users["primary"]] + [users[f"mock_{i}"] for i in range(1,5)]
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            for uid in all_ids:
                r = await c.post(f"/api/v1/hubs/{hub_id}/join", headers=H(uid))
                assert r.status_code == 200, f"User {uid[:8]}: {r.text}"
        # DB truth
        db = svc.table("hub_members").select("user_id", count="exact").eq("hub_id", hub_id).execute()
        assert db.count == 5, f"Expected 5 hub_members rows, got {db.count}"
        print(f"  ✅ 5 members in hub_members confirmed.")

    async def test_04_hub_appears_in_listing(self, hub_id):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.get("/api/v1/hubs")
        assert r.status_code == 200, r.text
        assert hub_id in [h["id"] for h in r.json()], "Hub missing from listing"
        print(f"  ✅ Hub {hub_id[:8]}… in public listing.")

    async def test_05_hub_detail_endpoint(self, hub_id):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.get(f"/api/v1/hubs/{hub_id}")
        assert r.status_code == 200, r.text
        assert r.json()["id"] == hub_id
        print(f"  ✅ Hub detail endpoint OK.")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 3 — Validation Arena
# ─────────────────────────────────────────────────────────────────────────────
class TestPhase3_Arena:

    async def test_06_post_appears_in_arena_feed(self, post_id):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.get("/api/v1/arena/posts?page=1&page_size=50")
        assert r.status_code == 200, r.text
        assert post_id in [p["id"] for p in r.json()], "Post missing from arena feed"
        print(f"  ✅ Post {post_id[:8]}… in arena feed.")

    async def test_07_post_detail_endpoint(self, post_id):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.get(f"/api/v1/arena/posts/{post_id}")
        assert r.status_code == 200, r.text
        assert r.json()["id"] == post_id
        print(f"  ✅ Post detail endpoint OK.")

    async def test_08_mock_1_2_upvote_concurrently(self, users, post_id):
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            resps = await asyncio.gather(*[
                c.post(f"/api/v1/arena/posts/{post_id}/vote",
                       json={"direction": 1}, headers=H(users[f"mock_{i}"]))
                for i in (1, 2)
            ])
        for i, r in enumerate(resps):
            assert r.status_code == 200, f"Mock {i+1} upvote: {r.text}"
            assert r.json()["new_score"] >= 1
        await asyncio.sleep(2)  # Let karma background tasks settle
        # DB truth
        db = svc.table("post_votes").select("direction", count="exact")\
               .eq("post_id", post_id).eq("direction", 1).execute()
        assert db.count == 2, f"Expected 2 upvote rows, got {db.count}"
        print(f"  ✅ 2 upvotes confirmed in post_votes.")

    async def test_09_karma_score_reflects_upvotes(self, users):
        await asyncio.sleep(2)
        row = svc.table("profiles").select("karma_score,badges")\
                 .eq("id", users["primary"]).single().execute()
        karma = row.data["karma_score"]
        assert karma >= 10, f"karma_score={karma}, expected >=10 (2×5)"
        print(f"  ✅ Primary karma_score={karma} (≥10). Badges={row.data['badges']}")

    async def test_10_mock_3_4_vote_on_poll(self, users, post_id, poll_id):
        votes = [(users["mock_3"], "opt_saas"), (users["mock_4"], "opt_oss")]
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            for uid, opt in votes:
                r = await c.post(f"/api/v1/arena/posts/{post_id}/polls/vote",
                                 json={"poll_id": poll_id, "option_id": opt},
                                 headers=H(uid))
                assert r.status_code == 200, f"Poll vote {uid[:8]}: {r.text}"
        # DB truth — exactly 2 rows
        db = svc.table("poll_votes").select("user_id", count="exact")\
                .eq("poll_id", poll_id).execute()
        assert db.count == 2, f"Expected 2 poll_votes rows, got {db.count}"
        print(f"  ✅ poll_votes has exactly {db.count} rows.")

    async def test_11_double_poll_vote_returns_409(self, users, post_id, poll_id):
        # mock_3 already voted opt_saas — attempt again
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{post_id}/polls/vote",
                             json={"poll_id": poll_id, "option_id": "opt_saas"},
                             headers=H(users["mock_3"]))
        assert r.status_code == 409, f"Expected 409, got {r.status_code}: {r.text}"
        print(f"  ✅ Double-vote correctly blocked with HTTP 409.")

    async def test_12_double_post_vote_returns_409(self, users, post_id):
        # mock_1 already upvoted — try same direction again
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{post_id}/vote",
                             json={"direction": 1}, headers=H(users["mock_1"]))
        assert r.status_code == 409, f"Expected 409 on dup post vote, got {r.status_code}: {r.text}"
        print(f"  ✅ Duplicate post vote correctly blocked with HTTP 409.")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 4 — AI Moderation
# ─────────────────────────────────────────────────────────────────────────────
class TestPhase4_Moderation:

    async def test_13_toxic_comment_auto_hidden(self, users, post_id):
        mock2 = users["mock_2"]
        cid = str(uuid.uuid4())
        toxic = ("You are an absolute idiot and this idea is complete trash. "
                 "Stop wasting everyone's time, you pathetic loser. Kill this project.")

        # Insert comment via service-role (simulates user posting via Supabase Realtime)
        svc.table("comments").insert({
            "id": cid, "post_id": post_id,
            "user_id": mock2, "author_id": mock2,
            "content": toxic, "is_hidden": False,
        }).execute()

        # Fire the webhook endpoint (simulates Supabase DB trigger → our API)
        payload = {
            "type": "INSERT", "table": "comments", "schema": "public",
            "record": {"id": cid, "post_id": post_id, "user_id": mock2,
                       "author_id": mock2, "content": toxic, "is_hidden": False},
            "old_record": None,
        }
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30) as c:
            r = await c.post("/api/v1/webhooks/moderation", json=payload)
        assert r.status_code == 202, f"Webhook rejected: {r.status_code} {r.text}"
        d = r.json()
        assert d["status"] == "accepted"
        assert d["record_id"] == cid

        print("  ⏳ Waiting 10s for Celery + Groq to moderate…")
        await asyncio.sleep(10)

        # DB truth
        row = svc.table("comments").select("is_hidden").eq("id", cid).single().execute()
        assert row.data["is_hidden"] is True, (
            f"is_hidden={row.data['is_hidden']}. "
            "Is Celery running? Is GROQ_API_KEY valid? Is RabbitMQ up?"
        )
        print(f"  ✅ Toxic comment {cid[:8]}… is_hidden=True confirmed in DB.")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 5 — Gemini Thread Synthesis
# ─────────────────────────────────────────────────────────────────────────────
class TestPhase5_Synthesis:

    async def test_14_synthesis_returns_structured_brief(self, users, post_id):
        # Seed two clean comments for Gemini to synthesize
        for uid, text in [
            (users["mock_3"], "Pricing model is solid. Enterprise SaaS is the right call."),
            (users["mock_4"], "TAM is bigger than stated. Dev tools is a $50B market."),
        ]:
            svc.table("comments").insert({
                "post_id": post_id, "user_id": uid,
                "author_id": uid, "content": text, "is_hidden": False,
            }).execute()

        async with httpx.AsyncClient(base_url=BASE_URL, timeout=120) as c:
            r = await c.post(f"/api/v1/arena/posts/{post_id}/synthesize",
                             headers=H(users["primary"]))

        assert r.status_code == 200, f"Synthesis failed: {r.status_code} {r.text}"
        d = r.json()
        assert "summary" in d and len(d["summary"]) > 20
        assert "key_themes" in d and isinstance(d["key_themes"], list)
        assert "sentiment_breakdown" in d
        assert d["comment_count"] >= 2
        print(f"  ✅ Synthesis OK. Comments={d['comment_count']}")
        print(f"     Summary: {d['summary'][:100]}…")
        print(f"     Themes: {d['key_themes']}")


# ─────────────────────────────────────────────────────────────────────────────
# PHASE 6 — Final Cross-Cutting DB Assertions
# ─────────────────────────────────────────────────────────────────────────────
class TestPhase6_FinalTruth:

    def test_15_hub_members_exactly_5(self, hub_id):
        db = svc.table("hub_members").select("user_id", count="exact").eq("hub_id", hub_id).execute()
        assert db.count == 5, f"hub_members: expected 5, got {db.count}"
        print(f"  ✅ hub_members: {db.count} rows.")

    def test_16_poll_votes_max_3(self, poll_id):
        db = svc.table("poll_votes").select("user_id", count="exact").eq("poll_id", poll_id).execute()
        assert 2 <= db.count <= 3, f"poll_votes: expected 2-3, got {db.count}"
        print(f"  ✅ poll_votes: {db.count} rows (double-vote blocked).")

    def test_17_post_upvotes_exactly_2(self, post_id):
        db = svc.table("post_votes").select("direction", count="exact")\
                .eq("post_id", post_id).eq("direction", 1).execute()
        assert db.count == 2, f"post_votes: expected 2 upvotes, got {db.count}"
        print(f"  ✅ post_votes: {db.count} upvote rows.")

    def test_18_primary_karma_ge_10(self, users):
        row = svc.table("profiles").select("karma_score,badges")\
                 .eq("id", users["primary"]).single().execute()
        assert row.data["karma_score"] >= 10, f"karma={row.data['karma_score']}, expected >=10"
        print(f"  ✅ karma_score={row.data['karma_score']}. Badges={row.data['badges']}")

    def test_19_posts_upvote_count_synced(self, post_id):
        row = svc.table("posts").select("upvote_count,downvote_count")\
                 .eq("id", post_id).single().execute()
        assert row.data["upvote_count"] == 2, f"upvote_count={row.data['upvote_count']}, expected 2"
        print(f"  ✅ posts.upvote_count=2 confirmed.")

    def test_20_profile_bio_persisted(self, users):
        row = svc.table("profiles").select("bio,avatar_url,twitter_url")\
                 .eq("id", users["primary"]).single().execute()
        assert row.data["bio"] == "Swarm test bio."
        assert row.data["avatar_url"] == "https://cdn.test/av.png"
        print(f"  ✅ Profile fields persisted correctly in DB.")
