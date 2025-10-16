#!/usr/bin/env python3
"""
OpenTelemetry initialization for Petrosa Realtime Strategies service.

This module sets up OpenTelemetry instrumentation for observability,
including metrics, traces, and logs collection.
"""

import logging
import os
import socket
import sys
from typing import Optional

# Add project root to path
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

import constants  # noqa: E402

# Import OpenTelemetry components at module level
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    OTEL_AVAILABLE = True
except ImportError as e:
    OTEL_AVAILABLE = False
    print(f"⚠️  OpenTelemetry not available: {e}")

# Global logger provider for attaching handlers
_global_logger_provider = None
_otlp_logging_handler = None


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
    if not constants.ENABLE_OTEL or not OTEL_AVAILABLE:
        return

    try:

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
            # Parse OTLP headers if provided
            headers_env = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
            span_headers = None
            if headers_env:
                # Parse headers as "key1=value1,key2=value2" format
                headers_list = [
                    tuple(h.split("=", 1)) for h in headers_env.split(",") if "=" in h
                ]
                span_headers = dict(headers_list)
            otlp_exporter = OTLPSpanExporter(
                endpoint=otlp_endpoint,
                headers=span_headers
            )
            trace_provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

        # Set up metrics
        if otlp_endpoint:
            metric_headers_env = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
            metric_headers = None
            if metric_headers_env:
                metric_headers_list = [
                    tuple(h.split("=", 1)) for h in metric_headers_env.split(",") if "=" in h
                ]
                metric_headers = dict(metric_headers_list)
            
            metric_reader = PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=otlp_endpoint, headers=metric_headers),
                export_interval_millis=int(os.getenv("OTEL_METRIC_EXPORT_INTERVAL", "60000"))
            )
            meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
            metrics.set_meter_provider(meter_provider)
            print(f"✅ OpenTelemetry metrics enabled")

        # Set up logging export via OTLP
        if otlp_endpoint:
            global _global_logger_provider
            LoggingInstrumentor().instrument(set_logging_format=False)
            
            log_headers_env = os.getenv("OTEL_EXPORTER_OTLP_HEADERS")
            log_headers = None
            if log_headers_env:
                log_headers_list = [
                    tuple(h.split("=", 1)) for h in log_headers_env.split(",") if "=" in h
                ]
                log_headers = dict(log_headers_list)
            
            log_exporter = OTLPLogExporter(endpoint=otlp_endpoint, headers=log_headers)
            logger_provider = LoggerProvider(resource=resource)
            logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))
            _global_logger_provider = logger_provider
            print(f"✅ OpenTelemetry logging export configured")
            print("   Note: Call attach_logging_handler() for health server in lifespan")

        # Set up HTTP instrumentations
        RequestsInstrumentor().instrument()
        URLLib3Instrumentor().instrument()
        AioHttpClientInstrumentor().instrument()
        
        # Try to instrument FastAPI (optional)
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
            # Note: FastAPI instrumentation will be applied when FastAPI app is created
            print("✅ FastAPI instrumentation available")
        except ImportError:
            print("⚠️  OpenTelemetry FastAPI instrumentation not available")
        
        # Try to instrument asyncio (optional)
        try:
            from opentelemetry.instrumentation.asyncio import AsyncioInstrumentor
            AsyncioInstrumentor().instrument()
        except ImportError:
            print("⚠️  OpenTelemetry asyncio instrumentation not available")

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


def attach_logging_handler():
    """
    Attach OTLP logging handler to root logger and uvicorn loggers.
    
    For FastAPI health server - must attach to uvicorn loggers.
    Call this in the health server's lifespan startup function.
    """
    global _global_logger_provider, _otlp_logging_handler

    if _global_logger_provider is None:
        print("⚠️  Logger provider not configured - logging export not available")
        return False

    try:
        # Get loggers
        root_logger = logging.getLogger()
        uvicorn_logger = logging.getLogger("uvicorn")
        uvicorn_access_logger = logging.getLogger("uvicorn.access")
        uvicorn_error_logger = logging.getLogger("uvicorn.error")

        # Check if handler already attached
        if _otlp_logging_handler is not None:
            if _otlp_logging_handler in root_logger.handlers:
                print("✅ OTLP logging handler already attached")
                return True

        # Create and attach handler
        handler = LoggingHandler(
            level=logging.NOTSET,
            logger_provider=_global_logger_provider,
        )

        # Attach to all loggers
        root_logger.addHandler(handler)
        uvicorn_logger.addHandler(handler)
        uvicorn_access_logger.addHandler(handler)
        uvicorn_error_logger.addHandler(handler)

        _otlp_logging_handler = handler

        print("✅ OTLP logging handler attached to root and uvicorn loggers")
        print(f"   Root logger handlers: {len(root_logger.handlers)}")
        print(f"   Uvicorn logger handlers: {len(uvicorn_logger.handlers)}")

        return True

    except Exception as e:
        print(f"⚠️  Failed to attach logging handler: {e}")
        return False


def attach_logging_handler_simple():
    """
    Attach OTLP logging handler to root logger only.
    
    For the main async service (NATS consumer) - simpler version.
    Call this in main() after setup_telemetry().
    """
    global _global_logger_provider, _otlp_logging_handler

    if _global_logger_provider is None:
        print("⚠️  Logger provider not configured - logging export not available")
        return False

    try:
        root_logger = logging.getLogger()

        # Check if handler already attached
        if _otlp_logging_handler is not None:
            if _otlp_logging_handler in root_logger.handlers:
                print("✅ OTLP logging handler already attached")
                return True

        # Create and attach handler
        handler = LoggingHandler(
            level=logging.NOTSET,
            logger_provider=_global_logger_provider,
        )

        root_logger.addHandler(handler)
        _otlp_logging_handler = handler

        print("✅ OTLP logging handler attached to root logger")
        print(f"   Total handlers: {len(root_logger.handlers)}")

        return True

    except Exception as e:
        print(f"⚠️  Failed to attach logging handler: {e}")
        return False


if __name__ == "__main__":
    setup_telemetry()
    setup_metrics()
