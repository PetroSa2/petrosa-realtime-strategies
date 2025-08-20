#!/usr/bin/env python3
"""
OpenTelemetry initialization for Petrosa Realtime Strategies service.

This module sets up OpenTelemetry instrumentation for observability,
including metrics, traces, and logs collection.
"""

import os
import sys
from typing import Optional

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

import constants  # noqa: E402


def setup_telemetry(service_name: Optional[str] = None) -> None:
    """
    Initialize OpenTelemetry instrumentation.
    
    Args:
        service_name: Name of the service for telemetry
    """
    if not constants.ENABLE_OTEL:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.logging import LoggingInstrumentor
        from opentelemetry.instrumentation.requests import RequestsInstrumentor
        from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
        from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
        from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
        from opentelemetry.instrumentation.nats import NatsInstrumentor

        # Set up resource
        resource = Resource.create({
            "service.name": service_name or constants.OTEL_SERVICE_NAME,
            "service.version": constants.OTEL_SERVICE_VERSION,
            "service.instance.id": os.getenv("HOSTNAME", "unknown"),
            "deployment.environment": constants.ENVIRONMENT,
        })

        # Set up trace provider
        trace_provider = TracerProvider(resource=resource)
        trace.set_tracer_provider(trace_provider)

        # Set up OTLP exporter
        otlp_endpoint = constants.OTEL_EXPORTER_OTLP_ENDPOINT
        if otlp_endpoint:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Set up instrumentations
        LoggingInstrumentor().instrument()
        RequestsInstrumentor().instrument()
        URLLib3Instrumentor().instrument()
        AsyncioInstrumentor().instrument()
        AioHttpClientInstrumentor().instrument()
        
        # NATS instrumentation (if available)
        try:
            NatsInstrumentor().instrument()
        except ImportError:
            pass  # NATS instrumentation not available

        print(f"✅ OpenTelemetry initialized for {service_name or constants.OTEL_SERVICE_NAME}")

    except ImportError as e:
        print(f"⚠️  OpenTelemetry not available: {e}")
    except Exception as e:
        print(f"❌ Failed to initialize OpenTelemetry: {e}")


def setup_metrics() -> None:
    """Set up Prometheus metrics collection."""
    if not constants.PROMETHEUS_ENABLED:
        return

    try:
        from prometheus_client import start_http_server, Counter, Histogram, Gauge
        import threading

        # Start Prometheus HTTP server
        def start_prometheus_server():
            start_http_server(constants.PROMETHEUS_PORT)

        thread = threading.Thread(target=start_prometheus_server, daemon=True)
        thread.start()

        print(f"✅ Prometheus metrics server started on port {constants.PROMETHEUS_PORT}")

    except ImportError:
        print("⚠️  Prometheus client not available")
    except Exception as e:
        print(f"❌ Failed to start Prometheus server: {e}")


if __name__ == "__main__":
    setup_telemetry()
    setup_metrics()
