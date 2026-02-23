# API Configuration Implementation Plan
## petrosa-realtime-strategies

**Status**: 📋 Implementation Plan  
**Priority**: High  
**Estimated Effort**: 8-12 hours  
**Target Completion**: 1-2 days  

---

## Executive Summary

This document outlines the complete implementation plan to add real-time API configuration to **petrosa-realtime-strategies**, following the proven architecture patterns successfully implemented in **petrosa-bot-ta-analysis** and **petrosa-tradeengine**.

### Current State
- ❌ Configuration only via environment variables (ConfigMap)
- ❌ Requires pod restart for any configuration change
- ❌ No per-symbol strategy configuration
- ❌ No configuration audit trail
- ❌ 30-60 second downtime during updates

### Target State
- ✅ Real-time API configuration without restarts
- ✅ Per-symbol strategy overrides
- ✅ Full audit trail with who/what/when/why
- ✅ Schema-based validation
- ✅ 60-second caching for performance
- ✅ MongoDB persistence
- ✅ Backward compatible with existing environment variables

---

## Architecture Overview

### Configuration Resolution Hierarchy

```
1. Cache (60-second TTL) ───────────────┐
   ↓ (cache miss)                       │ (cache hit)
2. MongoDB Symbol-Specific Config ──────┤
   ↓ (not found)                        │
3. MongoDB Global Config ───────────────┤
   ↓ (not found)                        │
4. Environment Variables (current) ─────┤
   ↓ (not set)                          │
5. Hardcoded Defaults ──────────────────┘
   ↓
   Return Resolved Config
```

### Components to Implement

```
strategies/
├── services/
│   └── config_manager.py       ← NEW: Configuration manager
├── api/
│   ├── __init__.py             ← NEW: API package
│   ├── config_routes.py        ← NEW: FastAPI routes
│   └── response_models.py      ← NEW: API response models
├── db/
│   └── mongodb_client.py       ← EXISTS: Extend with new methods
└── health/
    └── server.py               ← UPDATE: Integrate config routes
```

---

## Implementation Steps

### Phase 1: Expand Strategy Defaults (2 hours)

#### File: `strategies/market_logic/defaults.py`

**Current Status**: Only has 3 market logic strategies  
**Required**: Add all 6 strategies (orderbook_skew, trade_momentum, ticker_velocity, btc_dominance, cross_exchange_spread, onchain_metrics)

**Tasks**:

1. **Add Orderbook Skew Strategy Defaults**
```python
"orderbook_skew": {
    "top_levels": 5,
    "buy_threshold": 1.2,
    "sell_threshold": 0.8,
    "min_spread_percent": 0.1,
    "base_confidence": 0.70,
    "imbalance_weight": 0.6,
    "spread_weight": 0.4,
},
```

2. **Add Trade Momentum Strategy Defaults**
```python
"trade_momentum": {
    "price_weight": 0.4,
    "quantity_weight": 0.3,
    "maker_weight": 0.3,
    "buy_threshold": 0.7,
    "sell_threshold": -0.7,
    "min_quantity": 0.001,
    "base_confidence": 0.68,
    "time_decay_seconds": 300,
},
```

3. **Add Ticker Velocity Strategy Defaults**
```python
"ticker_velocity": {
    "time_window": 60,
    "buy_threshold": 0.5,
    "sell_threshold": -0.5,
    "min_price_change": 0.1,
    "base_confidence": 0.65,
    "acceleration_weight": 0.5,
},
```

4. **Add Parameter Schemas with Validation Rules**
   - Type (int, float, bool, str, list)
   - Min/max ranges
   - Descriptions
   - Examples

5. **Add Strategy Metadata**
   - Name, description, category, type

**Deliverable**: Complete defaults registry for all 6 strategies

---

### Phase 2: Create Configuration Manager (3 hours)

#### File: `strategies/services/config_manager.py` (NEW)

**Pattern**: Follow `petrosa-bot-ta-analysis/ta_bot/services/config_manager.py`

