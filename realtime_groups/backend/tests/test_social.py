# realtime_groups/backend/tests/test_social.py
# ---------------------------------------------------------------------------
# Comprehensive test suite — covers ALL 15 endpoints + services.
# Runs fully mocked (no live DB, no API keys needed).
#
# Run:
#   cd /Users/likhith./Startup_Scope_AI
#   PYTHONPATH=. pytest realtime_groups/backend/tests/test_social.py -v
# ---------------------------------------------------------------------------

import uuid
import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Helper: build a chainable Supabase mock that tracks per-table state
# ---------------------------------------------------------------------------
class FakeSupabaseTable:
    """Simulates the Supabase PostgREST query builder chain."""

    def __init__(self, data=None, count=None, raise_on_execute=None):
        self._data = data
        self._count = count
        self._raise = raise_on_execute

    # Every chained method returns self so .select().eq().single() works
    def select(self, *a, **kw):   return self
    def eq(self, *a, **kw):       return self
    def neq(self, *a, **kw):      return self
    def contains(self, *a, **kw): return self
    def order(self, *a, **kw):    return self
    def range(self, *a, **kw):    return self
    def single(self, *a, **kw):   return self
    def insert(self, *a, **kw):   return self
    def update(self, *a, **kw):   return self
    def upsert(self, *a, **kw):   return self
    def delete(self, *a, **kw):   return self

    def execute(self):
        if self._raise:
            raise self._raise
        resp = MagicMock()
        resp.data = self._data
        resp.count = self._count
        return resp


class FakeSupabase:
    """Routes .table(name) calls to pre-registered FakeSupabaseTable stubs."""

    def __init__(self):
        self._tables: dict[str, FakeSupabaseTable] = {}
        self._default = FakeSupabaseTable(data=[], count=0)

    def register(self, table_name: str, data=None, count=None, raise_on_execute=None):
        self._tables[table_name] = FakeSupabaseTable(data, count, raise_on_execute)

    def table(self, name: str):
        return self._tables.get(name, self._default)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_app():
    """Build a fresh FastAPI app with all social routers."""
    from realtime_groups.backend.api.profile_router import router as pr
    from realtime_groups.backend.api.arena_router import router as ar
    from realtime_groups.backend.api.community_router import router as cr
    from realtime_groups.backend.api.synthesis_router import router as sr
    app = FastAPI()
    app.include_router(pr)
    app.include_router(ar)
    app.include_router(cr)
    app.include_router(sr)
    return app


@pytest.fixture()
def fake_sb():
    return FakeSupabase()


@pytest.fixture()
def client(fake_sb):
    with patch("realtime_groups.backend.core.supabase_client.get_supabase", return_value=fake_sb):
        yield TestClient(_make_app())


@pytest.fixture()
def uid():
    return str(uuid.uuid4())


@pytest.fixture()
def uid2():
    return str(uuid.uuid4())


@pytest.fixture()
def vid():
    return str(uuid.uuid4())


@pytest.fixture()
def pid():
    return str(uuid.uuid4())


def H(user_id: str) -> dict:
    return {"x-user-id": user_id}


# ═══════════════════════════════════════════════════════════════════════════
# 1  PROFILES — PUT /me, GET /{username}, GET /{user_id}/validations
# ═══════════════════════════════════════════════════════════════════════════

