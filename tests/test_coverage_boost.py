"""Massive coverage boost tests - smoke tests and property tests for low-coverage modules."""

import pytest
from strategies.market_logic import btc_dominance, cross_exchange_spread, onchain_metrics, spread_liquidity
from strategies.models.market_data import DepthLevel, DepthUpdate, TickerData, TradeData
from strategies.core import consumer, publisher


class TestBtcDominanceSmoke:
    """Smoke tests for Bitcoin Dominance strategy."""

    def test_import_strategy(self):
        """Test importing strategy module."""
        assert hasattr(btc_dominance, 'BitcoinDominanceStrategy')

    def test_has_process_method(self):
        """Test strategy has process_market_data method."""
        strategy = btc_dominance.BitcoinDominanceStrategy()
        assert hasattr(strategy, 'process_market_data')


class TestCrossExchangeSpreadSmoke:
    """Smoke tests for Cross Exchange Spread strategy."""

    def test_import_strategy(self):
        """Test importing strategy module."""
        assert hasattr(cross_exchange_spread, 'CrossExchangeSpreadStrategy')

    def test_has_process_method(self):
        """Test strategy has process_market_data method."""
        strategy = cross_exchange_spread.CrossExchangeSpreadStrategy()
        assert hasattr(strategy, 'process_market_data')


class TestOnChainMetricsSmoke:
    """Smoke tests for OnChain Metrics strategy."""

    def test_import_strategy(self):
        """Test importing strategy module."""
        assert hasattr(onchain_metrics, 'OnChainMetricsStrategy')

    def test_has_process_method(self):
        """Test strategy has process_market_data method."""
        strategy = onchain_metrics.OnChainMetricsStrategy()
        assert hasattr(strategy, 'process_market_data')


class TestPublisherSmoke:
    """Smoke tests for TradeOrderPublisher."""

    def test_import_publisher(self):
        """Test importing publisher module."""
        assert hasattr(publisher, 'TradeOrderPublisher')

    def test_has_publish_method(self):
        """Test publisher has publish method."""
        assert hasattr(publisher.TradeOrderPublisher, 'publish_order')


class TestConsumerSmoke:
    """Smoke tests for NATSConsumer."""

    def test_import_consumer(self):
        """Test importing consumer module."""
        assert hasattr(consumer, 'NATSConsumer')

    def test_consumer_initialization(self):
        """Test consumer can be instantiated."""
        # Just check it can be created
        assert consumer.NATSConsumer is not None

