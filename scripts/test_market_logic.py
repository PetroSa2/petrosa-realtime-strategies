#!/usr/bin/env python3
"""
Test script for Market Logic Strategies.

This script tests the new market logic strategies adapted from QTZD.
"""

import asyncio
import os

# Add project root to path
import sys
import time
from datetime import datetime

project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from strategies.market_logic.btc_dominance import BitcoinDominanceStrategy
from strategies.market_logic.cross_exchange_spread import CrossExchangeSpreadStrategy
from strategies.market_logic.onchain_metrics import OnChainMetricsStrategy
from strategies.models.market_data import MarketDataMessage
from strategies.utils.logger import setup_logging


def create_test_market_data(
    symbol: str = "BTCUSDT", price: float = 45000.0
) -> MarketDataMessage:
    """Create test market data message."""

    # Simulate Binance ticker data
    test_data = {
        "stream": f"{symbol.lower()}@ticker",
        "data": {
            "e": "24hrTicker",
            "E": int(time.time() * 1000),
            "s": symbol,
            "p": "250.00",  # Price change
            "P": "0.56",  # Price change percent
            "w": str(price),  # Weighted average price
            "x": str(price - 10),  # Previous close
            "c": str(price),  # Current close price
            "Q": "10.0",  # Last quantity
            "b": str(price - 5),  # Best bid price
            "B": "5.0",  # Best bid quantity
            "a": str(price + 5),  # Best ask price
            "A": "5.0",  # Best ask quantity
            "o": str(price - 100),  # Open price
            "h": str(price + 200),  # High price
            "l": str(price - 200),  # Low price
            "v": "50000.0",  # Total traded base asset volume
            "q": str(price * 50000),  # Total traded quote asset volume
            "O": int(time.time() * 1000) - 86400000,  # Statistics open time
            "C": int(time.time() * 1000),  # Statistics close time
            "F": 1000000,  # First trade ID
            "L": 1050000,  # Last trade ID
            "n": 50000,  # Total number of trades
        },
    }

    return MarketDataMessage(
        stream=test_data["stream"],
        data=test_data["data"],
        timestamp=datetime.utcnow(),
        message_id=f"test_{int(time.time())}",
        source="test",
        version="1.0",
    )


async def test_btc_dominance_strategy():
    """Test Bitcoin Dominance Strategy."""
    print("\n🔍 Testing Bitcoin Dominance Strategy...")

    logger = setup_logging()
    strategy = BitcoinDominanceStrategy(logger=logger)

    # Test with different market data
    test_cases = [("BTCUSDT", 45000.0), ("ETHUSDT", 3000.0), ("BNBUSDT", 400.0)]

    for symbol, price in test_cases:
        print(f"\n  Testing {symbol} at ${price}")
        market_data = create_test_market_data(symbol, price)

        signal = await strategy.process_market_data(market_data)

        if signal:
            print("  ✅ Signal Generated:")
            print(f"    Symbol: {signal.symbol}")
            print(f"    Type: {signal.signal_type}")
            print(f"    Action: {signal.signal_action}")
            print(f"    Confidence: {signal.confidence_score:.2f}")
            print(f"    Reasoning: {signal.metadata.get('reasoning', 'N/A')}")
        else:
            print("  ❌ No signal generated")

    # Get strategy metrics
    metrics = strategy.get_metrics()
    print("\n  📊 Strategy Metrics:")
    for key, value in metrics.items():
        print(f"    {key}: {value}")


async def test_cross_exchange_spread_strategy():
    """Test Cross-Exchange Spread Strategy."""
    print("\n💱 Testing Cross-Exchange Spread Strategy...")

    logger = setup_logging()
    strategy = CrossExchangeSpreadStrategy(logger=logger)

    # Test with BTCUSDT data
    market_data = create_test_market_data("BTCUSDT", 45000.0)

    print("  Testing arbitrage opportunity detection...")
    signals = await strategy.process_market_data(market_data)

    if signals:
        print(f"  ✅ {len(signals)} Arbitrage Signals Generated:")
        for i, signal in enumerate(signals):
            print(f"    Signal {i + 1}:")
            print(f"      Symbol: {signal.symbol}")
            print(f"      Type: {signal.signal_type}")
            print(f"      Action: {signal.signal_action}")
            print(f"      Confidence: {signal.confidence_score:.2f}")
            print(f"      Exchange: {signal.metadata.get('target_exchange', 'N/A')}")
            print(f"      Spread: {signal.metadata.get('spread_percent', 0):.2f}%")
    else:
        print("  ❌ No arbitrage signals generated")

    # Get strategy metrics
    metrics = strategy.get_metrics()
    print("\n  📊 Strategy Metrics:")
    for key, value in metrics.items():
        print(f"    {key}: {value}")


async def test_onchain_metrics_strategy():
    """Test On-Chain Metrics Strategy."""
    print("\n⛓️  Testing On-Chain Metrics Strategy...")

    logger = setup_logging()
    strategy = OnChainMetricsStrategy(logger=logger)

    # Test with BTC and ETH data
    test_cases = [("BTCUSDT", 45000.0), ("ETHUSDT", 3000.0)]

    for symbol, price in test_cases:
        print(f"\n  Testing {symbol} fundamental analysis...")
        market_data = create_test_market_data(symbol, price)

        signal = await strategy.process_market_data(market_data)

        if signal:
            print("  ✅ On-Chain Signal Generated:")
            print(f"    Symbol: {signal.symbol}")
            print(f"    Type: {signal.signal_type}")
            print(f"    Action: {signal.signal_action}")
            print(f"    Confidence: {signal.confidence_score:.2f}")
            print(f"    Signal Type: {signal.metadata.get('signal_type', 'N/A')}")
            print(f"    Asset: {signal.metadata.get('asset', 'N/A')}")
        else:
            print("  ❌ No on-chain signal generated")

    # Get strategy metrics
    metrics = strategy.get_metrics()
    print("\n  📊 Strategy Metrics:")
    for key, value in metrics.items():
        print(f"    {key}: {value}")


async def main():
    """Main test function."""
    print("🚀 Testing Market Logic Strategies (QTZD Adaptation)")
    print("=" * 60)

    try:
        # Test each strategy
        await test_btc_dominance_strategy()
        await test_cross_exchange_spread_strategy()
        await test_onchain_metrics_strategy()

        print("\n" + "=" * 60)
        print("✅ All tests completed successfully!")
        print("\n💡 Next Steps:")
        print("  1. Deploy the updated service: make deploy")
        print("  2. Check logs: kubectl logs -f deployment/petrosa-realtime-strategies")
        print("  3. Monitor signals: Check NATS topic 'tradeengine.orders'")
        print("  4. Verify trade execution in petrosa-tradeengine")

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
