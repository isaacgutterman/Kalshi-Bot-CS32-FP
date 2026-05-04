# Kalshi Baseball Momentum Bot

A trading bot for [Kalshi](https://kalshi.com) focused on baseball game markets. It watches live prices and suggests buy, sell, or hold using plug-and-play algorithms (see below).

## What it does

- Discovers baseball win/loss style markets (not props/totals).
- Streams live quotes and prints signals for the algorithm you pick.
- Runs live paper trading (simulated positions and PnL).
- Optional stat-arb override using moneyline fair value from [The Odds API](https://the-odds-api.com/#get-access) (pick a bookmaker, e.g. DraftKings or FanDuel, via `--odds-bookmaker`).
- Runs backtests over the last month using market trades.
- Code is split across five scripts:
  - `src/api_client.py` (Kalshi API + market discovery/filtering)
  - `src/algorithm.py` (registry of strategies + paper position math)
  - `src/backtesting.py` (historical replay + PnL evaluation)
  - `src/live_trading.py` (live stream + live paper trading)
  - `src/odds_client.py` (The Odds API client + implied probability normalization)

## Setup

- `pip install -r requirements.txt`

## Algorithms (`--algo KEY`)

Run `backtesting.py` or `live_trading.py` without `--algo` in a normal terminal and it will prompt. In scripts or piped input, pass `--algo momentum` (or pass nothing: non-TTY defaults to `momentum`).

| Key | Idea |
|-----|------|
| `momentum` | Trend vs rolling average; buy YES on strength, NO on weakness. |
| `mean_reversion` | Fade stretches from the average (opposite side to momentum). |
| `rsi` | RSI-style oversold/overbought on recent price changes. |
| `range` | Stochastic-style: buy YES near rolling low, NO near rolling high. |
| `breakout` | Buy YES on break above prior window high (and NO on break below low). |

## Usage

- Live signal stream:
  - `python src/live_trading.py --mode stream --max-markets 5 --interval-seconds 10 --algo momentum`
- Live paper trading:
  - `python src/live_trading.py --mode paper --max-markets 5 --interval-seconds 10 --unit-size 1 --algo mean_reversion`
- Live paper with stat-arb from The Odds API (example: DraftKings lines in their feed):
  - `python src/live_trading.py --mode paper --algo momentum --external-odds-provider the_odds_api --odds-bookmaker draftkings --stat-arb-edge-cents 3`
- Same with another US bookmaker in the feed (see their bookmaker list):
  - `python src/live_trading.py --mode paper --algo momentum --external-odds-provider the_odds_api --odds-bookmaker fanduel --stat-arb-edge-cents 3`
- Last-month backtest:
  - `python src/backtesting.py --max-markets 8 --backtest-days 30 --algo rsi`

Optional:
- Force specific markets:
  - `--tickers "TICKER1,TICKER2"`
- Tune signal sensitivity:
  - `--lookback-samples 8 --threshold-cents 0.9`
- The Odds API stat-arb requirements:
  - Subscribe at [Get access](https://the-odds-api.com/#get-access), set `ODDS_API_KEY` (or `--odds-api-key`), and use `--external-odds-provider the_odds_api`. The legacy value `draftkings` still works and means the same provider.

Notes:
- `--mode stream` only prints signals and never opens positions; use `--mode paper` for simulated trade execution.

Credit Cursor for the project structure, code cleanup, and helping with this README.