**Class**: `StrategyConfigManager`

**Key Methods**:

```python
class StrategyConfigManager:
    """
    Strategy configuration manager with MongoDB persistence and caching.
    
    Configuration Resolution Priority:
    1. Cache (if not expired)
    2. MongoDB symbol-specific config
    3. MongoDB global config
    4. Environment variables (backward compatibility)
    5. Hardcoded defaults
    """
    
    async def start(self) -> None:
        """Initialize MongoDB and start cache refresh task"""
    
    async def stop(self) -> None:
        """Cleanup and shutdown"""
    
    async def get_config(
        self, strategy_id: str, symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get resolved configuration with caching.
        Returns: {parameters, version, source, is_override, ...}
        """
    
    async def set_config(
        self,
        strategy_id: str,
        parameters: Dict[str, Any],
        changed_by: str,
        symbol: Optional[str] = None,
        reason: Optional[str] = None,
        validate_only: bool = False,
    ) -> Tuple[bool, Optional[StrategyConfig], List[str]]:
        """Create or update configuration with validation"""
    
    async def delete_config(
        self,
        strategy_id: str,
        changed_by: str,
        symbol: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Tuple[bool, List[str]]:
        """Delete configuration"""
    
    async def list_strategies(self) -> List[Dict[str, Any]]:
        """List all strategies with config status"""
    
    async def get_audit_trail(
        self, strategy_id: str, symbol: Optional[str] = None, limit: int = 100
    ) -> List[StrategyConfigAudit]:
        """Get configuration change history"""
    
    async def refresh_cache(self) -> None:
        """Force cache invalidation"""
```

**Implementation Details**:

1. **Caching**:
   - Cache key: `f"{strategy_id}:{symbol or 'global'}"`
   - TTL: 60 seconds (configurable)
   - Automatic background cleanup

2. **Fallback Logic**:
   - Check MongoDB first
   - Fall back to environment variables (current behavior)
   - Use hardcoded defaults as last resort

3. **Validation**:
   - Use schema from `defaults.py`
   - Type checking
   - Range validation
   - Return clear error messages

4. **Audit Trail**:
   - Log all configuration changes
   - Store in MongoDB collection `strategy_config_audit`
   - Track: what changed, who changed it, when, why

**Environment Variable Fallback**:
```python
def _get_from_environment(self, strategy_id: str) -> Dict[str, Any]:
    """Get configuration from environment variables (backward compatibility)"""
    if strategy_id == "orderbook_skew":
        return {
            "top_levels": int(os.getenv("ORDERBOOK_SKEW_TOP_LEVELS", "5")),
            "buy_threshold": float(os.getenv("ORDERBOOK_SKEW_BUY_THRESHOLD", "1.2")),
            # ... etc
        }
    # Similar for other strategies
```

**Deliverable**: Fully functional configuration manager with MongoDB persistence

---

### Phase 3: Create API Routes (2 hours)

#### File: `strategies/api/__init__.py` (NEW)

```python
"""API package for configuration management."""
from .config_routes import router

__all__ = ["router"]
```

#### File: `strategies/api/response_models.py` (NEW)

**Pattern**: Follow `petrosa-bot-ta-analysis/ta_bot/api/response_models.py`

```python
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional

class APIResponse(BaseModel):
    """Standard API response wrapper"""
    success: bool
    data: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

class ConfigResponse(BaseModel):
    """Configuration response model"""
    strategy_id: str
    symbol: Optional[str]
    parameters: Dict[str, Any]
    version: int
    source: str
    is_override: bool
    created_at: Optional[str]
    updated_at: Optional[str]

class ConfigUpdateRequest(BaseModel):
    """Configuration update request"""
    parameters: Dict[str, Any]
    changed_by: str
    reason: Optional[str] = None
    validate_only: bool = False

class ParameterSchemaItem(BaseModel):
    """Parameter schema definition"""
    name: str
    type: str
    description: str
    default: Any
    min: Optional[float] = None
    max: Optional[float] = None
    allowed_values: Optional[List[Any]] = None
    example: Any

class StrategyListItem(BaseModel):
    """Strategy list item"""
    strategy_id: str
    name: str
    description: str
    has_global_config: bool
    symbol_overrides: List[str]
    parameter_count: int

class AuditTrailItem(BaseModel):
    """Audit trail record"""
    id: str
    strategy_id: str
    symbol: Optional[str]
    action: str
    old_parameters: Optional[Dict[str, Any]]
    new_parameters: Optional[Dict[str, Any]]
    changed_by: str
    changed_at: str
    reason: Optional[str]
```

