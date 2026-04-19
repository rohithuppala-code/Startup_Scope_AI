# alerts.py
# ---------------------------------------------------------------------------
# FEATURE 16: Smart Alerts
#
# When the weekly re-run (Feature 4) detects a significant change via
# deepdiff, this module sends an alert to the user who owns the validation.
#
# ALERT METHODS (in priority order):
#   1. Supabase Edge Function webhook (preferred in production).
#   2. Simple SMTP email (mocked by default, real when SMTP_HOST is set).
#   3. Redis Pub/Sub notification (always active — frontend can show a banner).
#
# DESIGN:
#   - The alert service is called from celery_tasks.py AFTER the temporal
#     comparison detects a significance_score > ALERT_THRESHOLD.
#   - It fetches the user's email from Supabase Auth admin.
#   - The SMTP sender is mocked by default (prints to stdout) and activates
#     when SMTP_HOST, SMTP_USER, SMTP_PASS are set in .env.
#
# THRESHOLD: significance_score > 0.3 triggers an alert.
# This means non-trivial changes (feasibility score shift > 30 points,
# strategy change, new competitors entering, etc.).
# ---------------------------------------------------------------------------

from __future__ import annotations

import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

import redis

from app.core.config import settings
from app.schemas.ai_reports import TemporalDiff
from supabase import create_client, Client


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ALERT_THRESHOLD = 0.3  # Significance score above which alerts are triggered


# ---------------------------------------------------------------------------
# Supabase + Redis clients
# ---------------------------------------------------------------------------
_supabase: Client | None = None


def _get_supabase() -> Client:
    global _supabase
    if _supabase is None:
        _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)
    return _supabase


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.REDIS_URL, decode_responses=True)


# ---------------------------------------------------------------------------
# STEP 1: Determine if an alert should fire
# ---------------------------------------------------------------------------

def should_alert(temporal_diff: Optional[TemporalDiff]) -> bool:
    """
    Returns True if the temporal change is significant enough to alert.

    Criteria:
      - temporal_diff is not None (i.e., this is NOT the first version)
      - significance_score > ALERT_THRESHOLD (0.3)
      - There are actual changes detected
    """
    if temporal_diff is None:
        return False

    if temporal_diff.significance_score <= ALERT_THRESHOLD:
        return False

    if not temporal_diff.changes:
        return False

    return True


# ---------------------------------------------------------------------------
# STEP 2: Fetch user email from Supabase Auth
# ---------------------------------------------------------------------------

def _get_user_email(validation_id: str) -> Optional[str]:
    """
    Looks up the user's email from the validation row's user_id.

    Flow:
      1. Fetch user_id from the validations table.
      2. Use Supabase Auth admin to get the user's email.
    """
    supabase = _get_supabase()

    try:
        # Get user_id from the validation
        result = (
            supabase.table("validations")
            .select("user_id")
            .eq("id", validation_id)
            .single()
            .execute()
        )

        if not result.data or not result.data.get("user_id"):
            print(f"[Alerts] No user_id found for validation {validation_id}.", flush=True)
            return None

        user_id = result.data["user_id"]

        # Get email from Supabase Auth admin
        user = supabase.auth.admin.get_user_by_id(user_id)
        if user and hasattr(user, "user") and user.user:
            return user.user.email
        elif isinstance(user, dict):
            return user.get("user", {}).get("email")

        return None

    except Exception as e:
        print(f"[Alerts] Failed to fetch user email: {e}", flush=True)
        return None


# ---------------------------------------------------------------------------
# STEP 3: Send alerts
# ---------------------------------------------------------------------------

def _build_alert_html(
    temporal_diff: TemporalDiff,
    idea_description: str = "",
) -> str:
    """Builds a professional HTML email body for the alert."""
    changes_html = "".join(
        f"<li><strong>{c.field_path}</strong>: "
        f"<span style='color:#f87171'>{c.old_value[:80]}</span> → "
        f"<span style='color:#4ade80'>{c.new_value[:80]}</span></li>"
        for c in temporal_diff.changes[:10]
    )

    return f"""
    <div style="font-family: Inter, sans-serif; background: #0f0f1a; color: #e0e0ef; padding: 40px; border-radius: 12px;">
        <h1 style="color: #7b93db;">🔔 StartupScope AI — Alert</h1>
        <p style="color: #8a8aaa;">Significant changes detected in your validation report.</p>

        <div style="background: #1a1a2e; border-radius: 10px; padding: 20px; margin: 20px 0; border: 1px solid rgba(100,149,237,0.15);">
            <h2 style="color: #fbbf24; font-size: 14pt;">⚠️ Significance Score: {temporal_diff.significance_score:.0%}</h2>
            <p>Version {temporal_diff.old_version} → {temporal_diff.new_version}</p>
        </div>

        <div style="background: #1a1a2e; border-radius: 10px; padding: 20px; margin: 20px 0; border: 1px solid rgba(100,149,237,0.15);">
            <h3 style="color: #7b93db;">Changes Detected</h3>
            <ul style="color: #c0c0d8;">{changes_html}</ul>
        </div>

        <div style="background: #1a1a2e; border-radius: 10px; padding: 20px; margin: 20px 0; border: 1px solid rgba(100,149,237,0.15);">
            <h3 style="color: #7b93db;">AI Analysis</h3>
            <p style="color: #c0c0d8;">{temporal_diff.change_narrative[:500]}</p>
        </div>

        <p style="color: #4a4a6a; font-size: 10pt; margin-top: 30px;">
            You received this alert because your startup validation report changed significantly.
            Log in to StartupScope AI to review the full report.
        </p>
    </div>
    """


