# Signal Contract Fix - Deployment Checklist

**Issue Fixed**: NATS message validation errors in tradeengine when processing signals from realtime-strategies

---

## ✅ Pre-Deployment Verification

- [x] **Signal adapter created** (`strategies/adapters/signal_adapter.py`)
- [x] **Publisher updated** to use adapter (`strategies/core/publisher.py`)
- [x] **24 adapter tests** created and passing (`tests/test_signal_adapter.py`)
- [x] **9 publisher tests** updated and passing (`tests/test_publisher.py`)
- [x] **141 total tests** passing (100% pass rate)
- [x] **No linter errors** in realtime-strategies
- [x] **Documentation** created (`docs/SIGNAL_CONTRACT_FIX.md`)

---

## Deployment Steps

### 1. Build Docker Image

```bash
cd /Users/yurisa2/petrosa/petrosa-realtime-strategies
docker build -t petrosa-realtime-strategies:latest .
```

### 2. Tag and Push Image

```bash
# Tag with version
docker tag petrosa-realtime-strategies:latest <registry>/petrosa-realtime-strategies:v1.x.x

# Push to registry
docker push <registry>/petrosa-realtime-strategies:v1.x.x
```

### 3. Update Kubernetes Deployment

```bash
# Update the deployment
kubectl set image deployment/realtime-strategies \
  realtime-strategies=<registry>/petrosa-realtime-strategies:v1.x.x \
  -n petrosa-apps

# Or apply the full manifest
kubectl apply -f k8s/deployment.yaml -n petrosa-apps
```

### 4. Monitor Deployment

```bash
# Watch rollout status
kubectl rollout status deployment/realtime-strategies -n petrosa-apps

# Check pod status
kubectl get pods -n petrosa-apps -l app=realtime-strategies

# Tail logs
kubectl logs -f deployment/realtime-strategies -n petrosa-apps
```

---

## Post-Deployment Verification

### 1. Check realtime-strategies Logs

```bash
kubectl logs -f deployment/realtime-strategies -n petrosa-apps | grep "Signal published"
```

**Expected**:
```
✅ Signal published successfully | symbol=BTCUSDT | signal_type=buy
```

### 2. Check tradeengine Logs

```bash
kubectl logs -f deployment/tradeengine -n petrosa-apps | grep "NATS MESSAGE"
```

**Expected**:
```
✅ NATS message processed successfully
```

**Should NOT see**:
```
❌ NATS MESSAGE PROCESSING FAILED
```

### 3. Verify Signal Format

```bash
# Monitor NATS traffic (if NATS CLI is available)
nats sub "signals.trading"
```

**Expected payload structure**:
```json
{
  "id": "uuid",
  "signal_id": "uuid",
  "strategy_id": "spread_liquidity_BTCUSDT",
  "symbol": "BTCUSDT",
  "signal_type": "buy",
  "action": "buy",
  "confidence": 0.85,
  "strength": "strong",
  "price": 50000.0,
  "quantity": 0.002,
  "current_price": 50000.0,
  "source": "realtime-strategies",
  "strategy": "spread_liquidity",
  "metadata": {
    "original_signal_type": "BUY",
    "original_signal_action": "OPEN_LONG",
    "original_confidence": "HIGH"
  }
}
```

### 4. Monitor Metrics

```bash
# Check Prometheus/Grafana for:
# - signals_received_total (should increase)
# - signals_validation_errors_total (should NOT increase)
# - orders_created_total (should increase)
```

---

## Rollback Plan (if needed)

### If Issues Occur

1. **Rollback deployment**:
   ```bash
   kubectl rollout undo deployment/realtime-strategies -n petrosa-apps
   ```

2. **Check rollback status**:
   ```bash
   kubectl rollout status deployment/realtime-strategies -n petrosa-apps
   ```

3. **Verify old version is running**:
   ```bash
   kubectl get pods -n petrosa-apps -l app=realtime-strategies
   kubectl logs -f deployment/realtime-strategies -n petrosa-apps
   ```

### Known Issues to Watch

- **Issue**: Signal processing still failing in tradeengine
  - **Cause**: Adapter not transforming all required fields
  - **Action**: Check tradeengine logs for specific missing fields
  
- **Issue**: Increased latency in signal publishing
  - **Cause**: Adapter transformation overhead
  - **Action**: Monitor publishing_time_ms metric

- **Issue**: Original signal data lost
  - **Cause**: Adapter not preserving metadata
  - **Action**: Check signal metadata for original_* fields

---

## Success Criteria

✅ All criteria must be met:

1. **No validation errors** in tradeengine logs (no "NATS MESSAGE PROCESSING FAILED")
2. **Signals published successfully** from realtime-strategies
3. **Orders created** from signals in tradeengine
4. **No increase** in error rates
5. **Latency acceptable** (publishing_time_ms < 100ms)
6. **All tests passing** in CI/CD pipeline

---

## Additional Notes

### Files Changed
- ✅ `strategies/adapters/__init__.py` (new)
- ✅ `strategies/adapters/signal_adapter.py` (new)
- ✅ `strategies/core/publisher.py` (modified)
- ✅ `tests/test_signal_adapter.py` (new)
- ✅ `tests/test_publisher.py` (modified)
- ✅ `tests/test_metrics_integration.py` (modified)
- ✅ `docs/SIGNAL_CONTRACT_FIX.md` (new)
- ✅ `DEPLOYMENT_CHECKLIST.md` (new)

### Other Services
- **ta-bot**: No changes needed (already compatible)
- **tradeengine**: No changes needed (consumer only)
- **socket-client**: Not affected (doesn't publish signals)
- **data-manager**: Not affected (doesn't publish signals)

### Breaking Changes
- **None**: The adapter is backward-compatible

---

## Contact

If issues occur during deployment:
1. Check the troubleshooting section in `docs/SIGNAL_CONTRACT_FIX.md`
2. Review tradeengine and realtime-strategies logs
3. Check NATS message payloads
4. Rollback if critical

---

**Deployment Date**: _____________  
**Deployed By**: _____________  
**Deployment Status**: _____________  
**Rollback Needed**: ☐ Yes ☐ No  


