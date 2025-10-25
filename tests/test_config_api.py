"""
Tests for Configuration API.

Tests the configuration management system including:
- Configuration manager
- API endpoints
- Parameter validation
- Caching
- Audit trail
"""


import pytest

from strategies.market_logic.defaults import get_strategy_defaults, validate_parameters
from strategies.services.config_manager import StrategyConfigManager


class TestConfigManager:
    """Test suite for StrategyConfigManager."""

    @pytest.mark.asyncio
    async def test_get_config_defaults(self):
        """Test that defaults are returned when no DB config exists."""
        manager = StrategyConfigManager()
        await manager.start()

        try:
            config = await manager.get_config("orderbook_skew")

            assert config["parameters"]["top_levels"] == 5
            assert config["parameters"]["buy_threshold"] == 1.2
            assert config["source"] in ["default", "environment"]
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_validate_parameters_valid(self):
        """Test parameter validation with valid parameters."""
        valid_params = {
            "top_levels": 10,
            "buy_threshold": 1.5,
            "sell_threshold": 0.7,
        }

        is_valid, errors = validate_parameters("orderbook_skew", valid_params)

        assert is_valid
        assert len(errors) == 0

    @pytest.mark.asyncio
    async def test_validate_parameters_invalid_range(self):
        """Test parameter validation with out-of-range values."""
        invalid_params = {
            "top_levels": -5,  # Invalid: min is 1
        }

        is_valid, errors = validate_parameters("orderbook_skew", invalid_params)

        assert not is_valid
        assert len(errors) > 0
        assert "must be >=" in errors[0]

    @pytest.mark.asyncio
    async def test_validate_parameters_invalid_type(self):
        """Test parameter validation with wrong type."""
        invalid_params = {
            "top_levels": "invalid",  # Should be int
        }

        is_valid, errors = validate_parameters("orderbook_skew", invalid_params)

        assert not is_valid
        assert len(errors) > 0
        assert "must be an integer" in errors[0]

    @pytest.mark.asyncio
    async def test_config_caching(self):
        """Test that caching works correctly."""
        manager = StrategyConfigManager(cache_ttl_seconds=60)
        await manager.start()

        try:
            # First call (cache miss)
            config1 = await manager.get_config("orderbook_skew")

            # Second call (cache hit)
            config2 = await manager.get_config("orderbook_skew")

            # Should return same data
            assert config1["parameters"] == config2["parameters"]

            # Second call should be from cache
            # (we can't directly check cache_hit without modifying returned data)
        finally:
            await manager.stop()

    @pytest.mark.asyncio
    async def test_all_strategies_have_defaults(self):
        """Test that all strategies have defaults configured."""
        from strategies.market_logic.defaults import list_all_strategies

        all_strategies = list_all_strategies()

        # Should have all 8 strategies (including microstructure strategies)
        assert len(all_strategies) == 8
        assert "orderbook_skew" in all_strategies
        assert "trade_momentum" in all_strategies
        assert "ticker_velocity" in all_strategies
        assert "btc_dominance" in all_strategies
        assert "cross_exchange_spread" in all_strategies
        assert "onchain_metrics" in all_strategies
        assert "iceberg_detector" in all_strategies
        assert "spread_liquidity" in all_strategies

        # Each should have defaults
        for strategy_id in all_strategies:
            defaults = get_strategy_defaults(strategy_id)
            assert len(defaults) > 0


class TestParameterSchemas:
    """Test suite for parameter schemas."""

    def test_orderbook_skew_schema(self):
        """Test orderbook_skew strategy schema."""
        from strategies.market_logic.defaults import get_parameter_schema

        schema = get_parameter_schema("orderbook_skew")

        assert "top_levels" in schema
        assert schema["top_levels"]["type"] == "int"
        assert schema["top_levels"]["min"] == 1
        assert schema["top_levels"]["max"] == 20

    def test_trade_momentum_schema(self):
        """Test trade_momentum strategy schema."""
        from strategies.market_logic.defaults import get_parameter_schema

        schema = get_parameter_schema("trade_momentum")

        assert "price_weight" in schema
        assert schema["price_weight"]["type"] == "float"
        assert schema["price_weight"]["min"] == 0.0
        assert schema["price_weight"]["max"] == 1.0

    def test_ticker_velocity_schema(self):
        """Test ticker_velocity strategy schema."""
        from strategies.market_logic.defaults import get_parameter_schema

        schema = get_parameter_schema("ticker_velocity")

        assert "time_window" in schema
        assert schema["time_window"]["type"] == "int"
        assert "volume_confirmation" in schema
        assert schema["volume_confirmation"]["type"] == "bool"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
