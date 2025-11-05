# Integration Test Plan for 90% Coverage

## Objective
Reach 90% test coverage through high-quality integration tests that validate real system behavior.

## Current Status
- **Coverage**: 78.00%
- **Target**: 90.00%
- **Gap**: 307 lines across infrastructure and integration code

## Phase 1: Test Infrastructure Setup

### 1.1 NATS Test Server
```yaml
# docker-compose.test.yml
version: '3.8'
services:
  nats-test:
    image: nats:latest
    ports:
      - "4222:4222"
      - "8222:8222"
    command: ["-js", "-m", "8222"]
```

### 1.2 Test Fixtures for Market Data
```python
# tests/fixtures/market_data_fixtures.py
"""Realistic market data fixtures for integration tests."""

BTCUSDT_KLINES = {
    "1m": [
        {"open": 50000, "high": 50100, "low": 49900, "close": 50050, "volume": 10.5},
        # ... 100 realistic candles
    ]
}

DEPTH_SNAPSHOTS = {
    "BTCUSDT": {
        "bids": [[50000, 1.5], [49900, 2.0], ...],
        "asks": [[50100, 1.0], [50200, 0.5], ...]
    }
}
```

### 1.3 Test Configuration
```python
# tests/integration/conftest.py
@pytest.fixture(scope="session")
async def nats_server():
    """Start test NATS server."""
    process = await start_nats_test_server()
    yield process
    await stop_nats_test_server(process)

@pytest.fixture
async def nats_client(nats_server):
    """Connect to test NATS."""
    nc = await nats.connect("nats://localhost:4222")
    yield nc
    await nc.close()
```

## Phase 2: Consumer Integration Tests

### 2.1 NATS Message Processing (Target: +50 lines)
```python
# tests/integration/test_consumer_integration.py

@pytest.mark.asyncio
@pytest.mark.integration
async def test_consumer_processes_depth_messages(nats_client):
    """Test consumer processes real depth messages from NATS."""
    consumer = NATSConsumer()
    await consumer.start()
    
    # Publish test depth message
    depth_msg = create_depth_message("BTCUSDT")
    await nats_client.publish("market.depth.BTCUSDT", json.dumps(depth_msg))
    
    # Wait for processing
    await asyncio.sleep(0.5)
    
    # Verify signal generated
    assert consumer.metrics.messages_processed > 0

@pytest.mark.asyncio
async def test_consumer_reconnection_logic():
    """Test consumer handles NATS disconnection and reconnection."""
    # Tests connection recovery, error handling
    pass
```

### 2.2 Strategy Processing Pipeline (Target: +40 lines)
```python
@pytest.mark.asyncio
async def test_end_to_end_signal_generation(nats_client):
    """Test complete pipeline from market data to signal."""
    consumer = NATSConsumer()
    await consumer.start()
    
    # Publish sequence of market data
    for msg in generate_test_market_sequence():
        await publish_message(nats_client, msg)
    
    # Verify strategies processed data
    # Verify signals generated
    # Verify orders published
```

## Phase 3: Publisher Integration Tests

### 3.1 Order Publishing (Target: +30 lines)
```python
# tests/integration/test_publisher_integration.py

@pytest.mark.asyncio
async def test_publisher_sends_orders_to_nats(nats_client):
    """Test publisher successfully publishes orders."""
    publisher = TradeOrderPublisher()
    await publisher.connect()
    
    order = create_test_order()
    await publisher.publish_order(order)
    
    # Verify message received on NATS
    msg = await subscribe_and_wait(nats_client, "orders.submit")
    assert msg.data["order_id"] == order.order_id
```

### 3.2 Error Handling & Retries (Target: +20 lines)
```python
@pytest.mark.asyncio
async def test_publisher_retries_on_failure():
    """Test publisher retry logic on transient failures."""
    # Simulate NATS failure
    # Verify retries
    # Verify eventual success
```

## Phase 4: Strategy Integration Tests

