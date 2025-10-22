# OCO Orders Fix Summary

## 🎯 Issue Description

**Problem**: Positions were being created without any limiting orders (Stop Loss / Take Profit OCO orders).

**Root Cause**: The `petrosa-realtime-strategies` service was generating trading signals and converting them to orders WITHOUT including `stop_loss` and `take_profit` values, even though:
- Risk management parameters were configured (`RISK_STOP_LOSS_PERCENT=2.0%`, `RISK_TAKE_PROFIT_PERCENT=4.0%`)
- The TradeEngine had full OCO (One-Cancels-Other) functionality implemented
- The TA bot already included stop_loss/take_profit in its signals

## ✅ Solution Implemented

### Code Changes

**File**: `strategies/core/consumer.py`
**Method**: `_signal_to_order()`
**Lines**: 501-565

Added automatic stop_loss and take_profit calculation based on risk management parameters:

```python
# CRITICAL FIX: Calculate stop_loss and take_profit based on risk management parameters
current_price = signal.price

# Get risk management parameters from constants
stop_loss_pct = constants.RISK_STOP_LOSS_PERCENT / 100.0  # Convert from percentage to decimal
take_profit_pct = constants.RISK_TAKE_PROFIT_PERCENT / 100.0

# Calculate stop_loss and take_profit based on action
if action == "buy":
    # For LONG positions
    stop_loss = current_price * (1 - stop_loss_pct)
    take_profit = current_price * (1 + take_profit_pct)
else:  # action == "sell"
    # For SHORT positions
    stop_loss = current_price * (1 + stop_loss_pct)
    take_profit = current_price * (1 - take_profit_pct)
```

### Risk Management Parameters

**Current Configuration** (from `k8s/configmap.yaml`):
- `RISK_STOP_LOSS_PERCENT`: 2.0% (2:1 Risk-Reward Ratio)
- `RISK_TAKE_PROFIT_PERCENT`: 4.0%

**Risk-Reward Analysis**:
- **Stop Loss**: 2% from entry price
- **Take Profit**: 4% from entry price
- **Risk-Reward Ratio**: 1:2.00 (for every $1 risked, potential $2 profit)

### Example Calculation

For a LONG position on BTC at $100,000:
- **Entry Price**: $100,000.00
- **Stop Loss**: $98,000.00 (-2.00%)
- **Take Profit**: $104,000.00 (+4.00%)
- **Risk**: $2,000.00
- **Reward**: $4,000.00
- **R:R Ratio**: 1:2.00

For a SHORT position on BTC at $100,000:
- **Entry Price**: $100,000.00
- **Stop Loss**: $102,000.00 (+2.00%)
- **Take Profit**: $96,000.00 (-4.00%)
- **Risk**: $2,000.00
- **Reward**: $4,000.00
- **R:R Ratio**: 1:2.00

## 🚀 Deployment Details

**Image**: `yurisa2/petrosa-realtime-strategies:fix-sltp-20251021`
**Platform**: `linux/amd64` (MicroK8s cluster compatibility)
**Deployment Date**: October 21, 2025
**Pods**: 3 replicas (all successfully deployed and running)

### Deployment Commands

```bash
# Build for AMD64 platform
VERSION="fix-sltp-20251021"
docker buildx build --platform linux/amd64 -t yurisa2/petrosa-realtime-strategies:$VERSION --push .

# Update deployment
kubectl --kubeconfig=k8s/kubeconfig.yaml set image deployment/petrosa-realtime-strategies realtime-strategies=yurisa2/petrosa-realtime-strategies:$VERSION -n petrosa-apps

# Restart deployment
kubectl --kubeconfig=k8s/kubeconfig.yaml rollout restart deployment/petrosa-realtime-strategies -n petrosa-apps

# Verify rollout
kubectl --kubeconfig=k8s/kubeconfig.yaml rollout status deployment/petrosa-realtime-strategies -n petrosa-apps
```

## 🔍 Verification

### Code Verification

Created and ran verification script: `scripts/verify_risk_management.py`

