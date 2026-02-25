# Realtime Strategies Business Metrics Dashboard

This directory contains the Grafana dashboard for monitoring business-level metrics of the Realtime Strategies service.

## Dashboard Overview

The dashboard provides visibility into:
- **Signal Generation**: Rate and total count of trading signals generated per strategy.
- **Processing Performance**: NATS message processing latency and strategy execution time.
- **System Health**: NATS consumer lag and strategy execution success/error rates.
- **Operational Changes**: Frequency and type of strategy configuration changes.
- **Market Analysis**: Rate of market microstructure metrics (depth, pressure) calculations.

## How to Import

1. Open your Grafana instance.
2. Navigate to **Dashboards** -> **Import**.
3. Upload the `realtime-strategies-business-metrics.json` file or paste its contents.
4. Select the appropriate **Prometheus** data source.
5. Click **Import**.

## Metrics Source

The metrics are emitted via OpenTelemetry Meter API and collected by Prometheus. The following custom metrics are used:

| Metric Name | Type | Description |
|-------------|------|-------------|
| `realtime_signals_generated_total` | Counter | Signals generated per strategy/action |
| `realtime_message_processing_latency` | Histogram | NATS message processing time |
| `realtime_strategy_latency` | Histogram | Individual strategy execution time |
| `realtime_consumer_lag` | Gauge | Time difference between message creation and processing |
| `realtime_strategy_executions_total` | Counter | Success/Error/No-signal counts |
| `realtime_config_changes_total` | Counter | Audit of configuration updates |
| `realtime_market_metrics_processed_total` | Counter | Market depth/pressure calculation count |

## Prerequisites

- Realtime Strategies service version >= 2.1.0
- OpenTelemetry Collector configured to scrape the service
- Prometheus as the backend for metrics