class TestProfileUpdate:

    def test_update_profile_success(self, client, fake_sb, uid):
        profile_row = {
            "id": uid, "username": "alice", "display_name": "Alice",
            "bio": "New bio", "avatar_url": None, "karma_score": 0,
            "badges": [], "twitter_url": None, "linkedin_url": None,
            "github_url": None, "website_url": None, "created_at": "2026-01-01T00:00:00+00:00",
        }
        fake_sb.register("profiles", data=profile_row)
        r = client.put("/api/v1/profiles/me", json={"bio": "New bio"}, headers=H(uid))
        assert r.status_code == 200
        assert r.json()["bio"] == "New bio"

    def test_update_profile_empty_body_rejected(self, client, fake_sb, uid):
        r = client.put("/api/v1/profiles/me", json={}, headers=H(uid))
        assert r.status_code == 400

    def test_update_profile_missing_header_returns_422(self, client, fake_sb):
        r = client.put("/api/v1/profiles/me", json={"bio": "x"})
        assert r.status_code == 422

    def test_update_profile_invalid_uuid_header(self, client, fake_sb):
        r = client.put("/api/v1/profiles/me", json={"bio": "x"}, headers={"x-user-id": "not-a-uuid"})
        assert r.status_code == 400


class TestProfileGet:

    def test_get_profile_success(self, client, fake_sb):
        fake_sb.register("profiles", data={
            "id": str(uuid.uuid4()), "username": "bob", "display_name": "Bob",
            "bio": "Hi", "avatar_url": None, "karma_score": 42,
            "badges": ["first_post"], "twitter_url": None, "linkedin_url": None,
            "github_url": None, "website_url": None, "created_at": "2026-01-01T00:00:00+00:00",
        })
        r = client.get("/api/v1/profiles/bob")
        assert r.status_code == 200
        assert r.json()["username"] == "bob"
        assert r.json()["karma_score"] == 42

    def test_get_profile_not_found(self, client, fake_sb):
        fake_sb.register("profiles", data=None)
        r = client.get("/api/v1/profiles/nonexistent")
        assert r.status_code == 500  # single() on empty raises, caught as 500


class TestFounderValidations:

    def test_get_founder_validations_success(self, client, fake_sb, uid):
        fake_sb.register("posts", data=[{
            "id": str(uuid.uuid4()), "title": "My Idea",
            "author_id": uid, "upvote_count": 3, "downvote_count": 1,
            "comment_count": 5, "tags": ["AI"], "created_at": "2026-01-01T00:00:00+00:00",
            "profiles": {"username": "alice"},
        }])
        r = client.get(f"/api/v1/profiles/{uid}/validations")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["author_username"] == "alice"
        assert data[0]["karma_score"] == 2  # 3 - 1

    def test_get_founder_validations_empty(self, client, fake_sb, uid):
        fake_sb.register("posts", data=[])
        r = client.get(f"/api/v1/profiles/{uid}/validations")
        assert r.status_code == 200
        assert r.json() == []


# ═══════════════════════════════════════════════════════════════════════════
# 2  ARENA — POST /publish, GET /posts, GET /posts/{id}, POST /vote, POST /polls/vote
# ═══════════════════════════════════════════════════════════════════════════

class TestArenaPublish:

    def _setup_publish(self, fake_sb, uid, vid, status="completed"):
        """Register all tables needed for a publish flow."""
        fake_sb.register("validations", data={
            "id": vid, "report_json": {"score": 85},
            "status": status, "user_id": uid,
        })
        fake_sb.register("posts", data=[])  # no existing post (for dup check)

    def test_publish_success(self, client, fake_sb, uid, vid):
        self._setup_publish(fake_sb, uid, vid)
        with patch("realtime_groups.backend.services.reputation_engine.async_add_karma"):
            r = client.post("/api/v1/arena/publish",
                json={"validation_id": vid, "title": "My Idea", "tags": ["SaaS"]},
                headers=H(uid))
        assert r.status_code == 201
        assert "post_id" in r.json()

    def test_publish_wrong_owner_forbidden(self, client, fake_sb, uid, vid):
        other = str(uuid.uuid4())
        fake_sb.register("validations", data={
            "id": vid, "report_json": {}, "status": "completed", "user_id": other,
        })
        r = client.post("/api/v1/arena/publish",
            json={"validation_id": vid, "title": "Stolen", "tags": []},
            headers=H(uid))
        assert r.status_code == 403

    def test_publish_pending_rejected(self, client, fake_sb, uid, vid):
        self._setup_publish(fake_sb, uid, vid, status="pending")
        r = client.post("/api/v1/arena/publish",
            json={"validation_id": vid, "title": "Too Early", "tags": []},
            headers=H(uid))
        assert r.status_code == 422

    def test_publish_duplicate_rejected(self, client, fake_sb, uid, vid):
        fake_sb.register("validations", data={
            "id": vid, "report_json": {}, "status": "completed", "user_id": uid,
        })
        fake_sb.register("posts", data=[{"id": "existing"}])  # already published
        r = client.post("/api/v1/arena/publish",
            json={"validation_id": vid, "title": "Again", "tags": []},
            headers=H(uid))
        assert r.status_code == 409