#### File: `strategies/api/config_routes.py` (NEW)

**Pattern**: Follow `petrosa-bot-ta-analysis/ta_bot/api/config_routes.py`

**Endpoints**:

```python
from fastapi import APIRouter, HTTPException, Path, Query
from strategies.services.config_manager import StrategyConfigManager
from strategies.market_logic.defaults import (
    get_strategy_defaults,
    get_parameter_schema,
    list_all_strategies,
)

router = APIRouter(prefix="/api/v1", tags=["configuration"])

# Global config manager instance
_config_manager: Optional[StrategyConfigManager] = None

@router.get("/strategies")
async def list_strategies():
    """List all available strategies"""

@router.get("/strategies/{strategy_id}/schema")
async def get_strategy_schema(strategy_id: str):
    """Get parameter schema for strategy"""

@router.get("/strategies/{strategy_id}/defaults")
async def get_strategy_defaults_endpoint(strategy_id: str):
    """Get default parameters"""

@router.get("/strategies/{strategy_id}/config")
async def get_global_config(strategy_id: str):
    """Get global configuration"""

@router.get("/strategies/{strategy_id}/config/{symbol}")
async def get_symbol_config(strategy_id: str, symbol: str):
    """Get symbol-specific configuration"""

@router.post("/strategies/{strategy_id}/config")
async def update_global_config(
    strategy_id: str, request: ConfigUpdateRequest
):
    """Create or update global configuration"""

@router.post("/strategies/{strategy_id}/config/{symbol}")
async def update_symbol_config(
    strategy_id: str, symbol: str, request: ConfigUpdateRequest
):
    """Create or update symbol-specific configuration"""

@router.delete("/strategies/{strategy_id}/config")
async def delete_global_config(
    strategy_id: str,
    changed_by: str = Query(...),
    reason: str = Query(None),
):
    """Delete global configuration"""

@router.delete("/strategies/{strategy_id}/config/{symbol}")
async def delete_symbol_config(
    strategy_id: str,
    symbol: str,
    changed_by: str = Query(...),
    reason: str = Query(None),
):
    """Delete symbol-specific configuration"""

@router.get("/strategies/{strategy_id}/audit")
async def get_audit_trail(
    strategy_id: str,
    symbol: str = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    """Get configuration change history"""

@router.post("/strategies/cache/refresh")
async def refresh_cache():
    """Force refresh configuration cache"""
```

**Deliverable**: Complete REST API for configuration management

---

### Phase 4: Integrate with Health Server (1 hour)

#### File: `strategies/health/server.py` (UPDATE)

**Changes**:

1. **Import Configuration Router**
```python
from strategies.api.config_routes import router as config_router
from strategies.api.config_routes import set_config_manager
from strategies.services.config_manager import StrategyConfigManager
```

