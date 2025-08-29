#!/usr/bin/env python3
"""
Test script for heartbeat functionality.

This script tests the heartbeat manager in isolation to verify it works correctly.
"""

import asyncio
import sys
import os
import time

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

import constants
from strategies.utils.heartbeat import HeartbeatManager
from strategies.utils.logger import setup_logging


class MockConsumer:
    """Mock consumer for testing."""
    
    def __init__(self):
        self.message_count = 0
        self.error_count = 0
        self.is_running = True
        self.last_message_time = time.time()
        self.avg_processing_time_ms = 5.2
        self.max_processing_time_ms = 12.8
        
    def get_metrics(self):
        # Simulate increasing message count
        self.message_count += 10
        if self.message_count > 50:
            self.error_count += 1
            
        return {
            "message_count": self.message_count,
            "error_count": self.error_count,
            "is_running": self.is_running,
            "last_message_time": self.last_message_time,
            "avg_processing_time_ms": self.avg_processing_time_ms,
            "max_processing_time_ms": self.max_processing_time_ms,
            "processing_times_count": 100,
            "circuit_breaker_state": "closed",
        }
    
    def get_health_status(self):
        return {
            "healthy": True,
            "is_running": self.is_running,
            "nats_connected": True,
            "subscription_active": True,
            "message_count": self.message_count,
            "error_count": self.error_count,
            "last_message_time": self.last_message_time,
        }


class MockPublisher:
    """Mock publisher for testing."""
    
    def __init__(self):
        self.order_count = 0
        self.error_count = 0
        self.is_running = True
        self.last_order_time = time.time()
        self.avg_publishing_time_ms = 3.1
        self.max_publishing_time_ms = 8.9
        self.queue_size = 5
        
    def get_metrics(self):
        # Simulate increasing order count
        self.order_count += 3
        if self.order_count > 20:
            self.error_count += 1
            
        return {
            "order_count": self.order_count,
            "error_count": self.error_count,
            "is_running": self.is_running,
            "last_order_time": self.last_order_time,
            "avg_publishing_time_ms": self.avg_publishing_time_ms,
            "max_publishing_time_ms": self.max_publishing_time_ms,
            "publishing_times_count": 50,
            "queue_size": self.queue_size,
            "circuit_breaker_state": "closed",
        }
    
    def get_health_status(self):
        return {
            "healthy": True,
            "is_running": self.is_running,
            "nats_connected": True,
            "order_count": self.order_count,
            "error_count": self.error_count,
            "last_order_time": self.last_order_time,
            "queue_size": self.queue_size,
        }


async def test_heartbeat():
    """Test the heartbeat functionality."""
    logger = setup_logging(level="INFO")
    logger.info("Starting heartbeat test")
    
    # Create mock components
    consumer = MockConsumer()
    publisher = MockPublisher()
    
    # Create heartbeat manager with short interval for testing
    heartbeat_manager = HeartbeatManager(
        consumer=consumer,
        publisher=publisher,
        logger=logger,
        enabled=True,
        interval_seconds=5,  # 5 seconds for testing
        include_detailed_stats=True,
    )
    
    try:
        # Start heartbeat manager
        await heartbeat_manager.start()
        logger.info("Heartbeat manager started")
        
        # Let it run for a few heartbeats
        logger.info("Running test for 20 seconds to see multiple heartbeats...")
        await asyncio.sleep(20)
        
        # Check status
        status = heartbeat_manager.get_heartbeat_status()
        logger.info("Heartbeat status", **status)
        
        # Force a heartbeat
        logger.info("Forcing immediate heartbeat...")
        heartbeat_manager.force_heartbeat()
        await asyncio.sleep(1)  # Give it time to log
        
        logger.info("✅ Heartbeat test completed successfully")
        
    except Exception as e:
        logger.error("❌ Heartbeat test failed", error=str(e))
        raise
    finally:
        # Stop heartbeat manager
        await heartbeat_manager.stop()
        logger.info("Heartbeat manager stopped")


if __name__ == "__main__":
    print("🧪 Testing Heartbeat Functionality")
    print("=" * 50)
    
    try:
        asyncio.run(test_heartbeat())
        print("\n✅ All tests passed!")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        sys.exit(1)