def send_email_alert(
    to_email: str,
    temporal_diff: TemporalDiff,
    idea_description: str = "",
) -> bool:
    """
    Sends an email alert via SMTP.

    If SMTP is not configured (no SMTP_HOST in settings), this function
    MOCKS the email by printing to stdout — useful for development.

    Returns True if the email was sent (or mocked) successfully.
    """
    subject = (
        f"🔔 StartupScope Alert: Significant change detected "
        f"(v{temporal_diff.old_version} → v{temporal_diff.new_version})"
    )
    html_body = _build_alert_html(temporal_diff, idea_description)

    # Check if SMTP is configured
    smtp_host = getattr(settings, "SMTP_HOST", "")
    if not smtp_host:
        # MOCK MODE: Print to stdout instead of sending email
        print(
            f"[Alerts] 📧 MOCK EMAIL (SMTP not configured):\n"
            f"  To: {to_email}\n"
            f"  Subject: {subject}\n"
            f"  Significance: {temporal_diff.significance_score:.0%}\n"
            f"  Changes: {len(temporal_diff.changes)} fields changed\n"
            f"  Narrative: {temporal_diff.change_narrative[:200]}",
            flush=True,
        )
        return True

    # REAL SMTP: Send the email
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = getattr(settings, "SMTP_FROM", "alerts@startupscope.ai")
        msg["To"] = to_email
        msg.attach(MIMEText(html_body, "html"))

        smtp_port = int(getattr(settings, "SMTP_PORT", 587))
        smtp_user = getattr(settings, "SMTP_USER", "")
        smtp_pass = getattr(settings, "SMTP_PASS", "")

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            if smtp_user and smtp_pass:
                server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        print(f"[Alerts] ✅ Email sent to {to_email}.", flush=True)
        return True

    except Exception as e:
        print(f"[Alerts] ❌ Email send failed: {e}", flush=True)
        return False


def send_redis_alert(
    validation_id: str,
    temporal_diff: TemporalDiff,
) -> None:
    """
    Publishes an alert event to the Redis Pub/Sub channel.

    The frontend can listen on the WebSocket for alerts and show a banner.
    This always fires — regardless of SMTP configuration.
    """
    try:
        r = _get_redis()
        r.publish("validation_events", json.dumps({
            "validation_id": validation_id,
            "status": "alert",
            "alert_type": "temporal_change",
            "significance_score": temporal_diff.significance_score,
            "old_version": temporal_diff.old_version,
            "new_version": temporal_diff.new_version,
            "change_count": len(temporal_diff.changes),
            "narrative": temporal_diff.change_narrative[:300],
        }))
        print(f"[Alerts] 📢 Redis alert published for {validation_id}.", flush=True)
    except Exception as e:
        print(f"[Alerts] Redis alert failed: {e}", flush=True)


# ---------------------------------------------------------------------------
# ORCHESTRATOR: Called from celery_tasks.py after temporal comparison
# ---------------------------------------------------------------------------

def process_alert(
    validation_id: str,
    temporal_diff: Optional[TemporalDiff],
    idea_description: str = "",
) -> None:
    """
    Checks if an alert should fire and dispatches it via all channels.

    Called from celery_tasks.py AFTER run_temporal_comparison().

    Args:
        validation_id: The validation that was re-run.
        temporal_diff: The diff result from the temporal comparison.
        idea_description: For email context.
    """
    if not should_alert(temporal_diff):
        print(
            f"[Alerts] No alert for {validation_id} "
            f"(significance: {temporal_diff.significance_score if temporal_diff else 'N/A'}).",
            flush=True,
        )
        return

    print(
        f"[Alerts] 🚨 Alert triggered for {validation_id}! "
        f"Significance: {temporal_diff.significance_score:.0%}, "
        f"Changes: {len(temporal_diff.changes)}.",
        flush=True,
    )

    # 1. Always send Redis alert (frontend banner)
    send_redis_alert(validation_id, temporal_diff)

    # 2. Try to send email alert
    email = _get_user_email(validation_id)
    if email:
        send_email_alert(email, temporal_diff, idea_description)
    else:
        print(f"[Alerts] No email found for validation {validation_id}. Skipping email alert.", flush=True)
