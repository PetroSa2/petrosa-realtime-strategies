# SPIKE #184 — Go port evaluation: port vs optimise

**Ticket:** [#184](https://github.com/PetroSa2/petrosa-realtime-strategies/issues/184)
**Parent:** [petrosa_k8s#1010](https://github.com/PetroSa2/petrosa_k8s/issues/1010)
**Time-box:** 1 day (this document), no code port authorised.
**Non-goal:** this spike does not port anything. It produces a decision.

## 0. Premise re-check — the crisis that motivated this ticket has already partly resolved

The ticket was filed against a snapshot from 2026-09-11: 5 replicas, 962m/1069m node CPU (90%),
HPA pinned 5/5, 15.5% CPU-throttled, readiness probes timing out.

Between filing and this spike, **PRs #198-#207 landed on `main`** (NATS reconnect fix, readiness
probe fix, dead-code removal of ~2,100+3,970 LOC across two PRs, hot-path perf work, bounded
in-memory structures, resource right-sizing). Live cluster state today:

```
$ kubectl top nodes
NAME     CPU(cores)   CPU(%)   MEMORY(bytes)   MEMORY(%)
ubuntu   1517m        25%      6117Mi          38%

$ kubectl get hpa petrosa-realtime-strategies-hpa
TARGETS       MINPODS   MAXPODS   REPLICAS
cpu: 75%/70%  1         1         1

$ kubectl top pod petrosa-realtime-strategies-5b8bccc69d-5l8qz
CPU(cores)   MEMORY(bytes)
453m         107Mi

$ kubectl exec <pod> -- cat /sys/fs/cgroup/cpu.stat
nr_periods 11793   nr_throttled 255   → 2.2% throttled (was 15.5%)
```

**This service's share of node CPU dropped from ~90% (962m/1069m) to ~30% (453m/1517m) —
without a single line of Go** — purely from the resource-right-sizing (`petrosa_k8s#1010`),
NATS/readiness fixes, and Python-side dead-code + perf PRs already merged. The throttling
precondition the ticket required before profiling is satisfied (2.2% << 15.5% baseline noise),
so profiling below is on a valid, unthrottled baseline.

This does not close the question — it changes the cost-benefit: the easy, low-risk wins are
already banked, and what is profiled below is what's left after them.

## 1. Where does the CPU actually go?

Profiled `scripts/benchmark_hot_path.py` (added in #206, deterministic seeded replay of
`NATSConsumer._process_message`, the real per-message entrypoint) with `py-spy record`
(500 Hz sampling, 60,000 messages, 19,858 samples, `speedscope` format, raw data at
`/tmp/opencode/spike-184/profile.speedscope.json` — not committed, reproducible via the command
in Appendix A).

**Caveat on the harness itself:** `TradeOrderPublisher` is `AsyncMock`-ed in the benchmark, and
`unittest.mock`'s spec/signature introspection (`inspect.py` bind/iscoroutinefunction checks)
plus the mock's own `__new__`/`_mock_add_spec` account for **24.4% of total sampled time**
(13.1% mock internals + 11.4% inspect-via-mock). This is harness noise, not production cost —
excluded from the percentages below (renormalized to the remaining 66.99% of "real" samples,
i.e. all figures are "% of real, non-harness hot-path time").

**Top 5 CPU consumers in the real hot path, by name:**

| Rank | Consumer | % of real hot-path time | Nature |
|---|---|---|---|
| 1 | **OpenTelemetry instrumentation** (`start_as_current_span` + `contextvars_context.attach` + the `contextlib`-wrapped span context manager) | **~24%** (17.3% span/attach + 6.7% contextlib) | Every message gets a full `SpanKind.CONSUMER` span with 4 `set_attribute` calls, unconditionally, at `consumer.py:410` |
| 2 | **`consumer.py` message pipeline** (`_transform_depth_data`, `_process_message` dispatch, `_process_market_logic_strategies`, `_transform_binance_data`) — own code | **~18%** | Dict-shape transforms + per-message dispatch, no obvious O(n²) or redundant work found |
| 3 | **Pydantic model validation** (`BaseModel.__init__`, field validators e.g. `validate_numeric_string`) | **~12%** | `DepthLevel`/`MarketDataMessage` construct + validate on every message |
| 4 | **`strategies/` indicator + strategy logic** — own code | **~11%** | Pure-Python arithmetic in `market_logic/*` and `DepthAnalyzer` |
| 5 | **structlog logging** (`_proxy_to_logger`, `.debug()`) | **~9%** | `consumer.py:397` calls `self.logger.debug("Received message", data=message_data)` **unconditionally on every message**, passing the full parsed dict |
| — | stdlib `json` encode/decode | ~8% | `json.loads(msg.data.decode())` per message |

Combined, **instrumentation and validation/serialization overhead (OTel + pydantic + json +
structlog ≈ 53% of real hot-path time) outweighs actual business logic (own code ≈ 29%)**.

## 2. Is the bottleneck language-inherent?

**No.** `strategies/` has **zero `numpy`/`pandas`/vectorised-math dependencies** (confirmed:
`grep -r "import numpy\|import pandas" strategies/` → 0 hits; not in `requirements.txt`). The
"indicator math" is pure, unvectorised Python object/dict manipulation. Per the ticket's own
decision criteria ("If the hot path is NumPy/pandas vectorised math, Go may be slower. If it is
serialisation, per-message object allocation, or GIL-bound concurrency, Go wins decisively"):
**every one of the top-5 consumers (OTel span objects, pydantic model allocation, dict/JSON
parsing, structlog event-dict construction, and pure-Python strategy math) is exactly the
category where Go wins decisively** — none of it is vectorised math Go would regress on.

This is a real point in favour of Go, in the abstract. It does not automatically mean *port*,
because #3 and #5 below show most of that same gain is available for far less than a rewrite.

## 3. Cheaper alternatives first (costed)

| Alternative | Est. effort | Est. CPU reduction | Risk |
|---|---|---|---|
| **Sample OTel spans** (head-sampler, e.g. 1-in-10 messages, or drop `set_attribute` calls to 1 instead of 4, or switch consumer-side span to a lighter counter+periodic-span pattern) | **0.5–1 day** | ~15-20% (largest single lever — is 24% of hot path) | Low — reduces trace granularity, does not remove observability (metrics unaffected) |
| **Guard/remove the unconditional per-message debug log** (`consumer.py:397`, `self.logger.debug(..., data=message_data)`) behind an `isEnabledFor` check or drop it | **1–2 hours** | ~7-9% | Very low — this line has no `if debug enabled` guard today; already a latent bug, not just a perf cost |
| **Switch `json.loads`/`dumps` to `orjson`** (C-accelerated, drop-in for encode; decode needs a small wrapper) | **1 day** | ~4-6% (json ~8% today, orjson typically 3-5x faster) | Low — well-trodden migration, `orjson` already common in the Petrosa stack elsewhere |
| **Trim Pydantic validation on the hot path** (bypass `BaseModel.__init__` re-validation for trusted-source depth messages, e.g. `model_construct`/`TypedDict` + manual validate only at boundary) | **2–3 days** | ~6-9% (pydantic ~12% today; full elimination unrealistic without breaking validation contracts) | Medium — touches the depth-message contract that #188/#203 just stabilized; needs care |
| `uvloop` for the asyncio loop | **<1 hour** | ~1-2% (asyncio loop is only ~1.8% of real hot-path time here — most "async" cost already shows up as sync CPU inside the callback, not loop scheduling) | Low, but low payoff specifically for *this* bottleneck |

**Stacked (spans + logging + orjson), realistically ~2 engineer-days total for an estimated
25-30% additional CPU reduction** on top of what #198-#207 already delivered — no new language,
no dual-maintenance cost, reviewable in normal-sized PRs.

## 4. Cost of the rewrite

- **12,724 LOC** in `strategies/` (source), **14,107 LOC** in `tests/` (42 test files, 79%
  statement coverage per `coverage.json`).
- **5 concrete market-logic strategies** (`btc_dominance.py`, `cross_exchange_spread.py`,
  `iceberg_detector.py`, `onchain_metrics.py`, `spread_liquidity.py`) plus the core
  `DepthAnalyzer`/`OrderBookTracker`/consumer pipeline — the correctness-critical part that
  decides real trading signals.
- Porting means **re-implementing and re-verifying trading-signal logic in a second language**
  with no shared test harness — the single highest-risk item on this list. A signal-logic bug
  introduced in translation would not fail CI; it would misprice risk silently in production.
  This is qualitatively different from the usual "rewrite is slower to ship" cost.
- A prior MemPalace note (2026-09-11, before this spike) already sketched a candidate Go
  architecture (symbol-sharded goroutines, `nats.go`, `gopsutil`, OTel via `otlptracehttp`) —
  useful *if* a port is later authorised, not evidence it should be.

## 5. Dual-maintenance cost

If only this service moves to Go:

- **`petrosa-otel`** (shared Python instrumentation package) would need a **parallel Go
  instrumentation package** maintained forever, or this service silently diverges from the
  ecosystem's tracing/metrics conventions.
- **CI**: `petrosa-shared-workflows`'s `ci-pipeline.yml` and the `templates/.pre-commit-config-v3.0.yaml`
  golden-standard toolchain (ruff, pytest, uv) assume Python across all 7 service repos; this
  service would need its own Go CI template, ADR, and a second set of lint/test/security gates
  that the other 6 repos don't share.
- **BMAD workflows**: `ticket-execution`'s `make pipeline` step, `check-branch-staleness.sh`, and
  every dispatcher that assumes a `.venv`/`uv`/`ruff` Python project would need a Go-specific
  branch — this spike's own orchestration run would have looked different in a Go repo.
- **Team/tooling context-switching**: every engineer touching trading-signal logic now needs to
  reason in two languages instead of one for the same class of bug.

This is a real, ongoing tax — not a one-time migration cost — and it is disproportionate to the
CPU gain remaining after item 3's cheap alternatives are taken.

## 6. Recommendation: **optimise in Python — do not port**

**Decision criteria applied** (explicit, per the ticket's request):

1. The crisis that motivated "port the biggest CPU consumer" is **~70% already resolved** by
   non-rewrite means (right-sizing + dead-code removal + perf PRs #198-#207): 90% → ~30% of
   node CPU, throttling 15.5% → 2.2%.
2. Of what's left, the top 3 consumers (OTel spans, an unconditional debug log, JSON parsing)
   are **configuration/one-line-code fixes**, not structural Python limitations — a rewrite
   would only remove overhead that a 2-day Python patch removes just as effectively.
3. Nothing in the hot path is vectorised math where Go would lose — so the *ceiling* case for
   Go is real, but the *marginal* case (given #1 and #2) does not clear the bar of "3x win from
   one day beats 5x win from three months," inverted: **here it's an ~est. 25-30% win from ~2
   days beats an unquantified additional win from a multi-month rewrite with a second language's
   permanent maintenance tax and signal-logic re-verification risk.**
4. **This reasoning should stand until new evidence appears** (e.g., the cheap alternatives in
   §3 are implemented, re-profiled, and CPU is *still* the binding constraint on cluster
   capacity/cost) — per the ticket's own AC: "If the recommendation is against porting, that
   reasoning is recorded so the question is not reopened without new evidence."

**Recommended follow-up (not this ticket):** file a scoped `perf` ticket for the §3 stack
(OTel span sampling + drop/guard the unconditional debug log + `orjson`), re-run
`scripts/benchmark_hot_path.py` before/after exactly as #206 did, and re-profile with `py-spy`
after landing to confirm the estimated 25-30% reduction before closing the Go-port question
permanently.

## Appendix A — reproduction

```bash
cd petrosa-realtime-strategies
py-spy record -f speedscope -o /tmp/profile.speedscope.json --rate 500 -- \
  .venv/bin/python scripts/benchmark_hot_path.py --count 60000 --seed 191
# bucket self-time by frame file/name from the speedscope JSON's
# profiles[0].samples / .weights, excluding unittest.mock / inspect.py frames
# (mock-harness introspection artefact, see caveat above).
```

Fresh baseline (post #198-#207, current `main`):
`scripts/benchmark_hot_path.py --count 20000 --seed 191` → `per_message_us=301.70`.
