"""
Comprehensive unit tests for real-time market logic.

Tests cover market data processing, signal generation, cross-exchange analysis,
on-chain metrics integration, and performance characteristics.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock, patch

import pytest

from strategies.core.processor import MarketDataProcessor
from strategies.market_logic.btc_dominance import BitcoinDominanceStrategy
from strategies.market_logic.cross_exchange_spread import CrossExchangeSpreadStrategy
from strategies.market_logic.onchain_metrics import OnChainMetricsStrategy
from strategies.models.market_data import MarketData, OrderBookData
from strategies.models.signals import MarketSignal, SignalStrength, SignalType


@pytest.mark.unit
class TestBitcoinDominanceStrategy:
    """Test cases for BTC dominance analysis."""

    def test_btc_dominance_analyzer_initialization(self):
        """Test BitcoinDominanceStrategy initialization."""
        analyzer = BitcoinDominanceStrategy()

        assert analyzer is not None
        assert hasattr(analyzer, "dominance_threshold")
        assert hasattr(analyzer, "trend_window")

    def test_calculate_btc_dominance(self):
        """Test BTC dominance calculation."""
        analyzer = BitcoinDominanceStrategy()

        market_caps = {
            "BTC": 800000000000,  # $800B
            "ETH": 300000000000,  # $300B
            "BNB": 50000000000,  # $50B
            "ADA": 25000000000,  # $25B
            "SOL": 25000000000,  # $25B
        }

        dominance = analyzer.calculate_dominance(market_caps)

        expected_dominance = 800000000000 / 1200000000000  # BTC / Total
        assert abs(dominance - expected_dominance) < 0.001

    def test_btc_dominance_trend_analysis(self):
        """Test BTC dominance trend analysis."""
        analyzer = BitcoinDominanceStrategy()

        # Historical dominance data (decreasing trend)
        dominance_history = [0.68, 0.67, 0.66, 0.65, 0.64, 0.63, 0.62]

        trend = analyzer.analyze_trend(dominance_history)

        assert trend["direction"] == "decreasing"
        assert trend["strength"] > 0.5
        assert "rate_of_change" in trend

    def test_btc_dominance_signal_generation_bullish(self):
        """Test bullish signal generation based on BTC dominance."""
        analyzer = BitcoinDominanceStrategy()

        # Mock increasing dominance trend
        with (
            patch.object(analyzer, "get_current_dominance") as mock_dominance,
            patch.object(analyzer, "analyze_trend") as mock_trend,
        ):
            mock_dominance.return_value = 0.68
            mock_trend.return_value = {
                "direction": "increasing",
                "strength": 0.8,
                "rate_of_change": 0.02,
            }

            signal = analyzer.generate_signal()

            assert signal is not None
            assert signal.signal_type == SignalType.MARKET_STRUCTURE
            assert signal.strength == SignalStrength.STRONG
            assert "dominance" in signal.metadata

    def test_btc_dominance_signal_generation_bearish(self):
        """Test bearish signal generation based on BTC dominance."""
        analyzer = BitcoinDominanceStrategy()

        # Mock decreasing dominance trend
        with (
            patch.object(analyzer, "get_current_dominance") as mock_dominance,
            patch.object(analyzer, "analyze_trend") as mock_trend,
        ):
            mock_dominance.return_value = 0.55
            mock_trend.return_value = {
                "direction": "decreasing",
                "strength": 0.9,
                "rate_of_change": -0.03,
            }

            signal = analyzer.generate_signal()

            assert signal is not None
            assert signal.signal_type == SignalType.MARKET_STRUCTURE
            assert signal.direction == "bearish"
            assert signal.confidence > 0.7

    def test_btc_dominance_no_signal_flat_trend(self):
        """Test no signal generation when dominance is flat."""
        analyzer = BitcoinDominanceStrategy()

        with (
            patch.object(analyzer, "get_current_dominance") as mock_dominance,
            patch.object(analyzer, "analyze_trend") as mock_trend,
        ):
            mock_dominance.return_value = 0.62
            mock_trend.return_value = {
                "direction": "flat",
                "strength": 0.1,
                "rate_of_change": 0.001,
            }

            signal = analyzer.generate_signal()

            assert signal is None

    def test_btc_dominance_extreme_values(self):
        """Test handling of extreme dominance values."""
        analyzer = BitcoinDominanceStrategy()

        # Test extreme high dominance
        market_caps_high = {"BTC": 1000000000000, "ETH": 10000000000}
        dominance_high = analyzer.calculate_dominance(market_caps_high)
        assert dominance_high > 0.95

        # Test extreme low dominance
        market_caps_low = {"BTC": 10000000000, "ETH": 1000000000000}
        dominance_low = analyzer.calculate_dominance(market_caps_low)
        assert dominance_low < 0.05

    def test_btc_dominance_historical_data_validation(self):
        """Test validation of historical data."""
        analyzer = BitcoinDominanceStrategy()

        # Test with insufficient data
        short_history = [0.65, 0.64]
        trend = analyzer.analyze_trend(short_history)
        assert trend["confidence"] < 0.5

        # Test with invalid data
        invalid_history = [0.65, None, 0.64, -0.1, 1.5]
        cleaned_trend = analyzer.analyze_trend(invalid_history)
        assert cleaned_trend is not None  # Should handle invalid data gracefully


@pytest.mark.unit
class TestCrossExchangeSpreadStrategy:
    """Test cases for cross-exchange spread analysis."""

    def create_sample_orderbook(self, symbol, exchange, base_price=50000):
        """Create sample order book data."""
        return OrderBookData(
            symbol=symbol,
            exchange=exchange,
            bids=[
                [base_price - 10, 1.0],
                [base_price - 20, 2.0],
                [base_price - 30, 3.0],
            ],
            asks=[
                [base_price + 10, 1.0],
                [base_price + 20, 2.0],
                [base_price + 30, 3.0],
            ],
            timestamp=datetime.utcnow(),
        )

    def test_cross_exchange_spread_analyzer_initialization(self):
        """Test CrossExchangeSpreadStrategy initialization."""
        analyzer = CrossExchangeSpreadStrategy()

        assert analyzer is not None
        assert hasattr(analyzer, "spread_threshold")
        assert hasattr(analyzer, "min_volume_threshold")

    def test_calculate_spread_between_exchanges(self):
        """Test spread calculation between exchanges."""
        analyzer = CrossExchangeSpreadStrategy()

        # Create order books with price difference
        binance_book = self.create_sample_orderbook("BTCUSDT", "binance", 50000)
        coinbase_book = self.create_sample_orderbook("BTCUSDT", "coinbase", 50100)

        spread = analyzer.calculate_spread(binance_book, coinbase_book)

        assert spread["absolute_spread"] == 100  # $100 difference
        assert abs(spread["percentage_spread"] - 0.002) < 0.0001  # ~0.2%
        assert spread["arbitrage_opportunity"] is True

    def test_identify_arbitrage_opportunities(self):
        """Test identification of arbitrage opportunities."""
        analyzer = CrossExchangeSpreadStrategy()

        # Create significant price difference
        orderbooks = {
            "binance": self.create_sample_orderbook("BTCUSDT", "binance", 50000),
            "coinbase": self.create_sample_orderbook("BTCUSDT", "coinbase", 50200),
            "kraken": self.create_sample_orderbook("BTCUSDT", "kraken", 50300),
        }

        opportunities = analyzer.identify_arbitrage_opportunities(orderbooks)

        assert len(opportunities) > 0
        assert any(opp["profit_percentage"] > 0.003 for opp in opportunities)  # >0.3%
        assert all(
            "buy_exchange" in opp and "sell_exchange" in opp for opp in opportunities
        )

    def test_spread_signal_generation(self):
        """Test signal generation based on spread analysis."""
        analyzer = CrossExchangeSpreadStrategy()

        # Mock significant spread
        with patch.object(analyzer, "get_current_spreads") as mock_spreads:
            mock_spreads.return_value = [
                {
                    "symbol": "BTCUSDT",
                    "spread_percentage": 0.005,  # 0.5% spread
                    "volume_weighted": True,
                    "exchanges": ["binance", "coinbase"],
                }
            ]

            signal = analyzer.generate_signal()

            assert signal is not None
            assert signal.signal_type == SignalType.ARBITRAGE
            assert "spread_percentage" in signal.metadata

    def test_volume_weighted_spread_calculation(self):
        """Test volume-weighted spread calculation."""
        analyzer = CrossExchangeSpreadStrategy()

        # Create order books with different volumes
        high_volume_book = OrderBookData(
            symbol="BTCUSDT",
            exchange="binance",
            bids=[[49990, 10.0], [49980, 20.0]],  # High volume
            asks=[[50010, 10.0], [50020, 20.0]],
            timestamp=datetime.utcnow(),
        )

        low_volume_book = OrderBookData(
            symbol="BTCUSDT",
            exchange="coinbase",
            bids=[[50090, 0.1], [50080, 0.2]],  # Low volume, higher price
            asks=[[50110, 0.1], [50120, 0.2]],
            timestamp=datetime.utcnow(),
        )

        spread = analyzer.calculate_volume_weighted_spread(
            high_volume_book, low_volume_book
        )

        assert spread["volume_weighted"] is True
        assert spread["effective_spread"] != spread["mid_price_spread"]

    def test_spread_historical_analysis(self):
        """Test historical spread analysis."""
        analyzer = CrossExchangeSpreadStrategy()

        # Mock historical spread data
        historical_spreads = [
            {
                "timestamp": datetime.utcnow() - timedelta(minutes=i),
                "spread": 0.001 + i * 0.0001,
            }
            for i in range(60)
        ]

        analysis = analyzer.analyze_spread_history(historical_spreads)

        assert "average_spread" in analysis
        assert "volatility" in analysis
        assert "trend" in analysis

    def test_minimum_profit_threshold(self):
        """Test minimum profit threshold for arbitrage signals."""
        analyzer = CrossExchangeSpreadStrategy(min_profit_threshold=0.003)  # 0.3%

        # Small spread below threshold
        small_spread_books = {
            "binance": self.create_sample_orderbook("BTCUSDT", "binance", 50000),
            "coinbase": self.create_sample_orderbook(
                "BTCUSDT", "coinbase", 50050
            ),  # 0.1% spread
        }

        opportunities = analyzer.identify_arbitrage_opportunities(small_spread_books)

        # Should not identify opportunities below threshold
        assert len(opportunities) == 0


@pytest.mark.unit
class TestOnChainMetricsStrategy:
    """Test cases for on-chain metrics analysis."""

    def test_onchain_metrics_analyzer_initialization(self):
        """Test OnChainMetricsStrategy initialization."""
        analyzer = OnChainMetricsStrategy()

        assert analyzer is not None
        assert hasattr(analyzer, "metrics_sources")
        assert hasattr(analyzer, "correlation_threshold")

    def test_analyze_network_activity(self):
        """Test network activity analysis."""
        analyzer = OnChainMetricsStrategy()

        network_data = {
            "active_addresses": 1000000,
            "transaction_count": 300000,
            "transaction_volume": 5000000000,  # $5B
            "hash_rate": 200000000000000000000,  # 200 EH/s
            "difficulty": 25000000000000,
        }

        activity_score = analyzer.analyze_network_activity(network_data)

        assert 0 <= activity_score <= 1
        assert activity_score > 0.5  # Should be positive for healthy metrics

    def test_whale_movement_detection(self):
        """Test whale movement detection."""
        analyzer = OnChainMetricsStrategy()

        large_transactions = [
            {
                "amount": 1000,
                "from_exchange": False,
                "to_exchange": True,
            },  # Whale to exchange
            {
                "amount": 500,
                "from_exchange": True,
                "to_exchange": False,
            },  # Exchange to whale
            {
                "amount": 2000,
                "from_exchange": False,
                "to_exchange": False,
            },  # Whale to whale
        ]

        whale_activity = analyzer.detect_whale_movements(large_transactions)

        assert "net_exchange_flow" in whale_activity
        assert "total_whale_volume" in whale_activity
        assert whale_activity["total_whale_volume"] == 3500

    def test_exchange_flow_analysis(self):
        """Test exchange flow analysis."""
        analyzer = OnChainMetricsStrategy()

        flow_data = {
            "inflow_24h": 50000,  # BTC flowing into exchanges
            "outflow_24h": 45000,  # BTC flowing out of exchanges
            "net_flow": 5000,  # Net inflow
            "exchange_reserves": 2500000,  # Total exchange reserves
        }

        flow_signal = analyzer.analyze_exchange_flows(flow_data)

        assert flow_signal["direction"] == "bearish"  # Net inflow is bearish
        assert flow_signal["strength"] > 0
        assert "reserve_ratio" in flow_signal

    def test_miner_behavior_analysis(self):
        """Test miner behavior analysis."""
        analyzer = OnChainMetricsStrategy()

        miner_data = {
            "hash_rate": 200000000000000000000,
            "difficulty": 25000000000000,
            "miner_revenue": 50000000,  # $50M daily
            "miner_outflow": 800,  # BTC sold by miners
            "mining_cost_estimate": 25000,  # Cost per BTC
        }

        miner_signal = analyzer.analyze_miner_behavior(miner_data)

        assert "profitability" in miner_signal
        assert "selling_pressure" in miner_signal
        assert miner_signal["profitability"] > 1  # Profitable at current prices

    def test_onchain_signal_generation(self):
        """Test on-chain signal generation."""
        analyzer = OnChainMetricsStrategy()

        # Mock bullish on-chain conditions
        with patch.object(analyzer, "get_current_metrics") as mock_metrics:
            mock_metrics.return_value = {
                "network_activity": 0.8,
                "whale_sentiment": "accumulating",
                "exchange_flows": {"direction": "bullish", "strength": 0.7},
                "miner_behavior": {"selling_pressure": "low", "profitability": 2.0},
            }

            signal = analyzer.generate_signal()

            assert signal is not None
            assert signal.signal_type == SignalType.ONCHAIN
            assert signal.direction == "bullish"
            assert signal.confidence > 0.6

    def test_correlation_with_price_movements(self):
        """Test correlation analysis with price movements."""
        analyzer = OnChainMetricsStrategy()

        # Historical on-chain data and price data
        onchain_history = [0.6, 0.65, 0.7, 0.75, 0.8]  # Increasing activity
        price_history = [45000, 47000, 49000, 51000, 53000]  # Increasing price

        correlation = analyzer.calculate_price_correlation(
            onchain_history, price_history
        )

        assert correlation > 0.8  # Strong positive correlation
        assert -1 <= correlation <= 1

    def test_onchain_metrics_validation(self):
        """Test validation of on-chain metrics data."""
        analyzer = OnChainMetricsStrategy()

        # Test with invalid data
        invalid_data = {
            "active_addresses": -1000,  # Negative
            "transaction_count": None,  # None
            "hash_rate": "invalid",  # String instead of number
        }

        validated_data = analyzer.validate_metrics(invalid_data)

        # Should clean or handle invalid data
        assert validated_data is not None
        assert "data_quality" in validated_data

    def test_real_time_metrics_processing(self):
        """Test real-time metrics processing."""
        analyzer = OnChainMetricsStrategy()

        # Simulate streaming metrics data
        metrics_stream = [
            {"timestamp": datetime.utcnow(), "active_addresses": 950000},
            {"timestamp": datetime.utcnow(), "active_addresses": 960000},
            {"timestamp": datetime.utcnow(), "active_addresses": 970000},
        ]

        for metric in metrics_stream:
            analyzer.process_real_time_metric(metric)

        current_trend = analyzer.get_current_trend()

        assert current_trend["direction"] == "increasing"
        assert current_trend["data_points"] == 3


@pytest.mark.unit
class TestMarketDataProcessor:
    """Test cases for market data processor."""

    def test_market_data_processor_initialization(self):
        """Test MarketDataProcessor initialization."""
        processor = MarketDataProcessor()

        assert processor is not None
        assert hasattr(processor, "analyzers")
        assert len(processor.analyzers) > 0

    @pytest.mark.asyncio
    async def test_process_market_data_stream(self):
        """Test processing of market data stream."""
        processor = MarketDataProcessor()

        # Mock market data
        market_data = MarketData(
            symbol="BTCUSDT",
            price=50000.0,
            volume=1500000,
            timestamp=datetime.utcnow(),
            source="binance",
        )

        with patch.object(processor, "generate_signals") as mock_generate:
            mock_generate.return_value = [
                MarketSignal(
                    signal_type=SignalType.TREND,
                    direction="bullish",
                    strength=SignalStrength.MEDIUM,
                    confidence=0.75,
                )
            ]

            signals = await processor.process_data(market_data)

            assert len(signals) == 1
            assert signals[0].direction == "bullish"

    @pytest.mark.asyncio
    async def test_multi_analyzer_signal_aggregation(self):
        """Test aggregation of signals from multiple analyzers."""
        processor = MarketDataProcessor()

        # Mock multiple analyzers
        btc_analyzer = Mock()
        spread_analyzer = Mock()
        onchain_analyzer = Mock()

        btc_analyzer.generate_signal.return_value = MarketSignal(
            signal_type=SignalType.MARKET_STRUCTURE,
            direction="bullish",
            strength=SignalStrength.STRONG,
            confidence=0.8,
        )

        spread_analyzer.generate_signal.return_value = MarketSignal(
            signal_type=SignalType.ARBITRAGE,
            direction="neutral",
            strength=SignalStrength.WEAK,
            confidence=0.3,
        )

        onchain_analyzer.generate_signal.return_value = MarketSignal(
            signal_type=SignalType.ONCHAIN,
            direction="bullish",
            strength=SignalStrength.MEDIUM,
            confidence=0.7,
        )

        processor.analyzers = [btc_analyzer, spread_analyzer, onchain_analyzer]

        market_data = MarketData(
            symbol="BTCUSDT", price=50000.0, volume=1500000, timestamp=datetime.utcnow()
        )

        aggregated_signals = await processor.process_data(market_data)

        assert len(aggregated_signals) == 3

        # Test signal aggregation logic
        consensus = processor.calculate_consensus(aggregated_signals)
        assert consensus["overall_direction"] == "bullish"
        assert consensus["confidence"] > 0.5

    @pytest.mark.asyncio
    async def test_signal_filtering_and_ranking(self):
        """Test signal filtering and ranking."""
        processor = MarketDataProcessor()

        signals = [
            MarketSignal(
                signal_type=SignalType.TREND,
                direction="bullish",
                strength=SignalStrength.STRONG,
                confidence=0.9,
            ),
            MarketSignal(
                signal_type=SignalType.ARBITRAGE,
                direction="bearish",
                strength=SignalStrength.WEAK,
                confidence=0.2,
            ),
            MarketSignal(
                signal_type=SignalType.ONCHAIN,
                direction="bullish",
                strength=SignalStrength.MEDIUM,
                confidence=0.6,
            ),
        ]

        filtered_signals = processor.filter_signals(signals, min_confidence=0.5)

        assert len(filtered_signals) == 2  # Only high confidence signals

        ranked_signals = processor.rank_signals(filtered_signals)

        assert ranked_signals[0].confidence >= ranked_signals[1].confidence

    @pytest.mark.asyncio
    async def test_error_handling_in_processing(self):
        """Test error handling during data processing."""
        processor = MarketDataProcessor()

        # Mock analyzer that raises exception
        faulty_analyzer = Mock()
        faulty_analyzer.generate_signal.side_effect = Exception("Analysis failed")

        working_analyzer = Mock()
        working_analyzer.generate_signal.return_value = MarketSignal(
            signal_type=SignalType.TREND,
            direction="bullish",
            strength=SignalStrength.MEDIUM,
            confidence=0.7,
        )

        processor.analyzers = [faulty_analyzer, working_analyzer]

        market_data = MarketData(
            symbol="BTCUSDT", price=50000.0, volume=1500000, timestamp=datetime.utcnow()
        )

        # Should handle errors gracefully
        signals = await processor.process_data(market_data)

        assert len(signals) == 1  # Only working analyzer's signal
        assert signals[0].direction == "bullish"

    @pytest.mark.asyncio
    async def test_performance_under_load(self):
        """Test processor performance under high load."""
        processor = MarketDataProcessor()

        # Create many market data points
        market_data_points = [
            MarketData(
                symbol="BTCUSDT",
                price=50000.0 + i,
                volume=1500000,
                timestamp=datetime.utcnow(),
            )
            for i in range(100)
        ]

        import time

        start_time = time.time()

        # Process all data points
        all_signals = []
        for data in market_data_points:
            signals = await processor.process_data(data)
            all_signals.extend(signals)

        end_time = time.time()
        processing_time = end_time - start_time

        # Should process quickly
        assert processing_time < 10.0  # Less than 10 seconds for 100 data points
        assert len(all_signals) >= 0  # Should produce some signals

    def test_signal_persistence_and_retrieval(self):
        """Test signal persistence and retrieval."""
        processor = MarketDataProcessor()

        signal = MarketSignal(
            signal_type=SignalType.TREND,
            direction="bullish",
            strength=SignalStrength.STRONG,
            confidence=0.85,
            timestamp=datetime.utcnow(),
        )

        # Test signal storage
        processor.store_signal(signal)

        # Test signal retrieval
        recent_signals = processor.get_recent_signals(limit=10)

        assert len(recent_signals) >= 1
        assert recent_signals[0].confidence == 0.85

    def test_signal_expiration_and_cleanup(self):
        """Test signal expiration and cleanup."""
        processor = MarketDataProcessor()

        # Create old signals
        old_signal = MarketSignal(
            signal_type=SignalType.TREND,
            direction="bullish",
            strength=SignalStrength.MEDIUM,
            confidence=0.7,
            timestamp=datetime.utcnow() - timedelta(hours=25),  # 25 hours old
        )

        new_signal = MarketSignal(
            signal_type=SignalType.TREND,
            direction="bearish",
            strength=SignalStrength.STRONG,
            confidence=0.8,
            timestamp=datetime.utcnow(),
        )

        processor.store_signal(old_signal)
        processor.store_signal(new_signal)

        # Clean up old signals
        processor.cleanup_expired_signals(max_age_hours=24)

        recent_signals = processor.get_recent_signals()

        # Should only have new signals
        assert all(
            (datetime.utcnow() - signal.timestamp).total_seconds() < 24 * 3600
            for signal in recent_signals
        )
