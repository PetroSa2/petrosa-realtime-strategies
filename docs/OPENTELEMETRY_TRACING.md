# OpenTelemetry Manual Span Creation Guidelines

## Overview

This document provides guidelines for adding manual OpenTelemetry spans to business logic in the `petrosa-realtime-strategies` service. Manual spans provide fine-grained observability into key business operations, enabling better performance monitoring, debugging, and latency analysis.

## When to Add Manual Spans

Add manual spans for:

1. **Signal Generation Algorithms**: Core logic that generates trading signals
2. **Risk Management Calculations**: Stop-loss, take-profit, and position sizing calculations
3. **Data Processing Operations**: Complex data transformations or aggregations
4. **External API Calls**: Fetching external data (e.g., exchange prices, on-chain metrics)
5. **Business Logic Decisions**: Critical decision points that affect trading behavior

**Do NOT add spans for:**
- Simple getters/setters
- Logging operations
- Basic data validation
- Trivial calculations

## Implementation Pattern

### 1. Import OpenTelemetry Tracer

At the module level:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)
```

### 2. Wrap Business Logic with Spans

Use context managers for automatic span lifecycle management:

```python
def analyze(self, symbol: str, bids: list, asks: list) -> Optional[Signal]:
    with tracer.start_as_current_span("strategy_name.operation_name") as span:
        # Set attributes at the start
        span.set_attribute("symbol", symbol)
        span.set_attribute("bids_count", len(bids))
        span.set_attribute("asks_count", len(asks))
        
        # Business logic here
        result = self._calculate_metrics(bids, asks)
        
        # Set result attributes
        if result:
            span.set_attribute("result", "success")
            span.set_attribute("signal_generated", True)
        else:
            span.set_attribute("result", "no_signal")
            span.set_attribute("signal_generated", False)
        
        return result
```

### 3. Nested Spans for Complex Operations

For complex operations with multiple steps, use nested spans:

```python
def _generate_signal(self, event: SpreadEvent, snapshot: SpreadSnapshot) -> Optional[Signal]:
    with tracer.start_as_current_span("spread_liquidity.generate_signal") as span:
        span.set_attribute("symbol", event.symbol)
        span.set_attribute("event_type", event.event_type)
        
        # Nested span for risk management
        with tracer.start_as_current_span("spread_liquidity.calculate_risk_management") as risk_span:
            risk_span.set_attribute("symbol", event.symbol)
            risk_span.set_attribute("mid_price", metrics.mid_price)
            
            # Risk calculation logic
            stop_loss = calculate_stop_loss(metrics.mid_price)
            take_profit = calculate_take_profit(metrics.mid_price)
            
            risk_span.set_attribute("stop_loss", stop_loss)
            risk_span.set_attribute("take_profit", take_profit)
            risk_span.set_attribute("risk_reward_ratio", calculate_rr_ratio(stop_loss, take_profit))
        
        # Continue with signal creation
        signal = Signal(...)
        span.set_attribute("signal_generated", True)
        return signal