2. **Initialize Config Manager in Lifespan**
```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager"""
    # Startup
    logger.info("Starting health server with configuration API...")
    
    # Initialize configuration manager
    from strategies.db.mongodb_client import MongoDBClient
    import constants
    
    mongodb_uri = os.getenv("MONGODB_URI", constants.MONGODB_URI if hasattr(constants, "MONGODB_URI") else "mongodb://localhost:27017")
    mongodb_database = os.getenv("MONGODB_DATABASE", constants.MONGODB_DATABASE if hasattr(constants, "MONGODB_DATABASE") else "petrosa")
    
    mongodb_client = MongoDBClient(uri=mongodb_uri, database=mongodb_database)
    config_manager = StrategyConfigManager(
        mongodb_client=mongodb_client,
        cache_ttl_seconds=60
    )
    
    await config_manager.start()
    set_config_manager(config_manager)
    
    logger.info("✅ Configuration manager initialized")
    
    # Attach OTLP logging handler
    try:
        import otel_init
        otel_init.attach_logging_handler()
    except Exception as e:
        logger.warning(f"Failed to attach OTLP logging handler: {e}")
    
    yield
    
    # Shutdown
    await config_manager.stop()
    logger.info("Configuration manager stopped")
```

3. **Include Configuration Router**
```python
# In __init__ method after creating self.app
self.app.include_router(config_router)
```

4. **Update Service Info Endpoint**
```python
@self.app.get("/info")
async def info():
    """Service information with configuration API links"""
    return {
        "service": {
            "name": constants.SERVICE_NAME,
            "version": constants.SERVICE_VERSION,
            "description": "Stateless trading signal service with real-time configuration API",
        },
        "endpoints": {
            "health": "/healthz",
            "readiness": "/ready",
            "metrics": "/metrics",
            "info": "/info",
            "configuration_api": "/api/v1/strategies",
            "api_docs": "/docs",  # Automatic Swagger UI
        },
        "configuration": {
            "enabled_strategies": constants.get_enabled_strategies(),
            "config": constants.get_strategy_config(),
        },
        # ... rest of info
    }
```

**Deliverable**: Integrated configuration API into health server

---

### Phase 5: Update Strategy Loading (2 hours)

#### File: `strategies/core/consumer.py` (UPDATE)

**Current**: Strategies read from `constants.py` directly  
**Target**: Strategies read from `StrategyConfigManager`

**Changes**:

1. **Accept ConfigManager in Constructor**
```python
class NATSConsumer:
    def __init__(
        self,
        nats_url: str,
        topic: str,
        consumer_name: str,
        consumer_group: str,
        publisher: TradeOrderPublisher,
        config_manager: StrategyConfigManager,  # NEW
        logger: Optional[structlog.BoundLogger] = None,
    ):
        self.config_manager = config_manager
        # ... rest
```

2. **Load Strategy Configs Dynamically**
```python
async def _initialize_strategies(self):
    """Initialize strategies with dynamic configuration"""
    
    # Orderbook Skew
    if constants.STRATEGY_ENABLED_ORDERBOOK_SKEW:
        config = await self.config_manager.get_config("orderbook_skew")
        self.orderbook_skew_strategy = OrderbookSkewStrategy(
            config=config["parameters"],
            logger=self.logger
        )
        self.logger.info("Orderbook Skew Strategy enabled", config=config)
    
    # Trade Momentum
    if constants.STRATEGY_ENABLED_TRADE_MOMENTUM:
        config = await self.config_manager.get_config("trade_momentum")
        self.trade_momentum_strategy = TradeMomentumStrategy(
            config=config["parameters"],
            logger=self.logger
        )
        self.logger.info("Trade Momentum Strategy enabled", config=config)
    
    # Similar for other strategies...
```

3. **Periodic Config Refresh**
```python
async def _config_refresh_loop(self):
    """Periodically check for configuration updates"""
    while self.is_running:
        try:
            await asyncio.sleep(60)  # Check every minute (matches cache TTL)
            
            # Reload each enabled strategy config
            if self.orderbook_skew_strategy:
                config = await self.config_manager.get_config("orderbook_skew")
                self.orderbook_skew_strategy.update_config(config["parameters"])
                self.logger.debug("Refreshed orderbook_skew config")
            
            # Similar for other strategies...
            
        except Exception as e:
            self.logger.error(f"Config refresh error: {e}")
            await asyncio.sleep(10)
```

4. **Update Strategy Classes to Accept Config**

Each strategy class needs to:
- Accept `config` parameter in `__init__`
- Implement `update_config(config: Dict[str, Any])` method
- Use config values instead of hardcoded constants

