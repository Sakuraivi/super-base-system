"""OpenTelemetry tracing initialization."""
from __future__ import annotations

import logging
import os

from opentelemetry import trace
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter

logger = logging.getLogger(__name__)


def init_tracing(service_name: str = "superbase-gateway") -> None:
    """Initialize OpenTelemetry tracing.

    - Always adds ConsoleSpanExporter (prints spans to stdout)
    - If OTEL_EXPORTER_OTLP_ENDPOINT is set, adds OTLP gRPC exporter
    """
    resource = Resource.create({"service.name": service_name})
    provider = TracerProvider(resource=resource)

    # Console exporter for development
    provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    # Optional OTLP exporter (for Jaeger, Tempo, etc.)
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        try:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

            provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )
            logger.info("[Tracing] OTLP exporter enabled: %s", otlp_endpoint)
        except ImportError:
            logger.warning("[Tracing] OTLP exporter not installed, using console only")

    trace.set_tracer_provider(provider)
    logger.info("[Tracing] Initialized (service=%s)", service_name)


def get_tracer(name: str) -> trace.Tracer:
    """Get a named tracer instance."""
    return trace.get_tracer(name)
