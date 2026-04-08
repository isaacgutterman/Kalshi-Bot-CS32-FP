# Kalshi Baseball Momentum Bot

A trading bot for [Kalshi](https://kalshi.com) focused on baseball game markets. It watches live prices and suggests buy, sell, or hold using a simple momentum read on the ticker.

**What It Does**

- It discovers open baseball-related markets from Kalshi's API
- It streams quote data in a loop (public REST polling) so you get live updates
- Momentum algo which keeps a rolling window of recent prices then compares where the price is now to that recent average.
- If the market has clearly moved up versus that window the bot leans toward YES; if it’s moved down, it leans toward NO; if the move is small or noisy, it says hold so you’re not reacting to every tiny thing.

**We will have a few guardrails**

- Skip or down-rank markets where the bid–ask spread is too wide meaning there’s often no real price there, just a gap.
- Wait a bit between signals (cooldown) so we’re not spammed with different intel.
- Stick to a limited set of tickers so the project stays debuggable and we're not trying to watch every game at once.

Under the hood the current skeleton uses REST to discover and stream in a polling loop. You can swap the loop to authenticated WebSockets later if you want lower-latency updates.

### Run it

- `pip install -r requirements.txt`
- `python src/kalshi_momentum.py --max-markets 5 --interval-seconds 10`
- Optional: pass explicit tickers with `--tickers "TICKER1,TICKER2"`

## Quick Start

- Install deps: `pip install -r requirements.txt`
- Run stream: `python src/kalshi_momentum.py`
- Tune defaults with flags: `--max-markets`, `--lookback-samples`, `--threshold-cents`, `--max-spread-cents`, `--interval-seconds`


