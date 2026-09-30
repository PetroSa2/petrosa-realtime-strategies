from unittest.mock import MagicMock

from strategies.utils.metrics import RealtimeStrategyMetrics


def test_realtime_catalog_uses_only_bounded_metric_labels(monkeypatch):
    meter = MagicMock()
    meter.create_counter.return_value = MagicMock()
    meter.create_histogram.return_value = MagicMock()
    monkeypatch.setattr("strategies.utils.metrics.get_meter", lambda name: meter)

    metrics = RealtimeStrategyMetrics()
    metrics.record_message_processed("BTCUSDT", "depth")
    metrics.record_message_latency(25, "depth")

    counter_attrs = meter.create_counter.return_value.add.call_args.kwargs["attributes"]
    histogram_attrs = meter.create_histogram.return_value.record.call_args.kwargs[
        "attributes"
    ]
    assert set(counter_attrs) == {"stream", "outcome"}
    assert set(histogram_attrs) == {"stream"}
    assert {call.kwargs["name"] for call in meter.create_counter.call_args_list} == {
        "petrosa_realtime_messages_total"
    }
    assert {call.kwargs["name"] for call in meter.create_histogram.call_args_list} == {
        "petrosa_realtime_lag_seconds"
    }


def test_summary_has_fixed_window_and_no_unbounded_fields(monkeypatch):
    meter = MagicMock()
    meter.create_counter.return_value = MagicMock()
    meter.create_histogram.return_value = MagicMock()
    monkeypatch.setattr("strategies.utils.metrics.get_meter", lambda name: meter)

    metrics = RealtimeStrategyMetrics()
    metrics.record_message_processed("BTCUSDT", "depth")
    summary = metrics.summary()

    assert summary["event"] == "SUMMARY"
    assert summary["window_seconds"] == 300
    assert summary["service"] == "petrosa-realtime-strategies"
    assert summary["outcomes"]["processed"] == 1
    assert set(summary) == {
        "event",
        "window_seconds",
        "service",
        "messages",
        "outcomes",
        "latency_seconds_p50",
        "latency_seconds_p95",
    }
