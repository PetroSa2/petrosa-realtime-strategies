#!/usr/bin/env python3
"""
Constants and configuration for Petrosa Realtime Strategies service.

This module contains all the configuration constants used throughout the service,
including environment variables, default values, and service-specific settings.
"""

import os

# Service Information
SERVICE_NAME = "petrosa-realtime-strategies"
SERVICE_VERSION = "1.0.0"
OTEL_SERVICE_NAME = "realtime-strategies"

# Environment
ENVIRONMENT = os.getenv("ENVIRONMENT", "production")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")

# NATS Configuration
NATS_URL = os.getenv("NATS_URL", "nats://localhost:4222")
NATS_CONSUMER_TOPIC = os.getenv("NATS_CONSUMER_TOPIC", "binance.futures.websocket.data")
# All signals/orders route through CIO; NATS_TOPIC_INTENTS is the single source of truth.
# NATS_PUBLISHER_TOPIC is retained for health-endpoint display only — it mirrors NATS_TOPIC_INTENTS
# so that the two never drift.
NATS_TOPIC_INTENTS = os.getenv("NATS_TOPIC_INTENTS", "cio.intent.trading")
NATS_PUBLISHER_TOPIC = NATS_TOPIC_INTENTS
NATS_CONSUMER_NAME = os.getenv("NATS_CONSUMER_NAME", "realtime-strategies-consumer")
NATS_CONSUMER_GROUP = os.getenv("NATS_CONSUMER_GROUP", "realtime-strategies-group")

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "petrosa")
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))

# Market Logic Strategies (from QTZD adaptation)
STRATEGY_ENABLED_BTC_DOMINANCE = (
    os.getenv("STRATEGY_ENABLED_BTC_DOMINANCE", "true").lower() == "true"
)
STRATEGY_ENABLED_CROSS_EXCHANGE_SPREAD = (
    os.getenv("STRATEGY_ENABLED_CROSS_EXCHANGE_SPREAD", "true").lower() == "true"
)
STRATEGY_ENABLED_ONCHAIN_METRICS = (
    os.getenv("STRATEGY_ENABLED_ONCHAIN_METRICS", "false").lower() == "true"
)

# Microstructure Strategies
STRATEGY_ENABLED_SPREAD_LIQUIDITY = (
    os.getenv("STRATEGY_ENABLED_SPREAD_LIQUIDITY", "true").lower() == "true"
)
STRATEGY_ENABLED_ICEBERG_DETECTOR = (
    os.getenv("STRATEGY_ENABLED_ICEBERG_DETECTOR", "true").lower() == "true"
)

# Bitcoin Dominance Strategy Parameters (from QTZD adaptation)
BTC_DOMINANCE_HIGH_THRESHOLD = float(
    os.getenv("BTC_DOMINANCE_HIGH_THRESHOLD", "70.0")
)  # Above 70% = rotate to BTC
BTC_DOMINANCE_LOW_THRESHOLD = float(
    os.getenv("BTC_DOMINANCE_LOW_THRESHOLD", "40.0")
)  # Below 40% = alt season
BTC_DOMINANCE_CHANGE_THRESHOLD = float(
    os.getenv("BTC_DOMINANCE_CHANGE_THRESHOLD", "5.0")
)  # 5% change triggers signal
BTC_DOMINANCE_WINDOW_HOURS = int(
    os.getenv("BTC_DOMINANCE_WINDOW_HOURS", "24")
)  # 24-hour analysis window
BTC_DOMINANCE_MIN_SIGNAL_INTERVAL = int(
    os.getenv("BTC_DOMINANCE_MIN_SIGNAL_INTERVAL", "14400")
)  # 4 hours between signals

