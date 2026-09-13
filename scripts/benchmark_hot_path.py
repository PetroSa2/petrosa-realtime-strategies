#!/usr/bin/env python3
"""Micro-benchmark for the message-processing hot path (#191 AC5).

Replays a fixed, seeded sequence of synthetic Binance-shaped depth messages
through `NATSConsumer._process_message` (the exact per-message entrypoint
that drives `_update_processing_metrics`, `DepthAnalyzer.analyze_depth`, the
microstructure strategies, and `OrderBookTracker.update_orderbook`) and
reports wall time.

This is a deterministic replay, not a live measurement: `kubectl top` across
several load-balanced pods is too noisy to attribute a delta to one code
change vs. market-volume variance (see #191's own "Measurement discipline"
note). Same seed + same message count => directly comparable before/after
numbers.

Usage:
    python scripts/benchmark_hot_path.py [--count 10000] [--seed 191]

To produce a real before/after comparison, run this script against two
checkouts (e.g. `git stash` / `git stash pop`, or two worktrees) with
identical --count/--seed and diff the reported `per_message_us`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

# Allow running as `python scripts/benchmark_hot_path.py` from the repo root
# without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("OTEL_NO_AUTO_INIT", "1")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from strategies.core.consumer import NATSConsumer  # noqa: E402
from strategies.core.publisher import TradeOrderPublisher  # noqa: E402
from strategies.utils.logger import setup_logging  # noqa: E402

# Silence structured logging so console I/O doesn't dominate the timing --
# only the hot-path CPU cost is being measured here.
setup_logging(level="CRITICAL")


def _make_depth_payload(symbol: str, seq: int) -> bytes:
    """Build one Binance Futures @depth20-shaped update (b/a short keys --
    the live wire format per #188's fix; see `_transform_depth_data`)."""
    mid = 50000.0 * (1 + random.uniform(-0.001, 0.001))
    spread_bps = random.uniform(5, 15)

    # DepthLevel requires string price/quantity (see
    # strategies/models/market_data.py) -- the live Binance WS payload is
    # JSON strings, not floats.
    bids = [
        [
            str(round(mid * (1 - spread_bps / 10000 - j * 0.0001), 2)),
            str(round(random.uniform(0.5, 3.0), 4)),
        ]
        for j in range(5)
    ]
    asks = [
        [
            str(round(mid * (1 + spread_bps / 10000 + j * 0.0001), 2)),
            str(round(random.uniform(0.5, 3.0), 4)),
        ]
        for j in range(5)
    ]

    payload = {
        "stream": f"{symbol.lower()}@depth20",
        "data": {
            "s": symbol,
            "E": int(time.time() * 1000) + seq,
            "U": seq,
            "u": seq,
            "b": bids,
            "a": asks,
        },
    }
    return json.dumps(payload).encode()


def _build_consumer() -> NATSConsumer:
    """A NATSConsumer wired exactly like the `consumer` fixture in
    tests/test_consumer.py -- no real NATS connection required for
    `_process_message`."""
    publisher = Mock(spec=TradeOrderPublisher)
    publisher.publish_signal = AsyncMock()
    publisher.publish_order = AsyncMock()
    return NATSConsumer(
        nats_url="nats://benchmark:4222",
        topic="benchmark.topic",
        consumer_name="benchmark-consumer",
        consumer_group="benchmark-group",
        publisher=publisher,
    )


async def run_benchmark(count: int, seed: int, symbols: int) -> float:
    """Replay `count` depth messages across `symbols` distinct symbols and
    return total elapsed wall-clock seconds."""
    random.seed(seed)
    consumer = _build_consumer()
    symbol_names = [f"SYM{i:02d}USDT" for i in range(symbols)]

    messages = [_make_depth_payload(symbol_names[i % symbols], i) for i in range(count)]

    start = time.perf_counter()
    for data in messages:
        msg = Mock()
        msg.data = data
        await consumer._process_message(msg)
    return time.perf_counter() - start


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count", type=int, default=10000, help="Number of depth messages to replay"
    )
    parser.add_argument("--seed", type=int, default=191, help="Random seed")
    parser.add_argument(
        "--symbols",
        type=int,
        default=5,
        help="Number of distinct symbols to round-robin across",
    )
    args = parser.parse_args()

    elapsed = asyncio.run(run_benchmark(args.count, args.seed, args.symbols))
    per_message_us = (elapsed / args.count) * 1_000_000

    print(
        f"messages={args.count} symbols={args.symbols} seed={args.seed} "
        f"total_seconds={elapsed:.4f} per_message_us={per_message_us:.2f}"
    )


if __name__ == "__main__":
    main()
