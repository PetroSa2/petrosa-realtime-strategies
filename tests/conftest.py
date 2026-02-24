import os

import pytest

# Disable OpenTelemetry auto-initialization during tests
os.environ["OTEL_NO_AUTO_INIT"] = "1"
os.environ["OTEL_SDK_DISABLED"] = "true"
os.environ["OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"] = "false"


def pytest_configure(config):
    """
    Setup before any tests are run.
    """
    os.environ["OTEL_NO_AUTO_INIT"] = "1"
    os.environ["OTEL_SDK_DISABLED"] = "true"


"""
Pytest configuration and fixtures for Petrosa Realtime Strategies tests.
"""

import os
from unittest.mock import Mock

import pytest
import structlog

# Disable OpenTelemetry auto-initialization during tests
os.environ["OTEL_NO_AUTO_INIT"] = "1"
os.environ["OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED"] = "false"


def pytest_configure(config):
    """Setup before any tests are run."""
    os.environ["OTEL_NO_AUTO_INIT"] = "1"


# Set up OpenTelemetry tracer provider BEFORE any imports that use it
# This ensures test spans are captured correctly
_test_span_exporter = None
_test_tracer_provider = None

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        SimpleSpanProcessor,
    )
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
        InMemorySpanExporter,
    )

    # Set up tracer provider early, before any test imports
    # Check if provider is already a TracerProvider (not a ProxyTracerProvider)
    current_provider = trace.get_tracer_provider()
    if not isinstance(current_provider, TracerProvider):
        # Provider not set yet, set it up
        _test_span_exporter = InMemorySpanExporter()
        _test_tracer_provider = TracerProvider()
        _test_tracer_provider.add_span_processor(
            SimpleSpanProcessor(_test_span_exporter)
        )
        try:
            trace.set_tracer_provider(_test_tracer_provider)
        except Exception:
            # Provider already set by another import, use current one
            # IMPORTANT: Add exporter to the current provider (the one actually being used)
            _test_tracer_provider = trace.get_tracer_provider()
            if isinstance(_test_tracer_provider, TracerProvider):
                _test_tracer_provider.add_span_processor(
                    SimpleSpanProcessor(_test_span_exporter)
                )
except ImportError:
    # OpenTelemetry not available - skip setup
    pass


@pytest.fixture
def logger():
    """Provide a test logger."""
    return structlog.get_logger()


@pytest.fixture
def mock_nats_client():
    """Provide a mock NATS client."""
    client = Mock()
    client.is_connected = True
    return client


@pytest.fixture
def sample_market_data():
    """Provide sample market data for testing."""
    return {
        "stream": "btcusdt@depth20",
        "data": {
            "symbol": "BTCUSDT",
            "event_time": 1234567890000,
            "first_update_id": 123456789,
            "final_update_id": 123456789,
            "bids": [
                {"price": "50000.00", "quantity": "1.0"},
                {"price": "49999.00", "quantity": "2.0"},
            ],
            "asks": [
                {"price": "50001.00", "quantity": "1.0"},
                {"price": "50002.00", "quantity": "2.0"},
            ],
        },
    }


@pytest.fixture
def sample_trade_data():
    """Provide sample trade data for testing."""
    return {
        "stream": "btcusdt@trade",
        "data": {
            "symbol": "BTCUSDT",
            "trade_id": 123456789,
            "price": "50000.00",
            "quantity": "1.0",
            "buyer_order_id": 123456789,
            "seller_order_id": 123456790,
            "trade_time": 1234567890000,
            "is_buyer_maker": False,
            "event_time": 1234567890000,
        },
    }


@pytest.fixture
def sample_ticker_data():
    """Provide sample ticker data for testing."""
    return {
        "stream": "btcusdt@ticker",
        "data": {
            "symbol": "BTCUSDT",
            "price_change": "100.00",
            "price_change_percent": "0.2",
            "weighted_avg_price": "50000.00",
            "prev_close_price": "49900.00",
            "last_price": "50000.00",
            "last_qty": "1.0",
            "bid_price": "49999.00",
            "bid_qty": "1.0",
            "ask_price": "50001.00",
            "ask_qty": "1.0",
            "open_price": "49900.00",
            "high_price": "50100.00",
            "low_price": "49800.00",
            "volume": "1000.0",
            "quote_volume": "50000000.0",
            "open_time": 1234567890000,
            "close_time": 1234567890000,
            "first_id": 123456789,
            "last_id": 123456790,
            "count": 100,
            "event_time": 1234567890000,
        },
    }
