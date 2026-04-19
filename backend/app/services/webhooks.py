# webhooks.py
# ---------------------------------------------------------------------------
# FEATURE 20: Outbound Webhooks
#
# Delivers event payloads to user-configured webhook URLs with
# cryptographic HMAC-SHA256 signature verification.
#
# SECURITY:
#   - Every payload is signed with the user's webhook secret.
#   - The signature is sent in the `X-Signature-256` header.
#   - Recipients can verify: HMAC-SHA256(secret, body) == header value.
#   - Secrets are NEVER included in the payload.
#
# RELIABILITY:
#   - tenacity exponential backoff (up to 5 attempts).
#   - Only retries on 5xx server errors or connection failures.
#   - 4xx responses are NOT retried (client error = permanent failure).
#   - Delivery attempts are logged for debugging.
#
# DELIVERY EVENTS:
#   - validation.completed   — Full pipeline finished
#   - validation.failed      — Pipeline failed after all retries
#   - alert.triggered        — Smart alert fired (Feature 16)
#   - comparison.completed   — Comparison report generated (Feature 15)
#
# CELERY TASK:
#   The `deliver_webhook` function is a Celery task so it runs
#   asynchronously and doesn't block the main pipeline. Failed
#   deliveries are logged but don't affect pipeline state.
# ---------------------------------------------------------------------------

from __future__ import annotations

import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional

import requests
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)

from celery import Celery

from app.core.config import settings


# ---------------------------------------------------------------------------
# Webhook delivery errors
# ---------------------------------------------------------------------------

class WebhookDeliveryError(Exception):
    """Raised when a webhook delivery fails with a retryable error (5xx)."""
    def __init__(self, status_code: int, url: str, response_body: str = ""):
        self.status_code = status_code
        self.url = url
        self.response_body = response_body
        super().__init__(
            f"Webhook delivery failed: {url} returned HTTP {status_code}"
        )


class WebhookPermanentError(Exception):
    """Raised on 4xx errors — these are NOT retried."""
    pass


# ---------------------------------------------------------------------------
# HMAC-SHA256 Signature Generation
#
# The signature is computed as:
#   sha256=HMAC-SHA256(secret_bytes, payload_bytes)
#
# The recipient verifies by:
#   1. Reading the raw request body.
#   2. Computing HMAC-SHA256 with their stored secret.
#   3. Comparing with the X-Signature-256 header value.
#
# This is the same scheme used by GitHub, Stripe, and Shopify.
# ---------------------------------------------------------------------------

def generate_signature(payload_bytes: bytes, secret: str) -> str:
    """
    Generates an HMAC-SHA256 signature for a webhook payload.

    Args:
        payload_bytes: The raw JSON payload as bytes.
        secret: The webhook secret key (shared with the recipient).

    Returns:
        Signature string in the format: "sha256=<hex_digest>"
    """
    mac = hmac.new(
        key=secret.encode("utf-8"),
        msg=payload_bytes,
        digestmod=hashlib.sha256,
    )
    return f"sha256={mac.hexdigest()}"


def verify_signature(
    payload_bytes: bytes,
    secret: str,
    received_signature: str,
) -> bool:
    """
    Verifies a received webhook signature.

    Utility for recipients to verify payloads from StartupScope.
    Uses constant-time comparison to prevent timing attacks.

    Args:
        payload_bytes: The raw request body.
        secret: The shared secret key.
        received_signature: The value from X-Signature-256 header.

    Returns:
        True if the signature is valid, False otherwise.
    """
    expected = generate_signature(payload_bytes, secret)
    return hmac.compare_digest(expected, received_signature)


# ---------------------------------------------------------------------------
# WEBHOOK DELIVERY with tenacity exponential backoff
#
# Retry strategy:
#   - Wait: 2^attempt seconds (2s, 4s, 8s, 16s, 32s)
#   - Max attempts: 5
#   - Retry on: WebhookDeliveryError (5xx or connection failure)
#   - Don't retry: WebhookPermanentError (4xx)
#   - Timeout: 10 seconds per attempt
# ---------------------------------------------------------------------------