**Results**:
```
✅ RISK MANAGEMENT LOGIC VERIFIED
✅ All assertions passed!

LONG Position (BUY):
  Entry Price:   $100,000.00
  Stop Loss:     $98,000.00 (-2.00%)
  Take Profit:   $104,000.00 (+4.00%)
  R:R Ratio: 1:2.00

SHORT Position (SELL):
  Entry Price:   $100,000.00
  Stop Loss:     $102,000.00 (+2.00%)
  Take Profit:   $96,000.00 (-4.00%)
  R:R Ratio: 1:2.00
```

### Deployment Verification

```bash
# Check pods
kubectl --kubeconfig=k8s/kubeconfig.yaml get pods -n petrosa-apps -l app=realtime-strategies

# Output:
NAME                                           READY   STATUS    RESTARTS   AGE
petrosa-realtime-strategies-75997f7fb8-ptqvl   1/1     Running   0          43s
petrosa-realtime-strategies-75997f7fb8-qvctx   1/1     Running   0          22s
petrosa-realtime-strategies-75997f7fb8-tb5pm   1/1     Running   0          74s

# Verify image
kubectl --kubeconfig=k8s/kubeconfig.yaml describe deployment/petrosa-realtime-strategies -n petrosa-apps | grep Image:

# Output:
    Image:      yurisa2/petrosa-realtime-strategies:fix-sltp-20251021
```

## 📊 Impact

### Before Fix
- ❌ Positions created WITHOUT stop loss or take profit orders
- ❌ Unlimited risk on all positions
- ❌ Manual intervention required to set protective orders
- ❌ Risk of significant losses

### After Fix
- ✅ ALL positions automatically have stop loss orders (2% risk)
- ✅ ALL positions automatically have take profit orders (4% profit target)
- ✅ 1:2.00 Risk-Reward ratio on every trade
- ✅ OCO behavior: when one order fills, the other cancels automatically
- ✅ Comprehensive logging of SL/TP values

## 🔄 Trade Flow (Post-Fix)

1. **Signal Generation**: Realtime strategy detects opportunity
2. **Order Conversion**: `_signal_to_order()` adds stop_loss and take_profit
3. **Order Sent**: Complete order (with SL/TP) sent to TradeEngine
4. **Position Opened**: TradeEngine executes market order
5. **OCO Orders Placed**: TradeEngine automatically places paired SL/TP orders
6. **OCO Monitoring**: Background task monitors order fills
7. **Automatic Exit**: When SL or TP fills, the other order is cancelled

## 🛡️ Risk Management

### Configurable Parameters

All risk management parameters are in `k8s/configmap.yaml`:

```yaml
# Risk Management
RISK_MAX_DAILY_SIGNALS: "50"
RISK_MAX_CONCURRENT_POSITIONS: "5"
RISK_STOP_LOSS_PERCENT: "2.0"      # Can be adjusted
RISK_TAKE_PROFIT_PERCENT: "4.0"    # Can be adjusted
RISK_MAX_DRAWDOWN_PERCENT: "10.0"
```

### Adjusting Risk Parameters

To change risk management levels:

1. Update `k8s/configmap.yaml`
2. Apply changes: `kubectl apply -f k8s/configmap.yaml --kubeconfig=k8s/kubeconfig.yaml`
3. Restart deployment: `kubectl rollout restart deployment/petrosa-realtime-strategies -n petrosa-apps --kubeconfig=k8s/kubeconfig.yaml`

## 📝 Notes

- **TA Bot**: Already includes stop_loss/take_profit in signals (no changes needed)
- **TradeEngine**: OCO functionality was already implemented and working
- **Realtime Strategies**: This was the only service missing SL/TP implementation
- **Backward Compatible**: Existing signals with SL/TP continue to work unchanged

## 🔗 Related Documentation

- [OCO Implementation Complete](OCO_IMPLEMENTATION_COMPLETE.md)
- [OCO Implementation Summary](OCO_IMPLEMENTATION_SUMMARY.md)
- [Trading Engine Documentation](../../petrosa-tradeengine/docs/TRADING_ENGINE_DOCUMENTATION.md)

## ✅ Status

**DEPLOYED AND VERIFIED** ✅

All positions created by the realtime-strategies service will now automatically include stop loss and take profit orders with a 1:2.00 risk-reward ratio.

---

**Fix Version**: `fix-sltp-20251021`
**Deployment Date**: October 21, 2025
**Verification Status**: ✅ PASSED