**Example for OrderbookSkewStrategy**:
```python
class OrderbookSkewStrategy:
    def __init__(self, config: Dict[str, Any], logger):
        self.config = config
        self.logger = logger
        self._update_from_config()
    
    def _update_from_config(self):
        """Update internal state from config"""
        self.top_levels = self.config.get("top_levels", 5)
        self.buy_threshold = self.config.get("buy_threshold", 1.2)
        self.sell_threshold = self.config.get("sell_threshold", 0.8)
        # ... etc
    
    def update_config(self, config: Dict[str, Any]):
        """Update configuration at runtime"""
        self.config = config
        self._update_from_config()
        self.logger.info("Configuration updated", config=config)
    
    async def process(self, market_data):
        """Process using current config"""
        # Use self.top_levels, self.buy_threshold, etc.
```

**Deliverable**: Dynamic strategy configuration loading with runtime updates

---

### Phase 6: Add MongoDB Configuration (30 minutes)

#### File: `constants.py` (UPDATE)

**Add MongoDB Configuration**:

```python
# MongoDB Configuration
MONGODB_URI = os.getenv(
    "MONGODB_URI",
    "mongodb://localhost:27017"  # Default for local development
)
MONGODB_DATABASE = os.getenv(
    "MONGODB_DATABASE",
    "petrosa"  # Default database name
)
MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", "5000"))
```

#### File: `k8s/deployment.yaml` (UPDATE)

**Add MongoDB Connection from Existing Secret**:

```yaml
env:
  # ... existing env vars ...
  
  # MongoDB Configuration (from existing petrosa-sensitive-credentials)
  - name: MONGODB_URI
    valueFrom:
      secretKeyRef:
        name: petrosa-sensitive-credentials
        key: mongodb-uri
  - name: MONGODB_DATABASE
    value: "petrosa"
  - name: MONGODB_TIMEOUT_MS
    value: "5000"
```

**Deliverable**: MongoDB connection configuration

---

### Phase 7: Update Main Entry Point (30 minutes)

#### File: `strategies/main.py` (UPDATE)

**Initialize and Pass ConfigManager**:

```python
async def start(self):
    """Start the service."""
    self.logger.info("Starting Petrosa Realtime Strategies service")

    try:
        # Initialize MongoDB and Configuration Manager FIRST
        from strategies.db.mongodb_client import MongoDBClient
        from strategies.services.config_manager import StrategyConfigManager
        
        mongodb_client = MongoDBClient(
            uri=constants.MONGODB_URI,
            database=constants.MONGODB_DATABASE
        )
        
        config_manager = StrategyConfigManager(
            mongodb_client=mongodb_client,
            cache_ttl_seconds=60
        )
        await config_manager.start()
        self.logger.info("Configuration manager initialized")
        
        # Start health server with config manager
        self.health_server = HealthServer(
            port=constants.HEALTH_CHECK_PORT,
            logger=self.logger,
            consumer=None,
            publisher=None,
            heartbeat_manager=None,
            config_manager=config_manager,  # NEW
        )
        await self.health_server.start()
        
        # ... rest of startup (publisher, consumer) ...
        
        # Pass config_manager to consumer
        self.consumer = NATSConsumer(
            nats_url=constants.NATS_URL,
            topic=constants.NATS_CONSUMER_TOPIC,
            consumer_name=constants.NATS_CONSUMER_NAME,
            consumer_group=constants.NATS_CONSUMER_GROUP,
            publisher=self.publisher,
            config_manager=config_manager,  # NEW
            logger=self.logger,
        )
        await self.consumer.start()
        
        # ... rest
```

**Deliverable**: Integrated configuration manager into service startup

---

## Testing Plan

### Unit Tests

Create `tests/test_config_manager.py`:

```python
import pytest
from strategies.services.config_manager import StrategyConfigManager
from strategies.market_logic.defaults import get_strategy_defaults

@pytest.mark.asyncio
async def test_get_config_defaults():
    """Test that defaults are returned when no DB config exists"""
    manager = StrategyConfigManager()
    config = await manager.get_config("orderbook_skew")
    
    assert config["parameters"]["top_levels"] == 5
    assert config["source"] == "default"

@pytest.mark.asyncio
async def test_set_config_validation():
    """Test parameter validation"""
    manager = StrategyConfigManager()
    
    # Valid config
    success, config, errors = await manager.set_config(
        strategy_id="orderbook_skew",
        parameters={"top_levels": 10},
        changed_by="test"
    )
    assert success
    assert len(errors) == 0
    
    # Invalid config (out of range)
    success, config, errors = await manager.set_config(
        strategy_id="orderbook_skew",
        parameters={"top_levels": -5},  # Invalid
        changed_by="test"
    )
    assert not success
    assert len(errors) > 0

@pytest.mark.asyncio
async def test_config_caching():
    """Test that caching works correctly"""
    manager = StrategyConfigManager(cache_ttl_seconds=60)
    
    # First call (cache miss)
    config1 = await manager.get_config("orderbook_skew")
    
    # Second call (cache hit)
    config2 = await manager.get_config("orderbook_skew")
    
    assert config1 == config2
    assert config2["cache_hit"] == True

@pytest.mark.asyncio
async def test_audit_trail():
    """Test that audit trail is created"""
    manager = StrategyConfigManager()
    
    await manager.set_config(
        strategy_id="orderbook_skew",
        parameters={"top_levels": 8},
        changed_by="admin",
        reason="Testing audit"
    )
    
    audit = await manager.get_audit_trail("orderbook_skew", limit=1)
    assert len(audit) > 0
    assert audit[0].changed_by == "admin"
    assert audit[0].reason == "Testing audit"
```

### Integration Tests

Create `tests/test_api_integration.py`:

```python
import pytest
from fastapi.testclient import TestClient
from strategies.health.server import HealthServer

@pytest.fixture
def client():
    """Create test client"""
    server = HealthServer(port=8080)
    # Initialize with test config manager
    return TestClient(server.app)

def test_list_strategies(client):
    """Test GET /api/v1/strategies"""
    response = client.get("/api/v1/strategies")
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert len(data["data"]) >= 6  # All 6 strategies

def test_get_schema(client):
    """Test GET /api/v1/strategies/{id}/schema"""
    response = client.get("/api/v1/strategies/orderbook_skew/schema")
    assert response.status_code == 200
    data = response.json()
    assert "top_levels" in [p["name"] for p in data["data"]]

def test_update_config(client):
    """Test POST /api/v1/strategies/{id}/config"""
    response = client.post(
        "/api/v1/strategies/orderbook_skew/config",
        json={
            "parameters": {"top_levels": 10},
            "changed_by": "test_user",
            "reason": "Integration test"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == True
    assert data["data"]["parameters"]["top_levels"] == 10

def test_validation_error(client):
    """Test parameter validation errors"""
    response = client.post(
        "/api/v1/strategies/orderbook_skew/config",
        json={
            "parameters": {"invalid_param": "bad_value"},
            "changed_by": "test_user"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["success"] == False
    assert "error" in data
```

### Manual Testing

```bash
# 1. Start service locally
python -m strategies.main run

# 2. Test API endpoints
curl http://localhost:8080/api/v1/strategies
curl http://localhost:8080/api/v1/strategies/orderbook_skew/schema
curl http://localhost:8080/api/v1/strategies/orderbook_skew/config

# 3. Update configuration
curl -X POST http://localhost:8080/api/v1/strategies/orderbook_skew/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {"top_levels": 10, "buy_threshold": 1.5},
    "changed_by": "admin",
    "reason": "Testing new threshold"
  }'

# 4. Verify configuration is active (check logs for config reload)

# 5. Check audit trail
curl http://localhost:8080/api/v1/strategies/orderbook_skew/audit
```

---

## Deployment Plan

### Step 1: Deploy Code Changes

