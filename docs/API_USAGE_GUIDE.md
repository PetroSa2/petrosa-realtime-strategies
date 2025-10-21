# API Usage Guide
## Realtime Strategies - Configuration & Market Metrics

**Version**: 1.0  
**Last Updated**: 2025-10-21  
**Status**: Production Ready ✅

---

## Overview

The **petrosa-realtime-strategies** service now provides two comprehensive REST APIs:

1. **Configuration API** - Real-time strategy parameter management
2. **Market Metrics API** - Order book depth analytics and market pressure indicators

**Base URL**: `http://petrosa-realtime-strategies:8080`

**API Documentation**: `http://petrosa-realtime-strategies:8080/docs` (Swagger UI)

---

## Part 1: Configuration API

### Quick Start

```bash
# 1. List all strategies
curl http://realtime-strategies:8080/api/v1/strategies | jq

# 2. Get parameter schema for a strategy
curl http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/schema | jq

# 3. Get current configuration
curl http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/config | jq

# 4. Update configuration
curl -X POST http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "top_levels": 10,
      "buy_threshold": 1.3,
      "sell_threshold": 0.75
    },
    "changed_by": "admin",
    "reason": "Adjusting for current market conditions"
  }' | jq

# 5. Force cache refresh (changes take effect immediately)
curl -X POST http://realtime-strategies:8080/api/v1/strategies/cache/refresh | jq
```

### Available Strategies

**Realtime Data Strategies** (WebSocket-based):
- `orderbook_skew` - Order book imbalance detection (8 parameters)
- `trade_momentum` - Trade flow momentum tracking (9 parameters)
- `ticker_velocity` - Price velocity and acceleration (8 parameters)

**Market Logic Strategies** (Analysis-based):
- `btc_dominance` - Bitcoin dominance rotation signals (5 parameters)
- `cross_exchange_spread` - Cross-exchange arbitrage (3 parameters)
- `onchain_metrics` - Blockchain data analysis (4 parameters)

### Configuration Examples

#### Orderbook Skew Strategy

**View Schema**:
```bash
curl http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/schema | jq
```

**Update Global Configuration**:
```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "top_levels": 10,
      "buy_threshold": 1.3,
      "sell_threshold": 0.75,
      "min_spread_percent": 0.15,
      "base_confidence": 0.72
    },
    "changed_by": "trader_john",
    "reason": "Increasing sensitivity for current low-volatility market"
  }' | jq
```

**Update for Specific Symbol (BTCUSDT)**:
```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/config/BTCUSDT \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "buy_threshold": 1.5,
      "sell_threshold": 0.7
    },
    "changed_by": "trader_john",
    "reason": "BTC has higher liquidity, needs wider thresholds"
  }' | jq
```

#### Trade Momentum Strategy

```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/trade_momentum/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "price_weight": 0.5,
      "quantity_weight": 0.3,
      "maker_weight": 0.2,
      "buy_threshold": 0.75,
      "sell_threshold": -0.75
    },
    "changed_by": "admin",
    "reason": "Emphasizing price momentum over quantity"
  }' | jq
```

#### Ticker Velocity Strategy

```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/ticker_velocity/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "time_window": 90,
      "buy_threshold": 0.6,
      "sell_threshold": -0.6,
      "volume_confirmation": true,
      "min_volume_change": 0.3
    },
    "changed_by": "admin",
    "reason": "Longer time window for less noise"
  }' | jq
```

### Configuration Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/strategies` | List all strategies with config status |
| GET | `/api/v1/strategies/{id}/schema` | Get parameter schema |
| GET | `/api/v1/strategies/{id}/defaults` | Get default values |
| GET | `/api/v1/strategies/{id}/config` | Get global config |
| GET | `/api/v1/strategies/{id}/config/{symbol}` | Get symbol config |
| POST | `/api/v1/strategies/{id}/config` | Update global config |
| POST | `/api/v1/strategies/{id}/config/{symbol}` | Update symbol config |
| DELETE | `/api/v1/strategies/{id}/config` | Delete global config |
| DELETE | `/api/v1/strategies/{id}/config/{symbol}` | Delete symbol config |
| GET | `/api/v1/strategies/{id}/audit` | Get change history |
| POST | `/api/v1/strategies/cache/refresh` | Force cache refresh |

### Best Practices

1. **Always check schema first**:
   ```bash
   curl http://realtime-strategies:8080/api/v1/strategies/{id}/schema
   ```

2. **Validate before applying**:
   ```bash
   curl -X POST .../config -d '{"parameters": {...}, "validate_only": true}'
   ```