_WEBHOOK_TIMEOUT = 10  # seconds per HTTP request
_WEBHOOK_USER_AGENT = "StartupScope-Webhooks/1.0"


@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=2, max=60),
    retry=retry_if_exception_type(WebhookDeliveryError),
    reraise=True,
)
def _deliver_with_retry(
    url: str,
    payload_bytes: bytes,
    signature: str,
    event_type: str,
    delivery_id: str,
) -> dict:
    """
    Delivers a webhook payload with exponential backoff on 5xx errors.

    Args:
        url: The destination webhook URL.
        payload_bytes: Serialized JSON payload.
        signature: HMAC-SHA256 signature for X-Signature-256 header.
        event_type: Event type for X-Webhook-Event header.
        delivery_id: Unique delivery ID for X-Delivery-ID header.

    Returns:
        Dict with delivery status metadata.

    Raises:
        WebhookDeliveryError: On 5xx errors (retried by tenacity).
        WebhookPermanentError: On 4xx errors (NOT retried).
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": _WEBHOOK_USER_AGENT,
        "X-Signature-256": signature,
        "X-Webhook-Event": event_type,
        "X-Delivery-ID": delivery_id,
        "X-Webhook-Timestamp": str(int(time.time())),
    }

    try:
        response = requests.post(
            url,
            data=payload_bytes,
            headers=headers,
            timeout=_WEBHOOK_TIMEOUT,
        )

        status = response.status_code

        if 200 <= status < 300:
            print(
                f"[Webhook] ✅ Delivered to {url} (HTTP {status}, id={delivery_id}).",
                flush=True,
            )
            return {
                "status": "delivered",
                "http_status": status,
                "delivery_id": delivery_id,
            }

        if 400 <= status < 500:
            # Client error — permanent failure, don't retry
            print(
                f"[Webhook] ❌ Permanent failure: {url} returned HTTP {status}. "
                f"Not retrying.",
                flush=True,
            )
            raise WebhookPermanentError(
                f"Webhook {url} returned HTTP {status}: {response.text[:200]}"
            )

        # 5xx server error — retryable
        print(
            f"[Webhook] ⚠️ Retryable failure: {url} returned HTTP {status}.",
            flush=True,
        )
        raise WebhookDeliveryError(
            status_code=status,
            url=url,
            response_body=response.text[:200],
        )

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
        # Network errors are retryable
        print(f"[Webhook] ⚠️ Connection error to {url}: {e}", flush=True)
        raise WebhookDeliveryError(status_code=0, url=url, response_body=str(e))


# ---------------------------------------------------------------------------
# PUBLIC API: deliver_webhook
#
# This is the function that the pipeline calls. It:
#   1. Serializes the payload to JSON bytes.
#   2. Generates the HMAC-SHA256 signature.
#   3. Delivers with exponential backoff.
#   4. Returns a delivery receipt.
# ---------------------------------------------------------------------------

def deliver_webhook(
    url: str,
    secret: str,
    payload: Dict[str, Any],
    event_type: str = "validation.completed",
    delivery_id: Optional[str] = None,
) -> dict:
    """
    Delivers a signed webhook payload to the specified URL.

    Args:
        url: Destination webhook URL (HTTPS recommended).
        secret: HMAC-SHA256 signing secret (shared with recipient).
        payload: The event data to deliver.
        event_type: Event type string for the X-Webhook-Event header.
        delivery_id: Unique delivery ID (auto-generated if not provided).

    Returns:
        Delivery receipt dict: {status, http_status, delivery_id}.

    Raises:
        WebhookDeliveryError: After 5 failed retry attempts (5xx).
        WebhookPermanentError: On 4xx client errors (immediate).
    """
    import uuid

    if not delivery_id:
        delivery_id = str(uuid.uuid4())

    # Inject metadata into the payload
    enriched_payload = {
        "event": event_type,
        "delivery_id": delivery_id,
        "timestamp": int(time.time()),
        "data": payload,
    }

    # Serialize to canonical JSON (sorted keys for deterministic signing)
    payload_bytes = json.dumps(
        enriched_payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")

    # Generate HMAC-SHA256 signature
    signature = generate_signature(payload_bytes, secret)

    print(
        f"[Webhook] 🚀 Delivering {event_type} to {url} "
        f"(id={delivery_id}, size={len(payload_bytes)} bytes).",
        flush=True,
    )

    try:
        return _deliver_with_retry(
            url=url,
            payload_bytes=payload_bytes,
            signature=signature,
            event_type=event_type,
            delivery_id=delivery_id,
        )
    except WebhookPermanentError as e:
        return {
            "status": "failed_permanent",
            "error": str(e),
            "delivery_id": delivery_id,
        }
    except WebhookDeliveryError as e:
        return {
            "status": "failed_exhausted",
            "error": str(e),
            "delivery_id": delivery_id,
        }


# ---------------------------------------------------------------------------
# CELERY TASK WRAPPER
#
# Wraps deliver_webhook as a Celery task so webhook delivery runs
# asynchronously and doesn't block the main validation pipeline.
#
# Usage from celery_tasks.py:
#   deliver_webhook_task.delay(
#       url="https://example.com/webhook",
#       secret="user_secret",
#       payload={"validation_id": "...", "status": "completed"},
#       event_type="validation.completed",
#   )
# ---------------------------------------------------------------------------

# Import the celery app from the worker module.
# We use a lazy import to avoid circular dependencies.
def _get_celery_app() -> Celery:
    from app.worker.celery_tasks import celery_app
    return celery_app


# Register as a Celery task via a factory pattern
# (avoids import-time circular dependency)
def register_webhook_task():
    """
    Registers the deliver_webhook Celery task.
    Call this after celery_app is initialized.
    """
    app = _get_celery_app()

    @app.task(
        name="app.services.webhooks.deliver_webhook_task",
        max_retries=0,  # tenacity handles retries internally
        acks_late=True,
        reject_on_worker_lost=True,
    )
    def _deliver_webhook_task(
        url: str,
        secret: str,
        payload: dict,
        event_type: str = "validation.completed",
    ) -> dict:
        """
        Celery task wrapper for deliver_webhook.
        Runs asynchronously in the worker process.
        """
        return deliver_webhook(
            url=url,
            secret=secret,
            payload=payload,
            event_type=event_type,
        )

    return _deliver_webhook_task


# ---------------------------------------------------------------------------
# CONVENIENCE: Dispatch webhook for common events
# ---------------------------------------------------------------------------

def dispatch_validation_webhook(
    validation_id: str,
    status: str,
    report_json: Optional[Dict] = None,
    webhook_url: Optional[str] = None,
    webhook_secret: Optional[str] = None,
) -> Optional[dict]:
    """
    Dispatches a webhook for a validation event.

    If no webhook URL is configured, this is a no-op.

    Args:
        validation_id: The validation ID.
        status: 'completed', 'failed', etc.
        report_json: The report data (if completed).
        webhook_url: The destination URL (from user config or env).
        webhook_secret: The HMAC secret (from user config or env).

    Returns:
        Delivery receipt or None if webhooks are not configured.
    """
    # Check for configured webhook URL
    url = webhook_url or getattr(settings, "WEBHOOK_URL", "")
    secret = webhook_secret or getattr(settings, "WEBHOOK_SECRET", "")

    if not url or not secret:
        return None

    event_type = f"validation.{status}"
    payload = {
        "validation_id": validation_id,
        "status": status,
    }
    if report_json:
        payload["report_json"] = report_json

    # Dispatch asynchronously via Celery
    from app.worker.celery_tasks import deliver_webhook_task
    deliver_webhook_task.delay(
        url=url,
        secret=secret,
        payload=payload,
        event_type=event_type,
    )
    
    return {"status": "dispatched", "url": url}
