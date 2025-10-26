# Petrosa Realtime Strategies

**Stateless real-time trading signal generation from streaming market data**

A high-performance, horizontally scalable trading signal service that processes real-time market data from NATS and generates trading signals using multiple stateless strategies. Designed for enterprise deployment with auto-scaling, comprehensive monitoring, and zero-state architecture.

---

## 🌐 PETROSA ECOSYSTEM OVERVIEW

[Same ecosystem overview as other services - maintaining consistency]

### Services in the Ecosystem

| Service | Purpose | Input | Output | Status |
|---------|---------|-------|--------|--------|
| **petrosa-socket-client** | Real-time WebSocket data ingestion | Binance WebSocket API | NATS: `binance.websocket.data` | Real-time Processing |
| **petrosa-binance-data-extractor** | Historical data extraction & gap filling | Binance REST API | MySQL (klines, funding rates, trades) | Batch Processing |
| **petrosa-bot-ta-analysis** | Technical analysis (28 strategies) | MySQL klines data | NATS: `signals.trading` | Signal Generation |
| **petrosa-realtime-strategies** | Real-time signal generation | NATS: `binance.websocket.data` | NATS: `signals.trading` | **YOU ARE HERE** |
| **petrosa-tradeengine** | Order execution & trade management | NATS: `signals.trading` | Binance Orders API, MongoDB audit | Order Execution |
| **petrosa_k8s** | Centralized infrastructure | Kubernetes manifests | Cluster resources | Infrastructure |

### Data Flow Pipeline

```
┌─────────────┐
│   Binance   │
│  WebSocket  │
└──────┬──────┘
       │
       ▼
┌──────────────────────┐
│   Socket Client      │
│  (WebSocket Client)  │
└──────┬───────────────┘
       │ NATS: binance.websocket.data
       │
       ▼
┌──────────────────────┐
│    NATS Server       │
│  (Message Bus)       │
└──────┬───────────────┘
       │
       ├────────────────┐
       │                │
       ▼                ▼
┌──────────────┐  ┌───────────────┐
│ Realtime     │  │  TA Bot       │
│ Strategies   │  │  (Historical) │
│ (THIS SERVICE)│  └───────────────┘
│              │
│ • Consume    │
│   live data  │
│ • Process    │
│   stateless  │
│ • Generate   │
│   signals    │
└──────┬───────┘
       │ NATS: signals.trading
       │
       ▼
┌──────────────────────┐
│   Trade Engine       │
│  (Order Execution)   │
└──────────────────────┘
```

### Transport Layer

#### NATS Messaging (Input & Output)

**Consumed Topic:** `binance.websocket.data`

**Message Types Consumed:**
1. **Trade Messages** - Individual trades
2. **Ticker Messages** - 24hr ticker updates
3. **Depth Messages** - Order book depth (top 20 levels)

**Published Topic:** `signals.trading`

**Message Format (Output):**
```json
{
  "strategy_id": "orderbook_skew",
  "symbol": "BTCUSDT",
  "action": "buy",
  "confidence": 0.75,
  "price": 50000.00,
  "quantity": 0.001,
  "current_price": 50000.00,
  "timeframe": "tick",
  "stop_loss": 49500.00,
  "take_profit": 50750.00,
  "indicators": {
    "bid_ask_ratio": 1.35,
    "spread_percent": 0.08
  },
  "metadata": {
    "strategy": "orderbook_skew",
    "top_bid": 49999.50,
    "top_ask": 50000.50
  },
  "timestamp": "2024-01-01T00:00:00.000Z"
}
```

---

## 🔧 REALTIME STRATEGIES - DETAILED DOCUMENTATION

