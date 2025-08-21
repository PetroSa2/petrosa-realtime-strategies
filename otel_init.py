#!/usr/bin/env python3
"""
OpenTelemetry initialization for Petrosa Realtime Strategies service.

This module sets up OpenTelemetry instrumentation for observability,
including metrics, traces, and logs collection.
"""

import os
import sys
from typing import Optional
import socket

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

import constants  # noqa: E402


def find_available_port(start_port: int, max_attempts: int = 10) -> int:
    """Find an available port starting from start_port."""
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('localhost', port))
                return port
        except OSError:
            continue
    return start_port  # Fallback to original port


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
        from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor

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
        AioHttpClientInstrumentor().instrument()
        
        # Try to instrument asyncio (optional)
        try:
            from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
            AsyncioInstrumentor().instrument()
        except ImportError:
            print("⚠️  OpenTelemetry asyncio instrumentation not available")
        
        # NATS instrumentation (if available)
        try:
            from opentelemetry.instrumentation.nats import NatsInstrumentor
            NatsInstrumentor().instrument()
        except ImportError:
            print("⚠️  OpenTelemetry NATS instrumentation not available")

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

        # Find available port for Prometheus
        prometheus_port = find_available_port(constants.PROMETHEUS_PORT)
        
        # Start Prometheus HTTP server
        def start_prometheus_server():
            try:
                start_http_server(prometheus_port)
                print(f"✅ Prometheus metrics server started on port {prometheus_port}")
            except Exception as e:
                print(f"❌ Failed to start Prometheus server on port {prometheus_port}: {e}")

        thread = threading.Thread(target=start_prometheus_server, daemon=True)
        thread.start()

    except ImportError:
        print("⚠️  Prometheus client not available")
    except Exception as e:
        print(f"❌ Failed to start Prometheus server: {e}")


if __name__ == "__main__":
    setup_telemetry()
    setup_metrics()