3. **Provide clear reasons**:
   ```json
   {"reason": "Adjusting buy_threshold from 1.2 to 1.3 because BTC showing higher liquidity"}
   ```

4. **Review audit trail**:
   ```bash
   curl http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/audit?limit=20
   ```

5. **Force cache refresh after updates**:
   ```bash
   curl -X POST http://realtime-strategies:8080/api/v1/strategies/cache/refresh
   ```

---

## Part 2: Market Metrics API

### Quick Start

```bash
# 1. Get depth metrics for a symbol
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq

# 2. Get pressure history (5-minute window)
curl "http://realtime-strategies:8080/api/v1/metrics/pressure/BTCUSDT?timeframe=5m" | jq

# 3. Get overall market summary
curl http://realtime-strategies:8080/api/v1/metrics/summary | jq

# 4. Get metrics for all tracked symbols
curl http://realtime-strategies:8080/api/v1/metrics/all | jq
```

### Market Metrics Explained

#### Depth Metrics Response

```json
{
  "symbol": "BTCUSDT",
  "timestamp": "2025-10-21T10:30:00Z",
  "imbalance": {
    "ratio": 0.15,           // -1 to 1: negative = more asks, positive = more bids
    "percent": 15.0,         // Imbalance as percentage
    "bid_volume": 125.5,     // Total bid volume
    "ask_volume": 95.3       // Total ask volume
  },
  "pressure": {
    "buy_pressure": 57.5,    // 0-100: percentage of total volume on bid side
    "sell_pressure": 42.5,   // 0-100: percentage of total volume on ask side
    "net_pressure": 15.0,    // -100 to 100: buy - sell
    "interpretation": "neutral"  // bullish (>20), bearish (<-20), or neutral
  },
  "liquidity": {
    "total": 220.8,          // Total liquidity (bid + ask volume)
    "bid_depth_5": 98.5,     // Volume at top 5 bid levels
    "ask_depth_5": 75.3,     // Volume at top 5 ask levels
    "bid_depth_10": 125.5,   // Volume at top 10 bid levels
    "ask_depth_10": 95.3     // Volume at top 10 ask levels
  },
  "spread": {
    "best_bid": 67450.0,
    "best_ask": 67465.0,
    "spread_abs": 15.0,      // Absolute spread
    "spread_bps": 2.22,      // Spread in basis points
    "mid_price": 67457.5
  },
  "vwap": {
    "bid": 67448.5,          // Volume-weighted average bid price
    "ask": 67468.2,          // Volume-weighted average ask price
    "spread": 19.7
  },
  "strongest_levels": {
    "bid": {"price": 67450.0, "volume": 2.5},  // Strongest support
    "ask": {"price": 67465.0, "volume": 1.8}   // Strongest resistance
  }
}
```

#### Pressure History Response

```json
{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "summary": {
    "avg_pressure": 18.5,      // Average net pressure over period
    "max_pressure": 45.2,      // Maximum pressure seen
    "min_pressure": -5.3,      // Minimum pressure seen
    "trend": "bullish",        // Overall trend direction
    "trend_strength": 0.75     // 0-1: how strong the trend is
  },
  "total_data_points": 300,
  "returned_data_points": 100,  // Limited to last 100 for response size
  "pressure_history": [
    {"timestamp": "2025-10-21T10:25:00Z", "pressure": 15.5},
    {"timestamp": "2025-10-21T10:26:00Z", "pressure": 18.2},
    // ... more data points
  ]
}
```

### Use Cases

#### Use Case 1: Monitor Market Sentiment

**Goal**: Check if market is showing buying or selling pressure

```bash
# Check current pressure for BTC
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq '.pressure'

# Response interpretation:
# net_pressure > 20: Strong buying pressure (bullish)
# net_pressure < -20: Strong selling pressure (bearish)
# net_pressure between -20 and 20: Neutral
```

#### Use Case 2: Detect Order Book Imbalance

**Goal**: Identify when one side of the order book is significantly larger

```bash
# Check imbalance
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq '.imbalance'

# Response interpretation:
# imbalance_percent > 30%: Significantly more bids (potential support)
# imbalance_percent < -30%: Significantly more asks (potential resistance)
```

#### Use Case 3: Monitor Liquidity Conditions

**Goal**: Check if there's enough liquidity for trading

```bash
# Check liquidity depth
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq '.liquidity'

# Key indicators:
# - total: Total available liquidity
# - bid_depth_5/ask_depth_5: How much volume at best prices
# - Low total liquidity = higher slippage risk
```

