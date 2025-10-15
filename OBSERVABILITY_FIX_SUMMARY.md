# Observability Fix Summary - Petrosa Realtime Strategies

## Date: October 15, 2025

## Problem Statement
The `petrosa-realtime-strategies` service was experiencing two main observability issues:
1. **Metric Export Failures**: Continuous errors exporting metrics to Grafana Alloy
2. **Missing Log Export**: Logs were not being sent to Grafana Cloud via OTLP

## Root Causes Identified

### 1. Network Policy Misconfiguration
- **Issue**: Network policy was configured to allow egress to namespace labeled `name: monitoring`
- **Reality**: Grafana Alloy is running in the `observability` namespace
- **Impact**: All OTLP export attempts (metrics, traces, logs) were blocked by network policies

### 2. Missing Environment Variables
- **Issue**: Deployment was missing `ENABLE_LOGS`, `ENABLE_METRICS`, and `ENABLE_TRACES` environment variables
- **Reality**: These variables are defined in `petrosa-common-config` ConfigMap but weren't referenced in the deployment
- **Impact**: OTLP components weren't being enabled even when network was accessible

### 3. OTEL_NO_AUTO_INIT Blocking Initialization
- **Issue**: Deployment had `OTEL_NO_AUTO_INIT=1` set as environment variable
- **Reality**: This prevented `setup_telemetry()` from being called in `main.py`
- **Impact**: Logger provider was never created, causing "Logger provider not configured" warnings

### 4. Import Scope Issue in otel_init.py
- **Issue**: `LoggingHandler` was imported inside `setup_telemetry()` function's try block
- **Reality**: `attach_logging_handler_simple()` is called separately and needs access to `LoggingHandler`
- **Impact**: "name 'LoggingHandler' is not defined" error when trying to attach logging handler

## Fixes Implemented

### ✅ 1. Network Policy Fix
**File**: `k8s/network-policy.yaml`

**Change**: Updated namespace selector from `name: monitoring` to `name: observability`

```yaml
# Before:
- to:
  - namespaceSelector:
      matchLabels:
        name: monitoring
  ports:
  - protocol: TCP
    port: 4317

# After:
- to:
  - namespaceSelector:
      matchLabels:
        name: observability
  ports:
  - protocol: TCP
    port: 4317
  - protocol: TCP
    port: 4318
```

**Applied**: Via `kubectl apply -f k8s/network-policy.yaml`

**Verification**: 
```bash
kubectl exec -n petrosa-apps <pod> -- nc -zv grafana-alloy.observability.svc.cluster.local 4317
# Result: grafana-alloy.observability.svc.cluster.local (10.152.183.41:4317) open
```

### ✅ 2. Environment Variables Fix
**File**: `k8s/deployment.yaml`

**Change**: Added missing OTLP control variables

```yaml
- name: ENABLE_LOGS
  valueFrom:
    configMapKeyRef:
      name: petrosa-common-config
      key: ENABLE_LOGS
- name: ENABLE_METRICS
  valueFrom:
    configMapKeyRef:
      name: petrosa-common-config
      key: ENABLE_METRICS
- name: ENABLE_TRACES
  valueFrom:
    configMapKeyRef:
      name: petrosa-common-config
      key: ENABLE_TRACES
```

**Applied**: Via `kubectl patch` command

### ✅ 3. Removed OTEL_NO_AUTO_INIT
**File**: `k8s/deployment.yaml`

**Change**: Removed the environment variable that was blocking initialization

```yaml
# Removed:
- name: OTEL_NO_AUTO_INIT
  value: "1"
```

**Applied**: Via `kubectl patch` command to remove the env var

### ✅ 4. Fixed otel_init.py Imports
**File**: `otel_init.py`

**Change**: Moved OpenTelemetry imports to module level

```python
# Added at module level (before function definitions):
try:
    from opentelemetry import metrics, trace
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.aiohttp_client import AioHttpClientInstrumentor
    from opentelemetry.instrumentation.logging import LoggingInstrumentor
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.urllib3 import URLLib3Instrumentor
    from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
    from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    OTEL_AVAILABLE = True
except ImportError as e:
    OTEL_AVAILABLE = False
    print(f"⚠️  OpenTelemetry not available: {e}")
```

**Status**: Code fixed locally, needs proper Docker build for amd64 platform

## Current Status

### ✅ Working
1. **Network Connectivity**: Pods can successfully reach Grafana Alloy on port 4317
2. **Metric Export**: No more "Failed to export metrics" errors in logs
3. **Service Health**: All pods running normally with proper heartbeat
4. **Configuration**: Deployment YAML updated with correct settings

### ⚠️ Pending
1. **Log Export**: Still not working due to LoggingHandler import issue
2. **Docker Image**: otel_init.py fix needs to be built for amd64 platform and deployed

## Next Steps

1. **Build Multi-Platform Docker Image**:
   ```bash
   docker buildx build --platform linux/amd64,linux/arm64 -t yurisa2/petrosa-realtime-strategies:v1.0.16 --push .
   ```

2. **Deploy Fixed Image**:
   ```bash
   kubectl --kubeconfig=<path> set image deployment/petrosa-realtime-strategies -n petrosa-apps realtime-strategies=yurisa2/petrosa-realtime-strategies:v1.0.16
   ```

3. **Verify Log Export**:
   ```bash
   # Check pod logs for successful initialization
   kubectl logs -n petrosa-apps <pod> | grep "OTLP logging handler attached"
   
   # Verify logs appear in Grafana Cloud
   ```

## Testing Commands

### Check Network Connectivity
```bash
kubectl exec -n petrosa-apps <pod> -- nc -zv grafana-alloy.observability.svc.cluster.local 4317
```

### Check Environment Variables
```bash
kubectl exec -n petrosa-apps <pod> -- env | grep -E "(ENABLE_OTEL|ENABLE_LOGS|ENABLE_METRICS|OTEL_EXPORTER)"
```

### Check Logs for Errors
```bash
kubectl logs -n petrosa-apps <pod> --tail=100 | grep -E "(Failed to export|Transient error|OTLP|OpenTelemetry)"
```

### Check Network Policy
```bash
kubectl describe networkpolicy -n petrosa-apps petrosa-realtime-strategies-allow-egress
```

## Impact

### Before Fixes
- ❌ Metric export failures every 60 seconds
- ❌ No telemetry data reaching Grafana Cloud
- ❌ Network policies blocking all OTLP traffic
- ❌ Missing observability for debugging and monitoring

### After Fixes
- ✅ Metrics exporting successfully (network policy fixed)
- ✅ No export errors in logs
- ✅ Service running normally
- ⚠️ Logs still pending (awaits proper Docker build)

## Lessons Learned

1. **Always verify namespace labels** when configuring network policies
2. **Check environment variables** are properly referenced from ConfigMaps
3. **Import scope matters** - module-level imports are needed for cross-function usage
4. **Platform-specific builds** - Use `docker buildx` for multi-platform images
5. **Test incrementally** - Network -> Config -> Code changes in order

## Files Modified

1. `/Users/yurisa2/petrosa/petrosa-realtime-strategies/k8s/network-policy.yaml`
2. `/Users/yurisa2/petrosa/petrosa-realtime-strategies/k8s/deployment.yaml`
3. `/Users/yurisa2/petrosa/petrosa-realtime-strategies/otel_init.py`

## Related Documentation

- [OpenTelemetry Python SDK](https://opentelemetry-python.readthedocs.io/)
- [Kubernetes Network Policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/)
- [Grafana Alloy Configuration](https://grafana.com/docs/alloy/)

