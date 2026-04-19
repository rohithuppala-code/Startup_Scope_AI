"""
Live-fire integration test — ALL 15 endpoints in realtime_groups.
Hits the REAL running server + REAL Supabase. No mocks.

Run:
    PYTHONPATH=/Users/likhith./Startup_Scope_AI \
    pytest realtime_groups/backend/tests/test_live_endpoints.py -v -s
"""
import asyncio, os, uuid
from pathlib import Path

import httpx, pytest
from dotenv import load_dotenv
from supabase import create_client, Client

_ENV = Path(__file__).resolve().parents[3] / "backend" / ".env"
load_dotenv(_ENV)

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SERVICE_ROLE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BASE = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")

svc: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
svc.postgrest.auth(SUPABASE_SERVICE_ROLE_KEY)

pytestmark = pytest.mark.asyncio

def H(uid: str) -> dict:
    return {"x-user-id": uid, "Content-Type": "application/json"}

# Shared state dict for cross-class communication
_state = {}

# ── SESSION FIXTURES ─────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def users():
    ids = []
    for i in range(1, 4):
        tag = uuid.uuid4().hex[:8]
        email = f"live_{i}_{tag}@test.invalid"
        resp = svc.auth.admin.create_user(
            {"email": email, "password": "LiveTest@123!", "email_confirm": True}
        )
        uid = str(resp.user.id)
        try:
            svc.table("profiles").insert({
                "id": uid, "username": f"live_{i}_{tag[:6]}",
                "karma_score": 0, "badges": [],
            }).execute()
        except Exception:
            svc.table("profiles").update({"username": f"live_{i}_{tag[:6]}"}).eq("id", uid).execute()
        ids.append(uid)
        print(f"  [Setup] User {i}: {uid[:8]}…")
    yield {"u1": ids[0], "u2": ids[1], "u3": ids[2]}
    # Teardown
    for uid in ids:
        try:
            svc.auth.admin.delete_user(uid)
        except Exception as e:
            print(f"  [Teardown] WARN: {e}")

@pytest.fixture(scope="session")
def hub_id(users):
    hid = str(uuid.uuid4())
    svc.table("hubs").insert({
        "id": hid, "name": f"Live Hub {hid[:6]}",
        "description": "Test hub", "created_by": users["u1"], "member_count": 0,
    }).execute()
    yield hid
    try:
        svc.table("hub_members").delete().eq("hub_id", hid).execute()
        svc.table("channels").delete().eq("hub_id", hid).execute()
        svc.table("hubs").delete().eq("id", hid).execute()
    except Exception:
        pass

@pytest.fixture(scope="session")
def channel_id(hub_id):
    cid = str(uuid.uuid4())
    svc.table("channels").insert({
        "id": cid, "hub_id": hub_id, "name": "general", "kind": "text", "channel_type": "text",
    }).execute()
    yield cid

@pytest.fixture(scope="session")
def validation_id(users):
    vid = str(uuid.uuid4())
    svc.table("validations").insert({
        "id": vid, "user_id": users["u1"],
        "idea_description": "Live-test AI SaaS for QA automation.",
        "target_market": "B2B", "budget_constraints": "$5k",
        "status": "completed", "idempotency_key": f"live-{vid}",
        "idea_hash": uuid.uuid4().hex,
        "report_json": {"score": 90, "summary": "Strong fit."},
    }).execute()
    yield vid
    try:
        svc.table("validations").delete().eq("id", vid).execute()
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 1 — PROFILES
# ═══════════════════════════════════════════════════════════════════════════

class TestP1_Profiles:

    async def test_01_put_profile(self, users):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.put("/api/v1/profiles/me", json={
                "bio": "Live test bio.", "twitter_url": "https://x.com/test",
            }, headers=H(users["u1"]))
        assert r.status_code == 200, r.text
        assert r.json()["bio"] == "Live test bio."
        row = svc.table("profiles").select("bio").eq("id", users["u1"]).single().execute()
        assert row.data["bio"] == "Live test bio."
        print("  ✅ PUT /profiles/me")

    async def test_02_put_profile_empty_400(self, users):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.put("/api/v1/profiles/me", json={}, headers=H(users["u1"]))
        assert r.status_code == 400
        print("  ✅ PUT /profiles/me empty → 400")

    async def test_03_get_profile(self, users):
        uname = svc.table("profiles").select("username").eq("id", users["u1"]).single().execute().data["username"]
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.get(f"/api/v1/profiles/{uname}")
        assert r.status_code == 200, r.text
        assert r.json()["username"] == uname
        print(f"  ✅ GET /profiles/{uname}")

    async def test_04_get_founder_validations(self, users):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.get(f"/api/v1/profiles/{users['u1']}/validations")
        assert r.status_code == 200
        assert isinstance(r.json(), list)
        print(f"  ✅ GET /profiles/{{uid}}/validations")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 2 — COMMUNITY
# ═══════════════════════════════════════════════════════════════════════════