### Service Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                Realtime Strategies Architecture                     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │                    Main Service                           │     │
│  │                                                            │     │
│  │  • NATS Consumer (binance.websocket.data)                │     │
│  │  • Signal Processor (stateless)                          │     │
│  │  • NATS Publisher (signals.trading)                      │     │
│  │  • Health Server (HTTP:8080)                             │     │
│  │  • Heartbeat Manager (periodic stats)                    │     │
│  └──────┬───────────────────────────────────────────────────┘     │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              NATS Consumer                                │     │
│  │                                                            │     │
│  │  • Subscribe to binance.websocket.data                   │     │
│  │  • Consumer group: realtime-strategies-group             │     │
│  │  • Load balancing across replicas                        │     │
│  │  • Circuit breaker protection                            │     │
│  │  • Message validation                                    │     │
│  └──────┬───────────────────────────────────────────────────┘     │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │             Message Router & Parser                       │     │
│  │                                                            │     │
│  │  Route by stream type:                                   │     │
│  │  • @trade    → Trade Momentum Strategy                   │     │
│  │  • @ticker   → Ticker Velocity Strategy                  │     │
│  │  • @depth20  → Order Book Skew Strategy                  │     │
│  └──────┬───────────────────────────────────────────────────┘     │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │              Stateless Strategy Processors                │     │
│  │                                                            │     │
│  │  ┌──────────────────────────────────────────────────┐   │     │
│  │  │  Order Book Skew Strategy                        │   │     │
│  │  │                                                    │   │     │
│  │  │  • Analyze bid/ask imbalance                     │   │     │
│  │  │  • Calculate top 5 levels ratio                  │   │     │
│  │  │  • Detect buying/selling pressure                │   │     │
│  │  │  • Generate signals on significant skew          │   │     │
│  │  │                                                    │   │     │
│  │  │  Thresholds:                                     │   │     │
│  │  │  • Buy:  ratio > 1.2 (more bids)                │   │     │
│  │  │  • Sell: ratio < 0.8 (more asks)                │   │     │
│  │  └──────────────────────────────────────────────────┘   │     │
│  │                                                            │     │
│  │  ┌──────────────────────────────────────────────────┐   │     │
│  │  │  Trade Momentum Strategy                         │   │     │
│  │  │                                                    │   │     │
│  │  │  • Analyze individual trades                     │   │     │
│  │  │  • Weighted momentum score:                      │   │     │
│  │  │    - Price movement (40%)                        │   │     │
│  │  │    - Quantity size (30%)                         │   │     │
│  │  │    - Maker/taker ratio (30%)                     │   │     │
│  │  │  • Detect momentum shifts                        │   │     │
│  │  │                                                    │   │     │
│  │  │  Thresholds:                                     │   │     │
│  │  │  • Buy:  momentum > 0.7                          │   │     │
│  │  │  • Sell: momentum < -0.7                         │   │     │
│  │  └──────────────────────────────────────────────────┘   │     │
│  │                                                            │     │
│  │  ┌──────────────────────────────────────────────────┐   │     │
│  │  │  Ticker Velocity Strategy                        │   │     │
│  │  │                                                    │   │     │
│  │  │  • Track price velocity over time window         │   │     │
│  │  │  • Calculate rate of change (60s window)         │   │     │
│  │  │  • Detect acceleration/deceleration              │   │     │
│  │  │  • Filter by minimum change threshold            │   │     │
│  │  │                                                    │   │     │
│  │  │  Thresholds:                                     │   │     │
│  │  │  • Buy:  velocity > 0.5% per minute              │   │     │
│  │  │  • Sell: velocity < -0.5% per minute             │   │     │
│  │  └──────────────────────────────────────────────────┘   │     │
│  └──────┬───────────────────────────────────────────────────┘     │
│         │                                                            │
│         ▼                                                            │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │            Signal Validation & Publishing                 │     │
│  │                                                            │     │
│  │  • Validate signal completeness                          │     │
│  │  • Check confidence threshold (>= 0.6)                   │     │
│  │  • Add risk management levels                            │     │
│  │  • Publish to signals.trading topic                      │     │
│  │  • Increment metrics                                     │     │
│  └──────────────────────────────────────────────────────────┘     │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │                    Monitoring                             │     │
│  │                                                            │     │
│  │  • Heartbeat (60s): Message processing stats             │     │
│  │  • Circuit Breaker: Connection fault tolerance           │     │
│  │  • Metrics: Prometheus-compatible                        │     │
│  │  • Health Checks: /healthz, /ready, /metrics             │     │
│  └──────────────────────────────────────────────────────────┘     │
└────────────────────────────────────────────────────────────────────┘
```

### Core Components

#### 1. NATS Consumer (`strategies/core/consumer.py`)

**Stateless Message Processing:**

```python
class NATSConsumer:
    """NATS consumer with stateless processing."""
    
    def __init__(
        self,
        nats_url: str,
        topic: str,
        consumer_name: str,
        consumer_group: str,
        publisher: TradeOrderPublisher,
        logger: Optional[structlog.BoundLogger] = None
    ):
        self.nats_url = nats_url
        self.topic = topic
        self.consumer_name = consumer_name
        self.consumer_group = consumer_group  # Load balancing
        self.publisher = publisher
        
        # Processing state (stateless - reset per message)
        self.message_count = 0
        self.error_count = 0
        
        # Initialize strategies
        self.strategies = {
            "orderbook_skew": OrderBookSkewStrategy(),
            "trade_momentum": TradeMomentumStrategy(),
            "ticker_velocity": TickerVelocityStrategy()
        }
    
    async def start(self) -> None:
        """Start consuming messages."""
        await self._connect_to_nats()
        await self._subscribe_to_topic()
        
        self.is_running = True
        asyncio.create_task(self._processing_loop())
    
    async def _subscribe_to_topic(self) -> None:
        """Subscribe with consumer group for load balancing."""
        self.subscription = await self.nats_client.subscribe(
            self.topic,
            queue=self.consumer_group,  # IMPORTANT: Enables load balancing
            cb=self._message_handler
        )
    
    async def _message_handler(self, msg):
        """Handle incoming message (stateless)."""
        try:
            # Parse message
            data = json.loads(msg.data.decode())
            
            # Determine stream type
            stream = data.get("stream", "")
            
            # Route to appropriate strategy (stateless)
            if "@trade" in stream:
                await self._process_trade(data)
            elif "@ticker" in stream:
                await self._process_ticker(data)
            elif "@depth" in stream:
                await self._process_depth(data)
            
            self.message_count += 1
            
        except Exception as e:
            self.error_count += 1
            logger.error(f"Message processing failed: {e}")
    
    async def _process_depth(self, data: dict):
        """Process order book depth data."""
        market_data = DepthUpdate.parse_obj(data["data"])
        
        # Run stateless strategy
        signal = self.strategies["orderbook_skew"].analyze(market_data)
        
        if signal:
            # Publish signal
            await self.publisher.publish_signal(signal)
            logger.info(f"Signal generated: {signal.strategy_id}")
