# Kalshi Baseball Momentum Bot

A trading bot for [Kalshi](https://kalshi.com) focused on baseball game markets. It watches live prices and suggests buy, sell, or hold using plug-and-play algorithms (see below).

## What it does

- Discovers baseball win/loss style markets (not props/totals).
- Streams live quotes and prints signals for the algorithm you pick.
- Runs live paper trading (simulated positions and PnL).
- Runs backtests over the last month using market trades.
- Code is split across four scripts:
  - `src/api_client.py` (Kalshi API + market discovery/filtering)
  - `src/algorithm.py` (registry of strategies + paper position math)
  - `src/backtesting.py` (historical replay + PnL evaluation)
  - `src/live_trading.py` (live stream + live paper trading)

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
- Last-month backtest:
  - `python src/backtesting.py --max-markets 8 --backtest-days 30 --algo rsi`

Optional:
- Force specific markets:
  - `--tickers "TICKER1,TICKER2"`
- Tune signal sensitivity:
  - `--lookback-samples 12 --threshold-cents 1.5`