class TestP2_Community:

    async def test_05_list_hubs(self, hub_id):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.get("/api/v1/hubs")
        assert r.status_code == 200
        assert hub_id in [h["id"] for h in r.json()]
        print(f"  ✅ GET /hubs")

    async def test_06_get_hub(self, hub_id):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.get(f"/api/v1/hubs/{hub_id}")
        assert r.status_code == 200
        assert r.json()["id"] == hub_id
        print(f"  ✅ GET /hubs/{{id}}")

    async def test_07_list_channels(self, hub_id, channel_id):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.get(f"/api/v1/hubs/{hub_id}/channels")
        assert r.status_code == 200
        assert channel_id in [ch["id"] for ch in r.json()]
        print(f"  ✅ GET /hubs/channels")

    async def test_08_join_hub(self, users, hub_id):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            for k in ("u1", "u2", "u3"):
                r = await c.post(f"/api/v1/hubs/{hub_id}/join", headers=H(users[k]))
                assert r.status_code == 200, f"{k}: {r.text}"
        db = svc.table("hub_members").select("user_id", count="exact").eq("hub_id", hub_id).execute()
        assert db.count == 3
        print(f"  ✅ POST /hubs/join — 3 members")

    async def test_09_join_hub_idempotent(self, users, hub_id):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post(f"/api/v1/hubs/{hub_id}/join", headers=H(users["u1"]))
        assert r.status_code == 200
        assert r.json()["already_member"] is True
        print(f"  ✅ POST /hubs/join idempotent")

    async def test_10_dm_init(self, users):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post("/api/v1/messages/dm",
                json={"recipient_id": users["u2"]}, headers=H(users["u1"]))
        assert r.status_code == 201, r.text
        ch_id = r.json()["channel_id"]
        svc.table("channels").delete().eq("id", ch_id).execute()
        print(f"  ✅ POST /messages/dm")

    async def test_11_dm_self_400(self, users):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post("/api/v1/messages/dm",
                json={"recipient_id": users["u1"]}, headers=H(users["u1"]))
        assert r.status_code == 400
        print(f"  ✅ POST /messages/dm self → 400")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 3 — ARENA
# ═══════════════════════════════════════════════════════════════════════════

class TestP3_Arena:

    async def test_12_publish(self, users, validation_id):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post("/api/v1/arena/publish", json={
                "validation_id": validation_id, "title": "Live Test Idea", "tags": ["AI"],
            }, headers=H(users["u1"]))
        assert r.status_code == 201, f"Publish failed: {r.status_code} {r.text}"
        _state["post_id"] = r.json()["post_id"]
        print(f"  ✅ POST /arena/publish → {_state['post_id'][:8]}…")

    async def test_13_publish_dup_409(self, users, validation_id):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post("/api/v1/arena/publish", json={
                "validation_id": validation_id, "title": "Dup", "tags": [],
            }, headers=H(users["u1"]))
        assert r.status_code == 409
        print(f"  ✅ POST /arena/publish dup → 409")

    async def test_14_list_posts(self):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.get("/api/v1/arena/posts?page=1&page_size=50")
        assert r.status_code == 200
        assert len(r.json()) >= 1
        print(f"  ✅ GET /arena/posts ({len(r.json())})")

    async def test_15_post_detail(self):
        pid = _state["post_id"]
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.get(f"/api/v1/arena/posts/{pid}")
        assert r.status_code == 200
        assert r.json()["id"] == pid
        print(f"  ✅ GET /arena/posts/{{id}}")

    async def test_16_upvote(self, users):
        pid = _state["post_id"]
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{pid}/vote",
                json={"direction": 1}, headers=H(users["u2"]))
        assert r.status_code == 200, r.text
        assert r.json()["new_score"] >= 1
        print(f"  ✅ POST /vote upvote → score={r.json()['new_score']}")

    async def test_17_downvote(self, users):
        pid = _state["post_id"]
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{pid}/vote",
                json={"direction": -1}, headers=H(users["u3"]))
        assert r.status_code == 200
        print(f"  ✅ POST /vote downvote → score={r.json()['new_score']}")

    async def test_18_double_vote_409(self, users):
        pid = _state["post_id"]
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{pid}/vote",
                json={"direction": 1}, headers=H(users["u2"]))
        assert r.status_code == 409
        print(f"  ✅ POST /vote double → 409")

    async def test_19_poll_vote(self, users):
        pid = _state["post_id"]
        poll_id = str(uuid.uuid4())
        svc.table("polls").insert({
            "id": poll_id, "post_id": pid, "question": "Best model?",
            "options": [{"id": "saas", "text": "SaaS"}, {"id": "oss", "text": "OSS"}],
        }).execute()
        _state["poll_id"] = poll_id
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{pid}/polls/vote",
                json={"poll_id": poll_id, "option_id": "saas"}, headers=H(users["u2"]))
        assert r.status_code == 200, r.text
        assert r.json()["option_id"] == "saas"
        print(f"  ✅ POST /polls/vote")

    async def test_20_poll_double_409(self, users):
        pid = _state["post_id"]
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{pid}/polls/vote",
                json={"poll_id": _state["poll_id"], "option_id": "oss"}, headers=H(users["u2"]))
        assert r.status_code == 409
        print(f"  ✅ POST /polls/vote double → 409")

    async def test_21_poll_bad_option_400(self, users):
        pid = _state["post_id"]
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post(f"/api/v1/arena/posts/{pid}/polls/vote",
                json={"poll_id": _state["poll_id"], "option_id": "BOGUS"}, headers=H(users["u3"]))
        assert r.status_code == 400
        print(f"  ✅ POST /polls/vote bad option → 400")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 4 — WEBHOOKS & SYNTHESIS