```

## Span Naming Conventions

### Format

Use dot-separated hierarchical names: `{module}.{operation}`

**Examples:**
- `spread_liquidity.analyze` - Main analysis operation
- `spread_liquidity.calculate_confidence` - Sub-operation
- `spread_liquidity.generate_signal` - Signal generation
- `consumer.signal_to_order` - Signal conversion
- `consumer.calculate_risk_management` - Risk calculation

### Guidelines

1. **Use lowercase with underscores**: `spread_liquidity.analyze` (not `SpreadLiquidity.Analyze`)
2. **Be descriptive**: `calculate_risk_management` (not `calc_risk`)
3. **Keep it concise**: Maximum 3-4 levels deep
4. **Match module structure**: Reflect the actual code organization

## Span Attributes

### Required Attributes

Always include:
- `symbol`: Trading symbol (e.g., "BTCUSDT")
- `result`: Operation outcome ("success", "no_signal", "rate_limited", "error")

### Recommended Attributes

Include relevant context:
- **Input parameters**: `bids_count`, `asks_count`, `current_price`
- **Calculated values**: `spread_bps`, `confidence_score`, `stop_loss`, `take_profit`
- **Decision points**: `signal_generated`, `event_detected`, `threshold_exceeded`
- **Performance metrics**: `processing_time_ms`, `data_points_processed`

### Attribute Naming

- Use **snake_case**: `confidence_score` (not `confidenceScore`)
- Be **descriptive**: `spread_bps` (not `spread`)
- Include **units** when relevant: `spread_bps`, `price_usdt`, `volume_btc`

## Error Handling

Always set error attributes when exceptions occur:

```python
def analyze(self, symbol: str, data: dict) -> Optional[Signal]:
    with tracer.start_as_current_span("strategy.analyze") as span:
        span.set_attribute("symbol", symbol)
        
        try:
            result = self._process_data(data)
            span.set_attribute("result", "success")
            return result
        except ValueError as e:
            span.set_attribute("result", "error")
            span.set_attribute("error_type", "ValueError")
            span.set_attribute("error_message", str(e))
            span.record_exception(e)
            raise
        except Exception as e:
            span.set_attribute("result", "error")
            span.set_attribute("error_type", type(e).__name__)
            span.set_attribute("error_message", str(e))
            span.record_exception(e)
            raise
```

## Examples from Codebase

### Example 1: Signal Generation

```python
# strategies/market_logic/spread_liquidity.py
def analyze(
    self,
    symbol: str,
    bids: list[tuple[float, float]],
    asks: list[tuple[float, float]],
    timestamp: Optional[datetime] = None,
) -> Optional[Signal]:
    with tracer.start_as_current_span("spread_liquidity.analyze") as span:
        span.set_attribute("symbol", symbol)
        span.set_attribute("bids_count", len(bids))
        span.set_attribute("asks_count", len(asks))
        
        # Calculate metrics
        metrics = self._calculate_spread_metrics(symbol, bids, asks, timestamp)
        if not metrics:
            span.set_attribute("result", "no_metrics")
            return None
        
        # Detect event
        event = self._detect_event(symbol, snapshot, timestamp)
        if event:
            span.set_attribute("event_detected", event.event_type)
            signal = self._generate_signal(event, snapshot)
            if signal:
                span.set_attribute("result", "signal_generated")
                span.set_attribute("signal_type", signal.signal_type.value)
                span.set_attribute("confidence_score", signal.confidence_score)
                return signal
        
        span.set_attribute("result", "no_signal")
        return None
```

### Example 2: Risk Management

```python
# strategies/core/consumer.py
def _signal_to_order(self, signal) -> dict[str, Any]:
    with tracer.start_as_current_span("consumer.signal_to_order") as span:
        span.set_attribute("symbol", signal.symbol)
        span.set_attribute("signal_type", signal.signal_type.value)
        span.set_attribute("strategy_name", signal.strategy_name)
        
        # Map signal action
        action = "buy" if signal.signal_action == "OPEN_LONG" else "sell"
        span.set_attribute("action", action)
        
        # Calculate risk management with nested span
        with tracer.start_as_current_span("consumer.calculate_risk_management") as risk_span:
            risk_span.set_attribute("symbol", signal.symbol)
            risk_span.set_attribute("action", action)
            risk_span.set_attribute("current_price", current_price)
            
            # Calculate stop-loss and take-profit
            if action == "buy":
                stop_loss = current_price * (1 - stop_loss_pct)
                take_profit = current_price * (1 + take_profit_pct)
            else:
                stop_loss = current_price * (1 + stop_loss_pct)
                take_profit = current_price * (1 - take_profit_pct)
            
            risk_span.set_attribute("stop_loss", stop_loss)
            risk_span.set_attribute("take_profit", take_profit)
            risk_span.set_attribute("risk_reward_ratio", calculate_rr_ratio(stop_loss, take_profit, current_price, action))
        
        # Create order
        order = {
            "symbol": signal.symbol,
            "action": action,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            # ... other fields
        }
        
        span.set_attribute("order_created", True)
        return order
