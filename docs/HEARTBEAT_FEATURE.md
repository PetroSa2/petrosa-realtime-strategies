# Heartbeat Feature Documentation

## Overview

The Petrosa Realtime Strategies service now includes a comprehensive heartbeat system that provides periodic logging of system statistics and message processing metrics. This feature helps with monitoring, debugging, and performance analysis.

## Features

### 📊 Statistics Tracking
- **Message Processing Stats**: Tracks messages processed, errors, processing times
- **Order Publishing Stats**: Tracks orders published, errors, publishing times  
- **Rate Calculations**: Messages per second, orders per second, error rates
- **Delta Tracking**: Shows changes since last heartbeat
- **Performance Metrics**: Average and maximum processing/publishing times

### 💓 Periodic Logging
- **Configurable Interval**: Default 60 seconds, customizable via environment variable
- **Structured Logging**: JSON format with comprehensive metrics
- **Uptime Tracking**: Service uptime in seconds, minutes, and hours
- **Health Status**: Component health and connectivity status

### 🔧 Configuration
- **Enable/Disable**: Can be completely disabled if not needed
- **Detailed Stats**: Option to include/exclude detailed component metrics
- **Environment Variables**: Fully configurable via environment variables

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HEARTBEAT_ENABLED` | `true` | Enable/disable heartbeat logging |
| `HEARTBEAT_INTERVAL_SECONDS` | `60` | Interval between heartbeats in seconds |
| `HEARTBEAT_INCLUDE_DETAILED_STATS` | `true` | Include detailed component statistics |

### Kubernetes Configuration

The heartbeat is configured in the Kubernetes ConfigMap:

```yaml
# Heartbeat Configuration
HEARTBEAT_ENABLED: "true"
HEARTBEAT_INTERVAL_SECONDS: "60"
HEARTBEAT_INCLUDE_DETAILED_STATS: "true"
```

## Heartbeat Log Format

### Basic Heartbeat Entry

```json
{
  "event": "💓 HEARTBEAT - System Statistics",
  "heartbeat_count": 5,
  "uptime_seconds": 300.45,
  "uptime_minutes": 5.01,
  "uptime_hours": 0.08,
  "interval_seconds": 60,
  
  "messages_processed_delta": 150,
  "consumer_errors_delta": 0,
  "orders_published_delta": 12,
  "publisher_errors_delta": 0,
  
  "messages_per_second": 2.5,
  "orders_per_second": 0.2,
  "error_rate_per_second": 0.0,
  
  "total_messages_processed": 750,
  "total_consumer_errors": 2,
  "total_orders_published": 60,
  "total_publisher_errors": 0
}
```

### Detailed Statistics (when enabled)

```json
{
  "event": "💓 HEARTBEAT - System Statistics",
  // ... basic stats ...
  
  "consumer_is_running": true,
  "consumer_is_healthy": true,
  "consumer_nats_connected": true,
  "consumer_subscription_active": true,
  "consumer_last_message_time": 1640995200.123,
  "consumer_avg_processing_time_ms": 5.2,
  "consumer_max_processing_time_ms": 12.8,
  "consumer_circuit_breaker_state": "closed",
  
  "publisher_is_running": true,
  "publisher_is_healthy": true,
  "publisher_nats_connected": true,
  "publisher_queue_size": 3,
  "publisher_last_order_time": 1640995180.456,
  "publisher_avg_publishing_time_ms": 3.1,
  "publisher_max_publishing_time_ms": 8.9,
  "publisher_circuit_breaker_state": "closed"
}
```

## Usage

### Service Integration

The heartbeat is automatically integrated into the main service and starts with the other components:

```python
# Heartbeat manager is automatically created and started
# No manual intervention required
```

### CLI Commands

#### View Configuration
```bash
python -m strategies.main config
```

#### Check Heartbeat Status
```bash
python -m strategies.main heartbeat
```

#### View Health Metrics
```bash
curl http://localhost:8080/metrics
```

### Testing

Run the heartbeat test script:

```bash
cd /path/to/petrosa-realtime-strategies
python scripts/test_heartbeat.py
```

## Monitoring Integration

### Health Endpoint

The heartbeat status is exposed via the health endpoint at `/metrics`:

```bash
curl http://localhost:8080/metrics
```

Response includes:
```json
{
  "components": {
    "heartbeat": {
      "enabled": true,
      "is_running": true,
      "interval_seconds": 60,
      "heartbeat_count": 10,
      "uptime_seconds": 600.0,
      "include_detailed_stats": true
    }
  }
}
```

### Log Analysis

Heartbeat logs can be easily filtered and analyzed:

```bash
# Filter heartbeat logs
kubectl logs -f deployment/petrosa-realtime-strategies | grep "HEARTBEAT"