class TestArenaFeed:

    def test_list_posts_success(self, client, fake_sb):
        fake_sb.register("posts", data=[{
            "id": str(uuid.uuid4()), "title": "Idea A",
            "author_id": str(uuid.uuid4()), "upvote_count": 10,
            "downvote_count": 2, "comment_count": 3,
            "tags": ["AI"], "created_at": "2026-01-01T00:00:00+00:00",
            "profiles": {"username": "charlie"},
        }])
        r = client.get("/api/v1/arena/posts?page=1&page_size=10")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["author_username"] == "charlie"

    def test_list_posts_empty(self, client, fake_sb):
        fake_sb.register("posts", data=[])
        r = client.get("/api/v1/arena/posts")
        assert r.status_code == 200
        assert r.json() == []


class TestArenaPostDetail:

    def test_get_post_success(self, client, fake_sb, pid):
        fake_sb.register("posts", data={
            "id": pid, "title": "Detail Test", "content": "Body",
            "profiles": {"username": "dan", "avatar_url": None, "karma_score": 5, "badges": []},
        })
        r = client.get(f"/api/v1/arena/posts/{pid}")
        assert r.status_code == 200
        assert r.json()["id"] == pid

    def test_get_post_not_found(self, client, fake_sb):
        fake_sb.register("posts", data=None)
        r = client.get(f"/api/v1/arena/posts/{uuid.uuid4()}")
        assert r.status_code == 500  # single() on empty raises


class TestArenaVoting:

    def test_upvote_success(self, client, fake_sb, uid, pid):
        fake_sb.register("post_votes", data=[])
        fake_sb.register("posts", data=[{"author_id": uid, "upvote_count": 1, "downvote_count": 0}])
        with patch("realtime_groups.backend.services.reputation_engine.reward_upvote"):
            r = client.post(f"/api/v1/arena/posts/{pid}/vote",
                json={"direction": 1}, headers=H(uid))
        assert r.status_code == 200
        assert r.json()["new_score"] >= 0

    def test_invalid_vote_direction(self, client, fake_sb, uid, pid):
        r = client.post(f"/api/v1/arena/posts/{pid}/vote",
            json={"direction": 99}, headers=H(uid))
        assert r.status_code == 422  # Pydantic validator rejects


