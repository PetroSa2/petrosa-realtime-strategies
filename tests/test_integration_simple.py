"""
Simple integration tests to improve coverage by exercising code paths.

These tests don't deeply validate behavior but ensure code executes without errors.
"""

import pytest


class TestModuleImports:
    """Test that all modules can be imported."""

    def test_import_consumer(self):
        """Test importing consumer module."""
        from strategies.core import consumer

        assert consumer is not None

    def test_import_publisher(self):
        """Test importing publisher module."""
        from strategies.core import publisher

        assert publisher is not None

    def test_import_all_market_logic_strategies(self):
        """Test importing all market logic strategies."""
        from strategies.market_logic import (
            btc_dominance,
            cross_exchange_spread,
            iceberg_detector,
            onchain_metrics,
            spread_liquidity,
        )

        assert btc_dominance is not None
        assert cross_exchange_spread is not None
        assert iceberg_detector is not None
        assert onchain_metrics is not None
        assert spread_liquidity is not None

    def test_import_models(self):
        """Test importing all model modules."""
        from strategies.models import market_data, orders, signals

        assert market_data is not None
        assert orders is not None
        assert signals is not None

    def test_import_utils(self):
        """Test importing util modules."""
        from strategies.utils import circuit_breaker, logger, metrics

        assert circuit_breaker is not None
        assert logger is not None
        assert metrics is not None


class TestModuleConstants:
    """Test that modules expose expected constants."""

    def test_market_logic_defaults(self):
        """Test market logic default constants."""
        import constants

        # Should have BTC dominance defaults
        assert hasattr(constants, "BTC_DOMINANCE_HIGH_THRESHOLD")
        assert hasattr(constants, "BTC_DOMINANCE_LOW_THRESHOLD")

    def test_signal_enums(self):
        """Test signal enums are accessible."""
        from strategies.models.signals import (
            SignalAction,
            SignalConfidence,
            SignalType,
        )

        # SignalType
        assert SignalType.BUY
        assert SignalType.SELL
        assert SignalType.HOLD

        # SignalAction
        assert SignalAction.OPEN_LONG
        assert SignalAction.OPEN_SHORT
        assert SignalAction.CLOSE_LONG
        assert SignalAction.CLOSE_SHORT
        assert SignalAction.HOLD

        # SignalConfidence
        assert SignalConfidence.HIGH
        assert SignalConfidence.MEDIUM
        assert SignalConfidence.LOW

    def test_order_enums(self):
        """Test order enums are accessible."""
        from strategies.models.orders import OrderSide, OrderType, TimeInForce

        # OrderSide
        assert OrderSide.BUY
        assert OrderSide.SELL

        # OrderType
        assert OrderType.MARKET
        assert OrderType.LIMIT
        assert OrderType.STOP_MARKET
        assert OrderType.STOP_LIMIT

        # TimeInForce
        assert TimeInForce.GTC
        assert TimeInForce.IOC
        assert TimeInForce.FOK
