import os
import asyncio
import requests
import websockets
import json
import sys
import time
from supabase import create_client

from app.core.config import settings

EMAIL = "kingjames.08623@gmail.com"
PASSWORD = "Likhith@123"
BASE_URL = "http://localhost:8000"
WS_BASE_URL = "ws://localhost:8000"

# ─── ANSI Colors ───────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):  print(f"  {GREEN}✅ {msg}{RESET}")
def fail(msg): print(f"  {RED}❌ {msg}{RESET}"); 
def info(msg): print(f"  {CYAN}ℹ  {msg}{RESET}")
def section(msg): print(f"\n{BOLD}{YELLOW}{'='*60}\n  {msg}\n{'='*60}{RESET}")

errors = []

# ─── TEST 1: Supabase Auth ─────────────────────────────────────
section("TEST 1 — Supabase Auth Login")
try:
    supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    response = supabase.auth.sign_in_with_password({"email": EMAIL, "password": PASSWORD})
    user_id = response.user.id
    ok(f"Authenticated successfully. User ID: {user_id}")
except Exception as e:
    fail(f"Auth Failed: {e}")
    sys.exit(1)

# ─── TEST 2: Health Check ──────────────────────────────────────
section("TEST 2 — FastAPI Server Health Check")
try:
    r = requests.get(f"{BASE_URL}/docs", timeout=5)
    if r.status_code == 200:
        ok(f"FastAPI is alive. /docs returned 200.")
    else:
        fail(f"/docs returned HTTP {r.status_code}")
        errors.append("health_check")
except Exception as e:
    fail(f"Cannot reach FastAPI at {BASE_URL}: {e}")
    errors.append("health_check")

# ─── TEST 3: Missing Header → 422 ─────────────────────────────
section("TEST 3 — POST /api/v1/validate (missing x-user-id → 422)")
try:
    r = requests.post(f"{BASE_URL}/api/v1/validate", json={"idea_description": "Test idea"}, timeout=5)
    if r.status_code == 422:
        ok(f"Correctly rejected with 422 Unprocessable Entity (missing header).")
    else:
        fail(f"Expected 422, got {r.status_code}: {r.text[:200]}")
        errors.append("missing_header")
except Exception as e:
    fail(f"Request failed: {e}")
    errors.append("missing_header")

# ─── TEST 4: Short idea → 422 ──────────────────────────────────
section("TEST 4 — POST /api/v1/validate (idea too short → 422)")
try:
    r = requests.post(
        f"{BASE_URL}/api/v1/validate",
        headers={"x-user-id": user_id},
        json={"idea_description": "short"},
        timeout=5
    )
    if r.status_code == 422:
        ok(f"Correctly rejected with 422 (idea_description min_length=10 enforced).")
    else:
        fail(f"Expected 422, got {r.status_code}: {r.text[:200]}")
        errors.append("short_idea")
except Exception as e:
    fail(f"Request failed: {e}")
    errors.append("short_idea")

# ─── TEST 5: Valid Submit → 202 ────────────────────────────────
section("TEST 5 — POST /api/v1/validate (valid request → 202 Accepted)")
IDEA = f"An AI-powered SaaS platform that automates the generation of unit tests for Python and JavaScript codebases. [Test Run {int(time.time())}]"
headers = {"x-user-id": user_id, "Content-Type": "application/json"}
payload = {
    "idea_description": IDEA,
    "target_market": "Software Developers, QA Engineers",
    "budget_constraints": "$0 open source, $50/mo enterprise"
}
validation_id = None
try:
    r = requests.post(f"{BASE_URL}/api/v1/validate", headers=headers, json=payload, timeout=10)
    if r.status_code == 202:
        data = r.json()
        validation_id = data["validation_id"]
        ok(f"Accepted! Validation ID: {validation_id}, Status: {data['status']}")
    else:
        fail(f"Expected 202, got {r.status_code}: {r.text[:300]}")
        errors.append("submit_validate")
        sys.exit(1)
except Exception as e:
    fail(f"Request failed: {e}")
    errors.append("submit_validate")
    sys.exit(1)

# ─── TEST 6: Supabase Row Verification ─────────────────────────
section("TEST 6 — Supabase DB Row Verification")
try:
    row = supabase.table("validations").select("*").eq("id", validation_id).single().execute()
    d = row.data
    if d:
        ok(f"Row exists in DB. Status: {d.get('status')}, idea_hash: {d.get('idea_hash','')[:16]}...")
        if d.get("user_id") == user_id:
            ok(f"user_id matches authenticated user.")
        else:
            fail(f"user_id mismatch! DB: {d.get('user_id')} vs Auth: {user_id}")
            errors.append("user_id_mismatch")
    else:
        fail(f"No row found in DB for validation_id={validation_id}")
        errors.append("db_row_missing")