#### Use Case 4: Identify Support/Resistance

**Goal**: Find the strongest price levels in the order book

```bash
# Find strongest levels
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq '.strongest_levels'

# Response shows:
# - strongest_bid_level: Price with most buy orders (support)
# - strongest_ask_level: Price with most sell orders (resistance)
```

#### Use Case 5: Track Pressure Trends

**Goal**: See if buying/selling pressure is increasing or decreasing

```bash
# Get 5-minute pressure trend
curl "http://realtime-strategies:8080/api/v1/metrics/pressure/BTCUSDT?timeframe=5m" | jq

# Check the trend field:
# - "bullish": Sustained buying pressure
# - "bearish": Sustained selling pressure
# - "neutral": No clear trend
# 
# Check trend_strength (0-1):
# - > 0.7: Strong trend
# - 0.4-0.7: Moderate trend
# - < 0.4: Weak trend
```

#### Use Case 6: Overall Market Health

**Goal**: Get sentiment across all tracked symbols

```bash
# Market-wide summary
curl http://realtime-strategies:8080/api/v1/metrics/summary | jq

# Shows:
# - How many symbols are bullish/bearish/neutral
# - Average market pressure
# - Top symbols by pressure
# - Overall liquidity
```

#### Use Case 7: Dashboard Data Feed

**Goal**: Get all metrics for a trading dashboard

```bash
# All symbols metrics
curl http://realtime-strategies:8080/api/v1/metrics/all | jq

# Returns compact metrics for every tracked symbol
# Perfect for real-time dashboard updates
```

### Market Metrics Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/metrics/depth/{symbol}` | Current depth metrics for symbol |
| GET | `/api/v1/metrics/pressure/{symbol}?timeframe={1m\|5m\|15m}` | Pressure history |
| GET | `/api/v1/metrics/summary` | Overall market summary |
| GET | `/api/v1/metrics/all` | Metrics for all symbols |

---

## Combined Workflows

### Workflow 1: Optimize Strategy Based on Market Pressure

```bash
# 1. Check current market pressure for BTC
PRESSURE=$(curl -s http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq -r '.pressure.net_pressure')

# 2. If strong buying pressure, increase buy threshold
if [ "$PRESSURE" -gt 30 ]; then
  curl -X POST http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/config/BTCUSDT \
    -H "Content-Type: application/json" \
    -d '{
      "parameters": {"buy_threshold": 1.4},
      "changed_by": "auto_optimizer",
      "reason": "Strong buying pressure detected, increasing threshold to reduce false signals"
    }'
fi
```

### Workflow 2: Alert on Market Conditions

```bash
# Monitor overall market sentiment
SUMMARY=$(curl -s http://realtime-strategies:8080/api/v1/metrics/summary)

BULLISH=$(echo $SUMMARY | jq -r '.market_sentiment.bullish_symbols')
BEARISH=$(echo $SUMMARY | jq -r '.market_sentiment.bearish_symbols')

echo "Market Status: $BULLISH bullish, $BEARISH bearish symbols"

# Alert if market turns too bearish
if [ "$BEARISH" -gt 30 ]; then
  echo "⚠️  WARNING: High number of bearish symbols detected"
  # Could trigger risk reduction in TradeEngine
fi
```

### Workflow 3: Adaptive Configuration

```bash
# Check pressure trend for ETH
TREND=$(curl -s "http://realtime-strategies:8080/api/v1/metrics/pressure/ETHUSDT?timeframe=5m" | jq -r '.summary.trend')

# Adjust strategy based on trend
if [ "$TREND" == "bullish" ]; then
  # Optimize for uptrend
  curl -X POST http://realtime-strategies:8080/api/v1/strategies/ticker_velocity/config/ETHUSDT \
    -d '{"parameters": {"buy_threshold": 0.4}, "changed_by": "auto", "reason": "Bullish trend detected"}'
elif [ "$TREND" == "bearish" ]; then
  # Be more conservative
  curl -X POST http://realtime-strategies:8080/api/v1/strategies/ticker_velocity/config/ETHUSDT \
    -d '{"parameters": {"buy_threshold": 0.7}, "changed_by": "auto", "reason": "Bearish trend detected"}'
fi
```

---

## Configuration Hierarchy

### Priority Order

1. **Symbol-Specific Config** (MongoDB) - Highest priority
2. **Global Config** (MongoDB)
3. **Environment Variables** (ConfigMap) - Backward compatible
4. **Hardcoded Defaults** - Fallback

### Example