```

#### 2. Order Book Skew Strategy (`strategies/core/orderbook_skew.py`)

**Stateless Analysis:**

```python
class OrderBookSkewStrategy:
    """
    Analyze order book imbalance for buying/selling pressure.
    
    Completely stateless - each message processed independently.
    No historical data required.
    
    Algorithm:
    1. Sum bid volumes (top 5 levels)
    2. Sum ask volumes (top 5 levels)
    3. Calculate ratio: bid_volume / ask_volume
    4. Generate signal if ratio exceeds threshold
    
    Thresholds:
    - Buy: ratio > 1.2 (20% more bids than asks)
    - Sell: ratio < 0.8 (20% more asks than bids)
    """
    
    def __init__(
        self,
        top_levels: int = 5,
        buy_threshold: float = 1.2,
        sell_threshold: float = 0.8,
        min_spread_percent: float = 0.1
    ):
        self.top_levels = top_levels
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.min_spread_percent = min_spread_percent
    
    def analyze(self, depth_data: DepthUpdate) -> Optional[Signal]:
        """
        Analyze order book depth (stateless).
        
        Args:
            depth_data: Order book depth update
        
        Returns:
            Signal if conditions met, None otherwise
        """
        # Calculate bid volume (top N levels)
        bid_volume = sum(
            float(level.quantity)
            for level in depth_data.bids[:self.top_levels]
        )
        
        # Calculate ask volume (top N levels)
        ask_volume = sum(
            float(level.quantity)
            for level in depth_data.asks[:self.top_levels]
        )
        
        if ask_volume == 0:
            return None
        
        # Calculate ratio
        ratio = bid_volume / ask_volume
        
        # Check spread (filter out low liquidity)
        top_bid = float(depth_data.bids[0].price)
        top_ask = float(depth_data.asks[0].price)
        spread_percent = ((top_ask - top_bid) / top_bid) * 100
        
        if spread_percent > self.min_spread_percent:
            return None  # Spread too wide
        
        # Generate signal
        action = None
        confidence = 0.0
        
        if ratio > self.buy_threshold:
            action = "buy"
            # Scale confidence based on how far above threshold
            confidence = min(0.95, 0.60 + (ratio - self.buy_threshold) * 0.5)
            
        elif ratio < self.sell_threshold:
            action = "sell"
            # Scale confidence based on how far below threshold
            confidence = min(0.95, 0.60 + (self.sell_threshold - ratio) * 0.5)
        
        if action is None:
            return None
        
        # Create signal
        return Signal(
            strategy_id="orderbook_skew",
            symbol=depth_data.symbol,
            action=action,
            confidence=confidence,
            price=top_bid if action == "buy" else top_ask,
            quantity=0.001,
            current_price=(top_bid + top_ask) / 2,
            timeframe="tick",
            indicators={
                "bid_volume": bid_volume,
                "ask_volume": ask_volume,
                "ratio": ratio,
                "spread_percent": spread_percent
            },
            metadata={
                "strategy": "orderbook_skew",
                "top_bid": top_bid,
                "top_ask": top_ask
            }
        )