```bash
# Commit changes
git add .
git commit -m "Add API configuration to realtime-strategies"
git push origin main

# GitHub Actions will build and push Docker image
# Wait for build to complete
```

### Step 2: Update Kubernetes

**No ConfigMap changes needed** - environment variables remain as fallback

```bash
# Apply deployment (if manifest updated)
kubectl apply -f k8s/deployment.yaml \
  --kubeconfig=k8s/kubeconfig.yaml \
  -n petrosa-apps

# Rolling restart to pick up new image
kubectl rollout restart deployment/petrosa-realtime-strategies \
  -n petrosa-apps \
  --kubeconfig=k8s/kubeconfig.yaml

# Monitor rollout
kubectl rollout status deployment/petrosa-realtime-strategies \
  -n petrosa-apps \
  --kubeconfig=k8s/kubeconfig.yaml
```

### Step 3: Verify API is Working

```bash
# Get pod name
POD=$(kubectl get pods -n petrosa-apps \
  -l app=realtime-strategies \
  --kubeconfig=k8s/kubeconfig.yaml \
  -o jsonpath='{.items[0].metadata.name}')

# Port forward
kubectl port-forward -n petrosa-apps \
  --kubeconfig=k8s/kubeconfig.yaml \
  $POD 8080:8080 &

# Test API
curl http://localhost:8080/api/v1/strategies
curl http://localhost:8080/api/v1/strategies/orderbook_skew/config

# Stop port forward
kill %1
```

### Step 4: Test Configuration Update

```bash
# Update a strategy parameter
curl -X POST http://realtime-strategies-service:8080/api/v1/strategies/orderbook_skew/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {
      "buy_threshold": 1.3,
      "sell_threshold": 0.75
    },
    "changed_by": "admin",
    "reason": "Adjusting thresholds for current market conditions"
  }'

# Wait 60 seconds (cache TTL)

# Verify configuration is active by checking logs
kubectl logs -n petrosa-apps \
  --kubeconfig=k8s/kubeconfig.yaml \
  -l app=realtime-strategies \
  --tail=50 | grep "Configuration updated"
```

---

## Backward Compatibility

### Environment Variables Still Work

- All existing environment variables in ConfigMap continue to work
- They serve as defaults when no database configuration exists
- No breaking changes to existing deployments

### Migration Path

**Option 1: Gradual Migration**
1. Deploy new code with API
2. Continue using environment variables initially
3. Gradually move configurations to API/database
4. Remove environment variables when confident

**Option 2: Immediate API Usage**
1. Deploy new code
2. Immediately start using API for configuration
3. Keep environment variables as backup

**Recommended**: Option 1 (gradual migration) for safety

---

## Documentation Updates

### README.md Updates

Add section on API configuration:

```markdown
## Configuration Management

### Real-Time Configuration via API

The service now supports real-time configuration updates via REST API.

**Base URL**: `http://realtime-strategies-service:8080/api/v1`

**Quick Start**:
```bash
# List all strategies
curl http://service:8080/api/v1/strategies

# Get strategy schema
curl http://service:8080/api/v1/strategies/orderbook_skew/schema

# Update configuration
curl -X POST http://service:8080/api/v1/strategies/orderbook_skew/config \
  -H "Content-Type: application/json" \
  -d '{
    "parameters": {"buy_threshold": 1.3},
    "changed_by": "your_name",
    "reason": "Adjusting for market conditions"
  }'
```

**API Documentation**: Access Swagger UI at `http://service:8080/docs`

### Configuration Hierarchy

1. MongoDB Symbol-Specific (highest priority)
2. MongoDB Global
3. Environment Variables (backward compatibility)
4. Hardcoded Defaults (fallback)

### Environment Variables (Still Supported)

