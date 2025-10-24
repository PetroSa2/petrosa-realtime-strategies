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
NATS_CONSUMER_TOPIC = os.getenv("NATS_CONSUMER_TOPIC", "binance.websocket.data")
# Changed from "tradeengine.orders" to "signals.trading" to match TradeEngine's subscription topic
# This ensures signals from realtime-strategies actually reach the TradeEngine
NATS_PUBLISHER_TOPIC = os.getenv("NATS_PUBLISHER_TOPIC", "signals.trading")
NATS_CONSUMER_NAME = os.getenv("NATS_CONSUMER_NAME", "realtime-strategies-consumer")
NATS_CONSUMER_GROUP = os.getenv("NATS_CONSUMER_GROUP", "realtime-strategies-group")

# MongoDB Configuration
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "petrosa")
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))

# Strategy Configuration
STRATEGY_ENABLED_ORDERBOOK_SKEW = (
    os.getenv("STRATEGY_ENABLED_ORDERBOOK_SKEW", "true").lower() == "true"
)
STRATEGY_ENABLED_TRADE_MOMENTUM = (
    os.getenv("STRATEGY_ENABLED_TRADE_MOMENTUM", "true").lower() == "true"
)
STRATEGY_ENABLED_TICKER_VELOCITY = (
    os.getenv("STRATEGY_ENABLED_TICKER_VELOCITY", "true").lower() == "true"
)

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

# Order Book Skew Strategy Parameters
ORDERBOOK_SKEW_TOP_LEVELS = int(os.getenv("ORDERBOOK_SKEW_TOP_LEVELS", "5"))
ORDERBOOK_SKEW_BUY_THRESHOLD = float(os.getenv("ORDERBOOK_SKEW_BUY_THRESHOLD", "1.2"))
ORDERBOOK_SKEW_SELL_THRESHOLD = float(os.getenv("ORDERBOOK_SKEW_SELL_THRESHOLD", "0.8"))
ORDERBOOK_SKEW_MIN_SPREAD_PERCENT = float(
    os.getenv("ORDERBOOK_SKEW_MIN_SPREAD_PERCENT", "0.1")
)

# Trade Momentum Strategy Parameters
TRADE_MOMENTUM_PRICE_WEIGHT = float(os.getenv("TRADE_MOMENTUM_PRICE_WEIGHT", "0.4"))
TRADE_MOMENTUM_QUANTITY_WEIGHT = float(
    os.getenv("TRADE_MOMENTUM_QUANTITY_WEIGHT", "0.3")
)
TRADE_MOMENTUM_MAKER_WEIGHT = float(os.getenv("TRADE_MOMENTUM_MAKER_WEIGHT", "0.3"))
TRADE_MOMENTUM_BUY_THRESHOLD = float(os.getenv("TRADE_MOMENTUM_BUY_THRESHOLD", "0.7"))
TRADE_MOMENTUM_SELL_THRESHOLD = float(
    os.getenv("TRADE_MOMENTUM_SELL_THRESHOLD", "-0.7")
)
TRADE_MOMENTUM_MIN_QUANTITY = float(os.getenv("TRADE_MOMENTUM_MIN_QUANTITY", "0.001"))

# Ticker Velocity Strategy Parameters
TICKER_VELOCITY_TIME_WINDOW = int(
    os.getenv("TICKER_VELOCITY_TIME_WINDOW", "60")
)  # seconds
TICKER_VELOCITY_BUY_THRESHOLD = float(os.getenv("TICKER_VELOCITY_BUY_THRESHOLD", "0.5"))
TICKER_VELOCITY_SELL_THRESHOLD = float(
    os.getenv("TICKER_VELOCITY_SELL_THRESHOLD", "-0.5")
)
TICKER_VELOCITY_MIN_PRICE_CHANGE = float(
    os.getenv("TICKER_VELOCITY_MIN_PRICE_CHANGE", "0.1")
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

# TradeEngine API Configuration
TRADEENGINE_API_URL = os.getenv(
    "TRADEENGINE_API_URL", "http://petrosa-tradeengine:8080"
)
TRADEENGINE_API_TIMEOUT = int(os.getenv("TRADEENGINE_API_TIMEOUT", "30"))
TRADEENGINE_API_RETRY_ATTEMPTS = int(os.getenv("TRADEENGINE_API_RETRY_ATTEMPTS", "3"))
TRADEENGINE_API_RETRY_DELAY = float(os.getenv("TRADEENGINE_API_RETRY_DELAY", "1.0"))

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

# Circuit Breaker Configuration
CIRCUIT_BREAKER_FAILURE_THRESHOLD = int(
    os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5")
)
CIRCUIT_BREAKER_RECOVERY_TIMEOUT = int(
    os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "60")
)
CIRCUIT_BREAKER_EXPECTED_EXCEPTION = os.getenv(
    "CIRCUIT_BREAKER_EXPECTED_EXCEPTION", "Exception"
)

# Performance Configuration
MAX_MEMORY_MB = int(os.getenv("MAX_MEMORY_MB", "512"))
MAX_CPU_PERCENT = int(os.getenv("MAX_CPU_PERCENT", "80"))
MESSAGE_PROCESSING_TIMEOUT = float(os.getenv("MESSAGE_PROCESSING_TIMEOUT", "1.0"))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", "100"))
BATCH_TIMEOUT = float(os.getenv("BATCH_TIMEOUT", "1.0"))