class TestPollVoting:

    def test_poll_vote_success(self, client, fake_sb, uid, pid):
        poll_id = str(uuid.uuid4())
        fake_sb.register("polls", data={
            "id": poll_id,
            "options": [{"id": "opt_a", "text": "SaaS"}, {"id": "opt_b", "text": "OSS"}],
        })
        fake_sb.register("poll_votes", data=[{"poll_id": poll_id}])
        r = client.post(f"/api/v1/arena/posts/{pid}/polls/vote",
            json={"poll_id": poll_id, "option_id": "opt_a"}, headers=H(uid))
        assert r.status_code == 200
        assert r.json()["option_id"] == "opt_a"

    def test_poll_double_vote_rejected(self, client, fake_sb, uid, pid):
        poll_id = str(uuid.uuid4())
        fake_sb.register("polls", data={
            "id": poll_id,
            "options": [{"id": "opt_a", "text": "SaaS"}],
        })
        fake_sb.register("poll_votes", data=None,
            raise_on_execute=Exception('duplicate key violates unique constraint "poll_votes_pkey" (23505)'))
        r = client.post(f"/api/v1/arena/posts/{pid}/polls/vote",
            json={"poll_id": poll_id, "option_id": "opt_a"}, headers=H(uid))
        assert r.status_code == 409

    def test_poll_invalid_option(self, client, fake_sb, uid, pid):
        poll_id = str(uuid.uuid4())
        fake_sb.register("polls", data={
            "id": poll_id,
            "options": [{"id": "opt_a", "text": "SaaS"}],
        })
        r = client.post(f"/api/v1/arena/posts/{pid}/polls/vote",
            json={"poll_id": poll_id, "option_id": "BOGUS"}, headers=H(uid))
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 3  COMMUNITY — GET /hubs, GET /hubs/{id}, GET channels, POST /join, POST /dm
# ═══════════════════════════════════════════════════════════════════════════

class TestHubListing:

    def test_list_hubs_success(self, client, fake_sb):
        hid = str(uuid.uuid4())
        fake_sb.register("hubs", data=[{
            "id": hid, "name": "SaaS Builders", "description": "For SaaS founders",
            "icon_url": None, "member_count": 42,
        }])
        fake_sb.register("channels", data=[], count=3)
        r = client.get("/api/v1/hubs")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["name"] == "SaaS Builders"

    def test_list_hubs_empty(self, client, fake_sb):
        fake_sb.register("hubs", data=[])
        r = client.get("/api/v1/hubs")
        assert r.status_code == 200
        assert r.json() == []


class TestHubDetail:

    def test_get_hub_success(self, client, fake_sb):
        hid = str(uuid.uuid4())
        fake_sb.register("hubs", data={
            "id": hid, "name": "Deep Tech", "description": "Science",
            "icon_url": None, "member_count": 10,
        })
        fake_sb.register("channels", data=[], count=2)
        r = client.get(f"/api/v1/hubs/{hid}")
        assert r.status_code == 200
        assert r.json()["name"] == "Deep Tech"

    def test_get_hub_not_found(self, client, fake_sb):
        fake_sb.register("hubs", data=None)
        r = client.get(f"/api/v1/hubs/{uuid.uuid4()}")
        assert r.status_code == 500  # single() raises


class TestHubChannels:

    def test_list_channels_success(self, client, fake_sb):
        hid = str(uuid.uuid4())
        fake_sb.register("channels", data=[{
            "id": str(uuid.uuid4()), "hub_id": hid,
            "name": "general", "kind": "text", "channel_type": "text",
            "description": "Main chat",
        }])
        r = client.get(f"/api/v1/hubs/{hid}/channels")
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["kind"] == "text"


class TestHubJoin:

    def test_join_hub_new_member(self, client, fake_sb, uid):
        hid = str(uuid.uuid4())
        fake_sb.register("hub_members", data=[])  # not already a member
        fake_sb.register("hubs", data={"member_count": 5})
        r = client.post(f"/api/v1/hubs/{hid}/join", headers=H(uid))
        assert r.status_code == 200
        assert r.json()["already_member"] is False

    def test_join_hub_idempotent(self, client, fake_sb, uid):
        hid = str(uuid.uuid4())
        fake_sb.register("hub_members", data=[{"hub_id": hid}])  # already a member
        r = client.post(f"/api/v1/hubs/{hid}/join", headers=H(uid))
        assert r.status_code == 200
        assert r.json()["already_member"] is True


