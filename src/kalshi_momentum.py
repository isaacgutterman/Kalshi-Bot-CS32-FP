import argparse
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, Iterable, List, Optional

import requests

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"


@dataclass
class MarketSnapshot:
    ticker: str
    yes_bid: Optional[float]
    yes_ask: Optional[float]
    no_bid: Optional[float]
    no_ask: Optional[float]
    last_price: Optional[float]
    volume: Optional[float]

    @property
    def mid(self) -> Optional[float]:
        if self.yes_bid is None and self.yes_ask is None:
            return self.last_price
        if self.yes_bid is None:
            return self.yes_ask
        if self.yes_ask is None:
            return self.yes_bid
        if self.yes_bid is None or self.yes_ask is None:
            return self.last_price
        return (self.yes_bid + self.yes_ask) / 2.0

    @property
    def spread(self) -> Optional[float]:
        if self.yes_bid is None or self.yes_ask is None:
            return None
        return self.yes_ask - self.yes_bid


@dataclass
class MomentumState:
    history: Deque[float] = field(default_factory=deque)

    def update(self, value: float, lookback: int) -> float:
        self.history.append(value)
        while len(self.history) > lookback:
            self.history.popleft()
        return sum(self.history) / len(self.history)


class KalshiPublicClient:
    def __init__(self, base_url: str = BASE_URL, timeout: int = 12) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.timeout = timeout

    def get_markets(self, series_ticker: str, limit: int = 200, status: str = "open") -> List[dict]:
        params = {"series_ticker": series_ticker, "status": status, "limit": limit}
        response = self.session.get(f"{self.base_url}/markets", params=params, timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("markets", [])

    def get_market(self, ticker: str) -> dict:
        response = self.session.get(f"{self.base_url}/markets/{ticker}", timeout=self.timeout)
        response.raise_for_status()
        data = response.json()
        return data.get("market", {})

    def get_orderbook(self, ticker: str) -> dict:
        response = self.session.get(f"{self.base_url}/markets/{ticker}/orderbook", timeout=self.timeout)
        response.raise_for_status()
        return response.json().get("orderbook_fp", {})

    def get_snapshots(self, tickers: Iterable[str]) -> List[MarketSnapshot]:
        snapshots: List[MarketSnapshot] = []
        for ticker in tickers:
            market = self.get_market(ticker)
            orderbook = self.get_orderbook(ticker)
            best_yes_bid, best_no_bid = _best_bids(orderbook)
            implied_yes_ask = 100.0 - best_no_bid if best_no_bid is not None else None
            implied_no_ask = 100.0 - best_yes_bid if best_yes_bid is not None else None
            snapshots.append(
                MarketSnapshot(
                    ticker=ticker,
                    yes_bid=best_yes_bid,
                    yes_ask=implied_yes_ask,
                    no_bid=best_no_bid,
                    no_ask=implied_no_ask,
                    last_price=_to_float(market.get("last_price")),
                    volume=_to_float(market.get("volume")),
                )
            )
        return snapshots


def _to_float(value: object) -> Optional[float]:
    if value is None:
        return None


def _best_bids(orderbook: dict) -> tuple[Optional[float], Optional[float]]:
    yes_levels = orderbook.get("yes_dollars", []) or []
    no_levels = orderbook.get("no_dollars", []) or []
    best_yes = None
    best_no = None

    if yes_levels:
        best_yes = max(float(level[0]) for level in yes_levels if level and level[0] is not None)
    if no_levels:
        best_no = max(float(level[0]) for level in no_levels if level and level[0] is not None)

    return best_yes, best_no
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_baseball_market(text: str) -> bool:
    normalized = text.lower()
    baseball_keywords = [
        "mlb",
        "baseball",
        "runs scored",
        "home run",
        "innings",
        "new york y",
        "los angeles d",
        "san diego",
        "kansas city",
        "boston",
        "baltimore",
        "seattle",
        "philadelphia",
        "houston",
        "st. louis",
        "miami",
        "tampa bay",
        "pittsburgh",
        "milwaukee",
        "atlanta",
        "toronto",
        "cincinnati",
    ]
    return any(keyword in normalized for keyword in baseball_keywords)


def select_baseball_markets(client: KalshiPublicClient, max_markets: int) -> List[str]:
    # Try MLB series first.
    markets = client.get_markets(series_ticker="MLB", limit=max(100, max_markets))
    tickers = [m.get("ticker") for m in markets if m.get("ticker")]

    if tickers:
        return tickers[:max_markets]

    # Fallback keyword matching if series ticker naming changes.
    fallback = client.session.get(
        f"{client.base_url}/markets",
        params={"status": "open", "limit": 500},
        timeout=client.timeout,
    )
    fallback.raise_for_status()
    entries = fallback.json().get("markets", [])
    baseball = []
    for market in entries:
        title = f"{market.get('title', '')} {market.get('subtitle', '')}"
        if _is_baseball_market(title):
            ticker = market.get("ticker")
            if ticker:
                baseball.append(ticker)
    return baseball[: max_markets * 5]


def _pick_tradable_markets(client: KalshiPublicClient, candidates: List[str], max_markets: int) -> List[str]:
    picked: List[str] = []
    for ticker in candidates:
        market = client.get_market(ticker)
        orderbook = client.get_orderbook(ticker)
        yes_bid, no_bid = _best_bids(orderbook)
        yes_ask = 100.0 - no_bid if no_bid is not None else None
        last_price = _to_float(market.get("last_price"))
        has_quote = yes_bid is not None or yes_ask is not None or last_price is not None
        if has_quote:
            picked.append(ticker)
        if len(picked) >= max_markets:
            break
    return picked


def momentum_signal(mid: float, moving_avg: float, threshold_cents: float) -> str:
    delta = mid - moving_avg
    if delta >= threshold_cents:
        return "BUY_YES"
    if delta <= -threshold_cents:
        return "BUY_NO"
    return "HOLD"


def run_stream(args: argparse.Namespace) -> None:
    client = KalshiPublicClient()
    tickers = [ticker.strip() for ticker in args.tickers.split(",") if ticker.strip()] if args.tickers else []
    if not tickers:
        candidates = select_baseball_markets(client, args.max_markets)
        tickers = _pick_tradable_markets(client, candidates, args.max_markets)
    if not tickers:
        raise RuntimeError("No baseball markets found. Try explicit --tickers.")

    print(f"Tracking {len(tickers)} markets: {', '.join(tickers)}")
    print("Press Ctrl+C to stop.\n")

    states: Dict[str, MomentumState] = {ticker: MomentumState() for ticker in tickers}

    iteration = 0
    while True:
        snapshots = client.get_snapshots(tickers)
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}]")
        for snap in snapshots:
            if snap.mid is None:
                print(f"  {snap.ticker:20s} mid=NA spread=NA signal=HOLD (insufficient quotes)")
                continue
            if snap.spread is not None and snap.spread > args.max_spread_cents:
                print(
                    f"  {snap.ticker:20s} mid={snap.mid:5.2f} spread={snap.spread:5.2f} "
                    "signal=HOLD (spread too wide)"
                )
                continue
            avg = states[snap.ticker].update(snap.mid, args.lookback_samples)
            signal = momentum_signal(snap.mid, avg, args.threshold_cents)
            spread_text = f"{snap.spread:5.2f}" if snap.spread is not None else "  NA "
            print(
                f"  {snap.ticker:20s} mid={snap.mid:5.2f} avg={avg:5.2f} "
                f"spread={spread_text} signal={signal}"
            )
        print()
        iteration += 1
        if args.iterations and iteration >= args.iterations:
            break
        time.sleep(args.interval_seconds)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kalshi baseball momentum signal stream.")
    parser.add_argument("--max-markets", type=int, default=5, help="Number of baseball markets to track.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated tickers to monitor directly.")
    parser.add_argument("--lookback-samples", type=int, default=12, help="Moving average window size.")
    parser.add_argument("--threshold-cents", type=float, default=1.5, help="Min delta from MA for signal.")
    parser.add_argument("--max-spread-cents", type=float, default=6.0, help="Skip markets above this spread.")
    parser.add_argument("--interval-seconds", type=float, default=15.0, help="Polling interval.")
    parser.add_argument("--iterations", type=int, default=0, help="Stop after N loops (0 runs forever).")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    run_stream(parser.parse_args())
