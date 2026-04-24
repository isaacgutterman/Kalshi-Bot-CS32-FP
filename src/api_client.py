import datetime as dt
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

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
        return (self.yes_bid + self.yes_ask) / 2.0

    @property
    def spread(self) -> Optional[float]:
        if self.yes_bid is None or self.yes_ask is None:
            return None
        return self.yes_ask - self.yes_bid


class KalshiPublicClient:
    def __init__(self, base_url: str = BASE_URL, timeout: int = 12) -> None:
        self.base_url = base_url
        self.session = requests.Session()
        self.timeout = timeout

    def _get_json(self, path: str, params: Optional[Dict[str, object]] = None) -> dict:
        url = f"{self.base_url}{path}"
        retries = 3
        backoff = 1.0
        for attempt in range(retries + 1):
            response = self.session.get(url, params=params, timeout=self.timeout)
            if response.status_code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(backoff)
                backoff *= 1.8
                continue
            response.raise_for_status()
            return response.json()
        return {}

    def get_markets(self, limit: int = 200, status: str = "open", series_ticker: Optional[str] = None) -> List[dict]:
        params = {"status": status, "limit": limit}
        if series_ticker:
            params["series_ticker"] = series_ticker
        return self._get_json("/markets", params=params).get("markets", [])

    def get_market(self, ticker: str) -> dict:
        return self._get_json(f"/markets/{ticker}").get("market", {})

    def get_orderbook(self, ticker: str) -> dict:
        return self._get_json(f"/markets/{ticker}/orderbook").get("orderbook_fp", {})

    def get_trades(
        self, ticker: str, min_ts: Optional[int] = None, max_ts: Optional[int] = None, limit: int = 1000
    ) -> List[dict]:
        params: Dict[str, object] = {"ticker": ticker, "limit": limit}
        if min_ts is not None:
            params["min_ts"] = min_ts
        if max_ts is not None:
            params["max_ts"] = max_ts
        return self._get_json("/markets/trades", params=params).get("trades", [])

    def get_recent_trades(self, limit: int = 1000) -> List[dict]:
        return self._get_json("/markets/trades", params={"limit": limit}).get("trades", [])

    def get_snapshots(self, tickers: Iterable[str]) -> List[MarketSnapshot]:
        snapshots: List[MarketSnapshot] = []
        for ticker in tickers:
            market = self.get_market(ticker)
            orderbook = self.get_orderbook(ticker)
            best_yes_bid, best_no_bid = best_bids(orderbook)
            implied_yes_ask = 100.0 - best_no_bid if best_no_bid is not None else None
            implied_no_ask = 100.0 - best_yes_bid if best_yes_bid is not None else None
            snapshots.append(
                MarketSnapshot(
                    ticker=ticker,
                    yes_bid=best_yes_bid,
                    yes_ask=implied_yes_ask,
                    no_bid=best_no_bid,
                    no_ask=implied_no_ask,
                    last_price=to_float(market.get("last_price")),
                    volume=to_float(market.get("volume")),
                )
            )
        return snapshots


def to_float(value: object) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def best_bids(orderbook: dict) -> Tuple[Optional[float], Optional[float]]:
    yes_levels = orderbook.get("yes_dollars", []) or []
    no_levels = orderbook.get("no_dollars", []) or []
    best_yes = max((float(level[0]) for level in yes_levels if level and level[0] is not None), default=None)
    best_no = max((float(level[0]) for level in no_levels if level and level[0] is not None), default=None)
    return best_yes, best_no


def parse_trade_yes_price_cents(trade: dict) -> Optional[float]:
    dollar = to_float(trade.get("yes_price_dollars"))
    if dollar is not None:
        return dollar * 100.0
    legacy = to_float(trade.get("yes_price"))
    if legacy is not None:
        return legacy
    return None


def parse_trade_time(trade: dict) -> Optional[dt.datetime]:
    raw = trade.get("created_time")
    if not raw:
        return None
    try:
        return dt.datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None


