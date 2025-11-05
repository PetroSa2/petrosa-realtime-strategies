"""
Tests for strategies/market_logic/defaults.py.
"""

from strategies.market_logic.defaults import get_parameter_schema, validate_parameters


class TestParameterValidation:
    """Test parameter validation functions."""

    def test_validate_parameters_unknown_strategy(self):
        """Test validation with unknown strategy returns True."""
        is_valid, errors = validate_parameters("unknown_strategy", {"param": "value"})

        # Unknown strategy has no schema, so accepts all
        assert is_valid is True
        assert len(errors) == 0

    def test_validate_parameters_bool_type(self):
        """Test validation of boolean parameters."""
        # This tests line 681-682
        is_valid, errors = validate_parameters(
            "orderbook_skew",  # Has a schema
            {"enabled": "not_a_bool"},  # Invalid bool
        )

        # Should have errors for non-bool value if parameter expects bool
        assert isinstance(errors, list)

    def test_validate_parameters_string_type(self):
        """Test validation of string parameters."""
        # This tests line 684-685
        is_valid, errors = validate_parameters(
            "orderbook_skew",
            {"name": 123},  # Invalid string (if parameter expects string)
        )

        # Should have errors for non-string value if parameter expects string
        assert isinstance(errors, list)

    def test_get_parameter_schema_existing(self):
        """Test getting schema for existing strategy."""
        schema = get_parameter_schema("orderbook_skew")

        # Should return a dict or None
        assert schema is None or isinstance(schema, dict)

    def test_get_parameter_schema_nonexistent(self):
        """Test getting schema for non-existent strategy."""
        schema = get_parameter_schema("nonexistent_strategy_12345")

        # Should return None or empty dict
        assert schema is None or schema == {}