# Extract metrics with jq
kubectl logs deployment/petrosa-realtime-strategies | grep "HEARTBEAT" | jq '.messages_per_second'
```

## Performance Impact

The heartbeat system is designed to be lightweight:

- **CPU Impact**: Minimal, runs only once per interval
- **Memory Impact**: Keeps only last 1000 processing times for averages
- **I/O Impact**: Single log entry per interval
- **Network Impact**: No additional network calls

## Troubleshooting

### Heartbeat Not Appearing

1. **Check if enabled**:
   ```bash
   python -m strategies.main config | grep Heartbeat
   ```

2. **Check logs for errors**:
   ```bash
   kubectl logs deployment/petrosa-realtime-strategies | grep -i heartbeat
   ```

3. **Verify service is running**:
   ```bash
   python -m strategies.main health
   ```

### High Error Rates in Heartbeat

If heartbeat shows high error rates:

1. **Check NATS connectivity**
2. **Review circuit breaker status**
3. **Check resource limits (CPU/memory)**
4. **Verify message format validation**

### Missing Statistics

If some statistics are missing:

1. **Check component health status**
2. **Verify NATS connections**
3. **Review component initialization order**

## Best Practices

### Production Configuration

```yaml
# Recommended production settings
HEARTBEAT_ENABLED: "true"
HEARTBEAT_INTERVAL_SECONDS: "60"    # 1 minute intervals
HEARTBEAT_INCLUDE_DETAILED_STATS: "true"
```

### Development Configuration

```yaml
# Recommended development settings
HEARTBEAT_ENABLED: "true"
HEARTBEAT_INTERVAL_SECONDS: "30"    # More frequent for debugging
HEARTBEAT_INCLUDE_DETAILED_STATS: "true"
```

### Log Management

- **Log Rotation**: Ensure log rotation is configured for heartbeat logs
- **Log Retention**: Keep heartbeat logs for performance analysis
- **Alerting**: Set up alerts for error rate thresholds in heartbeat logs

## Integration with Monitoring Systems

### Prometheus Metrics

The heartbeat data can be parsed and exposed as Prometheus metrics:

```python
# Example: Parse heartbeat logs for Prometheus
messages_per_second_gauge = Gauge('messages_per_second', 'Messages processed per second')
# Update from heartbeat logs
```

### Grafana Dashboards

Create dashboards using heartbeat metrics:
- **Message Processing Rate** over time
- **Error Rate Trends**
- **Performance Metrics** (avg/max processing times)
- **System Health** indicators

### Alerting Rules

Example alerting rules based on heartbeat data:

```yaml
# High error rate alert
- alert: HighErrorRate
  expr: error_rate_per_second > 0.1
  for: 5m
  
# Low message processing rate
- alert: LowMessageRate  
  expr: messages_per_second < 0.5
  for: 10m
```

## Future Enhancements

Planned improvements for the heartbeat system:

1. **Metrics Export**: Direct Prometheus metrics export
2. **Custom Thresholds**: Configurable alerting thresholds
3. **Historical Trends**: Longer-term trend analysis
4. **Performance Baselines**: Automatic baseline detection
5. **Predictive Alerts**: ML-based anomaly detection
