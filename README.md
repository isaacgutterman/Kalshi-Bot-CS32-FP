# Kalshi Baseball Momentum Bot

A trading bot for [Kalshi](https://kalshi.com) focused on baseball game markets. It watches live prices and suggests buy, sell, or hold using a momentum signal from a rolling price window.

## What it does

- Discovers baseball win/loss style markets (not props/totals).
- Streams live quotes and prints momentum signals.
- Runs live paper trading (simulated positions and PnL).
- Runs backtests over the last month using market trades.
- Code is split across four scripts:
  - `src/api_client.py` (Kalshi API + market discovery/filtering)
  - `src/algorithm.py` (momentum + signal + paper position math)
  - `src/backtesting.py` (historical replay + PnL evaluation)
  - `src/live_trading.py` (live stream + live paper trading)

## Setup

- `pip install -r requirements.txt`

## Usage

- Live signal stream:
  - `python src/live_trading.py --mode stream --max-markets 5 --interval-seconds 10`
- Live paper trading:
  - `python src/live_trading.py --mode paper --max-markets 5 --interval-seconds 10 --unit-size 1`
- Last-month backtest:
  - `python src/backtesting.py --max-markets 8 --backtest-days 30`

Optional:
- Force specific markets:
  - `--tickers "TICKER1,TICKER2"`
- Tune signal sensitivity:
  - `--lookback-samples 12 --threshold-cents 1.5`