# ═══════════════════════════════════════════════════════════════════════════

class TestP4_WebhooksSynthesis:

    async def test_22_webhook_accepted(self, users):
        pid = _state["post_id"]
        cid = str(uuid.uuid4())
        svc.table("comments").insert({
            "id": cid, "post_id": pid, "user_id": users["u2"], "author_id": users["u2"],
            "content": "Great idea, solid market analysis!", "is_hidden": False,
        }).execute()
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post("/api/v1/webhooks/moderation", json={
                "type": "INSERT", "table": "comments", "schema": "public",
                "record": {"id": cid, "content": "Great idea!", "author_id": users["u2"]},
            })
        assert r.status_code == 202
        assert r.json()["status"] == "accepted"
        print(f"  ✅ POST /webhooks/moderation → accepted")

    async def test_23_webhook_ignored(self):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post("/api/v1/webhooks/moderation", json={
                "type": "INSERT", "table": "profiles", "schema": "public",
                "record": {"id": "x", "content": "y", "author_id": "z"},
            })
        assert r.status_code == 202
        assert r.json()["status"] == "ignored"
        print(f"  ✅ POST /webhooks/moderation → ignored")

    async def test_24_webhook_skipped(self):
        async with httpx.AsyncClient(base_url=BASE, timeout=30) as c:
            r = await c.post("/api/v1/webhooks/moderation", json={
                "type": "INSERT", "table": "comments", "schema": "public",
                "record": {"id": "", "content": "", "author_id": ""},
            })
        assert r.status_code == 202
        assert r.json()["status"] == "skipped"
        print(f"  ✅ POST /webhooks/moderation → skipped")

    async def test_25_synthesis(self, users):
        pid = _state["post_id"]
        svc.table("comments").insert({
            "post_id": pid, "user_id": users["u3"], "author_id": users["u3"],
            "content": "TAM is bigger. DevTools is a $50B market.", "is_hidden": False,
        }).execute()
        async with httpx.AsyncClient(base_url=BASE, timeout=120) as c:
            r = await c.post(f"/api/v1/arena/posts/{pid}/synthesize", headers=H(users["u1"]))
        assert r.status_code == 200, f"Synthesis: {r.status_code} {r.text}"
        d = r.json()
        assert "summary" in d
        assert d["comment_count"] >= 2
        print(f"  ✅ POST /synthesize → {d['comment_count']} comments")


# ═══════════════════════════════════════════════════════════════════════════
# PHASE 5 — DB TRUTH
# ═══════════════════════════════════════════════════════════════════════════

class TestP5_DBTruth:

    async def test_26_karma(self, users):
        await asyncio.sleep(2)  # Let background karma tasks settle
        row = svc.table("profiles").select("karma_score,badges").eq("id", users["u1"]).single().execute()
        print(f"  ℹ️  karma={row.data['karma_score']} badges={row.data['badges']}")
        # Karma should be at least KARMA_POST (3) from publishing
        assert row.data["karma_score"] >= 3, f"karma={row.data['karma_score']}"
        print(f"  ✅ karma >= 3")

    async def test_27_vote_counts(self):
        pid = _state["post_id"]
        row = svc.table("posts").select("upvote_count,downvote_count").eq("id", pid).single().execute()
        assert row.data["upvote_count"] >= 1
        assert row.data["downvote_count"] >= 1
        print(f"  ✅ votes synced: up={row.data['upvote_count']} down={row.data['downvote_count']}")

    async def test_28_hub_members(self, hub_id):
        db = svc.table("hub_members").select("user_id", count="exact").eq("hub_id", hub_id).execute()
        assert db.count == 3
        print(f"  ✅ hub_members={db.count}")

    async def test_29_poll_votes(self):
        db = svc.table("poll_votes").select("user_id", count="exact").eq("poll_id", _state["poll_id"]).execute()
        assert db.count == 1
        print(f"  ✅ poll_votes={db.count}")


# ═══════════════════════════════════════════════════════════════════════════
# CLEANUP
# ═══════════════════════════════════════════════════════════════════════════

class TestP6_Cleanup:

    async def test_99_cleanup(self, users, validation_id):
        pid = _state.get("post_id")
        poll_id = _state.get("poll_id")
        if poll_id:
            svc.table("poll_votes").delete().eq("poll_id", poll_id).execute()
            svc.table("polls").delete().eq("id", poll_id).execute()
        if pid:
            svc.table("comments").delete().eq("post_id", pid).execute()
            svc.table("post_votes").delete().eq("post_id", pid).execute()
            svc.table("posts").delete().eq("id", pid).execute()
        print("  ✅ Cleanup done")