def is_baseball_win_loss_market(market: dict) -> bool:
    title = f"{market.get('title', '')} {market.get('subtitle', '')}".lower()
    ticker = str(market.get("ticker", "")).lower()
    event = str(market.get("event_ticker", "")).lower()

    mlb_teams = (
        "yankees", "mets", "red sox", "blue jays", "orioles", "rays", "guardians", "tigers", "royals", "twins",
        "white sox", "astros", "rangers", "mariners", "athletics", "angels", "braves", "marlins", "phillies",
        "nationals", "cubs", "brewers", "cardinals", "pirates", "reds", "dodgers", "padres", "giants",
        "diamondbacks", "rockies", "new york y", "new york m", "los angeles d", "los angeles a", "kansas city",
        "st. louis",
    )
    baseball_signal = any(
        token in title or token in ticker or token in event for token in ("mlb", "baseball", "runs scored", "home run")
    ) or any(team in title for team in mlb_teams)
    if not baseball_signal:
        return False

    must_not_have = (
        " hit", "strikeout", "nba", "nfl", "nhl", "barcelona", "real madrid", "arsenal",
        "multigame", "crosscategory", "spread", "home run",
    )
    if any(token in title or token in ticker for token in must_not_have):
        return False

    ticker_upper = ticker.upper()
    is_game_winner = "wins" in title or "game" in ticker_upper
    is_prop_code = any(code in ticker_upper for code in ("RFI", "TB-", "HR-", "SPREAD"))
    return is_game_winner and not is_prop_code


def is_baseball_market_broad(market: dict) -> bool:
    title = f"{market.get('title', '')} {market.get('subtitle', '')}".lower()
    ticker = str(market.get("ticker", "")).upper()
    team_tokens = (
        "new york y", "new york m", "los angeles d", "los angeles a", "san diego", "kansas city", "boston",
        "baltimore", "seattle", "philadelphia", "houston", "st. louis", "miami", "tampa bay", "pittsburgh",
        "milwaukee", "atlanta", "toronto", "cincinnati",
    )
    return ticker.startswith("KXMLB") or "mlb" in title or "baseball" in title or any(team in title for team in team_tokens)


def discover_baseball_winloss_markets(client: KalshiPublicClient, max_markets: int, include_settled: bool) -> List[str]:
    statuses = ["open"] if not include_settled else ["open", "closed", "settled"]
    strict_candidates: List[str] = []
    broad_candidates: List[str] = []

    for status in statuses:
        markets = client.get_markets(limit=1000, status=status)
        for market in markets:
            if is_baseball_win_loss_market(market):
                ticker = market.get("ticker")
                if ticker:
                    strict_candidates.append(str(ticker))
            elif is_baseball_market_broad(market):
                ticker = market.get("ticker")
                if ticker:
                    broad_candidates.append(str(ticker))
            if len(strict_candidates) >= max_markets * 12:
                break
        if len(strict_candidates) >= max_markets * 12:
            break

    combined = strict_candidates if strict_candidates else broad_candidates
    return list(dict.fromkeys(combined))


def pick_tradable_markets(client: KalshiPublicClient, candidates: List[str], max_markets: int) -> List[str]:
    picked: List[str] = []
    for ticker in candidates:
        market = client.get_market(ticker)
        orderbook = client.get_orderbook(ticker)
        yes_bid, no_bid = best_bids(orderbook)
        yes_ask = 100.0 - no_bid if no_bid is not None else None
        last_price = to_float(market.get("last_price"))
        has_quote = yes_bid is not None or yes_ask is not None or last_price is not None
        if has_quote:
            picked.append(ticker)
        if len(picked) >= max_markets:
            break
    return picked


def get_target_tickers(client: KalshiPublicClient, tickers_arg: str, max_markets: int, include_settled: bool) -> List[str]:
    explicit = [ticker.strip() for ticker in tickers_arg.split(",") if ticker.strip()] if tickers_arg else []
    if explicit:
        return explicit

    candidates = discover_baseball_winloss_markets(client, max_markets, include_settled=include_settled)
    if include_settled:
        return candidates[:max_markets]

    tradable = pick_tradable_markets(client, candidates, max_markets)
    if tradable:
        return tradable

    recent = client.get_recent_trades(limit=1000)
    recent_candidates: List[str] = []
    for trade in recent:
        ticker = str(trade.get("ticker", ""))
        if not ticker.startswith("KXMLB"):
            continue
        market = client.get_market(ticker)
        if is_baseball_win_loss_market(market):
            recent_candidates.append(ticker)
        if len(recent_candidates) >= max_markets * 10:
            break
    deduped = list(dict.fromkeys(recent_candidates))
    return pick_tradable_markets(client, deduped, max_markets)