### 4.1 Market Logic Strategies (Target: +80 lines)
```python
# tests/integration/test_strategies_integration.py

@pytest.mark.asyncio
async def test_btc_dominance_with_real_data():
    """Test BTC dominance strategy with realistic market data."""
    strategy = BitcoinDominanceStrategy()
    
    # Feed historical BTC and altcoin data
    for ticker in load_btc_dominance_fixtures():
        signal = await strategy.process_ticker(ticker)
    
    # Verify signal generation logic
    assert strategy.get_statistics()["signals_generated"] > 0

@pytest.mark.asyncio
async def test_cross_exchange_spread():
    """Test cross-exchange spread detection."""
    strategy = CrossExchangeSpreadStrategy()
    
    # Feed ticker data from multiple exchanges
    # Verify spread detection
    # Verify arbitrage signals
```

### 4.2 Microstructure Strategies (Target: +40 lines)
```python
@pytest.mark.asyncio
async def test_spread_liquidity_detection():
    """Test spread/liquidity monitoring."""
    strategy = SpreadLiquidityStrategy()
    
    # Feed orderbook updates
    for depth in load_spread_fixtures():
        signal = await strategy.process_depth(depth)
    
    # Verify spread widening detection
    # Verify liquidity alerts
```

## Phase 5: End-to-End Scenarios

### 5.1 Complete Trading Flow (Target: +30 lines)
```python
@pytest.mark.asyncio
@pytest.mark.e2e
async def test_complete_trading_flow(nats_client):
    """Test complete flow: market data → strategy → signal → order."""
    # Start consumer and publisher
    consumer = NATSConsumer()
    await consumer.start()
    
    # Publish market data that should trigger signal
    await publish_triggering_market_data(nats_client)
    
    # Wait for processing
    await asyncio.sleep(1.0)
    
    # Verify order was published
    orders = await consume_orders(nats_client)
    assert len(orders) > 0
```

### 5.2 Error Scenarios (Target: +20 lines)
```python
@pytest.mark.asyncio
async def test_handles_malformed_messages():
    """Test system handles malformed NATS messages."""
    # Test invalid JSON
    # Test missing fields
    # Test invalid data types
```

## Phase 6: Performance & Load Tests

### 6.1 Throughput Testing (Target: +10 lines)
```python
@pytest.mark.asyncio
@pytest.mark.slow
async def test_high_throughput_processing():
    """Test consumer handles high message volume."""
    # Publish 10,000 messages rapidly
    # Verify all processed
    # Verify no data loss
```

## Implementation Timeline

### Day 1: Infrastructure Setup (8 hours)
- Set up test NATS server
- Create market data fixtures
- Configure test environment
- **Target**: Infrastructure ready

### Day 2: Consumer & Publisher Tests (8 hours)
- Write consumer integration tests
- Write publisher integration tests
- Debug and fix issues
- **Target**: +100 lines coverage

### Day 3: Strategy & E2E Tests (8 hours)
- Write strategy integration tests
- Write end-to-end scenarios
- Performance testing
- **Target**: +150 lines coverage, reach 90%

## Expected Outcome

### Coverage Breakdown
- **Consumer**: 69% → 85% (+54 lines)
- **Publisher**: 60% → 82% (+37 lines)
- **BTC Dominance**: 34% → 65% (+46 lines)
- **Cross Exchange**: 57% → 78% (+28 lines)
- **OnChain Metrics**: 13% → 45% (+50 lines)
- **Other modules**: +92 lines

**Total**: 307 lines, reaching **90.00%** coverage

### Quality Metrics
- ✅ Real NATS message flow
- ✅ Realistic market data
- ✅ True async behavior
- ✅ Integration verification
- ✅ Production-like scenarios

## Risks & Mitigation

### Risk 1: Test Flakiness
**Mitigation**: 
- Use deterministic test data
- Implement proper wait strategies
- Add timeout handling

### Risk 2: CI/CD Complexity
**Mitigation**:
- Use Docker Compose for NATS
- Make integration tests optional
- Provide local dev setup guide

### Risk 3: Test Maintenance
**Mitigation**:
- Keep fixtures up to date
- Document test scenarios
- Use test helpers for common patterns

## Conclusion

This plan provides a path to **90% coverage with high-quality integration tests** that validate real system behavior. The tests will:
- Be maintainable and reliable
- Catch real bugs
- Document system behavior
- Support refactoring

**Recommendation**: Proceed with implementation in 3-day sprint.

