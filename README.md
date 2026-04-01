# Kalshi Baseball Momentum Bot

A small trading assistant for [Kalshi](https://kalshi.com) that discovers baseball-related markets, streams live prices over the WebSocket API, and emits **buy / sell / hold** signals from a **momentum** rule. Designed for a CS32-scale project: clear logic, bounded scope, and optional **paper trading** (no live orders required).

## Strategy: momentum

The bot tracks a **reference price** per market (typically the **mid** of the best YES bid and ask, or the last traded price if the book is empty). On each update it compares the current mid to a **moving average** of recent mids over a fixed **lookback window** (e.g. last *N* samples or *T* minutes).

- **Positive momentum** (mid meaningfully **above** the moving average) → lean **buy YES** or reduce NO exposure (configurable).
- **Negative momentum** (mid meaningfully **below** the moving average) → lean **buy NO** or reduce YES exposure (configurable).
- **Weak or noisy moves** → **hold** until the deviation exceeds a **minimum threshold** (in cents or as a fraction of the average).

This is a **rule-based** policy, not a guarantee of profit. Momentum on prediction markets can reverse quickly (news, lineups, in-game events).

## Risk and quality gates (recommended)

Before any signal is promoted to “actionable,” the bot should apply **filters** so you are not trading illiquid or chaotic books:

- **Maximum bid–ask spread** (e.g. skip if spread &gt; *X* cents).
- **Minimum volume or depth** (optional; requires fields from ticker or order book).
- **Cooldown** after a signal (avoid spamming the same side).
- **Cap** on number of markets followed at once (e.g. 5–20 tickers).

Document your chosen constants in config or in this README for reproducibility.

## Architecture (high level)

1. **Discover** – REST: list events/markets and filter to baseball (series, category, or title keywords per Kalshi’s API).
2. **Stream** – WebSocket: subscribe to `ticker` (and optionally order book / public trades) for selected `market_tickers`. See [Kalshi WebSocket quick start](https://docs.kalshi.com/getting_started/quick_start_websockets).
3. **State** – Per market: ring buffer or deque of `(timestamp, mid)` for the moving average; latest bid/ask, spread, volume.
4. **Signal** – Momentum + gates → discrete recommendation (and optional order intent for paper or live execution).
5. **Execute (optional)** – REST place/cancel orders; use **demo** environment first.

## Configuration

Suggested parameters (names are illustrative—match your implementation):

| Parameter | Role |
|-----------|------|
| `lookback_samples` or `lookback_seconds` | Window for moving average |
| `momentum_threshold_cents` | Min mid − MA (or MA − mid) to trigger |
| `max_spread_cents` | Skip market if spread too wide |
| `poll_or_buffer` | Whether you sample on each tick or on a timer |
| `market_tickers` | Explicit list and/or max count from discovery |

## Setup

1. Create a Kalshi account and generate **API credentials** (key ID + private key for signing). Prefer the **demo** API while developing.
2. Clone this repo and install dependencies (add steps here once the stack is chosen, e.g. Python + `websockets` / `requests`, or C++ with your HTTP/WebSocket library).
3. Copy `.env.example` to `.env` (if provided) and set keys **without** committing them.
4. Run the bot (command TBD once the entrypoint exists).

## Usage

```text
# Example (placeholder—replace with your CLI)
python -m kalshi_momentum --config config.yaml
```

Add real commands and flags after the implementation is in place.

## Project constraints (CS32)

- **In scope:** Data structures for per-market history (e.g. `std::deque` / `vector` / ring buffer), maps from ticker to state, clear separation of discovery, streaming, strategy, and optional execution.
- **Out of scope (unless required):** Machine learning, multi-exchange arbitrage, sub-second latency, or claims of expected profit.

## Disclaimer

This software is for **education**. Prediction markets involve **risk of loss**. Kalshi’s terms, fees, and market rules apply. The authors are not providing financial advice. Test on **demo** and/or **paper** mode before any live trading.

## License

Specify your course/policy (e.g. MIT, or “all rights reserved” for class submission).