```

#### 3. Trade Momentum Strategy

**Weighted Momentum Score:**

```python
class TradeMomentumStrategy:
    """
    Analyze individual trades for momentum indicators.
    
    Weighted scoring system:
    - Price movement: 40%
    - Quantity size: 30%
    - Maker/taker status: 30%
    """
    
    def analyze(self, trade_data: TradeData) -> Optional[Signal]:
        """Stateless trade analysis."""
        # Calculate price momentum
        price_change = trade_data.price - trade_data.previous_price
        price_momentum = price_change / trade_data.previous_price if trade_data.previous_price > 0 else 0
        
        # Quantity score (normalized)
        quantity_score = min(1.0, trade_data.quantity / trade_data.avg_quantity)
        
        # Maker/taker score
        # is_buyer_maker=True means seller initiated (bearish)
        # is_buyer_maker=False means buyer initiated (bullish)
        maker_score = -1.0 if trade_data.is_buyer_maker else 1.0
        
        # Weighted momentum
        momentum = (
            price_momentum * 0.4 +
            quantity_score * 0.3 +
            maker_score * 0.3
        )
        
        # Check thresholds
        if momentum > 0.7:
            action = "buy"
            confidence = min(0.95, 0.65 + momentum * 0.2)
        elif momentum < -0.7:
            action = "sell"
            confidence = min(0.95, 0.65 + abs(momentum) * 0.2)
        else:
            return None
        
        return Signal(
            strategy_id="trade_momentum",
            symbol=trade_data.symbol,
            action=action,
            confidence=confidence,
            price=trade_data.price,
            quantity=0.001,
            current_price=trade_data.price,
            timeframe="tick",
            indicators={
                "momentum": momentum,
                "price_momentum": price_momentum,
                "quantity_score": quantity_score,
                "maker_score": maker_score
            }
        )
```

#### 4. Ticker Velocity Strategy

**Price Velocity Detection:**

```python
class TickerVelocityStrategy:
    """
    Analyze price velocity over time windows.
    
    Tracks rate of change to detect acceleration/deceleration.
    """
    
    def __init__(
        self,
        time_window: int = 60,  # seconds
        buy_threshold: float = 0.5,  # % per minute
        sell_threshold: float = -0.5
    ):
        self.time_window = time_window
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        
        # In-memory cache for velocity calculation
        # NOTE: This introduces minimal state but is acceptable
        #       for velocity calculations
        self.price_cache = {}  # {symbol: [(timestamp, price)]}
    
    def analyze(self, ticker_data: TickerData) -> Optional[Signal]:
        """Calculate velocity and generate signal."""
        symbol = ticker_data.symbol
        current_price = ticker_data.last_price
        current_time = time.time()
        
        # Update cache
        if symbol not in self.price_cache:
            self.price_cache[symbol] = []
        
        self.price_cache[symbol].append((current_time, current_price))
        
        # Remove old entries (outside time window)
        cutoff_time = current_time - self.time_window
        self.price_cache[symbol] = [
            (t, p) for t, p in self.price_cache[symbol]
            if t >= cutoff_time
        ]
        
        # Need at least 2 points for velocity
        if len(self.price_cache[symbol]) < 2:
            return None
        
        # Calculate velocity (% change per minute)
        oldest_time, oldest_price = self.price_cache[symbol][0]
        time_elapsed = (current_time - oldest_time) / 60  # minutes
        
        if time_elapsed == 0 or oldest_price == 0:
            return None
        
        price_change = ((current_price - oldest_price) / oldest_price) * 100
        velocity = price_change / time_elapsed  # % per minute
        
        # Check thresholds
        if velocity > self.buy_threshold:
            action = "buy"
            confidence = min(0.95, 0.60 + (velocity / 10))
        elif velocity < self.sell_threshold:
            action = "sell"
            confidence = min(0.95, 0.60 + (abs(velocity) / 10))
        else:
            return None
        
        return Signal(
            strategy_id="ticker_velocity",
            symbol=symbol,
            action=action,
            confidence=confidence,
            price=current_price,
            quantity=0.001,
            current_price=current_price,
            timeframe="tick",
            indicators={
                "velocity": velocity,
                "time_window": time_elapsed * 60,
                "price_change_percent": price_change
            }
        )