class TestDMInit:

    def test_dm_init_creates_new_channel(self, client, fake_sb, uid, uid2):
        fake_sb.register("channels", data=[])  # no existing DM
        r = client.post("/api/v1/messages/dm",
            json={"recipient_id": uid2}, headers=H(uid))
        assert r.status_code == 201
        assert "channel_id" in r.json()

    def test_dm_init_returns_existing_channel(self, client, fake_sb, uid, uid2):
        existing_id = str(uuid.uuid4())
        fake_sb.register("channels", data=[{"id": existing_id}])
        r = client.post("/api/v1/messages/dm",
            json={"recipient_id": uid2}, headers=H(uid))
        assert r.status_code == 200  # Note: existing returns 200, not 201

    def test_dm_self_rejected(self, client, fake_sb, uid):
        r = client.post("/api/v1/messages/dm",
            json={"recipient_id": uid}, headers=H(uid))
        assert r.status_code == 400


# ═══════════════════════════════════════════════════════════════════════════
# 4  AI SYNTHESIS & MODERATION WEBHOOKS
# ═══════════════════════════════════════════════════════════════════════════

class TestSynthesis:

    def test_synthesis_success(self, client, fake_sb, uid, pid):
        with patch("realtime_groups.backend.services.synthesis_service.synthesize_thread") as mock_synth:
            mock_synth.return_value = {
                "post_id": pid, "summary": "Strong idea with good TAM.",
                "comment_count": 5, "key_themes": ["pricing", "market"],
                "sentiment_breakdown": {"positive": 70, "negative": 30},
            }
            r = client.post(f"/api/v1/arena/posts/{pid}/synthesize", headers=H(uid))
        assert r.status_code == 200
        d = r.json()
        assert "summary" in d
        assert d["comment_count"] == 5

    def test_synthesis_no_comments_returns_404(self, client, fake_sb, uid, pid):
        with patch("realtime_groups.backend.services.synthesis_service.synthesize_thread") as mock_synth:
            mock_synth.side_effect = ValueError("Post has no visible comments")
            r = client.post(f"/api/v1/arena/posts/{pid}/synthesize", headers=H(uid))
        assert r.status_code == 404


class TestModerationWebhook:

    def test_webhook_accepted(self, client, fake_sb):
        with patch("realtime_groups.backend.workers.celery_tasks.moderate_content_task") as mock_task:
            mock_task.delay = MagicMock()
            r = client.post("/api/v1/webhooks/moderation", json={
                "type": "INSERT", "table": "comments", "schema": "public",
                "record": {"id": str(uuid.uuid4()), "content": "Great idea!",
                           "author_id": str(uuid.uuid4())},
            })
        assert r.status_code == 202
        assert r.json()["status"] == "accepted"

    def test_webhook_unsupported_table_ignored(self, client, fake_sb):
        r = client.post("/api/v1/webhooks/moderation", json={
            "type": "INSERT", "table": "profiles", "schema": "public",
            "record": {"id": "x", "content": "y", "author_id": "z"},
        })
        assert r.status_code == 202
        assert r.json()["status"] == "ignored"

    def test_webhook_missing_fields_skipped(self, client, fake_sb):
        r = client.post("/api/v1/webhooks/moderation", json={
            "type": "INSERT", "table": "comments", "schema": "public",
            "record": {"id": "", "content": "", "author_id": ""},
        })
        assert r.status_code == 202
        assert r.json()["status"] == "skipped"


# ═══════════════════════════════════════════════════════════════════════════
# 5  REPUTATION ENGINE (unit tests — service layer)
# ═══════════════════════════════════════════════════════════════════════════

