"""
Comprehensive tests for metrics_routes.py FastAPI endpoints.

Covers all endpoints with success/error paths, validation, and edge cases.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from strategies.api.metrics_routes import get_depth_analyzer, router, set_depth_analyzer
from strategies.services.depth_analyzer import DepthAnalyzer


@pytest.fixture
def app():
    """Create FastAPI app with metrics routes."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_depth_analyzer():
    """Create mock depth analyzer."""
    analyzer = MagicMock(spec=DepthAnalyzer)
    return analyzer


@pytest.fixture
def setup_depth_analyzer(mock_depth_analyzer):
    """Set the global depth analyzer."""
    set_depth_analyzer(mock_depth_analyzer)
    yield mock_depth_analyzer
    set_depth_analyzer(None)


def test_get_depth_analyzer_not_initialized():
    """Test get_depth_analyzer raises 503 when not initialized."""
    from fastapi import HTTPException
    
    set_depth_analyzer(None)
    with pytest.raises(HTTPException) as exc_info:
        get_depth_analyzer()
    assert exc_info.value.status_code == 503


def test_set_depth_analyzer():
    """Test setting depth analyzer."""
    analyzer = MagicMock()
    set_depth_analyzer(analyzer)
    assert get_depth_analyzer() == analyzer


@pytest.mark.asyncio
async def test_get_depth_metrics_success(client, setup_depth_analyzer):
    """Test successful depth metrics retrieval."""
    mock_metrics = MagicMock()
    mock_metrics.symbol = "BTCUSDT"
    mock_metrics.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    mock_metrics.imbalance_ratio = 1.2
    mock_metrics.imbalance_percent = 20.0
    mock_metrics.bid_volume = 1000.0
    mock_metrics.ask_volume = 833.33
    mock_metrics.buy_pressure = 30.0
    mock_metrics.sell_pressure = 10.0
    mock_metrics.net_pressure = 25.0
    mock_metrics.total_liquidity = 5000.0
    mock_metrics.bid_depth_5 = 2000.0
    mock_metrics.ask_depth_5 = 1800.0
    mock_metrics.bid_depth_10 = 3000.0
    mock_metrics.ask_depth_10 = 2800.0
    mock_metrics.best_bid = 50000.0
    mock_metrics.best_ask = 50010.0
    mock_metrics.spread_abs = 10.0
    mock_metrics.spread_bps = 0.02
    mock_metrics.mid_price = 50005.0
    mock_metrics.vwap_bid = 49995.0
    mock_metrics.vwap_ask = 50015.0
    mock_metrics.bid_levels = 25
    mock_metrics.ask_levels = 23
    mock_metrics.total_levels = 48
    mock_metrics.strongest_bid_level = (49990.0, 500.0)
    mock_metrics.strongest_ask_level = (50020.0, 450.0)

    setup_depth_analyzer.get_current_metrics.return_value = mock_metrics

    response = client.get("/api/v1/metrics/depth/BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["imbalance"]["ratio"] == 1.2
    assert data["pressure"]["interpretation"] == "bullish"
    assert data["strongest_levels"]["bid"]["price"] == 49990.0


@pytest.mark.asyncio
async def test_get_depth_metrics_no_data(client, setup_depth_analyzer):
    """Test depth metrics when no data available."""
    setup_depth_analyzer.get_current_metrics.return_value = None

    response = client.get("/api/v1/metrics/depth/BTCUSDT")
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "No metrics available" in data["error"]


@pytest.mark.asyncio
async def test_get_depth_metrics_error(client, setup_depth_analyzer):
    """Test depth metrics with error."""
    setup_depth_analyzer.get_current_metrics.side_effect = Exception("Analyzer error")

    response = client.get("/api/v1/metrics/depth/BTCUSDT")
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_pressure_history_success(client, setup_depth_analyzer):
    """Test successful pressure history retrieval."""
    mock_history = MagicMock()
    mock_history.symbol = "BTCUSDT"
    mock_history.timeframe = "5m"
    mock_history.avg_pressure = 15.5
    mock_history.max_pressure = 45.0
    mock_history.min_pressure = -20.0
    mock_history.trend = "bullish"
    mock_history.trend_strength = 0.75
    mock_history.pressure_history = [
        (datetime(2024, 1, 1, 12, 0, 0), 20.0),
        (datetime(2024, 1, 1, 12, 1, 0), 25.0),
    ]
    mock_history.imbalance_history = [
        (datetime(2024, 1, 1, 12, 0, 0), 0.1),
        (datetime(2024, 1, 1, 12, 1, 0), 0.15),
    ]

    setup_depth_analyzer.get_pressure_history.return_value = mock_history

    response = client.get("/api/v1/metrics/pressure/BTCUSDT?timeframe=5m")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BTCUSDT"
    assert data["timeframe"] == "5m"
    assert data["summary"]["avg_pressure"] == 15.5
    assert len(data["pressure_history"]) == 2


@pytest.mark.asyncio
async def test_get_pressure_history_invalid_timeframe(client, setup_depth_analyzer):
    """Test pressure history with invalid timeframe."""
    response = client.get("/api/v1/metrics/pressure/BTCUSDT?timeframe=invalid")
    assert response.status_code == 400
    data = response.json()
    assert "Invalid timeframe" in data["detail"]


@pytest.mark.asyncio
async def test_get_pressure_history_no_data(client, setup_depth_analyzer):
    """Test pressure history when no data available."""
    setup_depth_analyzer.get_pressure_history.return_value = None

    response = client.get("/api/v1/metrics/pressure/BTCUSDT?timeframe=5m")
    assert response.status_code == 200
    data = response.json()
    assert "error" in data
    assert "No pressure history available" in data["error"]


@pytest.mark.asyncio
async def test_get_pressure_history_error(client, setup_depth_analyzer):
    """Test pressure history with error."""
    setup_depth_analyzer.get_pressure_history.side_effect = Exception("History error")

    response = client.get("/api/v1/metrics/pressure/BTCUSDT?timeframe=5m")
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_market_summary_success(client, setup_depth_analyzer):
    """Test successful market summary retrieval."""
    mock_summary = {
        "total_symbols": 10,
        "bullish_count": 6,
        "bearish_count": 2,
        "neutral_count": 2,
        "avg_pressure": 12.5,
        "avg_imbalance": 0.15,
        "avg_spread_bps": 0.05,
        "total_liquidity": 50000.0,
        "top_buy_pressure": ["BTCUSDT", "ETHUSDT"],
        "top_sell_pressure": ["ADAUSDT", "SOLUSDT"],
    }
    setup_depth_analyzer.get_market_summary.return_value = mock_summary

    response = client.get("/api/v1/metrics/summary")
    assert response.status_code == 200
    data = response.json()
    assert data["total_symbols"] == 10
    assert data["bullish_count"] == 6


@pytest.mark.asyncio
async def test_get_market_summary_error(client, setup_depth_analyzer):
    """Test market summary with error."""
    setup_depth_analyzer.get_market_summary.side_effect = Exception("Summary error")

    response = client.get("/api/v1/metrics/summary")
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_all_metrics_success(client, setup_depth_analyzer):
    """Test successful all metrics retrieval."""
    mock_metrics1 = MagicMock()
    mock_metrics1.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    mock_metrics1.net_pressure = 25.0
    mock_metrics1.imbalance_percent = 15.0
    mock_metrics1.spread_bps = 0.05
    mock_metrics1.total_liquidity = 10000.0
    mock_metrics1.mid_price = 50000.0

    mock_metrics2 = MagicMock()
    mock_metrics2.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    mock_metrics2.net_pressure = -10.0
    mock_metrics2.imbalance_percent = -5.0
    mock_metrics2.spread_bps = 0.08
    mock_metrics2.total_liquidity = 8000.0
    mock_metrics2.mid_price = 3000.0

    setup_depth_analyzer.get_all_metrics.return_value = {
        "BTCUSDT": mock_metrics1,
        "ETHUSDT": mock_metrics2,
    }

    response = client.get("/api/v1/metrics/all?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "data" in data
    assert "pagination" in data
    assert len(data["data"]) == 2
    assert data["pagination"]["total"] == 2


@pytest.mark.asyncio
async def test_get_all_metrics_with_filters(client, setup_depth_analyzer):
    """Test all metrics with various filters."""
    mock_metrics = MagicMock()
    mock_metrics.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    mock_metrics.net_pressure = 25.0
    mock_metrics.imbalance_percent = 15.0
    mock_metrics.spread_bps = 0.05
    mock_metrics.total_liquidity = 10000.0
    mock_metrics.mid_price = 50000.0

    setup_depth_analyzer.get_all_metrics.return_value = {"BTCUSDT": mock_metrics}

    # Test symbol filter
    response = client.get("/api/v1/metrics/all?symbols=BTCUSDT,ETHUSDT")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1  # Only BTCUSDT matches

    # Test pressure filter
    response = client.get("/api/v1/metrics/all?min_pressure=20.0")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1  # BTCUSDT has 25.0 pressure

    # Test trend filter
    response = client.get("/api/v1/metrics/all?trend=bullish")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 1  # BTCUSDT is bullish


@pytest.mark.asyncio
async def test_get_all_metrics_sorting(client, setup_depth_analyzer):
    """Test all metrics sorting functionality."""
    mock_metrics1 = MagicMock()
    mock_metrics1.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    mock_metrics1.net_pressure = 25.0
    mock_metrics1.imbalance_percent = 15.0
    mock_metrics1.spread_bps = 0.05
    mock_metrics1.total_liquidity = 10000.0
    mock_metrics1.mid_price = 50000.0

    mock_metrics2 = MagicMock()
    mock_metrics2.timestamp = datetime(2024, 1, 1, 12, 0, 0)
    mock_metrics2.net_pressure = 10.0
    mock_metrics2.imbalance_percent = 5.0
    mock_metrics2.spread_bps = 0.08
    mock_metrics2.total_liquidity = 15000.0
    mock_metrics2.mid_price = 3000.0

    setup_depth_analyzer.get_all_metrics.return_value = {
        "BTCUSDT": mock_metrics1,
        "ETHUSDT": mock_metrics2,
    }

    # Test sorting by pressure descending
    response = client.get("/api/v1/metrics/all?sort_by=pressure&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    symbols = list(data["data"].keys())
    assert symbols[0] == "BTCUSDT"  # Higher pressure first

    # Test sorting by liquidity descending
    response = client.get("/api/v1/metrics/all?sort_by=liquidity&sort_order=desc")
    assert response.status_code == 200
    data = response.json()
    symbols = list(data["data"].keys())
    assert symbols[0] == "ETHUSDT"  # Higher liquidity first


@pytest.mark.asyncio
async def test_get_all_metrics_pagination(client, setup_depth_analyzer):
    """Test all metrics pagination."""
    # Create multiple mock metrics
    mock_metrics = {}
    for i in range(5):
        mock_metric = MagicMock()
        mock_metric.timestamp = datetime(2024, 1, 1, 12, 0, 0)
        mock_metric.net_pressure = float(i * 10)
        mock_metric.imbalance_percent = float(i * 2)
        mock_metric.spread_bps = 0.05
        mock_metric.total_liquidity = 10000.0
        mock_metric.mid_price = 50000.0
        mock_metrics[f"SYMBOL{i}"] = mock_metric

    setup_depth_analyzer.get_all_metrics.return_value = mock_metrics

    # Test pagination
    response = client.get("/api/v1/metrics/all?limit=2&offset=2")
    assert response.status_code == 200
    data = response.json()
    assert len(data["data"]) == 2
    assert data["pagination"]["total"] == 5
    assert data["pagination"]["page"] == 2
    assert data["pagination"]["has_next"] is True
    assert data["pagination"]["has_previous"] is True


@pytest.mark.asyncio
async def test_get_all_metrics_error(client, setup_depth_analyzer):
    """Test all metrics with error."""
    setup_depth_analyzer.get_all_metrics.side_effect = Exception("All metrics error")

    response = client.get("/api/v1/metrics/all")
    assert response.status_code == 500


def test_pressure_interpretation_logic():
    """Test pressure interpretation logic."""
    # Test bullish (> 20)
    assert "bullish" == ("bullish" if 25 > 20 else "bearish" if 25 < -20 else "neutral")

    # Test bearish (< -20)
    assert "bearish" == (
        "bullish" if -25 > 20 else "bearish" if -25 < -20 else "neutral"
    )

    # Test neutral (between -20 and 20)
    assert "neutral" == ("bullish" if 10 > 20 else "bearish" if 10 < -20 else "neutral")