```

---

## 🎛️ RUNTIME CONFIGURATION & MARKET METRICS API

### Overview

The Realtime Strategies service provides **two comprehensive REST APIs**:

1. **Configuration API** - Real-time strategy parameter management
2. **Market Metrics API** - Order book depth analytics and market pressure indicators

Both APIs are production-ready, fully documented, and LLM-agent friendly.

**Base URL**: `http://realtime-strategies:8080`  
**Swagger UI**: `http://realtime-strategies:8080/docs`

---

### Part 1: Configuration API

#### FastAPI Endpoints

**Discovery**:
```bash
GET /api/v1/strategies                      # List all strategies
GET /api/v1/strategies/{id}/schema          # Get parameter schema
GET /api/v1/strategies/{id}/defaults        # Get default values
```

**Configuration Management**:
```bash
GET /api/v1/strategies/{id}/config          # Get global config
POST /api/v1/strategies/{id}/config         # Update global config
GET /api/v1/strategies/{id}/config/{symbol} # Get symbol config
POST /api/v1/strategies/{id}/config/{symbol}# Update symbol config
DELETE /api/v1/strategies/{id}/config       # Delete global config
DELETE /api/v1/strategies/{id}/config/{symbol} # Delete symbol config
```

**Monitoring**:
```bash
GET /api/v1/strategies/{id}/audit           # Get change history
POST /api/v1/strategies/cache/refresh       # Force cache refresh
```

#### Configurable Strategies (All 6)

**Realtime Data Strategies** (WebSocket-based):

1. **Orderbook Skew** (8 parameters):
```json
{
  "top_levels": 5,
  "buy_threshold": 1.2,
  "sell_threshold": 0.8,
  "min_spread_percent": 0.1,
  "base_confidence": 0.70,
  "imbalance_weight": 0.6,
  "spread_weight": 0.4,
  "min_total_volume": 0.001
}
```

2. **Trade Momentum** (9 parameters):
```json
{
  "price_weight": 0.4,
  "quantity_weight": 0.3,
  "maker_weight": 0.3,
  "buy_threshold": 0.7,
  "sell_threshold": -0.7,
  "min_quantity": 0.001,
  "base_confidence": 0.68,
  "time_decay_seconds": 300,
  "momentum_window": 10
}
```

3. **Ticker Velocity** (8 parameters):
```json
{
  "time_window": 60,
  "buy_threshold": 0.5,
  "sell_threshold": -0.5,
  "min_price_change": 0.1,
  "base_confidence": 0.65,
  "acceleration_weight": 0.5,
  "volume_confirmation": true,
  "min_volume_change": 0.2
}
```

**Market Logic Strategies** (Analysis-based):

4. **BTC Dominance** (5 parameters) - Already documented below
5. **Cross-Exchange Spread** (3 parameters) - Already documented below
6. **On-Chain Metrics** (4 parameters) - Already documented below

---

### Part 2: Market Metrics API ✨ NEW

Real-time order book depth analytics providing market pressure indicators:

#### Endpoints

```bash
GET /api/v1/metrics/depth/{symbol}                    # Current depth metrics
GET /api/v1/metrics/pressure/{symbol}?timeframe=5m    # Pressure history
GET /api/v1/metrics/summary                           # Market-wide summary
GET /api/v1/metrics/all                               # All symbols metrics
```

#### What You Get

**Order Book Imbalance**:
- Bid vs ask volume ratio
- Imbalance percentage
- Buy/sell pressure (0-100 scale)
- Net pressure indicator

**Liquidity Analysis**:
- Total liquidity
- Depth at top 5/10 levels
- Volume-weighted prices (VWAP)

**Spread Metrics**:
- Bid-ask spread (absolute & basis points)
- Mid price
- Best bid/ask

**Market Insights**:
- Strongest support/resistance levels
- Pressure trends (bullish/bearish/neutral)
- Market-wide sentiment aggregation

#### Quick Examples

**Check market pressure for BTC**:
```bash
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq '.pressure'

# Response:
{
  "buy_pressure": 65.5,
  "sell_pressure": 34.5,
  "net_pressure": 31.0,
  "interpretation": "bullish"
}
```

**Get pressure trend**:
```bash
curl "http://realtime-strategies:8080/api/v1/metrics/pressure/BTCUSDT?timeframe=5m" | jq '.summary'

# Response:
{
  "avg_pressure": 25.5,
  "trend": "bullish",
  "trend_strength": 0.75
}
```

**Overall market sentiment**:
```bash
curl http://realtime-strategies:8080/api/v1/metrics/summary | jq '.market_sentiment'

# Response:
{
  "bullish_symbols": 28,
  "bearish_symbols": 12,
  "neutral_symbols": 5,
  "avg_net_pressure": 15.5
}
```

