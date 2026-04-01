# Kalshi Baseball Momentum Bot

A small trading assistant for [Kalshi](https://kalshi.com) focused on baseball game markets. Instead of guessing how you should trade, it watches live prices and nudges you toward **buy**, **sell**, or **hold** using a simple momentum read on the ticker.

**What it’s doing, in plain terms**

- It connects to Kalshi’s **WebSocket** feed so you get prices as they update, not just when you remember to refresh.
- **Momentum** here means: keep a rolling window of recent prices (think “what has the market been doing lately?”), then compare where the price is *now* to that recent average.
- If the market has clearly **moved up** versus that window, the bot leans toward **YES**; if it’s **moved down**, it leans toward **NO**; if the move is small or noisy, it says **hold** so you’re not reacting to every tiny blip.

**A few guardrails so it doesn’t yell at you on junk quotes**

- Skip or down-rank markets where the **bid–ask spread** is too wide—there’s often no real “price” there, just a gap.
- Optionally wait a bit between signals (**cooldown**) so you’re not spammed.
- Stick to a **limited set of tickers** so the project stays debuggable and you’re not trying to watch every game at once.

Under the hood you’ll use **REST** to find which baseball markets exist, then **WebSockets** to stream them; Kalshi’s side of that is documented [here](https://docs.kalshi.com/getting_started/quick_start_websockets).

## Setup

Get API credentials from Kalshi, prefer **demo** while you’re building, and don’t commit keys.

## Disclaimer

School / learning project. Prediction markets are risky. Not financial advice.