# OpenTelemetry Configuration
ENABLE_OTEL = os.getenv("ENABLE_OTEL", "true").lower() == "true"
OTEL_SERVICE_VERSION = os.getenv("OTEL_SERVICE_VERSION", SERVICE_VERSION)
OTEL_EXPORTER_OTLP_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317"
)
OTEL_METRICS_EXPORTER = os.getenv("OTEL_METRICS_EXPORTER", "otlp")
OTEL_TRACES_EXPORTER = os.getenv("OTEL_TRACES_EXPORTER", "otlp")
OTEL_LOGS_EXPORTER = os.getenv("OTEL_LOGS_EXPORTER", "otlp")

# Prometheus Metrics Configuration
PROMETHEUS_PORT = int(os.getenv("PROMETHEUS_PORT", "9090"))
PROMETHEUS_ENABLED = os.getenv("PROMETHEUS_ENABLED", "true").lower() == "true"

# Logging Configuration
LOG_FORMAT = os.getenv("LOG_FORMAT", "json")
LOG_LEVEL_STRATEGIES = os.getenv("LOG_LEVEL_STRATEGIES", "INFO")
LOG_LEVEL_NATS = os.getenv("LOG_LEVEL_NATS", "WARNING")
LOG_LEVEL_HTTP = os.getenv("LOG_LEVEL_HTTP", "WARNING")

# Message Processing Configuration
MESSAGE_TTL_SECONDS = int(os.getenv("MESSAGE_TTL_SECONDS", "60"))
MESSAGE_MAX_RETRIES = int(os.getenv("MESSAGE_MAX_RETRIES", "3"))
MESSAGE_RETRY_DELAY = float(os.getenv("MESSAGE_RETRY_DELAY", "1.0"))

# Validation Configuration
VALIDATE_MESSAGES = os.getenv("VALIDATE_MESSAGES", "true").lower() == "true"
VALIDATE_ORDERS = os.getenv("VALIDATE_ORDERS", "true").lower() == "true"
VALIDATE_SYMBOLS = os.getenv("VALIDATE_SYMBOLS", "true").lower() == "true"

# Development Configuration
DEBUG_MODE = os.getenv("DEBUG_MODE", "false").lower() == "true"
DRY_RUN_MODE = os.getenv("DRY_RUN_MODE", "false").lower() == "true"
SIMULATION_MODE = os.getenv("SIMULATION_MODE", "false").lower() == "true"

# Default strategy weights (for signal aggregation)
STRATEGY_WEIGHTS = {
    "orderbook_skew": float(os.getenv("STRATEGY_WEIGHT_ORDERBOOK_SKEW", "0.4")),
    "trade_momentum": float(os.getenv("STRATEGY_WEIGHT_TRADE_MOMENTUM", "0.3")),
    "ticker_velocity": float(os.getenv("STRATEGY_WEIGHT_TICKER_VELOCITY", "0.3")),
}

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
    "CIRCUIT_BREAKER_OPEN": "E008",
}

# Success codes
SUCCESS_CODES = {
    "SIGNAL_GENERATED": "S001",
    "ORDER_SENT": "S002",
    "MESSAGE_PROCESSED": "S003",
    "HEALTH_CHECK_PASSED": "S004",
}


def get_enabled_strategies() -> list[str]:
    """Get list of enabled strategies."""
    strategies = []
    if STRATEGY_ENABLED_ORDERBOOK_SKEW:
        strategies.append("orderbook_skew")
    if STRATEGY_ENABLED_TRADE_MOMENTUM:
        strategies.append("trade_momentum")
    if STRATEGY_ENABLED_TICKER_VELOCITY:
        strategies.append("ticker_velocity")
    return strategies


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
    """Get list of enabled strategies."""
    enabled = []
    if STRATEGY_ENABLED_ORDERBOOK_SKEW:
        enabled.append("orderbook_skew")
    if STRATEGY_ENABLED_TRADE_MOMENTUM:
        enabled.append("trade_momentum")
    if STRATEGY_ENABLED_TICKER_VELOCITY:
        enabled.append("ticker_velocity")
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
    return {
        "orderbook_skew": {
            "enabled": STRATEGY_ENABLED_ORDERBOOK_SKEW,
            "top_levels": ORDERBOOK_SKEW_TOP_LEVELS,
            "buy_threshold": ORDERBOOK_SKEW_BUY_THRESHOLD,
            "sell_threshold": ORDERBOOK_SKEW_SELL_THRESHOLD,
            "min_spread_percent": ORDERBOOK_SKEW_MIN_SPREAD_PERCENT,
        },
        "trade_momentum": {
            "enabled": STRATEGY_ENABLED_TRADE_MOMENTUM,
            "price_weight": TRADE_MOMENTUM_PRICE_WEIGHT,
            "quantity_weight": TRADE_MOMENTUM_QUANTITY_WEIGHT,
            "maker_weight": TRADE_MOMENTUM_MAKER_WEIGHT,
            "buy_threshold": TRADE_MOMENTUM_BUY_THRESHOLD,
            "sell_threshold": TRADE_MOMENTUM_SELL_THRESHOLD,
            "min_quantity": TRADE_MOMENTUM_MIN_QUANTITY,
        },
        "ticker_velocity": {
            "enabled": STRATEGY_ENABLED_TICKER_VELOCITY,
            "time_window": TICKER_VELOCITY_TIME_WINDOW,
            "buy_threshold": TICKER_VELOCITY_BUY_THRESHOLD,
            "sell_threshold": TICKER_VELOCITY_SELL_THRESHOLD,
            "min_price_change": TICKER_VELOCITY_MIN_PRICE_CHANGE,
        },
    }
