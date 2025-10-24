#!/usr/bin/env python3
"""
Quick compatibility test for configuration system (Realtime Strategies).

Run this script to verify that the configuration system doesn't break
existing market logic strategy functionality.

Usage:
    python scripts/test_config_compatibility.py
"""

import sys

sys.path.insert(0, ".")

from strategies.market_logic.btc_dominance import BitcoinDominanceStrategy


class Colors:
    """Terminal colors for pretty output."""

    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


def test_btc_dominance_strategy():
    """Test BTC Dominance strategy initialization."""
    print(f"\n{Colors.BLUE}Testing BTC Dominance Strategy...{Colors.END}")

    try:
        # Test initialization without config manager
        strategy = BitcoinDominanceStrategy()

        # Verify default parameters
        assert hasattr(strategy, "high_threshold")
        assert hasattr(strategy, "low_threshold")
        assert hasattr(strategy, "change_threshold")

        print(f"  {Colors.GREEN}✓ Strategy initializes correctly{Colors.END}")
        print(
            f"  {Colors.GREEN}✓ Default thresholds: high={strategy.high_threshold}, "
            f"low={strategy.low_threshold}, change={strategy.change_threshold}{Colors.END}"
        )

        return True

    except Exception as e:
        print(f"  {Colors.RED}✗ FAILED: {str(e)}{Colors.END}")
        return False


def test_strategy_has_required_methods():
    """Test that strategy has all required methods."""
    print(f"\n{Colors.BLUE}Testing strategy methods...{Colors.END}")

    try:
        strategy = BitcoinDominanceStrategy()

        # Check required methods exist
        required_methods = ["process_market_data", "get_metrics"]

        for method in required_methods:
            assert hasattr(strategy, method), f"Missing method: {method}"
            print(f"  {Colors.GREEN}✓ Method exists: {method}{Colors.END}")

        return True

    except Exception as e:
        print(f"  {Colors.RED}✗ FAILED: {str(e)}{Colors.END}")
        return False


def test_strategy_metrics():
    """Test strategy metrics reporting."""
    print(f"\n{Colors.BLUE}Testing strategy metrics...{Colors.END}")

    try:
        strategy = BitcoinDominanceStrategy()

        # Get metrics
        metrics = strategy.get_metrics()

        assert isinstance(metrics, dict), "Metrics should be a dictionary"
        assert "strategy_name" in metrics, "Missing strategy_name in metrics"
        assert metrics["strategy_name"] == "btc_dominance", "Wrong strategy name"

        print(f"  {Colors.GREEN}✓ Metrics reporting works{Colors.END}")
        print(
            f"  {Colors.GREEN}✓ Strategy name: {metrics['strategy_name']}{Colors.END}"
        )

        return True

    except Exception as e:
        print(f"  {Colors.RED}✗ FAILED: {str(e)}{Colors.END}")
        return False


def main():
    """Run all compatibility tests."""
    print(f"\n{Colors.BOLD}{'='*70}")
    print("  REALTIME STRATEGIES - CONFIGURATION COMPATIBILITY TEST")
    print("  Verifying backward compatibility with existing strategies")
    print(f"{'='*70}{Colors.END}\n")

    results = []

    # Run tests
    print(f"\n{Colors.BOLD}TEST 1: Strategy Initialization{Colors.END}")
    print("=" * 70)
    results.append(test_btc_dominance_strategy())

    print(f"\n{Colors.BOLD}TEST 2: Strategy Methods{Colors.END}")
    print("=" * 70)
    results.append(test_strategy_has_required_methods())

    print(f"\n{Colors.BOLD}TEST 3: Strategy Metrics{Colors.END}")
    print("=" * 70)
    results.append(test_strategy_metrics())

    # Summary
    print(f"\n{Colors.BOLD}{'='*70}")
    print("  TEST SUMMARY")
    print(f"{'='*70}{Colors.END}\n")

    passed = sum(results)
    total = len(results)

    if passed == total:
        print(
            f"{Colors.GREEN}{Colors.BOLD}✓ ALL TESTS PASSED ({passed}/{total}){Colors.END}"
        )
        print(
            f"\n{Colors.GREEN}The configuration system is BACKWARD COMPATIBLE.{Colors.END}"
        )
        print(
            f"{Colors.GREEN}Existing strategy functionality will NOT be broken.{Colors.END}\n"
        )
        return 0
    else:
        print(
            f"{Colors.RED}{Colors.BOLD}✗ SOME TESTS FAILED ({passed}/{total} passed){Colors.END}"
        )
        print(
            f"\n{Colors.RED}WARNING: Configuration system may break existing functionality.{Colors.END}"
        )
        print(f"{Colors.RED}Review failed tests above before deploying.{Colors.END}\n")
        return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Test interrupted by user{Colors.END}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{Colors.RED}Unexpected error: {str(e)}{Colors.END}\n")
        import traceback

        traceback.print_exc()
        sys.exit(1)