# Cross-Exchange Spread Strategy Parameters (from QTZD adaptation)
SPREAD_THRESHOLD_PERCENT = float(
    os.getenv("SPREAD_THRESHOLD_PERCENT", "0.5")
)  # 0.5% minimum spread
SPREAD_MIN_SIGNAL_INTERVAL = int(
    os.getenv("SPREAD_MIN_SIGNAL_INTERVAL", "300")
)  # 5 minutes between signals
SPREAD_MAX_POSITION_SIZE = float(
    os.getenv("SPREAD_MAX_POSITION_SIZE", "500")
)  # USDT per arbitrage
SPREAD_EXCHANGES = os.getenv("SPREAD_EXCHANGES", "binance,coinbase").split(",")

# On-Chain Metrics Strategy Parameters (from QTZD adaptation)
ONCHAIN_NETWORK_GROWTH_THRESHOLD = float(
    os.getenv("ONCHAIN_NETWORK_GROWTH_THRESHOLD", "10.0")
)  # 10% growth
ONCHAIN_VOLUME_THRESHOLD = float(
    os.getenv("ONCHAIN_VOLUME_THRESHOLD", "15.0")
)  # 15% volume increase
ONCHAIN_MIN_SIGNAL_INTERVAL = int(
    os.getenv("ONCHAIN_MIN_SIGNAL_INTERVAL", "86400")
)  # 24 hours between signals

# Trading Configuration
TRADING_SYMBOLS = os.getenv("TRADING_SYMBOLS", "BTCUSDT,ETHUSDT,BNBUSDT").split(",")
TRADING_QUANTITY_PERCENT = float(
    os.getenv("TRADING_QUANTITY_PERCENT", "0.1")
)  # 0.1% of available balance
TRADING_MAX_POSITION_SIZE = float(
    os.getenv("TRADING_MAX_POSITION_SIZE", "1000")
)  # USDT
TRADING_MIN_POSITION_SIZE = float(os.getenv("TRADING_MIN_POSITION_SIZE", "10"))  # USDT
TRADING_LEVERAGE = int(os.getenv("TRADING_LEVERAGE", "1"))  # 1x leverage (spot-like)
TRADING_ENABLE_SHORTS = os.getenv("TRADING_ENABLE_SHORTS", "true").lower() == "true"

# Risk Management
RISK_MAX_DAILY_SIGNALS = int(os.getenv("RISK_MAX_DAILY_SIGNALS", "50"))
RISK_MAX_CONCURRENT_POSITIONS = int(os.getenv("RISK_MAX_CONCURRENT_POSITIONS", "5"))
RISK_STOP_LOSS_PERCENT = float(os.getenv("RISK_STOP_LOSS_PERCENT", "2.0"))
RISK_TAKE_PROFIT_PERCENT = float(os.getenv("RISK_TAKE_PROFIT_PERCENT", "4.0"))
RISK_MAX_DRAWDOWN_PERCENT = float(os.getenv("RISK_MAX_DRAWDOWN_PERCENT", "10.0"))

# Health Check Configuration
HEALTH_CHECK_PORT = int(os.getenv("HEALTH_CHECK_PORT", "8080"))
HEALTH_CHECK_INTERVAL = int(os.getenv("HEALTH_CHECK_INTERVAL", "30"))

# Heartbeat Configuration
HEARTBEAT_ENABLED = os.getenv("HEARTBEAT_ENABLED", "true").lower() == "true"
HEARTBEAT_INTERVAL_SECONDS = int(
    os.getenv("HEARTBEAT_INTERVAL_SECONDS", "60")
)  # 60 seconds default
HEARTBEAT_INCLUDE_DETAILED_STATS = (
    os.getenv("HEARTBEAT_INCLUDE_DETAILED_STATS", "true").lower() == "true"
)

# OpenTelemetry Configuration
ENABLE_OTEL = os.getenv("ENABLE_OTEL", "true").lower() == "true"
OTEL_SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", SERVICE_VERSION)
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
)
OTEL_METRICS_EXPORTER = os.getenv("OTEL_METRICS_EXPORTER", "otlp")
OTEL_TRACES_EXPORTER = os.getenv("OTEL_TRACES_EXPORTER", "otlp")
OTEL_LOGS_EXPORTER = os.getenv("OTEL_LOGS_EXPORTER", "otlp")