class TestReputationEngine:

    def test_add_karma_positive(self, fake_sb):
        uid = str(uuid.uuid4())
        fake_sb.register("profiles", data={
            "id": uid, "karma_score": 50, "badges": [], "username": "testuser",
        })
        fake_sb.register("posts", data=[], count=0)

        with patch("realtime_groups.backend.core.supabase_client.get_supabase", return_value=fake_sb):
            from realtime_groups.backend.services.reputation_engine import add_karma
            result = add_karma(uid, 5, "test_upvote")
        assert result["karma_score"] == 55

    def test_karma_floored_at_zero(self, fake_sb):
        uid = str(uuid.uuid4())
        fake_sb.register("profiles", data={
            "id": uid, "karma_score": 5, "badges": [], "username": "testuser",
        })
        fake_sb.register("posts", data=[], count=0)

        with patch("realtime_groups.backend.core.supabase_client.get_supabase", return_value=fake_sb):
            from realtime_groups.backend.services.reputation_engine import add_karma
            result = add_karma(uid, -100, "big_penalty")
        assert result["karma_score"] == 0

    def test_profile_not_found_raises(self, fake_sb):
        uid = str(uuid.uuid4())
        fake_sb.register("profiles", data=None)

        with patch("realtime_groups.backend.core.supabase_client.get_supabase", return_value=fake_sb):
            from realtime_groups.backend.services.reputation_engine import add_karma
            with pytest.raises(ValueError, match="Profile not found"):
                add_karma(uid, 5, "test")


# ═══════════════════════════════════════════════════════════════════════════
# 6  AI MODERATOR (unit tests — service layer)
# ═══════════════════════════════════════════════════════════════════════════

class TestAIModerator:

    def test_groq_catches_toxic_content(self):
        toxic_resp = MagicMock()
        toxic_resp.choices[0].message.content = (
            '{"toxicity_score": 0.95, "spam_score": 0.1, '
            '"verdict": "toxic", "reason": "Severe profanity."}'
        )
        with patch("realtime_groups.backend.services.ai_moderator.Groq") as MockGroq, \
             patch("realtime_groups.backend.services.ai_moderator._hide_content") as mock_hide, \
             patch("realtime_groups.backend.services.ai_moderator._deduct_karma") as mock_karma:
            MockGroq.return_value.chat.completions.create.return_value = toxic_resp
            from realtime_groups.backend.services.ai_moderator import moderate_content
            result = moderate_content("toxic garbage", "comments", str(uuid.uuid4()), str(uuid.uuid4()))
        assert result["verdict"] == "toxic"
        assert result["action_taken"] == "hidden_and_penalized"
        mock_hide.assert_called_once()
        mock_karma.assert_called_once()

    def test_clean_content_no_action(self):
        clean_resp = MagicMock()
        clean_resp.choices[0].message.content = (
            '{"toxicity_score": 0.02, "spam_score": 0.05, '
            '"verdict": "clean", "reason": "Constructive feedback."}'
        )
        with patch("realtime_groups.backend.services.ai_moderator.Groq") as MockGroq:
            MockGroq.return_value.chat.completions.create.return_value = clean_resp
            from realtime_groups.backend.services.ai_moderator import moderate_content
            result = moderate_content("Good pricing strategy.", "comments", str(uuid.uuid4()), str(uuid.uuid4()))
        assert result["verdict"] == "clean"
        assert result["action_taken"] == "none"

    def test_spam_content_hidden_no_karma_penalty(self):
        spam_resp = MagicMock()
        spam_resp.choices[0].message.content = (
            '{"toxicity_score": 0.1, "spam_score": 0.95, '
            '"verdict": "spam", "reason": "Promotional link spam."}'
        )
        with patch("realtime_groups.backend.services.ai_moderator.Groq") as MockGroq, \
             patch("realtime_groups.backend.services.ai_moderator._hide_content") as mock_hide, \
             patch("realtime_groups.backend.services.ai_moderator._deduct_karma") as mock_karma:
            MockGroq.return_value.chat.completions.create.return_value = spam_resp
            from realtime_groups.backend.services.ai_moderator import moderate_content
            result = moderate_content("BUY NOW cheap pills", "messages", str(uuid.uuid4()), str(uuid.uuid4()))
        assert result["verdict"] == "spam"
        assert result["action_taken"] == "hidden_spam"
        mock_hide.assert_called_once()
        mock_karma.assert_not_called()