```
Environment: ORDERBOOK_SKEW_BUY_THRESHOLD=1.2
Global Config: buy_threshold=1.3
Symbol Config (BTCUSDT): buy_threshold=1.5

Result:
- BTCUSDT uses: 1.5 (symbol config wins)
- ETHUSDT uses: 1.3 (global config wins)
- If global deleted: Uses 1.2 (environment variable)
- If env not set: Uses default (1.2 from code)
```

---

## Deployment

### Local Testing

```bash
# Start service locally
cd /Users/yurisa2/petrosa/petrosa-realtime-strategies
python -m strategies.main run

# In another terminal, test APIs
curl http://localhost:8080/api/v1/strategies
curl http://localhost:8080/api/v1/metrics/summary
```

### Kubernetes Deployment

```bash
# Deploy updated version
cd /Users/yurisa2/petrosa/petrosa-realtime-strategies

# Build and push
make build
make push

# Deploy to cluster
kubectl apply -f k8s/deployment.yaml \
  --kubeconfig=k8s/kubeconfig.yaml \
  -n petrosa-apps

# Monitor rollout
kubectl rollout status deployment/petrosa-realtime-strategies \
  -n petrosa-apps \
  --kubeconfig=k8s/kubeconfig.yaml

# Check logs
kubectl logs -n petrosa-apps \
  -l app=realtime-strategies \
  --tail=50 | grep "Configuration manager initialized"
```

### Port Forwarding

```bash
# Forward service port
kubectl port-forward -n petrosa-apps \
  svc/petrosa-realtime-strategies 8080:8080 \
  --kubeconfig=k8s/kubeconfig.yaml &

# Test locally
curl http://localhost:8080/api/v1/strategies
curl http://localhost:8080/api/v1/metrics/depth/BTCUSDT
curl http://localhost:8080/docs  # Swagger UI

# Stop port forward
kill %1
```

---

## Monitoring

### Health Checks

```bash
# Service health
curl http://realtime-strategies:8080/healthz

# Service info (includes API links)
curl http://realtime-strategies:8080/info

# Prometheus metrics
curl http://realtime-strategies:8080/metrics
```

### Configuration Monitoring

```bash
# Check recent configuration changes
curl http://realtime-strategies:8080/api/v1/strategies/orderbook_skew/audit?limit=10

# View current config for all strategies
for strategy in orderbook_skew trade_momentum ticker_velocity btc_dominance; do
  echo "=== $strategy ==="
  curl -s http://realtime-strategies:8080/api/v1/strategies/$strategy/config | \
    jq '.data.parameters'
done
```

### Market Metrics Monitoring

```bash
# Monitor top pressure symbols
watch -n 5 'curl -s http://realtime-strategies:8080/api/v1/metrics/summary | jq .top_pressure_symbols'

# Track specific symbol pressure
watch -n 2 'curl -s http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq .pressure'

# Alert on extreme conditions
while true; do
  PRESSURE=$(curl -s http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT | jq -r '.pressure.net_pressure')
  if (( $(echo "$PRESSURE > 50" | bc -l) )); then
    echo "🚨 ALERT: Extreme buying pressure on BTC: $PRESSURE"
  fi
  sleep 10
done
```

---

## Troubleshooting

### Configuration Not Taking Effect

**Symptom**: Updated configuration but strategy still using old values

**Solution**:
```bash
# 1. Force cache refresh
curl -X POST http://realtime-strategies:8080/api/v1/strategies/cache/refresh

# 2. Check current config
curl http://realtime-strategies:8080/api/v1/strategies/{id}/config

# 3. Check logs for config updates
kubectl logs -n petrosa-apps -l app=realtime-strategies --tail=100 | grep "Config updated"

# 4. Wait 60 seconds (cache TTL)
```

### MongoDB Connection Failed

**Symptom**: Configuration updates return error

**Solution**:
```bash
# Service degrades gracefully to environment variables
# No action needed - check MongoDB status

# Verify MongoDB connection in logs
kubectl logs -n petrosa-apps -l app=realtime-strategies | grep MongoDB
```

### No Metrics for Symbol

**Symptom**: `/api/v1/metrics/depth/{symbol}` returns "No metrics available"

**Solution**:
```bash
# 1. Check if symbol is being consumed
curl http://realtime-strategies:8080/info | jq '.configuration.trading.symbols'

# 2. Check all tracked symbols
curl http://realtime-strategies:8080/api/v1/metrics/all | jq '.symbols_count'

# 3. Symbol might not have depth data yet - wait for WebSocket updates
```

### Validation Errors

