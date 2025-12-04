# GitHub Copilot Instructions - Realtime Strategies

## Service Context

**Purpose**: Real-time trading strategy execution consuming TA Bot signals and publishing trade orders.

**Deployment**: Kubernetes Deployment with HPA (2-10 replicas) - stateless design

**Role in Ecosystem**: Consumes signals → Executes strategies → Publishes orders → Trade Engine

---

## Architecture

**Data Flow**:
```
NATS (TA signals) → Realtime Strategies → Strategy Execution → NATS (trade orders) → Trade Engine
                         ↓
                    MongoDB (config, state)
```

**Key Components**:
- `strategies/executors/` - Strategy execution logic
- `strategies/consumers/nats_consumer.py` - NATS consumer group
- `strategies/publishers/` - Trade order publishing
- `strategies/services/config_manager.py` - Runtime configuration

---

## Service-Specific Patterns

### Stateless Design

```python
# ✅ GOOD - No instance state
class StrategyExecutor:
    async def execute(self, signal: Signal) -> Order:
        # All state from MongoDB/NATS
        config = await load_config_from_mongodb()
        return self.generate_order(signal, config)

# ❌ BAD - Instance state (won't scale horizontally)
class StrategyExecutor:
    def __init__(self):
        self.state = {}  # Lost on pod restart!
```

### NATS Consumer Groups

```python
# ✅ GOOD - Consumer group for load balancing
await nats.subscribe(
    subject="ta.signals.*",
    queue="realtime-strategies-group",  # Load balanced
    cb=process_signal
)

# Multiple pods share the load
```

### HPA Scaling

**Triggers**:
- CPU > 70%
- Message queue depth > 100
- Processing latency > 5s

**Considerations**:
- Design for horizontal scaling
- No shared in-memory state
- MongoDB for persistent state only

---

## Testing Patterns

```python
# Test strategy execution
@pytest.mark.asyncio
async def test_execute_buy_signal():
    signal = create_buy_signal()
    order = await executor.execute(signal)
    assert order.side == "BUY"

# Mock NATS consumer
@pytest.fixture
def mock_nats_consumer():
    with patch('strategies.consumers.nats_consumer.NATSConsumer') as mock:
        yield mock
```

---

## Common Issues

**Signal Processing Lag**: Scale up replicas via HPA  
**Duplicate Orders**: Check consumer group configuration  
**Config Sync Issues**: MongoDB replication lag

---

**Master Rules**: See `/Users/yurisa2/petrosa/petrosa_k8s/.cursorrules`  
**Service Rules**: `.cursorrules` in this repo