# Per #223: bound telemetry-provider shutdown so a slow/unreachable OTLP
# collector can never consume the whole pod terminationGracePeriodSeconds.
# `MeterProvider.shutdown()`'s own SDK default is 30_000ms and
# `TracerProvider.shutdown()` has NO timeout at all -- both are called from
# the SIGTERM path, so an unbounded/slow collector call was turning a normal
# liveness-probe restart into a forced SIGKILL (exit 137, reason=Error,
# misread as OOMKilled -- see #223).
TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS = float(
    os.getenv("TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS", "3.0")
)
# Hard safety net: if the full async shutdown sequence (telemetry flush +
# shutdown + consumer/publisher/health-server/config-manager stop) hasn't
# finished this many seconds after SIGTERM, force-exit rather than let
# kubelet SIGKILL us once terminationGracePeriodSeconds (30s) elapses.
# Must stay comfortably below that grace period.
SHUTDOWN_WATCHDOG_SECONDS = float(os.getenv("SHUTDOWN_WATCHDOG_SECONDS", "20.0"))

# Per #225: #223's bounded telemetry shutdown was not enough on its own --
# `StrategiesService.stop()` still awaited each component's `stop()`
# (health_evaluator, heartbeat_manager, consumer, publisher, health_server,
# config_manager) SEQUENTIALLY with NO per-component timeout. A single slow
# or hung call inside that chain (e.g. `NATSConsumer.stop()`'s
# `subscription.drain()` / `nats_client.close()` blocking on an unreachable
# broker) silently consumed the entire SHUTDOWN_WATCHDOG_SECONDS budget,
# turning every such SIGTERM into a forced `os._exit(1)` (observed live:
# "Graceful shutdown exceeded 20.0s watchdog -- forcing exit", exit 1, no
# traceback). Components are now stopped CONCURRENTLY, each individually
# bounded by this timeout, so one hung dependency can no longer block the
# others or exhaust the watchdog. Must stay well below SHUTDOWN_WATCHDOG_SECONDS
# even when combined with TELEMETRY_SHUTDOWN_TIMEOUT_SECONDS (run after).
COMPONENT_STOP_TIMEOUT_SECONDS = float(
    os.getenv("COMPONENT_STOP_TIMEOUT_SECONDS", "5.0")
)

# Per #225: /ready and /healthz must be cheap and bounded -- no probe request
# should ever be able to hang past this internal deadline (well under the
# k8s probe's own timeoutSeconds), even if a future change accidentally adds
# a slow call to the check path. On timeout the handler returns 503 fast
# instead of tying up the request past the probe budget.
READINESS_PROBE_INTERNAL_DEADLINE_SECONDS = float(
    os.getenv("READINESS_PROBE_INTERNAL_DEADLINE_SECONDS", "2.0")
)
HEALTHZ_PROBE_INTERNAL_DEADLINE_SECONDS = float(
    os.getenv("HEALTHZ_PROBE_INTERNAL_DEADLINE_SECONDS", "2.0")
)

# Prometheus Metrics Configuration
PROMETHEUS_ENABLED = os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true"

# Logging Configuration
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")
LOG_LEVEL_STRATEGIES = os.getenv("LOG_LEVEL_STRATEGIES", "INFO")
LOG_LEVEL_NATS = os.getenv("LOG_LEVEL_NATS", "WARNING")
LOG_LEVEL_HTTP = os.getenv("LOG_LEVEL_HTTP", "WARNING")