---

### Configuration Architecture

- **MongoDB Persistence**: Primary storage for configurations
- **60-Second Caching**: Fast performance, automatic refresh
- **Environment Fallback**: Backward compatible with ConfigMap
- **Audit Trail**: Full change history tracking
- **Schema Validation**: Prevents invalid configurations
- **Symbol Overrides**: Global + per-symbol customization

### Remaining Market Logic Strategies

#### BTC Dominance Strategy (5 parameters)
```json
{
  "high_threshold": 70.0,
  "low_threshold": 40.0,
  "change_threshold": 5.0,
  "window_hours": 24,
  "min_signal_interval": 14400
}
```

#### Cross-Exchange Spread Strategy (3 parameters)
```json
{
  "spread_threshold_percent": 0.5,
  "min_signal_interval": 300,
  "max_position_size": 500
}
```

#### On-Chain Metrics Strategy (4 parameters)
```json
{
  "whale_threshold_btc": 100,
  "whale_threshold_eth": 1000,
  "exchange_flow_threshold_percent": 10.0,
  "min_signal_interval": 3600
}
```

### Configuration Examples

**Update Orderbook Skew globally**:
```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "buy_threshold": 1.3,
      "sell_threshold": 0.75
    },
    "changed_by": "admin",
    "reason": "Adjusting sensitivity for current market conditions"
  }'
```

**Update for specific symbol (BTCUSDT)**:
```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/config/BTCUSDT \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "buy_threshold": 1.5
    },
    "changed_by": "admin",
    "reason": "BTC requires higher threshold due to liquidity"
  }'
```

**Force cache refresh**:
```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/cache/refresh
```

### Configuration Inheritance

Supports **global defaults with per-symbol overrides**:

```
Global Config: high_threshold = 70.0 (all symbols)
BTCUSDT Override: high_threshold = 75.0 (only for BTC)
ETHUSDT: uses global 70.0
```

### Signal Metadata

All signals include configuration metadata for tracking:

```json
{
  "strategy_id": "btc_dominance",
  "symbol": "BTCUSDT",
  "action": "buy",
  "confidence": 0.80,
  "metadata": {
    "strategy_config": {
      "version": 2,
      "parameters": {
        "high_threshold": 75.0,
        "change_threshold": 7.0
      },
      "source": "mongodb",
      "is_override": false
    },
    "dominance": 72.5,
    "trend": "rising"
  }
}
```

### Configuration Features

- ✅ **5-Level Priority**: Cache → MongoDB Symbol → MySQL Symbol → MongoDB Global → MySQL Global → Defaults
- ✅ **Dual Persistence**: MongoDB primary, MySQL fallback
- ✅ **60-Second Cache**: Minimal database load
- ✅ **Full Audit Trail**: Track all changes with who/what/when/why
- ✅ **Parameter Validation**: Type checking and range validation
- ✅ **100% Backward Compatible**: Works with or without config system
- ✅ **MCP-Compatible API**: Structured for LLM agent integration

### Configuration Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DATABASE` | `petrosa` | MongoDB database name |
| `MYSQL_URI` | `mysql://user:pass@host:3306/db` | MySQL connection string |
| `CONFIG_CACHE_TTL_SECONDS` | `60` | Configuration cache TTL |
| `FASTAPI_PORT` | `8080` | Configuration API port |

