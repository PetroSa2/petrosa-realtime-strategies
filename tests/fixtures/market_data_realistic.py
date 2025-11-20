"""Realistic market data fixtures for testing strategies."""

from datetime import datetime, timedelta

# Realistic Bitcoin price action over 1 hour
BTCUSDT_REALISTIC_SEQUENCE = [
    # Timestamp, Open, High, Low, Close, Volume
    (datetime(2024, 1, 1, 10, 0), 50000.0, 50050.0, 49950.0, 50025.0, 10.5),
    (datetime(2024, 1, 1, 10, 1), 50025.0, 50100.0, 50000.0, 50075.0, 12.3),
    (datetime(2024, 1, 1, 10, 2), 50075.0, 50150.0, 50050.0, 50125.0, 15.7),
    (datetime(2024, 1, 1, 10, 3), 50125.0, 50200.0, 50100.0, 50180.0, 18.2),
    (datetime(2024, 1, 1, 10, 4), 50180.0, 50250.0, 50150.0, 50220.0, 20.1),
]

# Orderbook depth snapshot with realistic spread
BTCUSDT_DEPTH_SNAPSHOT = {
    "bids": [
        [50000.0, 1.5],
        [49950.0, 2.3],
        [49900.0, 3.1],
        [49850.0, 4.2],
        [49800.0, 5.5],
    ],
    "asks": [
        [50050.0, 1.2],
        [50100.0, 2.1],
        [50150.0, 2.8],
        [50200.0, 3.5],
        [50250.0, 4.3],
    ],
}

# Widening spread scenario (liquidity event)
BTCUSDT_WIDENING_SPREAD = [
    # Normal spread (0.1%)
    {"bids": [[50000.0, 10.0]], "asks": [[50050.0, 10.0]]},
    # Spread widens (0.3%)
    {"bids": [[50000.0, 5.0]], "asks": [[50150.0, 5.0]]},
    # Spread widens more (0.5%)
    {"bids": [[50000.0, 2.0]], "asks": [[50250.0, 2.0]]},
]

# Trade sequence showing iceberg order
BTCUSDT_ICEBERG_TRADES = [
    # Small visible trades at same price
    {"price": 50000.0, "quantity": 0.1, "is_buyer_maker": True},
    {"price": 50000.0, "quantity": 0.1, "is_buyer_maker": True},
    {"price": 50000.0, "quantity": 0.1, "is_buyer_maker": True},
    {"price": 50000.0, "quantity": 0.1, "is_buyer_maker": True},
    {"price": 50000.0, "quantity": 0.1, "is_buyer_maker": True},
    # Pattern indicates hidden iceberg order
]

# BTC dominance data
BTC_DOMINANCE_SCENARIO = {
    "BTC": [
        {
            "timestamp": datetime(2024, 1, 1, 10, 0),
            "price": 50000.0,
            "market_cap": 1000000000000,
        },
        {
            "timestamp": datetime(2024, 1, 1, 10, 5),
            "price": 50500.0,
            "market_cap": 1010000000000,
        },
        {
            "timestamp": datetime(2024, 1, 1, 10, 10),
            "price": 51000.0,
            "market_cap": 1020000000000,
        },
    ],
    "ETH": [
        {
            "timestamp": datetime(2024, 1, 1, 10, 0),
            "price": 3000.0,
            "market_cap": 360000000000,
        },
        {
            "timestamp": datetime(2024, 1, 1, 10, 5),
            "price": 2980.0,
            "market_cap": 357600000000,
        },
        {
            "timestamp": datetime(2024, 1, 1, 10, 10),
            "price": 2960.0,
            "market_cap": 355200000000,
        },
    ],
}

# Cross-exchange spread
CROSS_EXCHANGE_ARBITRAGE = {
    "binance": [
        {
            "symbol": "BTCUSDT",
            "price": 50000.0,
            "timestamp": datetime(2024, 1, 1, 10, 0),
        },
        {
            "symbol": "BTCUSDT",
            "price": 50010.0,
            "timestamp": datetime(2024, 1, 1, 10, 1),
        },
    ],
    "coinbase": [
        {
            "symbol": "BTC-USD",
            "price": 50150.0,
            "timestamp": datetime(2024, 1, 1, 10, 0),
        },  # 0.3% premium
        {
            "symbol": "BTC-USD",
            "price": 50160.0,
            "timestamp": datetime(2024, 1, 1, 10, 1),
        },
    ],
}


def generate_realistic_klines(
    symbol: str, count: int = 100, start_price: float = 50000.0
):
    """Generate realistic candlestick data with random walk."""
    import random

    klines = []
    current_price = start_price
    timestamp = datetime.utcnow()

    for i in range(count):
        # Random walk with slight upward bias
        price_change = random.uniform(-0.002, 0.0025) * current_price
        open_price = current_price
        close_price = current_price + price_change

        high_price = max(open_price, close_price) * random.uniform(1.0, 1.001)
        low_price = min(open_price, close_price) * random.uniform(0.999, 1.0)
        volume = random.uniform(5.0, 20.0)

        klines.append(
            {
                "symbol": symbol,
                "timestamp": timestamp + timedelta(minutes=i),
                "open": round(open_price, 2),
                "high": round(high_price, 2),
                "low": round(low_price, 2),
                "close": round(close_price, 2),
                "volume": round(volume, 4),
            }
        )

        current_price = close_price

    return klines


def generate_depth_updates(symbol: str, count: int = 50):
    """Generate sequence of realistic depth updates."""
    import random

    updates = []
    base_price = 50000.0

    for i in range(count):
        mid_price = base_price * (1 + random.uniform(-0.001, 0.001))
        spread_bps = random.uniform(5, 15)  # 5-15 basis points

        bids = [
            [
                mid_price * (1 - spread_bps / 10000 - j * 0.0001),
                random.uniform(0.5, 3.0),
            ]
            for j in range(5)
        ]
        asks = [
            [
                mid_price * (1 + spread_bps / 10000 + j * 0.0001),
                random.uniform(0.5, 3.0),
            ]
            for j in range(5)
        ]

        updates.append(
            {
                "symbol": symbol,
                "timestamp": datetime.utcnow() + timedelta(seconds=i),
                "bids": bids,
                "asks": asks,
            }
        )

    return updates
