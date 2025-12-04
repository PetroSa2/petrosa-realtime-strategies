# Signal Confidence Type Error Fix

## Problem

The `petrosa-realtime-strategies` service was experiencing runtime errors in the `iceberg_detector` strategy:

```
"'>=' not supported between instances of 'SignalConfidence' and 'float'"
```

This error was occurring repeatedly in production, causing the strategy to fail when processing order book data.

## Root Cause

The issue was in `strategies/core/consumer.py` at line 645, where the code was incorrectly passing `signal.confidence` (a `SignalConfidence` enum) to `ctx.record_signal()` instead of `signal.confidence_score` (a float).

### Type Confusion

The `Signal` model has two related but distinct fields:

1. **`confidence`** (`SignalConfidence` enum): A categorical confidence level (`HIGH`, `MEDIUM`, `LOW`)
2. **`confidence_score`** (`float`): A numerical confidence score (0.0-1.0)

The `RealtimeStrategyMetrics._get_confidence_bucket()` method expects a float value to compare against numeric thresholds (>= 0.9, >= 0.75, etc.). Passing the enum caused Python to fail when attempting the comparison.

## Code Locations Fixed

### 1. strategies/core/consumer.py (Line 645)

**Before:**
```python
ctx.record_signal(signal.signal_action, signal.confidence)
```

**After:**
```python
ctx.record_signal(signal.signal_action.value, signal.confidence_score)
```

**Changes:**
- Changed `signal.confidence` → `signal.confidence_score` (use float instead of enum)
- Changed `signal.signal_action` → `signal.signal_action.value` (explicitly convert enum to string)

### 2. strategies/core/consumer.py (Line 654)

**Before:**
```python
confidence=round(signal.confidence, 2),
```

**After:**
```python
confidence=signal.confidence.value,
```

**Changes:**
- Changed from trying to round an enum (which would also fail) to using the enum's string value for logging

### 3. strategies/utils/metrics.py (Line 264)

**Before:**
```python
ctx.record_signal(signal.signal_action, signal.confidence)
```

**After:**
```python
ctx.record_signal(signal.signal_action.value, signal.confidence_score)
```

**Changes:**
- Updated docstring example to show correct usage pattern

## Why Other Strategies Didn't Fail

Looking at the codebase, most other strategy handlers in `consumer.py` (lines 701, 712, 717, 726) were already using the correct pattern:

```python
ctx.record_signal(signal.signal_type, signal.confidence_score)
```

The iceberg_detector was the only microstructure strategy using the incorrect enum-based approach.

## Testing

All tests pass after the fix:

1. **Metrics tests**: 21/21 passed
   ```bash
   pytest tests/test_metrics.py -v
   ```

2. **Iceberg detector tests**: 19/19 passed
   ```bash
   pytest tests/ -k "iceberg" -v
   ```

## Impact

This fix resolves the production errors in the `iceberg_detector` strategy. The strategy will now correctly:

1. Record signal metrics with float confidence scores
2. Use confidence buckets for metric grouping (`very_high`, `high`, `medium`, `low`)
3. Log signals with proper enum string values

## Prevention

To prevent similar issues in the future:

1. **Type hints**: The `record_signal` method already has correct type hints (`confidence: float`)
2. **Testing**: The existing tests in `test_metrics.py` line 233 already show the correct usage pattern
3. **Code review**: Future strategy implementations should follow the established pattern used by `btc_dominance`, `cross_exchange_spread`, and `onchain_metrics` strategies

## Related Files

- `strategies/models/signals.py` - Defines `Signal` model with both `confidence` (enum) and `confidence_score` (float)
- `strategies/utils/metrics.py` - Contains `_get_confidence_bucket()` that expects float values
- `strategies/core/consumer.py` - Main consumer that processes signals and records metrics
- `tests/test_metrics.py` - Tests showing correct usage patterns

## Date

Fixed: October 28, 2025

