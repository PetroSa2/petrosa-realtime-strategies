# Microstructure Trading Strategies

**Advanced order book analysis strategies for futures trading**

This document covers two quantitative strategies that exploit market microstructure inefficiencies:
1. **Spread Liquidity Strategy** - Detects liquidity events through spread analysis
2. **Iceberg Detector Strategy** - Identifies large hidden institutional orders

---

## Table of Contents

- [Overview](#overview)
- [Strategy 1: Spread Liquidity](#strategy-1-spread-liquidity)
- [Strategy 2: Iceberg Detector](#strategy-2-iceberg-detector)
- [Configuration](#configuration)
- [Deployment](#deployment)
- [Monitoring](#monitoring)
- [Performance Metrics](#performance-metrics)
- [Troubleshooting](#troubleshooting)

---

## Overview

### What are Microstructure Strategies?

Market microstructure strategies analyze the **mechanics of order execution** and **price formation** at the order book level. Unlike technical analysis (which uses price/volume history), these strategies detect:

- **Liquidity events**: When smart money enters/exits
- **Hidden orders**: Large institutional positions
- **Information asymmetry**: Who knows what, when
- **Market quality**: Spread, depth, and resilience

### Why They Work in Crypto Futures

1. **High Leverage** → Amplifies liquidity needs → More iceberg orders
2. **24/7 Markets** → More liquidity events (funding, liquidations)
3. **Transparent Order Books** → We can see depth changes in real-time
4. **Retail-Heavy** → Institutions hide size to avoid front-running
5. **Lower Latency Requirements** → Strategies work on 100ms data updates

### Integration with Existing System

Both strategies integrate seamlessly into `petrosa-realtime-strategies`:

```
Binance WebSocket (@depth20@100ms)
    ↓
Socket Client (publishes to NATS)
    ↓
Realtime Strategies Consumer
    ├─ Spread Liquidity Strategy ← NEW
    ├─ Iceberg Detector Strategy  ← NEW
    ├─ Order Book Skew
    ├─ Trade Momentum
    └─ Ticker Velocity
    ↓
NATS intent.trading.* (CIO intercepted)
    ↓
Trade Engine (executes orders)
```

**Key Features:**
- ✅ **Single-asset** (no cross-dependencies)
- ✅ **Pure quantitative** (no news/sentiment)
- ✅ **Real-time** (100ms order book updates)
- ✅ **Low overhead** (~100 KB + 60 MB memory)
- ✅ **Configuration API** (runtime parameter tuning)

---

## Strategy 1: Spread Liquidity

### Overview

**Strategy Type:** Liquidity Event Detection  
**Timeframe:** Real-time (tick-by-tick)  
**Signal Frequency:** 5-10 per symbol per day  
**Win Rate Target:** 55-65%  
**Average Hold Time:** 5-15 minutes  

### Theoretical Foundation

The **bid-ask spread** is the market's "price of liquidity." Changes in spread reveal:

**Academic Basis:**
- **Kyle (1985):** Spread reflects informed trading probability
- **Glosten & Milgrom (1985):** Spread compensates for adverse selection
- **O'Hara (1995):** Microstructure signals precede price moves

**Key Insight:** When smart money withdraws liquidity, spreads widen. When they return, spreads normalize. We can profit from these transitions.

### Signal Logic

#### BUY Signal: Spread Normalization

**Conditions:**
```python
spread_bps > 10.0                  # Wide spread (>10 basis points)
spread_ratio > 2.5                 # 2.5x normal spread
spread_velocity < -0.5             # Rapidly narrowing (-50%)
persistence_seconds > 30           # Was wide for 30+ seconds
```

**Reasoning:** Liquidity is returning after withdrawal. Price likely to stabilize or rise.

**Example:**
```
t=0s:   Spread = 2 bps (normal)
t=30s:  Spread = 25 bps (5x normal, liquidation cascade)
t=60s:  Spread = 15 bps (narrowing)
t=90s:  Spread = 5 bps (normalizing) → BUY SIGNAL
```

#### SELL Signal: Liquidity Withdrawal

**Conditions:**
```python
spread_bps < 3.0 AND spread_velocity > 1.0  # Rapid widening from tight
spread_ratio > 3.0                           # 3x normal
order_book_depth_top5 < avg_depth * 0.5     # 50% depth reduction
```

**Reasoning:** Smart money is exiting. Volatility incoming.

**Example:**
```
t=0s:   Spread = 1 bps, Depth = $500k (normal)
t=10s:  Spread = 8 bps, Depth = $200k (widening + depth drop)
t=20s:  Spread = 12 bps → SELL SIGNAL
```

### Mathematical Model

#### Spread Metrics

```python
# 1. Absolute Spread (basis points)
spread_bps = ((best_ask - best_bid) / mid_price) * 10000

# 2. Relative Spread (vs historical average)
spread_ratio = current_spread / avg_spread_20_ticks

# 3. Spread Velocity (rate of change)
spread_velocity = (spread_now - spread_1min_ago) / spread_1min_ago

# 4. Spread Persistence (time above threshold)
persistence_seconds = time_since_spread_above_threshold
```

#### Confidence Calculation

```python
confidence = base_confidence  # 0.70

# Narrowing signals
if event_type == "narrowing":
    confidence += (spread_ratio - 2.5) * 0.05  # Higher ratio = stronger
    confidence += min(0.10, persistence / 300.0 * 0.10)  # Longer persistence

# Widening signals
elif event_type == "widening":
    confidence += abs(spread_velocity) * 0.10  # Faster widening
    confidence += depth_reduction_pct * 0.15   # More depth loss

confidence = min(0.95, confidence)  # Cap at 95%
```

### Risk Management

```python
# Stop Loss: Tight (spread events are quick)
stop_loss_pct = 0.5  # 0.5%

# Take Profit: Quick scalp
take_profit_pct = 1.0  # 1.0%

# Time Stop: Very short
max_hold_seconds = 300  # 5 minutes
```

### Configuration Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `spread_threshold_bps` | 10.0 | 1.0 - 100.0 | Minimum spread in bps to consider |
| `spread_ratio_threshold` | 2.5 | 1.5 - 10.0 | Spread ratio threshold (current/avg) |
| `velocity_threshold` | 0.5 | 0.1 - 2.0 | Minimum spread velocity (% per second) |
| `persistence_threshold_seconds` | 30.0 | 10.0 - 300.0 | Minimum persistence time |
| `min_depth_reduction_pct` | 0.5 | 0.1 - 0.9 | Minimum depth reduction |
| `base_confidence` | 0.70 | 0.5 - 1.0 | Base confidence level |
| `lookback_ticks` | 20 | 5 - 100 | Rolling average window |
| `min_signal_interval_seconds` | 60.0 | 30.0 - 600.0 | Rate limiting |

### Usage Example

**Update configuration:**
```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/spread_liquidity/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "spread_threshold_bps": 12.0,
      "spread_ratio_threshold": 3.0
    },
    "changed_by": "admin",
    "reason": "Increasing sensitivity for current volatility"
  }'
```

**Monitor signals:**
```bash
# Check recent spread events
kubectl logs -n petrosa-apps -l app=realtime-strategies --tail=100 | grep "spread_liquidity"
```

---

## Strategy 2: Iceberg Detector

### Overview

**Strategy Type:** Hidden Order Detection  
**Timeframe:** Real-time (tick-by-tick)  
**Signal Frequency:** 2-5 per symbol per day  
**Win Rate Target:** 60-70%  
**Average Hold Time:** 10-30 minutes  

### Theoretical Foundation

**Iceberg orders** are large institutional orders split into small visible portions. The "iceberg" analogy: small tip visible, large mass hidden.

**Why Institutions Use Icebergs:**
1. **Avoid front-running:** Hide size from other traders
2. **Reduce slippage:** Don't move market with one large order
3. **Maintain flexibility:** Can cancel hidden portion

**Our Edge:** We detect the pattern through:
- **Repeated refills:** Volume depletes then restores quickly
- **Consistent sizing:** Similar volumes repeatedly appear
- **Price anchoring:** Level persists despite market movement

### Detection Patterns

#### Pattern 1: Repeated Refills (Strongest Signal)

**Logic:** If order book level repeatedly depletes and refills quickly, it's likely a hidden order refreshing.

**Detection:**
```python
# Track volume at price level
t=0s:  Level 50000.00 has 2.0 BTC
t=5s:  Level 50000.00 has 0.2 BTC (depleted by takers)
t=8s:  Level 50000.00 has 2.0 BTC (refilled in <5s) ← REFILL 1

t=15s: Level 50000.00 has 0.3 BTC (depleted again)
t=18s: Level 50000.00 has 2.0 BTC (refilled) ← REFILL 2

t=25s: Level 50000.00 has 0.1 BTC (depleted)
t=28s: Level 50000.00 has 2.0 BTC (refilled) ← REFILL 3

# After 3+ refills in <5s each → ICEBERG DETECTED
confidence = 0.65 + (refill_count - 3) * 0.05
```

#### Pattern 2: Consistent Sizing

**Logic:** If volumes at a level have low variance, it's likely automated order placement.

**Detection:**
```python
# Track volume standard deviation
volumes_at_level = [2.0, 2.0, 1.9, 2.0, 2.1, 2.0, 2.0]
avg_volume = 2.0
std_dev = 0.07
coefficient_of_variation = 0.07 / 2.0 = 0.035

if cv < 0.1:  # Low variance
    consistent_volume = True
    confidence = 0.70
```

#### Pattern 3: Price Anchoring

**Logic:** If a level persists for 2+ minutes despite market movement, it's a sticky level (likely large order).

**Detection:**
```python
# Track level persistence
first_seen = t=0s
last_seen = t=180s
persistence = 180s

if persistence > 120s:  # 2+ minutes
    pattern = "anchor"
    confidence = 0.75
```

### Signal Logic

#### BUY Signal: Iceberg Bid (Support)

**Conditions:**
```python
iceberg_detected_on_bid_side = True
price_within_1pct_of_iceberg_level = True
refill_count >= 3
current_price > iceberg_price * 0.999  # Near support
```

**Reasoning:** Large hidden buyer providing support. Price likely to bounce off this level.

**Example:**
```
Iceberg detected at 50,000 (bid side)
Current price: 50,050 (within 1%)
Price dips to 50,010 → BUY SIGNAL
Stop loss: 49,950 (below iceberg)
Take profit: 50,200
```

#### SELL Signal: Iceberg Ask (Resistance)

**Conditions:**
```python
iceberg_detected_on_ask_side = True
price_within_1pct_of_iceberg_level = True
refill_count >= 3
current_price < iceberg_price * 1.001  # Near resistance
```

**Reasoning:** Large hidden seller capping upside. Price likely to reject at this level.

### Mathematical Model

#### Refill Detection

```python
def is_refill(history, current_qty):
    if len(history) < 3:
        return False
    
    recent = history[-3:]
    vol_0, vol_1, vol_2 = recent[0].quantity, recent[1].quantity, recent[2].quantity
    
    # Volume dropped >50% then restored >80%
    if vol_1 < vol_0 * 0.5 and vol_2 > vol_0 * 0.8:
        # Check speed (fast refill)
        time_elapsed = recent[2].timestamp - recent[0].timestamp
        if time_elapsed < 5.0:  # seconds
            return True
    
    return False
```

#### Confidence Calculation

```python
# Refill pattern
if pattern_type == "refill":
    confidence = 0.65 + (refill_count - 3) * 0.05
    confidence = min(0.85, confidence)

# Consistency pattern
elif pattern_type == "consistent_size":
    volume_consistency_score = 1.0 - (std_dev / avg_volume)
    confidence = 0.70 * volume_consistency_score

# Anchoring pattern
elif pattern_type == "anchor":
    confidence = 0.75 + (persistence_seconds / 600.0) * 0.10
    confidence = min(0.85, confidence)
```

### Risk Management

```python
# Stop Loss: Tight (protect below/above iceberg level)
atr_proxy = max(distance_to_level, current_price * 0.005)

if action == "buy":
    stop_loss = iceberg_price - atr_proxy
    take_profit = current_price + (atr_proxy * 2.5)
else:  # sell
    stop_loss = iceberg_price + atr_proxy
    take_profit = current_price - (atr_proxy * 2.5)
```

### Configuration Parameters

| Parameter | Default | Range | Description |
|-----------|---------|-------|-------------|
| `min_refill_count` | 3 | 2 - 10 | Minimum refills to detect iceberg |
| `refill_speed_threshold_seconds` | 5.0 | 1.0 - 30.0 | Max refill time for fast refill |
| `consistency_threshold` | 0.1 | 0.05 - 0.5 | Max std dev ratio for consistency |
| `persistence_threshold_seconds` | 120.0 | 60.0 - 600.0 | Min persistence for anchoring |
| `level_proximity_pct` | 1.0 | 0.1 - 5.0 | Signal only if within X% of iceberg |
| `base_confidence` | 0.70 | 0.5 - 1.0 | Base confidence level |
| `history_window_seconds` | 300 | 60 - 900 | Order book history window (5min) |
| `max_symbols` | 100 | 10 - 200 | Max symbols to track |
| `min_signal_interval_seconds` | 120.0 | 60.0 - 600.0 | Rate limiting |

### Usage Example

**Update configuration:**
```bash
curl -X POST http://realtime-strategies:8080/api/v1/strategies/iceberg_detector/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "min_refill_count": 4,
      "level_proximity_pct": 0.5
    },
    "changed_by": "admin",
    "reason": "Increasing detection threshold and tightening proximity"
  }'
```

**Monitor icebergs:**
```bash
# Check detected icebergs
kubectl logs -n petrosa-apps -l app=realtime-strategies --tail=100 | grep "Iceberg detected"
```

---

## Configuration

### Runtime Configuration via API

Both strategies support runtime configuration through the Configuration API:

**List available strategies:**
```bash
GET /api/v1/strategies
```

**Get current config:**
```bash
GET /api/v1/strategies/spread_liquidity/config
GET /api/v1/strategies/iceberg_detector/config
```

**Update configuration:**
```bash
POST /api/v1/strategies/{strategy_id}/config
```

**View change history:**
```bash
GET /api/v1/strategies/{strategy_id}/audit
```

### Configuration Inheritance

**Global Defaults** → **Symbol Overrides**

```python
# Global (all symbols)
spread_liquidity:
  spread_threshold_bps: 10.0

# Symbol override (BTCUSDT only)
BTCUSDT:
  spread_threshold_bps: 12.0  # Higher threshold for BTC
```

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STRATEGY_ENABLED_SPREAD_LIQUIDITY` | `true` | Enable spread strategy |
| `STRATEGY_ENABLED_ICEBERG_DETECTOR` | `true` | Enable iceberg strategy |
| `CONFIG_CACHE_TTL_SECONDS` | `60` | Configuration cache TTL |

---

## Deployment

### Kubernetes Integration

Both strategies are automatically deployed as part of `petrosa-realtime-strategies`:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: petrosa-realtime-strategies
  namespace: petrosa-apps
spec:
  replicas: 3
  template:
    spec:
      containers:
      - name: realtime-strategies
        image: yurisa2/petrosa-realtime-strategies:VERSION_PLACEHOLDER
        env:
        - name: STRATEGY_ENABLED_SPREAD_LIQUIDITY
          value: "true"
        - name: STRATEGY_ENABLED_ICEBERG_DETECTOR
          value: "true"
```

**Deploy:**
```bash
cd /Users/yurisa2/petrosa/petrosa-realtime-strategies
make deploy
```

**Check status:**
```bash
kubectl get pods -n petrosa-apps -l app=realtime-strategies
kubectl logs -n petrosa-apps -l app=realtime-strategies --tail=100
```

### Gradual Rollout (Recommended)

**Phase 1:** Confidence-based deployment
```python
# Week 1: Only high-confidence signals (≥0.80)
# Week 2: Medium confidence (≥0.75)
# Week 3: Normal confidence (≥0.70)
# Week 4: Full deployment
```

**Phase 2:** Position sizing
```python
# Week 1: 25% of normal size
# Week 2: 50% of normal size
# Week 3: 75% of normal size
# Week 4: 100% (full size)
```

---

## Monitoring

### Key Metrics

**Spread Liquidity:**
- Signal frequency: 5-10 per symbol per day
- Win rate: Target 55-65%
- Average spread widening events per day
- Spread normalization events per day

**Iceberg Detector:**
- Signal frequency: 2-5 per symbol per day
- Win rate: Target 60-70%
- Icebergs detected per day
- Refill patterns vs consistency vs anchoring

### Logging

**Spread signals:**
```
INFO: Spread signal generated: BUY
  symbol=BTCUSDT
  event_type=narrowing
  confidence=0.75
  spread_bps=15.2
  spread_ratio=3.1
```

**Iceberg detections:**
```
INFO: Iceberg signal generated: BUY
  symbol=BTCUSDT
  iceberg_price=50000.00
  current_price=50050.00
  pattern_type=refill
  confidence=0.80
  refill_count=5
```

### Health Checks

```bash
# Check strategy statistics
curl http://realtime-strategies:8080/health

# View market depth metrics
curl http://realtime-strategies:8080/api/v1/metrics/depth/BTCUSDT

# Check spread trends
curl http://realtime-strategies:8080/api/v1/metrics/pressure/BTCUSDT
```

---

## Performance Metrics

### Expected Performance

| Metric | Spread Liquidity | Iceberg Detector |
|--------|------------------|------------------|
| Signal Frequency | 5-10/day | 2-5/day |
| Win Rate | 55-65% | 60-70% |
| Average Hold Time | 5-15 min | 10-30 min |
| Profit Factor | 1.5+ | 1.8+ |
| Max Drawdown | <3% | <2% |
| Sharpe Ratio | 1.2+ | 1.5+ |

### Success Criteria

**Week 1 (Paper Trading):**
- ✅ Signal generation working
- ✅ No critical errors
- ✅ Reasonable signal frequency

**Week 2-4 (Live with 25% sizing):**
- ✅ Win rate ≥50%
- ✅ Profit factor ≥1.2
- ✅ Max drawdown <5%

**Week 5+ (Full deployment):**
- ✅ Win rate ≥55% (spread) / ≥60% (iceberg)
- ✅ Profit factor ≥1.5 (spread) / ≥1.8 (iceberg)
- ✅ Positive P&L over 30 days

---

## Troubleshooting

### Common Issues

**1. No Signals Generated**

**Cause:** Thresholds too strict or insufficient market volatility

**Solution:**
```bash
# Lower thresholds
curl -X POST .../spread_liquidity/config -d '{
  "parameters": {"spread_ratio_threshold": 2.0}
}'

# Check market conditions
curl .../metrics/depth/BTCUSDT
```

**2. Too Many Signals (False Positives)**

**Cause:** Thresholds too loose

**Solution:**
```bash
# Increase thresholds
curl -X POST .../iceberg_detector/config -d '{
  "parameters": {"min_refill_count": 4}
}'
```

**3. High Memory Usage**

**Cause:** Tracking too many symbols or long history window

**Solution:**
```bash
# Reduce history window
curl -X POST .../iceberg_detector/config -d '{
  "parameters": {"history_window_seconds": 180}
}'
```

**4. Signals Rate Limited**

**Cause:** `min_signal_interval_seconds` too high

**Solution:**
```bash
# Reduce interval
curl -X POST .../spread_liquidity/config -d '{
  "parameters": {"min_signal_interval_seconds": 30.0}
}'
```

### Diagnostic Commands

```bash
# Check strategy status
kubectl logs -n petrosa-apps deployment/petrosa-realtime-strategies | grep -E "spread_liquidity|iceberg_detector"

# View recent signals
kubectl logs -n petrosa-apps deployment/petrosa-realtime-strategies --tail=1000 | grep "signal generated"

# Check configuration
curl http://realtime-strategies:8080/api/v1/strategies

# View audit trail
curl http://realtime-strategies:8080/api/v1/strategies/spread_liquidity/audit?limit=50
```

---

## Best Practices

### Parameter Tuning

1. **Start conservative:** Use higher thresholds initially
2. **Monitor for 7 days:** Collect data before adjusting
3. **One parameter at a time:** Don't change multiple params simultaneously
4. **Document changes:** Always provide reason in API calls
5. **A/B test:** Use symbol overrides to test on subset

### Risk Management

1. **Position sizing:** Start at 25% of normal size
2. **Tight stops:** These are scalping strategies
3. **Time stops:** Exit if signal doesn't play out quickly
4. **Correlation monitoring:** Watch for signal overlap with other strategies

### Continuous Improvement

1. **Monthly reviews:** Analyze false positives/negatives
2. **Quarterly enhancements:** Consider ML-based pattern recognition
3. **Market regime adaptation:** Adjust parameters for bull/bear markets
4. **Backtesting:** Test parameter changes on historical data first

---

## References

### Academic Papers

1. Kyle, A. S. (1985). "Continuous Auctions and Insider Trading"
2. Glosten, L. R., & Milgrom, P. R. (1985). "Bid, Ask and Transaction Prices"
3. O'Hara, M. (1995). "Market Microstructure Theory"

### Implementation Notes

- Spread metrics calculation: `strategies/models/spread_metrics.py`
- Order book tracking: `strategies/models/orderbook_tracker.py`
- Strategy implementations: `strategies/market_logic/`
- Tests: `tests/test_spread_liquidity.py`, `tests/test_iceberg_detector.py`

---

**Version:** 1.0  
**Last Updated:** October 2025  
**Author:** Petrosa Systems  
**Contact:** See project README for support channels