All existing environment variables continue to work as defaults.
```

---

## Success Criteria

### Functional Requirements

- ✅ All 6 strategies have complete defaults and schemas
- ✅ Configuration manager implements MongoDB persistence
- ✅ API endpoints return correct data
- ✅ Configuration updates take effect within 60 seconds
- ✅ Validation prevents invalid configurations
- ✅ Audit trail tracks all changes
- ✅ Backward compatibility with environment variables

### Non-Functional Requirements

- ✅ API response time < 100ms (cached)
- ✅ API response time < 500ms (database)
- ✅ No service downtime during configuration updates
- ✅ MongoDB connection failures degrade gracefully
- ✅ Cache hit rate > 90% after warmup

### Documentation Requirements

- ✅ All API endpoints documented
- ✅ README updated with API examples
- ✅ Migration guide provided
- ✅ OpenAPI/Swagger documentation available

---

## Risk Mitigation

### Risk 1: MongoDB Connection Failure

**Mitigation**:
- Graceful degradation to environment variables
- Connection retry with exponential backoff
- Health check detects MongoDB issues
- Service continues to function with cached/default configs

### Risk 2: Invalid Configuration Breaks Strategy

**Mitigation**:
- Schema-based validation before saving
- `validate_only` flag for testing
- Configuration versioning
- Audit trail for rollback
- Strategies validate config on load

### Risk 3: Cache Inconsistency

**Mitigation**:
- 60-second TTL matches other systems
- Force refresh endpoint available
- Background cache cleanup
- Cache key includes strategy + symbol

### Risk 4: Performance Impact

**Mitigation**:
- Caching reduces database calls
- Async operations don't block message processing
- Config refresh runs in background task
- MongoDB indexed for fast queries

---

## Timeline

### Day 1 (6 hours)
- **Morning**: Phase 1 + 2 (Defaults + Config Manager)
- **Afternoon**: Phase 3 (API Routes)

### Day 2 (6 hours)
- **Morning**: Phase 4 + 5 + 6 (Integration + Strategy Loading + MongoDB)
- **Afternoon**: Phase 7 + Testing + Documentation

### Total: 12 hours over 2 days

---

## Next Steps

1. **Review this plan** - Ensure all stakeholders agree
2. **Create feature branch** - `feature/api-configuration`
3. **Implement Phase 1** - Start with strategy defaults
4. **Iterative development** - Complete phases sequentially
5. **Test thoroughly** - Unit + integration + manual
6. **Deploy to production** - Follow deployment plan
7. **Monitor closely** - Watch for issues in first 24 hours
8. **Document lessons learned** - Update this plan

---

## Questions & Answers

**Q: Will this require changes to existing deployment?**  
A: Minimal changes. Only need to ensure MongoDB connection secret is available.

**Q: What happens if MongoDB is down?**  
A: Service continues with environment variables and cached configs. No downtime.

**Q: How do we roll back a bad configuration?**  
A: Use audit trail to see previous config, then POST the old values back.

**Q: Can we test configuration changes before applying?**  
A: Yes, use `validate_only: true` flag in the request.

**Q: Will this slow down message processing?**  
A: No, configuration is loaded once and cached. Message processing unaffected.

**Q: How do we know when a configuration update takes effect?**  
A: Check logs for "Configuration updated" messages. Max 60 seconds (cache TTL).

---

## References

- **TA Bot Config Manager**: `/Users/yurisa2/petrosa/petrosa-bot-ta-analysis/ta_bot/services/config_manager.py`
- **TA Bot API Routes**: `/Users/yurisa2/petrosa/petrosa-bot-ta-analysis/ta_bot/api/config_routes.py`
- **TradeEngine Config Manager**: `/Users/yurisa2/petrosa/petrosa-tradeengine/tradeengine/config_manager.py`
- **TradeEngine API Routes**: `/Users/yurisa2/petrosa/petrosa-tradeengine/tradeengine/api_config_routes.py`
- **MongoDB Client (existing)**: `/Users/yurisa2/petrosa/petrosa-realtime-strategies/strategies/db/mongodb_client.py`

---

**Document Version**: 1.0  
**Last Updated**: 2025-10-21  
**Author**: AI Assistant  
**Status**: Ready for Implementation