# Signal confidence thresholds
SIGNAL_CONFIDENCE_HIGH = float(os.getenv("SIGNAL_CONFIDENCE_HIGH", "0.8"))
SIGNAL_CONFIDENCE_MEDIUM = float(os.getenv("SIGNAL_CONFIDENCE_MEDIUM", "0.6"))
SIGNAL_CONFIDENCE_LOW = float(os.getenv("SIGNAL_CONFIDENCE_LOW", "0.4"))

# Order types supported
SUPPORTED_ORDER_TYPES = ["MARKET", "LIMIT", "STOP_MARKET", "STOP_LIMIT"]
DEFAULT_ORDER_TYPE = os.getenv("DEFAULT_ORDER_TYPE", "MARKET")

# Time in force options
SUPPORTED_TIME_IN_FORCE = ["GTC", "IOC", "FOK"]
DEFAULT_TIME_IN_FORCE = os.getenv("DEFAULT_TIME_IN_FORCE", "GTC")

# Market data stream types
SUPPORTED_STREAM_TYPES = ["depth20", "trade", "ticker"]
ENABLED_STREAM_TYPES = os.getenv("ENABLED_STREAM_TYPES", "depth20,trade,ticker").split(
    ","
)

# Signal types
SIGNAL_TYPES = ["BUY", "SELL", "HOLD"]
SIGNAL_ACTIONS = ["OPEN_LONG", "OPEN_SHORT", "CLOSE_LONG", "CLOSE_SHORT", "HOLD"]

# Error codes
ERROR_CODES = {
    "INVALID_MESSAGE": "E001",
    "STRATEGY_ERROR": "E002",
    "NATS_ERROR": "E003",
    "TRADEENGINE_ERROR": "E004",
    "VALIDATION_ERROR": "E005",
    "CONFIGURATION_ERROR": "E006",
    "TIMEOUT_ERROR": "E007",
}

# Success codes
SUCCESS_CODES = {
    "SIGNAL_GENERATED": "S001",
    "ORDER_SENT": "S002",
    "MESSAGE_PROCESSED": "S003",
    "HEALTH_CHECK_PASSED": "S004",
}


def get_trading_config() -> dict:
    """Get trading configuration as a dictionary."""
    return {
        "symbols": TRADING_SYMBOLS,
        "quantity_percent": TRADING_QUANTITY_PERCENT,
        "max_position_size": TRADING_MAX_POSITION_SIZE,
        "min_position_size": TRADING_MIN_POSITION_SIZE,
        "leverage": TRADING_LEVERAGE,
        "enable_shorts": TRADING_ENABLE_SHORTS,
    }


def get_risk_config() -> dict:
    """Get risk management configuration as a dictionary."""
    return {
        "max_daily_signals": RISK_MAX_DAILY_SIGNALS,
        "max_concurrent_positions": RISK_MAX_CONCURRENT_POSITIONS,
        "stop_loss_percent": RISK_STOP_LOSS_PERCENT,
        "take_profit_percent": RISK_TAKE_PROFIT_PERCENT,
        "max_drawdown_percent": RISK_MAX_DRAWDOWN_PERCENT,
    }


def get_enabled_strategies() -> list[str]:
    """Get list of enabled strategies.

    Per #190: returns only strategies actually registered in
    strategies/core/consumer.py's __init__ (market_logic_strategies +
    microstructure_strategies). Order matches consumer.py registration order.
    """
    enabled = []
    if STRATEGY_ENABLED_BTC_DOMINANCE:
        enabled.append("btc_dominance")
    if STRATEGY_ENABLED_CROSS_EXCHANGE_SPREAD:
        enabled.append("cross_exchange_spread")
    if STRATEGY_ENABLED_ONCHAIN_METRICS:
        enabled.append("onchain_metrics")
    if STRATEGY_ENABLED_SPREAD_LIQUIDITY:
        enabled.append("spread_liquidity")
    if STRATEGY_ENABLED_ICEBERG_DETECTOR:
        enabled.append("iceberg_detector")
    return enabled


def get_strategy_config() -> dict:
    """Get strategy configuration as a dictionary."""
    return {}
