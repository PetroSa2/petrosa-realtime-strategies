import asyncio

import pytest

from strategies.core.processor import MessageProcessor


def test_processor_initialization():
    """Test that processor initializes correctly."""
    queue = asyncio.Queue()
    processor = MessageProcessor(queue)

    assert processor is not None
    assert processor.messages_processed == 0
    assert processor.signals_generated == 0
    assert processor.errors_count == 0


@pytest.mark.asyncio
async def test_processor_async_initialization():
    """Test that processor initializes correctly in async context."""
    queue = asyncio.Queue()
    processor = MessageProcessor(queue)

    assert processor is not None
    assert processor.messages_processed == 0
    assert processor.signals_generated == 0
    assert processor.errors_count == 0
