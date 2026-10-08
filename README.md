# Petrosa Realtime Strategies

Stateless real-time trading signal generation from streaming market data.

## Responsibilities

The service consumes market events from NATS, evaluates enabled strategies, and
publishes trading intents for the CIO gatekeeper. Database access is provided by
the data-manager API; this service does not connect to MongoDB or MySQL directly.

Input subject: `binance.futures.websocket.data`.

Output subject: `intent.trading.*`.

The service exposes health, readiness, metrics, runtime configuration, and market
metrics endpoints on port `8080`.

## Strategies

- Order-book skew: compares bid and ask liquidity.
- Trade momentum: evaluates trade direction, price movement, and size.
- Ticker velocity: evaluates price movement over a bounded time window.
- Market-logic strategies: use data-manager-backed configuration and market data.

Each NATS replica uses the shared `realtime-strategies-group` queue group. The
ticker velocity cache is bounded and pruned by its configured time window.

## Configuration

Common environment variables include:

| Variable | Default | Purpose |
|---|---|---|
| `NATS_URL` | `nats://localhost:4222` | NATS server address |
| `NATS_CONSUMER_TOPIC` | `binance.futures.websocket.data` | Input subject |
| `NATS_PUBLISHER_TOPIC` | `intent.trading.*` | Output subject |
| `NATS_CONSUMER_GROUP` | `realtime-strategies-group` | Queue group |
| `TRADING_SYMBOLS` | `BTCUSDT,ETHUSDT,BNBUSDT` | Symbols to process |
| `CONFIG_CACHE_TTL_SECONDS` | `60` | Runtime configuration cache TTL |
| `FASTAPI_PORT` | `8080` | HTTP server port |

Strategy-specific variables are documented in [API usage](docs/API_USAGE_GUIDE.md).

## Development

```bash
make setup
make lint
make unit
```

Run the complete local verification pipeline with `make pipeline`.

The repository requires Python 3.11 or newer. See [documentation](docs/INDEX.md)
for maintained API, operations, and observability references.