For complete documentation, examples, and troubleshooting, see the [TA Bot Configuration Guide](../petrosa-bot-ta-analysis/README.md#runtime-configuration-management).

---

### Configuration

**Environment Variables:**

| Variable | Default | Description |
|----------|---------|-------------|
| `NATS_URL` | `nats://localhost:4222` | NATS server URL |
| `MONGODB_URI` | `mongodb://localhost:27017` | MongoDB connection string |
| `MONGODB_DATABASE` | `petrosa` | MongoDB database name |
| `MYSQL_URI` | `mysql://user:pass@host:3306/db` | MySQL connection string (fallback) |
| `NATS_CONSUMER_TOPIC` | `binance.websocket.data` | Input topic |
| `NATS_PUBLISHER_TOPIC` | `signals.trading` | Output topic |
| `NATS_CONSUMER_GROUP` | `realtime-strategies-group` | Consumer group for load balancing |
| `TRADING_SYMBOLS` | `BTCUSDT,ETHUSDT,BNBUSDT` | Symbols to process |
| `STRATEGY_ENABLED_ORDERBOOK_SKEW` | `true` | Enable order book strategy |
| `STRATEGY_ENABLED_TRADE_MOMENTUM` | `true` | Enable trade momentum strategy |
| `STRATEGY_ENABLED_TICKER_VELOCITY` | `true` | Enable ticker velocity strategy |
| `ORDERBOOK_SKEW_BUY_THRESHOLD` | `1.2` | Bid/ask ratio for buy signal |
| `TRADE_MOMENTUM_BUY_THRESHOLD` | `0.7` | Momentum score for buy signal |
| `TICKER_VELOCITY_BUY_THRESHOLD` | `0.5` | Velocity (% per min) for buy |
| `CONFIG_CACHE_TTL_SECONDS` | `60` | Config cache TTL |
| `FASTAPI_PORT` | `8080` | Configuration API port |
| `HEARTBEAT_INTERVAL_SECONDS` | `60` | Heartbeat logging interval |

### Deployment

**Kubernetes Deployment (Horizontal Scaling):**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: petrosa-realtime-strategies
  namespace: petrosa-apps
spec:
  replicas: 3  # Horizontal scaling
  selector:
    matchLabels:
      app: realtime-strategies
  template:
    spec:
      containers:
      - name: realtime-strategies
        image: yurisa2/petrosa-realtime-strategies:VERSION_PLACEHOLDER
        env:
        - name: NATS_URL
          valueFrom:
            configMapKeyRef:
              name: petrosa-common-config
              key: NATS_URL
        - name: NATS_CONSUMER_TOPIC
          value: "binance.websocket.data"
        - name: NATS_PUBLISHER_TOPIC
          value: "signals.trading"
        - name: NATS_CONSUMER_GROUP
          value: "realtime-strategies-group"  # CRITICAL for load balancing
        resources:
          requests:
            memory: "256Mi"
            cpu: "200m"
          limits:
            memory: "512Mi"
            cpu: "1000m"
---
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: realtime-strategies-hpa
  namespace: petrosa-apps
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: petrosa-realtime-strategies
  minReplicas: 3
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

**Why Horizontal Scaling Works:**

1. **Stateless Design**: Each message processed independently
2. **NATS Consumer Groups**: Automatic load balancing
3. **No Shared State**: No coordination required between pods
4. **Linear Scalability**: Performance scales with pod count

---

## Monitoring & Observability

### Grafana Dashboard
📊 **[Realtime Strategies Business Metrics](https://grafana.com/)** (Dashboard pending import - see [issue #72](https://github.com/PetroSa2/petrosa-realtime-strategies/issues/72))

The service exposes comprehensive business metrics via OpenTelemetry:

#### Key Metrics
- **Message Processing Rate**: `rate(realtime_messages_processed_total[1m])`
- **Strategy Latency (p95)**: `histogram_quantile(0.95, rate(realtime_strategy_latency_bucket[1m]))`
- **Consumer Lag**: `realtime_consumer_lag`
- **Signal Generation Rate**: `rate(realtime_signals_generated_total[1m])`
- **Strategy Success Rate**: `rate(realtime_strategy_executions_total{result="success"}[1m]) / rate(realtime_strategy_executions_total[1m])`

#### Expected Performance
- Message processing: **1000+ msg/sec**
- Strategy latency (p95): **< 50ms**
- Consumer lag: **< 5 seconds**
- Strategy success rate: **> 90%**

### Documentation
- 📖 [Complete Metrics Guide](docs/BUSINESS_METRICS.md) - Metric descriptions, PromQL queries, alerting rules
- 🎨 [Grafana Dashboard Config](docs/grafana-dashboard.json) - Dashboard JSON for import

### Quick Troubleshooting

**High consumer lag?**
```bash
# Check message processing rate
kubectl logs -n petrosa-apps deployment/petrosa-realtime-strategies | grep "Message processed"

# Scale horizontally if needed
kubectl scale deployment/petrosa-realtime-strategies --replicas=5 -n petrosa-apps
```

**High strategy latency?**
```bash
# Check which strategy is slow
curl http://petrosa-realtime-strategies:8080/metrics | grep strategy_latency

# Review strategy configuration
curl http://petrosa-realtime-strategies:8080/api/v1/strategies
```

**No signals being generated?**
```bash
# Check strategy execution results
curl http://petrosa-realtime-strategies:8080/metrics | grep strategy_executions

# Verify strategies are enabled
python -m strategies.main config
```

See [BUSINESS_METRICS.md](docs/BUSINESS_METRICS.md#troubleshooting) for complete troubleshooting guide.

---

### Monitoring

**Heartbeat Logs (Every 60s):**

```json
{
  "level": "INFO",
  "message": "HEARTBEAT: Realtime Strategies Statistics",
  "messages_processed": 1500,
  "signals_generated": 75,
  "consumer_errors": 0,
  "publisher_errors": 0,
  "messages_per_second": 25.0,
  "signals_per_minute": 1.25,
  "uptime_seconds": 3600,
  "strategies": {
    "orderbook_skew": {"signals": 30},
    "trade_momentum": {"signals": 25},
    "ticker_velocity": {"signals": 20}
  }
}
```

**Prometheus Metrics:**

```
# Message processing
realtime_strategies_messages_processed_total 150000
realtime_strategies_messages_errors_total 0
realtime_strategies_processing_latency_seconds 0.002

# Signal generation
realtime_strategies_signals_generated_total{strategy="orderbook_skew"} 3000
realtime_strategies_signals_generated_total{strategy="trade_momentum"} 2500

# Connection health
realtime_strategies_nats_connected 1
realtime_strategies_circuit_breaker_state{name="nats"} 0
```

**Grafana Dashboards:**

📊 **[Realtime Strategies Business Metrics](https://grafana.com/)** (Dashboard pending import - see issue #72)

The Grafana dashboard provides comprehensive visualization of:
- **Message Processing Rate**: Real-time throughput (target: 1000+ msg/sec)
- **Strategy Execution Latency**: P95/P99 performance (target: < 50ms)
- **NATS Consumer Lag**: Processing backlog (normal: < 5s)
- **Signal Generation**: Tracking by strategy, type, and confidence level
- **Error Rates**: Success/failure rates and health indicators

**Dashboard Location**: `docs/grafana-dashboard.json`  
**Import Guide**: See [`petrosa_k8s/docs/GRAFANA_DASHBOARD_IMPORT_GUIDE.md`](https://github.com/PetroSa2/petrosa_k8s/blob/main/docs/GRAFANA_DASHBOARD_IMPORT_GUIDE.md)

**Key Metrics Thresholds**:
- ✅ **Message Processing Rate**: > 1000 msg/sec (healthy)
- ⚠️ **Strategy Latency (p95)**: > 50ms (review performance)
- ✅ **Consumer Lag**: < 5s (normal)
- ⚠️ **Consumer Lag**: 5-30s (warning)
- 🚨 **Consumer Lag**: > 30s (critical - investigation required)
- ✅ **Error Rate**: < 1% (healthy)

**Dashboard Panels (12 total)**:
1. Message Processing Rate (timeseries)
2. Strategy Execution Latency p95 (timeseries)
3. NATS Consumer Lag (timeseries with thresholds)
4. Signals Generated by Type (timeseries)
5. Strategy Success Rate (percentage)
6. Error Rate (timeseries)
7. Message Types Distribution (pie chart)
8. Signal Confidence Distribution (pie chart)
9. Top Strategies by Signal Count (bar gauge)
10. Strategy Execution Count (stat)
11. Total Messages Processed (stat)
12. Average Strategy Latency (timeseries)

For detailed metrics documentation, see [`docs/BUSINESS_METRICS.md`](docs/BUSINESS_METRICS.md).

### Troubleshooting

**Common Issues:**

1. **Duplicate Signals**
   - Check consumer group configuration
   - Verify only one subscription per group
   - Review NATS connection logs

2. **No Signals Generated**
   - Check message flow from socket-client
   - Verify strategy thresholds aren't too strict
   - Review indicators calculation

3. **High Memory Usage**
   - Monitor ticker velocity cache size
   - Reduce time window if needed
   - Check for memory leaks

---

## 📚 Documentation Structure

Core documentation (kept up-to-date):
- `README.md` - Project overview and quick start
- `QUICK_REFERENCE.md` - Common commands and workflows
- `DEPLOYMENT_GUIDE.md` - Production deployment
- `CI_CD_PIPELINE.md` - CI/CD reference
- `TESTING.md` - Testing procedures
- `MAKEFILE.md` - Makefile commands

Archive:
- `docs/archive/` - Historical documentation for reference only
  - `docs/archive/summaries/` - Implementation and feature summaries
  - `docs/archive/fixes/` - Bug fix and resolution reports
  - `docs/archive/investigations/` - Temporary analysis and diagnostic docs
  - `docs/archive/migrations/` - Migration and upgrade documentation

---

## 🚀 Quick Start

```bash
# Setup
make setup

# Run locally
make run-local

# Deploy to Kubernetes
make deploy

# Check status
make k8s-status
```

---

**Production Status:** ✅ **ACTIVE** - Processing 1000+ messages/second, generating 50-150 signals/day