**Symptom**: Parameter update rejected

**Solution**:
```bash
# 1. Check parameter schema
curl http://realtime-strategies:8080/api/v1/strategies/{id}/schema

# 2. Validate before submitting
curl -X POST .../config -d '{
  "parameters": {...},
  "validate_only": true,
  "changed_by": "test"
}'

# 3. Fix parameters to match schema constraints
```

---

## Performance Notes

### Configuration API
- **Cached responses**: < 100ms
- **Database queries**: < 500ms
- **Cache TTL**: 60 seconds
- **Updates take effect**: Within 60 seconds (or immediate with cache refresh)

### Market Metrics API
- **Response time**: < 50ms (in-memory)
- **Update frequency**: Real-time (as WebSocket data arrives)
- **History retention**: 15 minutes
- **Memory usage**: ~100MB for 100 symbols

---

## Security Notes

### Current Setup
- No authentication (internal cluster only)
- All endpoints accessible within cluster
- Audit trail tracks all changes

### Production Recommendations
- Add API key authentication
- Implement role-based access control
- Rate limiting on write endpoints
- Alert on suspicious configuration changes

---

## API Documentation

### Swagger UI

Interactive API documentation with:
- Complete endpoint list
- Request/response schemas
- Try-it-out functionality
- Example requests

**Access**: `http://realtime-strategies:8080/docs`

### OpenAPI Spec

Download the OpenAPI specification:

```bash
curl http://realtime-strategies:8080/openapi.json > openapi.json
```

---

## Examples

### Python Client Example

```python
import requests

# Configuration API
def update_strategy_config(strategy_id, params, changed_by, reason=""):
    """Update strategy configuration."""
    response = requests.post(
        f"http://realtime-strategies:8080/api/v1/strategies/{strategy_id}/config",
        json={
            "parameters": params,
            "changed_by": changed_by,
            "reason": reason
        }
    )
    return response.json()

# Market Metrics API
def get_market_pressure(symbol):
    """Get current market pressure for a symbol."""
    response = requests.get(
        f"http://realtime-strategies:8080/api/v1/metrics/depth/{symbol}"
    )
    data = response.json()
    return data["pressure"]["net_pressure"]

# Example usage
pressure = get_market_pressure("BTCUSDT")
if pressure > 30:
    print(f"Strong buying pressure: {pressure}")
    update_strategy_config(
        "orderbook_skew",
        {"buy_threshold": 1.4},
        "auto_optimizer",
        f"Increasing threshold due to high pressure: {pressure}"
    )
```

### Shell Script Example

```bash
#!/bin/bash
# Auto-adjust strategy based on market conditions

API_BASE="http://realtime-strategies:8080/api/v1"

# Get market summary
SUMMARY=$(curl -s $API_BASE/metrics/summary)
AVG_PRESSURE=$(echo $SUMMARY | jq -r '.market_sentiment.avg_net_pressure')

echo "Average market pressure: $AVG_PRESSURE"

# Adjust global strategy settings
if (( $(echo "$AVG_PRESSURE > 25" | bc -l) )); then
  echo "Bullish market detected - adjusting strategies"
  
  curl -X POST $API_BASE/strategies/orderbook_skew/config \
    -H "Content-Type: application/json" \
    -d '{
      "parameters": {"buy_threshold": 1.4, "sell_threshold": 0.8},
      "changed_by": "auto_script",
      "reason": "Bullish market conditions"
    }'
elif (( $(echo "$AVG_PRESSURE < -25" | bc -l) )); then
  echo "Bearish market detected - adjusting strategies"
  
  curl -X POST $API_BASE/strategies/orderbook_skew/config \
    -H "Content-Type: application/json" \
    -d '{
      "parameters": {"buy_threshold": 1.1, "sell_threshold": 0.7},
      "changed_by": "auto_script",
      "reason": "Bearish market conditions"
    }'
fi
```

---

## Next Steps

1. **Deploy to production** - Follow deployment guide
2. **Test APIs** - Verify all endpoints work
3. **Monitor metrics** - Watch market pressure indicators
4. **Optimize strategies** - Use market metrics to inform configuration changes
5. **Build dashboards** - Visualize market pressure and imbalances

---

## Support

- **Swagger UI**: http://realtime-strategies:8080/docs
- **Implementation Plan**: `docs/API_CONFIGURATION_IMPLEMENTATION_PLAN_V2.md`
- **Quick Reference**: `/Users/yurisa2/petrosa/CONFIGURATION_API_QUICK_REFERENCE.md`

---

**Happy Trading! 🚀**