```

### Example 3: External Data Fetching

```python
# strategies/market_logic/cross_exchange_spread.py
async def _fetch_exchange_price(
    self, session: aiohttp.ClientSession, exchange: str
) -> None:
    with tracer.start_as_current_span(f"cross_exchange_spread.fetch_price.{exchange}") as span:
        span.set_attribute("exchange", exchange)
        
        try:
            # Fetch price from external exchange
            async with session.get(f"https://{exchange}.com/api/ticker") as response:
                if response.status == 200:
                    data = await response.json()
                    price = data["price"]
                    span.set_attribute("price_fetched", price)
                    span.set_attribute("result", "success")
                    self.exchange_prices[exchange] = {"price": price, "timestamp": datetime.utcnow()}
                else:
                    span.set_attribute("result", "error")
                    span.set_attribute("http_status", response.status)
        except Exception as e:
            span.set_attribute("result", "error")
            span.set_attribute("error_type", type(e).__name__)
            span.set_attribute("error_message", str(e))
            span.record_exception(e)
```

## Verification in Grafana

After adding spans, verify they appear in Grafana:

1. **Navigate to Grafana**: Open the traces explorer
2. **Filter by service**: `service.name = "petrosa-realtime-strategies"`
3. **Search for span names**: Use the span name (e.g., `spread_liquidity.analyze`)
4. **Check attributes**: Verify all expected attributes are present
5. **Analyze latency**: Review span duration to identify performance bottlenecks

### Expected Spans

The following spans should be visible in Grafana:

**Signal Generation:**
- `spread_liquidity.analyze`
- `spread_liquidity.calculate_confidence`
- `spread_liquidity.generate_signal`
- `strategy.btc_dominance.process`
- `btc_dominance.generate_signal`
- `cross_exchange_spread.process_market_data`
- `cross_exchange_spread.generate_spread_signals`
- `onchain_metrics.process_market_data`
- `onchain_metrics.analyze_metrics`

**Risk Management:**
- `consumer.signal_to_order`
- `spread_liquidity.calculate_risk_management`

**External Operations:**
- `onchain_metrics.fetch_metrics`

## Best Practices

1. **Keep spans focused**: One span per logical operation
2. **Set attributes early**: Add input attributes at span start
3. **Set result attributes**: Always indicate operation outcome
4. **Use nested spans**: For complex multi-step operations
5. **Record exceptions**: Use `span.record_exception()` for errors
6. **Avoid over-instrumentation**: Don't add spans to trivial operations
7. **Test span visibility**: Verify spans appear in Grafana after deployment

## Performance Considerations

- **Span overhead**: Minimal (~1-5ms per span)
- **Attribute limits**: Keep attributes under 100 per span
- **Nested span depth**: Limit to 3-4 levels maximum
- **Async operations**: Spans work seamlessly with async/await

## Troubleshooting

**Spans not appearing in Grafana?**
1. Check OpenTelemetry exporter configuration
2. Verify `OTEL_EXPORTER_OTLP_ENDPOINT` is set correctly
3. Check service name matches: `service.name = "petrosa-realtime-strategies"`
4. Review OpenTelemetry logs for export errors

**Missing attributes?**
1. Verify `span.set_attribute()` calls are executed
2. Check attribute values are not None (None values are not exported)
3. Ensure attributes are set before span ends

**High span overhead?**
1. Review span count per operation
2. Consider reducing nested span depth
3. Remove spans from hot paths if needed

## References

- [OpenTelemetry Python Documentation](https://opentelemetry.io/docs/instrumentation/python/)
- [OpenTelemetry Span API](https://opentelemetry-python.readthedocs.io/en/latest/api/trace.html)
- [Grafana Tempo Documentation](https://grafana.com/docs/tempo/latest/)
