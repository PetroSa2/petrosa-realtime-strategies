# Signal Contract Mismatch Fix

**Date**: 2025-10-28  
**Issue**: NATS message validation errors in tradeengine when processing signals from realtime-strategies  
**Status**: ✅ RESOLVED

---

## Problem Statement

The tradeengine service was failing to process signals published by the realtime-strategies service with the following validation errors:

```
❌ NATS MESSAGE PROCESSING FAILED | Subject: signals.trading | Error: 8 validation errors for Signal
strategy_id  Field required
signal_type  Input should be 'buy', 'sell', 'hold' or 'close' [type=enum, input_value='SELL']
action  Field required
confidence  Input should be a valid number, unable to parse string as a number [input_value='HIGH']
quantity  Field required
current_price  Field required
source  Field required
strategy  Field required
```

### Root Cause

There was a **contract mismatch** between the signal formats used by different services:

#### realtime-strategies (Producer)
- `signal_type`: Uppercase enum ("BUY", "SELL", "HOLD")
- `confidence`: String enum ("HIGH", "MEDIUM", "LOW")
- Missing fields: `strategy_id`, `action`, `quantity`, `current_price`, `source`, `strategy`

#### tradeengine (Consumer)
- `signal_type`: Lowercase ("buy", "sell", "hold", "close")
- `action`: Lowercase literal ("buy", "sell", "hold", "close")
- `confidence`: Float (0-1)
- Requires all the missing fields above

#### ta-bot (Producer)
- ✅ Already correctly aligned with tradeengine contract
- Uses lowercase action, float confidence, and all required fields

---

## Solution

### 1. Created Signal Adapter

A new adapter module was created to transform realtime-strategies signals to match the tradeengine contract:

**File**: `strategies/adapters/signal_adapter.py`

**Key Features**:
- Transforms uppercase signal types to lowercase
- Maps `SignalAction` enum to tradeengine `action` field
- Converts `SignalConfidence` string to numeric `confidence` (0-1)
- Generates required fields: `strategy_id`, `quantity`, `source`, `strategy`
- Adds risk management defaults: `stop_loss_pct`, `take_profit_pct`
- Preserves original signal data in metadata for debugging

**Transformation Mappings**:

```python
# Signal Type Mapping
SignalType.BUY  → "buy"
SignalType.SELL → "sell"
SignalType.HOLD → "hold"

# Signal Action Mapping
SignalAction.OPEN_LONG   → "buy"
SignalAction.OPEN_SHORT  → "sell"
SignalAction.CLOSE_LONG  → "close"
SignalAction.CLOSE_SHORT → "close"
SignalAction.HOLD        → "hold"

# Confidence Mapping
SignalConfidence.HIGH   + confidence_score → confidence_score (0.85)
SignalConfidence.MEDIUM + confidence_score → confidence_score (0.65)
SignalConfidence.LOW    + confidence_score → confidence_score (0.35)

# Strength Mapping (from confidence_score)
>= 0.9 → "extreme"
>= 0.7 → "strong"
>= 0.5 → "medium"
<  0.5 → "weak"
```

**Generated Fields**:
- `strategy_id`: `{strategy_name}_{symbol}` (e.g., "spread_liquidity_BTCUSDT")
- `quantity`: Calculated based on price and confidence
- `source`: Always "realtime-strategies"
- `strategy`: Taken from `strategy_name`

**Risk Management Defaults**:

| Confidence | Stop Loss | Take Profit |
|-----------|-----------|-------------|
| High (≥0.8) | 2% | 5% |
| Medium (0.6-0.79) | 3% | 4% |
| Low (<0.6) | 5% | 3% |

### 2. Updated Publisher

Modified `strategies/core/publisher.py` to use the adapter:

```python
# Before
signal_dict = signal.dict() or signal.model_dump()

# After
from strategies.adapters.signal_adapter import transform_signal_for_tradeengine
signal_dict = transform_signal_for_tradeengine(signal)
```

### 3. Comprehensive Testing

Created extensive test suite for the adapter:

**File**: `tests/test_signal_adapter.py`

**Test Coverage**:
- ✅ Signal transformation for all signal types (BUY, SELL, HOLD)
- ✅ Signal action mapping (OPEN_LONG, OPEN_SHORT, CLOSE_LONG, CLOSE_SHORT, HOLD)
- ✅ Confidence to strength mapping
- ✅ Timestamp conversion to ISO format
- ✅ Metadata preservation and augmentation
- ✅ Risk management defaults
- ✅ Order configuration defaults
- ✅ Quantity calculation
- ✅ Edge cases and boundary values

**Test Results**: ✅ 24/24 tests passing

**Updated Existing Tests**:
- Updated `tests/test_publisher.py` to expect transformed signal format
- All 9 publisher tests now passing

---

## Verification

### Before Fix

