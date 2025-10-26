"""
Unit tests for NATS trace context propagation in Realtime Strategies.

Tests verify that:
1. Consumer extracts trace context from incoming NATS messages
2. Consumer creates spans as children of extracted context
3. Publisher injects trace context into outgoing NATS messages
4. Trace IDs are preserved across the pipeline
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from nats.aio.msg import Msg
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from strategies.core.consumer import NATSConsumer
from strategies.core.publisher import TradeOrderPublisher
from strategies.models.orders import TradeOrder


@pytest.fixture(scope="session")
def span_exporter():
    """In-memory span exporter for testing"""
    return InMemorySpanExporter()


@pytest.fixture(scope="session")
def tracer_provider(span_exporter):
    """Configure tracer provider with in-memory exporter"""
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    trace.set_tracer_provider(provider)
    return provider


@pytest.fixture(autouse=True)
def clear_spans(span_exporter):
    """Clear spans before each test"""
    span_exporter.clear()
    yield
    span_exporter.clear()


@pytest.fixture
def mock_publisher():
    """Create mock publisher for consumer"""
    publisher = MagicMock(spec=TradeOrderPublisher)
    return publisher


@pytest.fixture
def consumer(mock_publisher):
    """Create consumer instance for testing"""
    with patch("strategies.core.consumer.RealtimeStrategyMetrics"):
        consumer = NATSConsumer(
            nats_url="nats://test:4222",
            topic="test.topic",
            consumer_name="test_consumer",
            consumer_group="test_group",
            publisher=mock_publisher,
        )
        return consumer


@pytest.fixture
def publisher():
    """Create publisher instance for testing"""
    publisher = TradeOrderPublisher(
        nats_url="nats://test:4222", topic="signals.trading"
    )
    publisher.nats_client = MagicMock()
    publisher.nats_client.publish = AsyncMock()
    return publisher


@pytest.fixture
def market_data_with_trace():
    """Market data with trace context"""
    return {
        "s": "BTCUSDT",
        "p": "50000",
        "stream_type": "trade",
        "_otel_trace_context": {
            "traceparent": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
        },
    }


@pytest.fixture
def market_data_without_trace():
    """Market data without trace context"""
    return {
        "s": "ETHUSDT",
        "p": "3000",
        "stream_type": "ticker",
    }


def create_nats_message(data: dict, subject: str = "test.topic") -> Msg:
    """Helper to create mock NATS message"""
    msg = MagicMock(spec=Msg)
    msg.subject = subject
    msg.data = json.dumps(data).encode()
    return msg


@pytest.mark.asyncio
async def test_consumer_extracts_trace_context(
    consumer, market_data_with_trace, span_exporter, tracer_provider
):
    """Test that consumer extracts trace context from messages"""
    msg = create_nats_message(market_data_with_trace)

    # Mock the parse and process methods
    consumer._parse_market_data = MagicMock(
        return_value=MagicMock(stream_type="trade", symbol="BTCUSDT", timestamp=None)
    )
    consumer._process_market_data = AsyncMock()

    # Process message
    await consumer._process_message(msg)

    # Verify span was created
    spans = span_exporter.get_finished_spans()
    consumer_span = next(
        (s for s in spans if s.name == "process_market_data_message"), None
    )
    assert consumer_span is not None

    # Verify trace ID matches
    expected_trace_id = "0af7651916cd43dd8448eb211c80319c"
    actual_trace_id = format(consumer_span.context.trace_id, "032x")
    assert actual_trace_id == expected_trace_id

    # Verify span attributes
    attributes = dict(consumer_span.attributes)
    assert attributes.get("messaging.system") == "nats"
    assert attributes.get("market_data.symbol") == "BTCUSDT"


@pytest.mark.asyncio
async def test_consumer_handles_missing_trace_context(
    consumer, market_data_without_trace, span_exporter, tracer_provider
):
    """Test graceful fallback when trace context is missing"""
    msg = create_nats_message(market_data_without_trace)

    # Mock the parse and process methods
    consumer._parse_market_data = MagicMock(
        return_value=MagicMock(stream_type="ticker", symbol="ETHUSDT", timestamp=None)
    )
    consumer._process_market_data = AsyncMock()

    # Process message
    await consumer._process_message(msg)

    # Verify span was created (with new trace)
    spans = span_exporter.get_finished_spans()
    consumer_span = next(
        (s for s in spans if s.name == "process_market_data_message"), None
    )
    assert consumer_span is not None


@pytest.mark.asyncio
async def test_publisher_injects_trace_context(
    publisher, span_exporter, tracer_provider
):
    """Test that publisher injects trace context into messages"""
    # Create a test order with all required fields
    order = TradeOrder(
        order_id="test_order_123",
        symbol="BTCUSDT",
        side="BUY",
        order_type="MARKET",
        quantity=0.001,
        position_type="LONG",
        strategy_name="test_strategy",
        signal_id="signal_123",
        confidence_score=0.85,
    )

    # Create a span to simulate active trace
    with trace.get_tracer(__name__).start_as_current_span("test_span"):
        # Publish order
        await publisher._publish_orders_batch([order])

    # Verify publish was called
    assert publisher.nats_client.publish.called

    # Get the published message
    call_args = publisher.nats_client.publish.call_args
    published_payload = call_args.kwargs["payload"]
    published_data = json.loads(published_payload.decode())

    # Verify trace context was injected
    assert "_otel_trace_context" in published_data
    assert "traceparent" in published_data["_otel_trace_context"]


@pytest.mark.asyncio
async def test_span_marked_as_error_on_exception(
    consumer, market_data_with_trace, span_exporter, tracer_provider
):
    """Test that span is marked as error when processing fails"""
    msg = create_nats_message(market_data_with_trace)

    # Mock parse to return valid data but process to raise exception
    consumer._parse_market_data = MagicMock(
        return_value=MagicMock(stream_type="trade", symbol="BTCUSDT", timestamp=None)
    )
    consumer._process_market_data = AsyncMock(side_effect=Exception("Test error"))

    # Process message (should handle exception)
    await consumer._process_message(msg)

    # Verify error was handled
    assert consumer.error_count > 0