except Exception as e:
    fail(f"DB check failed: {e}")
    errors.append("db_check")

# ─── TEST 7: WebSocket + Full Pipeline ────────────────────────
section("TEST 7 — WebSocket Real-time + Full AI Pipeline (max 180s)")

async def test_websocket_pipeline():
    ws_url = f"{WS_BASE_URL}/ws/validation/{validation_id}"
    info(f"Connecting to: {ws_url}")
    try:
        async with websockets.connect(ws_url, open_timeout=10) as ws:
            ok("WebSocket connected! Waiting for Celery worker to complete AI pipeline...")
            start = time.time()
            message_str = await asyncio.wait_for(ws.recv(), timeout=180.0)
            elapsed = time.time() - start
            message = json.loads(message_str)
            ok(f"Redis Pub/Sub event received after {elapsed:.1f}s!")
            info(f"Event payload: {json.dumps(message, indent=4)}")

            if message.get("status") == "completed":
                # Verify DB was written
                final_row = supabase.table("validations").select("*").eq("id", validation_id).single().execute()
                fd = final_row.data
                ok(f"DB status: {fd.get('status')}")
                ok(f"Tokens used: {fd.get('tokens_used')}")
                ok(f"Estimated cost: ${fd.get('estimated_cost', 0):.6f}")

                report = fd.get("report_json", {})
                ok(f"Feasibility Score: {report.get('feasibility_score')}/100")
                ok(f"Market Viability: {report.get('market_viability')}")
                ok(f"Gaps Identified: {len(report.get('gaps_identified', []))} items")

                markdown = fd.get("markdown_report", "")
                ok(f"Markdown report length: {len(markdown)} chars")
                info(f"Markdown preview:\n{markdown[:500]}...")
                return True
            else:
                fail(f"Pipeline returned non-completed status: {message}")
                errors.append("pipeline_failed")

                # Fetch error from DB
                err_row = supabase.table("validations").select("error_message").eq("id", validation_id).single().execute()
                fail(f"DB error_message: {err_row.data.get('error_message')}")
                return False

    except asyncio.TimeoutError:
        fail("WebSocket timed out after 180s — Celery worker did not publish completion event.")
        row = supabase.table("validations").select("status, error_message").eq("id", validation_id).single().execute()
        fail(f"DB status at timeout: {row.data}")
        errors.append("ws_timeout")
        return False
    except Exception as e:
        fail(f"WebSocket error: {e}")
        errors.append("ws_error")
        return False

pipeline_passed = asyncio.run(test_websocket_pipeline())

# ─── TEST 8: Idempotency (same key → 409) ─────────────────────
section("TEST 8 — Idempotency Key Deduplication (same key → 409)")
try:
    idem_key = f"test-idem-key-{int(time.time())}"
    # First request
    r1 = requests.post(
        f"{BASE_URL}/api/v1/validate",
        headers=headers,
        json={**payload, "idempotency_key": idem_key},
        timeout=10
    )
    if r1.status_code == 202:
        ok(f"First request with idempotency_key accepted (202).")
        # Second request with same key
        r2 = requests.post(
            f"{BASE_URL}/api/v1/validate",
            headers=headers,
            json={**payload, "idempotency_key": idem_key},
            timeout=10
        )
        if r2.status_code == 409:
            ok("Second request with same idempotency_key correctly rejected (409 Conflict).")
        else:
            fail(f"Expected 409, got {r2.status_code}: {r2.text[:200]}")
            errors.append("idempotency")
    else:
        fail(f"First idempotency request failed: {r1.status_code}: {r1.text[:200]}")
        errors.append("idempotency")
except Exception as e:
    fail(f"Idempotency test failed: {e}")
    errors.append("idempotency")

# ─── FINAL REPORT ─────────────────────────────────────────────
section("FINAL TEST REPORT")
if not errors:
    print(f"\n  {GREEN}{BOLD}🎉 ALL TESTS PASSED PERFECTLY! 🎉{RESET}\n")
else:
    print(f"\n  {RED}{BOLD}❌ {len(errors)} TEST(S) FAILED: {errors}{RESET}\n")
    sys.exit(1)
