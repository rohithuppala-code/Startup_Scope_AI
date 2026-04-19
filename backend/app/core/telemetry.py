# telemetry.py
# ---------------------------------------------------------------------------
# FEATURE 18: Observability — OpenTelemetry Tracing
#
# Provides structured tracing for all AI model calls via OpenTelemetry.
#
# DESIGN:
#   - Uses the standard OpenTelemetry Python SDK.
#   - Exports traces to an OTLP-compatible backend (Jaeger, Tempo, etc.).
#   - Falls back to console export if no OTLP endpoint is configured.
#   - Provides a `track_ai_call()` context manager that records:
#       * model_name, latency_ms, input_tokens, output_tokens
#       * estimated_cost (from cost_guard pricing table)
#       * error (if the call fails)
#       * validation_id (for correlation)
#
# CONFIGURATION:
#   - OTEL_EXPORTER_OTLP_ENDPOINT env var (e.g., "http://jaeger:4317")
#   - If not set, traces are printed to console (useful for development).
#
# USAGE IN ai_pipeline.py:
#   with track_ai_call("gemini-2.0-flash", validation_id="...") as span:
#       response = client.generate(...)
#       span.set_tokens(input=1000, output=500)
# ---------------------------------------------------------------------------

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Optional

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.resources import Resource

from app.core.config import settings
from app.services.cost_guard import compute_actual_cost


# ---------------------------------------------------------------------------
# INITIALIZATION
#
# Called once at import time. Sets up the TracerProvider with either:
#   1. OTLP gRPC exporter (if OTEL_EXPORTER_OTLP_ENDPOINT is set)
#   2. Console exporter (fallback for development)
# ---------------------------------------------------------------------------

_INITIALIZED = False


def init_telemetry() -> None:
    """
    Initializes the OpenTelemetry TracerProvider.

    Safe to call multiple times — only initializes once.
    """
    global _INITIALIZED
    if _INITIALIZED:
        return

    resource = Resource.create({
        "service.name": "startupscope-ai",
        "service.version": "2.0.0",
        "deployment.environment": getattr(settings, "ENVIRONMENT", "development"),
    })

    provider = TracerProvider(resource=resource)

    # Try OTLP exporter first, fall back to console
    otlp_endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")

    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            print(f"[Telemetry] OTLP exporter configured: {otlp_endpoint}", flush=True)
        except ImportError:
            print(
                "[Telemetry] OTLP exporter not available. "
                "Install opentelemetry-exporter-otlp-proto-grpc.",
                flush=True,
            )
            provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    else:
        # Console exporter for development
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        print("[Telemetry] Console exporter configured (no OTLP endpoint).", flush=True)

    trace.set_tracer_provider(provider)
    _INITIALIZED = True


# Initialize on import
init_telemetry()

# Module-level tracer
tracer = trace.get_tracer("startupscope.ai", "2.0.0")


# ---------------------------------------------------------------------------
# AI CALL TRACKING — Context Manager
#
# Usage:
#   with track_ai_call("gemini-2.0-flash", validation_id="abc") as span:
#       response = client.models.generate_content(...)
#       span.set_tokens(
#           input_tokens=response.usage_metadata.prompt_token_count,
#           output_tokens=response.usage_metadata.candidates_token_count,
#       )
# ---------------------------------------------------------------------------

class AICallSpan:
    """
    Wrapper around an OpenTelemetry span with AI-specific helpers.

    Tracks model name, latency, token counts, and estimated cost.
    """

    def __init__(
        self,
        span: trace.Span,
        model_name: str,
        start_time: float,
    ):
        self._span = span
        self._model_name = model_name
        self._start_time = start_time
        self._input_tokens: int = 0
        self._output_tokens: int = 0

    def set_tokens(
        self,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        """
        Records the actual token counts from the API response.

        Should be called AFTER the LLM call completes.
        """
        self._input_tokens = input_tokens
        self._output_tokens = output_tokens

        self._span.set_attribute("ai.input_tokens", input_tokens)
        self._span.set_attribute("ai.output_tokens", output_tokens)
        self._span.set_attribute(
            "ai.total_tokens", input_tokens + output_tokens
        )

        # Compute cost from the pricing table
        cost = compute_actual_cost(
            model_name=self._model_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self._span.set_attribute("ai.estimated_cost_usd", cost)

    def set_error(self, error: Exception) -> None:
        """Records an error on the span."""
        self._span.set_attribute("ai.error", True)
        self._span.set_attribute("ai.error_type", type(error).__name__)
        self._span.set_attribute("ai.error_message", str(error)[:500])
        self._span.record_exception(error)
        self._span.set_status(trace.StatusCode.ERROR, str(error)[:200])

    def finalize(self) -> None:
        """
        Finalizes the span with latency and summary attributes.
        Called automatically by the context manager on exit.
        """
        latency_ms = (time.time() - self._start_time) * 1000
        self._span.set_attribute("ai.latency_ms", latency_ms)

        print(
            f"[Telemetry] {self._model_name}: "
            f"latency={latency_ms:.0f}ms, "
            f"tokens={self._input_tokens}+{self._output_tokens}, "
            f"cost=${compute_actual_cost(self._model_name, self._input_tokens, self._output_tokens):.6f}",
            flush=True,
        )


@contextmanager
def track_ai_call(
    model_name: str,
    validation_id: Optional[str] = None,
    operation: str = "generate",
):
    """
    Context manager that traces an AI model call.

    Records: model_name, latency_ms, input_tokens, output_tokens,
    estimated_cost_usd, and errors.

    Args:
        model_name: The AI model being called (e.g., "gemini-2.0-flash").
        validation_id: For correlation with the validation pipeline.
        operation: The operation type (e.g., "generate", "embed", "extract").

    Yields:
        AICallSpan: Call `.set_tokens()` after the LLM responds.

    Example:
        with track_ai_call("gemini-2.0-flash", validation_id="abc") as span:
            response = client.generate(...)
            span.set_tokens(input_tokens=1000, output_tokens=500)
    """
    span_name = f"ai.{operation}.{model_name}"

    with tracer.start_as_current_span(span_name) as otel_span:
        # Set initial attributes
        otel_span.set_attribute("ai.model", model_name)
        otel_span.set_attribute("ai.operation", operation)
        if validation_id:
            otel_span.set_attribute("validation.id", validation_id)

        ai_span = AICallSpan(
            span=otel_span,
            model_name=model_name,
            start_time=time.time(),
        )

        try:
            yield ai_span
        except Exception as e:
            ai_span.set_error(e)
            raise
        finally:
            ai_span.finalize()


# ---------------------------------------------------------------------------
# PIPELINE SPAN — tracks the entire validation pipeline
# ---------------------------------------------------------------------------

@contextmanager
def track_pipeline(validation_id: str):
    """
    Context manager that traces the entire validation pipeline.

    Wraps all 14 steps in a single parent span for end-to-end visibility.

    Usage in celery_tasks.py:
        with track_pipeline(validation_id) as span:
            ... all 14 pipeline steps ...
    """
    with tracer.start_as_current_span("pipeline.process_validation") as span:
        span.set_attribute("validation.id", validation_id)
        span.set_attribute("pipeline.version", "2.0")
        try:
            yield span
        except Exception as e:
            span.set_status(trace.StatusCode.ERROR, str(e)[:200])
            span.record_exception(e)
            raise