```log
2025-10-28 07:25:35.923 error ❌ NATS MESSAGE PROCESSING FAILED | Subject: signals.trading
Error: 8 validation errors for Signal
- strategy_id: Field required
- signal_type: Input should be 'buy', 'sell', 'hold' or 'close' [input_value='SELL']
- action: Field required
- confidence: Input should be a valid number [input_value='HIGH']
- quantity: Field required
- current_price: Field required
- source: Field required
- strategy: Field required
```

### After Fix

Expected result when deployed:
```log
✅ Signal published successfully
✅ NATS message processed successfully
✅ Trade order created from signal
```

### Example Transformation

**Input** (realtime-strategies Signal):
```python
{
    "symbol": "BTCUSDT",
    "signal_type": "BUY",
    "signal_action": "OPEN_LONG",
    "confidence": "HIGH",
    "confidence_score": 0.85,
    "price": 50000.0,
    "strategy_name": "spread_liquidity",
    "metadata": {"timeframe": "tick"}
}
```

**Output** (tradeengine-compatible Signal):
```python
{
    "id": "uuid-generated",
    "signal_id": "uuid-generated",
    "strategy_id": "spread_liquidity_BTCUSDT",
    "strategy_mode": "deterministic",
    "symbol": "BTCUSDT",
    "signal_type": "buy",
    "action": "buy",
    "confidence": 0.85,
    "strength": "strong",
    "price": 50000.0,
    "quantity": 0.002,
    "current_price": 50000.0,
    "target_price": 50000.0,
    "source": "realtime-strategies",
    "strategy": "spread_liquidity",
    "metadata": {
        "timeframe": "tick",
        "original_signal_type": "BUY",
        "original_signal_action": "OPEN_LONG",
        "original_confidence": "HIGH"
    },
    "timeframe": "tick",
    "order_type": "market",
    "time_in_force": "GTC",
    "stop_loss": null,
    "stop_loss_pct": 0.02,
    "take_profit": null,
    "take_profit_pct": 0.05,
    "timestamp": "2025-10-28T10:30:09.463809"
}
```

---

## Impact Assessment

### ✅ Services Fixed
- **realtime-strategies**: Now publishes signals in tradeengine-compatible format

### ✅ Services Already Compliant
- **ta-bot**: Already using correct format (no changes needed)

### ✅ Services Unaffected
- **socket-client**: Does not publish trading signals
- **data-manager**: Does not publish trading signals
- **binance-data-extractor**: Does not publish trading signals

### ⚠️ Breaking Changes
- **None**: The adapter is backward-compatible at the publisher level
- Original signal data is preserved in metadata for debugging

---

## Deployment Steps

1. **Build and Deploy realtime-strategies**:
   ```bash
   cd /Users/yurisa2/petrosa/petrosa-realtime-strategies
   make docker-build
   make deploy
   ```

2. **Monitor tradeengine Logs**:
   ```bash
   kubectl logs -f deployment/tradeengine -n petrosa-apps | grep "NATS MESSAGE"
   ```

3. **Verify Signal Processing**:
   - Watch for "✅ Signal processed successfully" messages
   - No more "❌ NATS MESSAGE PROCESSING FAILED" errors
   - Check that orders are being created from signals

4. **Monitor Metrics**:
   - `signals_received_total` in tradeengine should increase
   - `signals_validation_errors_total` should not increase
   - `orders_created_total` should increase

---

## Future Improvements

### Short-term
1. **Centralize Signal Contract**: Move signal models to a shared library (e.g., `petrosa-contracts`)
2. **Add Schema Validation**: Implement JSON Schema validation at NATS level
3. **Add Contract Tests**: Create integration tests that verify signal compatibility

### Long-term
1. **API Gateway for Signals**: Route all signals through a validation gateway
2. **Signal Versioning**: Add version field to support multiple signal formats
3. **Centralized Signal Registry**: Document all signal types and formats in one place

---

## Testing Checklist

- [x] Unit tests for signal adapter (24 tests)
- [x] Unit tests for publisher (9 tests)
- [x] Linter checks pass
- [ ] Integration test with live tradeengine (requires deployment)
- [ ] End-to-end test: signal → order → execution (requires deployment)

---

## Related Files

### New Files
- `strategies/adapters/__init__.py`
- `strategies/adapters/signal_adapter.py`
- `tests/test_signal_adapter.py`
- `docs/SIGNAL_CONTRACT_FIX.md` (this file)

### Modified Files
- `strategies/core/publisher.py`
- `tests/test_publisher.py`

### Reference Files
- `petrosa-tradeengine/contracts/signal.py` (tradeengine contract)
- `petrosa-bot-ta-analysis/ta_bot/models/signal.py` (ta-bot contract - already correct)

---

## Conclusion

The signal contract mismatch between realtime-strategies and tradeengine has been resolved by implementing a signal adapter that transforms signals to the expected format. All tests are passing, and the solution is ready for deployment.

The adapter approach:
- ✅ Preserves original signal data
- ✅ Adds missing required fields intelligently
- ✅ Is non-breaking and backward-compatible
- ✅ Is fully tested (33 tests total)
- ✅ Maintains distributed tracing support

**Next Step**: Deploy realtime-strategies and monitor tradeengine logs for successful signal processing.

