"""
Cross-Exchange Spread Strategy.

Adapted from QTZD MS Cash NoSQL service's spread calculation logic.
Monitors price differences across exchanges to identify arbitrage opportunities.

Strategy Logic:
- Large spreads (>0.5%) = Arbitrage opportunity
- Persistent spreads = Market inefficiency to exploit
- Spread direction indicates price discovery leadership
"""

import asyncio
import time
from datetime import datetime
from typing import Any, Optional

import aiohttp
import structlog

import constants
from strategies.models.market_data import MarketDataMessage
from strategies.models.signals import Signal, SignalAction, SignalConfidence, SignalType


class CrossExchangeSpreadStrategy:
    """
    Cross-Exchange Spread Strategy for arbitrage opportunities.

    This strategy monitors price differences between exchanges to identify
    profitable arbitrage opportunities with minimal risk.
    """

    def __init__(self, logger: Optional[structlog.BoundLogger] = None):
        """Initialize the Cross-Exchange Spread Strategy."""
        self.logger = logger or structlog.get_logger()

        # Configuration from constants (QTZD-style thresholds)
        self.spread_threshold = constants.SPREAD_THRESHOLD_PERCENT  # 0.5%
        self.min_signal_interval = constants.SPREAD_MIN_SIGNAL_INTERVAL  # 5 minutes
        self.max_position_size = constants.SPREAD_MAX_POSITION_SIZE  # 500 USDT
        self.exchanges = constants.SPREAD_EXCHANGES  # ["binance", "coinbase"]

        # Price cache (QTZD-style data storage)
        self.price_cache: dict[str, dict[str, Any]] = {}
        self.spread_history: dict[str, list[dict[str, Any]]] = {}
        self.last_signal_times: dict[str, datetime] = {}

        # Exchange API endpoints (simplified for demo)
        self.exchange_apis = {
            "binance": "https://api.binance.com/api/v3/ticker/price",
            "coinbase": "https://api.coinbase.com/v2/exchange-rates",
            "kraken": "https://api.kraken.com/0/public/Ticker",
        }

        # Strategy metrics
        self.signals_generated = 0
        self.arbitrage_opportunities_found = 0
        self.last_update_time = time.time()

        self.logger.info(
            "Cross-Exchange Spread Strategy initialized",
            spread_threshold=self.spread_threshold,
            exchanges=self.exchanges,
        )

    async def process_market_data(
        self, market_data: MarketDataMessage
    ) -> Optional[list[Signal]]:
        """
        Process market data and generate spread-based arbitrage signals.

        Args:
            market_data: Real-time market data from Binance WebSocket

        Returns:
            List of signals if arbitrage opportunities found, None otherwise
        """
        try:
            # Update Binance price from WebSocket (primary exchange)
            await self._update_binance_price(market_data)

            # Fetch prices from other exchanges (QTZD-style external data)
            await self._fetch_external_exchange_prices()

            # Calculate spreads and generate signals
            signals = await self._generate_spread_signals(market_data)

            if signals:
                self.signals_generated += len(signals)
                self.arbitrage_opportunities_found += 1
                self.logger.info(
                    "Cross-exchange arbitrage signals generated",
                    signal_count=len(signals),
                    symbol=market_data.symbol,
                )

            return signals if signals else None

        except Exception as e:
            self.logger.error(
                "Error processing cross-exchange spread data", error=str(e)
            )
            return None

    async def _update_binance_price(self, market_data: MarketDataMessage) -> None:
        """Update Binance price from WebSocket data."""
        symbol = market_data.symbol
        current_time = time.time()

        # Extract price from market data
        price = None
        if market_data.is_ticker and hasattr(market_data.data, "c"):
            price = float(market_data.data.c)  # Close price from ticker
        elif market_data.is_trade and hasattr(market_data.data, "p"):
            price = float(market_data.data.p)  # Trade price

        if price:
            cache_key = f"binance_{symbol}"
            self.price_cache[cache_key] = {
                "price": price,
                "timestamp": current_time,
                "exchange": "binance",
                "symbol": symbol,
            }

    async def _fetch_external_exchange_prices(self) -> None:
        """
        Fetch current prices from external exchanges.

        QTZD-style external data fetching with error handling.
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=5)
            ) as session:
                tasks = []
                for exchange in self.exchanges:
                    if exchange != "binance":  # Binance comes from WebSocket
                        tasks.append(self._fetch_exchange_price(session, exchange))

                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)

        except Exception as e:
            self.logger.error("Error fetching external exchange prices", error=str(e))

    async def _fetch_exchange_price(
        self, session: aiohttp.ClientSession, exchange: str
    ) -> None:
        """Fetch price from a specific exchange."""
        try:
            current_time = time.time()

            # Simplified exchange API calls (in production, use proper API clients)
            if exchange == "coinbase":
                # Coinbase Pro API (simplified)
                url = "https://api.coinbase.com/v2/exchange-rates?currency=BTC"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "data" in data and "rates" in data["data"]:
                            btc_price = float(data["data"]["rates"].get("USD", 0))
                            if btc_price > 0:
                                self.price_cache["coinbase_BTCUSDT"] = {
                                    "price": btc_price,
                                    "timestamp": current_time,
                                    "exchange": "coinbase",
                                    "symbol": "BTCUSDT",
                                }

            elif exchange == "kraken":
                # Kraken API (simplified)
                url = "https://api.kraken.com/0/public/Ticker?pair=XBTUSD"
                async with session.get(url) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "result" in data and "XXBTZUSD" in data["result"]:
                            ticker_data = data["result"]["XXBTZUSD"]
                            if "c" in ticker_data and len(ticker_data["c"]) > 0:
                                btc_price = float(ticker_data["c"][0])  # Current price
                                self.price_cache["kraken_BTCUSDT"] = {
                                    "price": btc_price,
                                    "timestamp": current_time,
                                    "exchange": "kraken",
                                    "symbol": "BTCUSDT",
                                }

        except Exception as e:
            self.logger.error(f"Error fetching {exchange} prices", error=str(e))

    async def _generate_spread_signals(
        self, market_data: MarketDataMessage
    ) -> Optional[list[Signal]]:
        """
        Generate arbitrage signals based on cross-exchange spreads.

        Uses QTZD-style spread analysis and threshold logic.
        """
        symbol = market_data.symbol
        signals = []

        # Get prices from all exchanges for this symbol
        exchange_prices = self._get_exchange_prices(symbol)

        if len(exchange_prices) < 2:
            return None  # Need at least 2 exchanges

        # Find highest and lowest prices (QTZD-style min/max analysis)
        highest_exchange = max(
            exchange_prices, key=lambda x: exchange_prices[x]["price"]
        )
        lowest_exchange = min(
            exchange_prices, key=lambda x: exchange_prices[x]["price"]
        )

        highest_price = exchange_prices[highest_exchange]["price"]
        lowest_price = exchange_prices[lowest_exchange]["price"]

        # Calculate spread percentage
        spread_percent = ((highest_price - lowest_price) / lowest_price) * 100

        # Update spread history (QTZD-style time series tracking)
        self._update_spread_history(
            symbol, spread_percent, highest_exchange, lowest_exchange
        )

        # Generate signal if spread exceeds threshold (QTZD-style threshold logic)
        if spread_percent >= self.spread_threshold:
            # Rate limiting (QTZD-style minimum intervals)
            signal_key = f"{symbol}_{highest_exchange}_{lowest_exchange}"
            if self._should_generate_signal(signal_key):
                # Calculate confidence based on spread size
                confidence_score = min(
                    0.95, spread_percent / 2.0
                )  # Higher spread = higher confidence

                # Create buy signal for lower-priced exchange
                buy_signal = self._create_arbitrage_signal(
                    signal_type=SignalType.BUY,
                    action=SignalAction.OPEN_LONG,
                    symbol=symbol,
                    confidence_score=confidence_score,
                    reasoning=f"Arbitrage buy on {lowest_exchange}: {spread_percent:.2f}% spread",
                    market_data=market_data,
                    exchange=lowest_exchange,
                    price=lowest_price,
                    metadata={
                        "spread_percent": spread_percent,
                        "buy_exchange": lowest_exchange,
                        "sell_exchange": highest_exchange,
                        "buy_price": lowest_price,
                        "sell_price": highest_price,
                        "potential_profit": spread_percent,
                        "arbitrage_type": "cross_exchange",
                        "position_size_usdt": min(
                            self.max_position_size,
                            self.max_position_size * confidence_score,
                        ),
                    },
                )

                # Create sell signal for higher-priced exchange
                sell_signal = self._create_arbitrage_signal(
                    signal_type=SignalType.SELL,
                    action=SignalAction.OPEN_SHORT,
                    symbol=symbol,
                    confidence_score=confidence_score,
                    reasoning=f"Arbitrage sell on {highest_exchange}: {spread_percent:.2f}% spread",
                    market_data=market_data,
                    exchange=highest_exchange,
                    price=highest_price,
                    metadata={
                        "spread_percent": spread_percent,
                        "buy_exchange": lowest_exchange,
                        "sell_exchange": highest_exchange,
                        "buy_price": lowest_price,
                        "sell_price": highest_price,
                        "potential_profit": spread_percent,
                        "arbitrage_type": "cross_exchange",
                        "position_size_usdt": min(
                            self.max_position_size,
                            self.max_position_size * confidence_score,
                        ),
                    },
                )

                signals.extend([buy_signal, sell_signal])
                self.last_signal_times[signal_key] = datetime.utcnow()

        return signals if signals else None

    def _get_exchange_prices(self, symbol: str) -> dict[str, dict[str, Any]]:
        """Get current prices from all exchanges for a symbol."""
        exchange_prices = {}
        current_time = time.time()
        max_age = 60  # 1 minute max age for prices

        for cache_key, price_data in self.price_cache.items():
            if (
                price_data["symbol"] == symbol
                and current_time - price_data["timestamp"] <= max_age
            ):
                exchange_prices[price_data["exchange"]] = price_data

        return exchange_prices

    def _update_spread_history(
        self,
        symbol: str,
        spread_percent: float,
        highest_exchange: str,
        lowest_exchange: str,
    ) -> None:
        """Update spread history for trend analysis."""
        if symbol not in self.spread_history:
            self.spread_history[symbol] = []

        current_time = time.time()
        spread_entry = {
            "timestamp": current_time,
            "spread_percent": spread_percent,
            "highest_exchange": highest_exchange,
            "lowest_exchange": lowest_exchange,
        }

        self.spread_history[symbol].append(spread_entry)

        # Keep only recent history (1 hour)
        cutoff_time = current_time - 3600
        self.spread_history[symbol] = [
            entry
            for entry in self.spread_history[symbol]
            if entry["timestamp"] > cutoff_time
        ]

    def _should_generate_signal(self, signal_key: str) -> bool:
        """
        Check if enough time has passed since last signal.

        QTZD-style rate limiting to prevent signal spam.
        """
        if signal_key not in self.last_signal_times:
            return True

        time_since_last = datetime.utcnow() - self.last_signal_times[signal_key]
        return time_since_last.total_seconds() >= self.min_signal_interval

    def _create_arbitrage_signal(
        self,
        signal_type: SignalType,
        action: SignalAction,
        symbol: str,
        confidence_score: float,
        reasoning: str,
        market_data: MarketDataMessage,
        exchange: str,
        price: float,
        metadata: dict[str, Any],
    ) -> Signal:
        """Create an arbitrage trading signal."""

        # Map confidence score to confidence level
        if confidence_score >= 0.8:
            confidence = SignalConfidence.HIGH
        elif confidence_score >= 0.6:
            confidence = SignalConfidence.MEDIUM
        else:
            confidence = SignalConfidence.LOW

        return Signal(
            symbol=symbol,
            signal_type=signal_type,
            signal_action=action,
            confidence=confidence,
            confidence_score=confidence_score,
            price=price,
            strategy_name="cross_exchange_spread",
            metadata={
                **metadata,
                "reasoning": reasoning,
                "target_exchange": exchange,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def get_metrics(self) -> dict[str, Any]:
        """Get strategy metrics."""
        return {
            "strategy_name": "cross_exchange_spread",
            "signals_generated": self.signals_generated,
            "arbitrage_opportunities_found": self.arbitrage_opportunities_found,
            "cached_prices_count": len(self.price_cache),
            "spread_history_symbols": list(self.spread_history.keys()),
            "active_exchanges": list(
                set(data["exchange"] for data in self.price_cache.values())
            ),
            "uptime_seconds": time.time() - self.last_update_time,
        }
