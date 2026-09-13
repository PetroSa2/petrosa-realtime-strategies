#!/usr/bin/env python3
"""
Test setup script for Petrosa Realtime Strategies service.

This script verifies that the service can be imported and configured correctly.
"""

import os
import sys

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


def test_imports():
    """Test that all modules can be imported."""
    print("Testing imports...")

    try:
        import constants

        print("✅ constants imported successfully")

        from strategies import __version__

        print(f"✅ strategies package imported successfully (version: {__version__})")

        from strategies.models.market_data import (
            DepthUpdate,
            MarketDataMessage,
            TickerData,
            TradeData,
        )

        print("✅ market data models imported successfully")

        from strategies.models.signals import (
            Signal,
            SignalAction,
            SignalConfidence,
            SignalType,
        )

        print("✅ signal models imported successfully")

        from strategies.core.consumer import NATSConsumer

        print("✅ NATS consumer imported successfully")

        from strategies.core.publisher import TradeOrderPublisher

        print("✅ trade order publisher imported successfully")

        from strategies.health.server import HealthServer

        print("✅ health server imported successfully")

        from strategies.utils.logger import setup_logging

        print("✅ logger utility imported successfully")

        assert True  # All imports successful
        return True

    except ImportError as e:
        print(f"❌ Import failed: {e}")
        raise AssertionError(f"Import failed: {e}")
        return False


def test_configuration():
    """Test configuration loading."""
    print("\nTesting configuration...")

    try:
        import constants

        # Test basic configuration
        assert constants.SERVICE_NAME == "petrosa-realtime-strategies"
        assert constants.SERVICE_VERSION == "1.0.0"
        assert constants.ENVIRONMENT in ["development", "staging", "production"]

        print("✅ Basic configuration loaded successfully")

        # Test strategy configuration
        enabled_strategies = constants.get_enabled_strategies()
        print(f"✅ Enabled strategies: {enabled_strategies}")

        # Test trading configuration
        trading_config = constants.get_trading_config()
        print(f"✅ Trading configuration: {trading_config}")

        # Test risk configuration
        risk_config = constants.get_risk_config()
        print(f"✅ Risk configuration: {risk_config}")

        return True

    except Exception as e:
        print(f"❌ Configuration test failed: {e}")
        return False


def test_logging():
    """Test logging setup."""
    print("\nTesting logging...")

    try:
        from strategies.utils.logger import setup_logging

        logger = setup_logging(level="INFO")
        logger.info("Test log message", test=True)

        print("✅ Logging setup successful")
        assert logger is not None
        return True

    except Exception as e:
        print(f"❌ Logging test failed: {e}")
        raise AssertionError(f"Logging test failed: {e}")
        return False


def test_models():
    """Test model creation."""
    print("\nTesting models...")

    try:
        from strategies.models.market_data import DepthUpdate
        from strategies.models.signals import (
            Signal,
            SignalAction,
            SignalConfidence,
            SignalType,
        )

        # Test depth update
        depth_data = {
            "symbol": "BTCUSDT",
            "event_time": 1234567890000,
            "first_update_id": 123456789,
            "final_update_id": 123456789,
            "bids": [{"price": "50000.00", "quantity": "1.0"}],
            "asks": [{"price": "50001.00", "quantity": "1.0"}],
        }
        depth_update = DepthUpdate(**depth_data)
        print("✅ Depth update model created successfully")

        # Test signal
        signal = Signal(
            symbol="BTCUSDT",
            signal_type=SignalType.BUY,
            signal_action=SignalAction.OPEN_LONG,
            confidence=SignalConfidence.HIGH,
            confidence_score=0.8,
            price=50000.0,
            strategy_name="test_strategy",
        )
        print("✅ Signal model created successfully")

        assert depth_update is not None
        assert signal is not None
        return True

    except Exception as e:
        print(f"❌ Model test failed: {e}")
        raise AssertionError(f"Model test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Petrosa Realtime Strategies - Setup Test")
    print("=" * 50)

    tests = [
        test_imports,
        test_configuration,
        test_logging,
        test_models,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        if test():
            passed += 1
        print()

    print("=" * 50)
    print(f"📊 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("✅ All tests passed! Service is ready to use.")
        return 0
    else:
        print("❌ Some tests failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
