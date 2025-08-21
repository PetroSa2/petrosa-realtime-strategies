# Petrosa Realtime Strategies

A high-performance, stateless trading signal service that processes real-time market data from NATS and generates trading signals using multiple strategies for Binance Futures trading.

## Overview

This service is designed to be completely stateless, horizontally scalable, and production-ready for enterprise deployment. It consumes real-time market data from Binance WebSocket streams via NATS, processes the data through multiple stateless strategies, and publishes trade orders to the TradeEngine service.

## Features

- **Stateless Architecture**: Completely stateless design for horizontal scalability
- **Multiple Strategies**: Three configurable trading strategies
  - Order Book Skew Strategy
  - Trade Momentum Strategy  
  - Ticker Velocity Strategy
- **Real-time Processing**: High-performance async processing of market data
- **Futures Trading Support**: Full support for Binance Futures including short positions
- **Enterprise Ready**: Comprehensive monitoring, health checks, and observability
- **Kubernetes Native**: Designed for Kubernetes deployment with auto-scaling

## Architecture

### Core Components

1. **NATS Consumer** - Subscribes to `binance.websocket.data` topic
2. **Strategy Processors** - Stateless strategy implementations
3. **Trade Order Publisher** - Sends orders to `tradeengine.orders` topic
4. **Health Server** - FastAPI-based health checks and metrics
5. **Circuit Breaker** - Fault tolerance and failure handling

### Data Flow

```
Binance WebSocket → NATS → Realtime Strategies → TradeEngine
     ↓                    ↓                    ↓
Market Data        Signal Generation    Order Execution
```

## Strategies

### 1. Order Book Skew Strategy

Analyzes order book depth to identify buying/selling pressure imbalances.

**Parameters:**
- `top_levels`: Number of order book levels to analyze (default: 5)
- `buy_threshold`: Ratio threshold for buy signals (default: 1.2)
- `sell_threshold`: Ratio threshold for sell signals (default: 0.8)
- `min_spread_percent`: Minimum spread percentage (default: 0.1%)

### 2. Trade Momentum Strategy

Analyzes individual trades for momentum indicators.

**Parameters:**
- `price_weight`: Weight for price movement (default: 0.4)
- `quantity_weight`: Weight for trade quantity (default: 0.3)
- `maker_weight`: Weight for maker/taker status (default: 0.3)
- `buy_threshold`: Momentum threshold for buy signals (default: 0.7)
- `sell_threshold`: Momentum threshold for sell signals (default: -0.7)

### 3. Ticker Velocity Strategy

Analyzes price velocity over time windows.

**Parameters:**
- `time_window`: Analysis window in seconds (default: 60)
- `buy_threshold`: Velocity threshold for buy signals (default: 0.5)
- `sell_threshold`: Velocity threshold for sell signals (default: -0.5)
- `min_price_change`: Minimum price change percentage (default: 0.1%)

## Quick Start

### Prerequisites

- Python 3.11+
- Docker
- Kubernetes cluster
- NATS server
- TradeEngine service

### Local Development

```bash
# Clone the repository
git clone <repository-url>
cd petrosa-realtime-strategies

# Setup development environment
make setup

# Run locally
make run-local

# Run tests
make test

# Run complete pipeline
make pipeline
```

### Docker

```bash
# Build image
make build

# Run container
make container

# Deploy to Kubernetes
make deploy
```

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `NATS_URL` | NATS server URL | `nats://localhost:4222` |
| `NATS_CONSUMER_TOPIC` | Market data topic | `binance.websocket.data` |
| `NATS_PUBLISHER_TOPIC` | Order topic | `tradeengine.orders` |
| `TRADING_SYMBOLS` | Trading symbols | `BTCUSDT,ETHUSDT,BNBUSDT` |
| `TRADING_ENABLE_SHORTS` | Enable short positions | `true` |
| `TRADING_LEVERAGE` | Futures leverage | `1` |
| `LOG_LEVEL` | Logging level | `INFO` |

### Strategy Configuration

Each strategy can be enabled/disabled and configured via environment variables:

```bash
# Enable/disable strategies
STRATEGY_ENABLED_ORDERBOOK_SKEW=true
STRATEGY_ENABLED_TRADE_MOMENTUM=true
STRATEGY_ENABLED_TICKER_VELOCITY=true

# Strategy parameters
ORDERBOOK_SKEW_BUY_THRESHOLD=1.2
TRADE_MOMENTUM_BUY_THRESHOLD=0.7
TICKER_VELOCITY_BUY_THRESHOLD=0.5
```

## Deployment

### DockerHub Configuration

The service uses DockerHub for container image storage. For detailed setup instructions, see [DockerHub Setup and CI/CD Configuration](docs/DOCKERHUB_SETUP.md).

**Key Information:**
- **Registry**: DockerHub (docker.io)
- **Username**: yurisa2
- **Repository**: petrosa-realtime-strategies
- **CI/CD**: Automated deployment to private MicroK8s cluster

### Kubernetes

```bash
# Deploy to cluster
make deploy

# Check status
make k8s-status

# View logs
make k8s-logs

# Clean up
make k8s-clean
```

### Helm (if available)

```bash
helm install petrosa-realtime-strategies ./helm-chart
```

## Monitoring

### Health Checks

- **Liveness**: `GET /healthz`
- **Readiness**: `GET /ready`
- **Metrics**: `GET /metrics`
- **Info**: `GET /info`

### Metrics

The service exposes comprehensive metrics including:

- Message processing rates
- Signal generation statistics
- Order submission metrics
- Processing latency
- Error rates
- Circuit breaker status

### Logging

Structured JSON logging with correlation IDs for request tracing.

## Development

### Project Structure

```
petrosa-realtime-strategies/
├── strategies/
│   ├── core/           # Core business logic
│   ├── models/         # Data models
│   ├── health/         # Health checks
│   └── utils/          # Utilities
├── tests/              # Test suite
├── k8s/               # Kubernetes manifests
├── scripts/           # Automation scripts
└── docs/              # Documentation
```

### Testing

```bash
# Run all tests
make test

# Run specific test types
make unit
make integration
make e2e

# Coverage report
make coverage
```

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Type checking
make type-check

# Security scan
make security
```

## Performance

### Expected Performance

- **Message Processing**: 1000+ messages/second per pod
- **Signal Generation**: 50-150 trade orders/day across all strategies
- **Latency**: Sub-millisecond processing time per message
- **Memory Usage**: 256-512MB per pod under normal load
- **CPU Usage**: 200-500m per pod during peak periods

### Scaling

The service is designed to scale horizontally:

- **Auto-scaling**: HPA based on CPU/memory utilization
- **Load Distribution**: NATS consumer groups for load balancing
- **Stateless Design**: No shared state between instances

## Security

- Non-root container execution
- Read-only root filesystem
- Minimal base images
- Network segmentation
- Secret management for sensitive configuration

## Troubleshooting

### Common Issues

1. **NATS Connection Issues**
   - Check NATS server availability
   - Verify connection URL and credentials
   - Check network connectivity

2. **High Memory Usage**
   - Monitor message processing rates
   - Check for memory leaks in strategies
   - Adjust batch sizes and timeouts

3. **Signal Generation Issues**
   - Verify strategy parameters
   - Check market data quality
   - Review strategy logic

### Debug Mode

Enable debug mode for detailed logging:

```bash
export DEBUG_MODE=true
export LOG_LEVEL=DEBUG
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Run the full pipeline
6. Submit a pull request

## License

MIT License - see LICENSE file for details.

## Documentation

For complete setup and configuration details:

- [Complete Setup Summary](docs/COMPLETE_SETUP_SUMMARY.md) - Full setup guide with DockerHub and CI/CD
- [DockerHub Setup](docs/DOCKERHUB_SETUP.md) - DockerHub configuration and credentials
- [CI/CD Pipeline](docs/CI_CD_PIPELINE_IMPLEMENTATION.md) - Pipeline implementation details
- [Deployment Guide](docs/DEPLOYMENT.md) - Kubernetes deployment guide

## Support

For support and questions:

- Create an issue in the repository
- Check the documentation
- Review the troubleshooting guide
