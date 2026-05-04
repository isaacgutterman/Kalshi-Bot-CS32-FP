import argparse
import re
import time
from typing import Dict, List, Optional

from api_client import KalshiPublicClient, get_target_tickers
from algorithm import (
    PaperPosition,
    TradingAlgorithm,
    algorithm_params_from_args,
    create_algorithm,
    list_algorithm_choices,
    resolve_algorithm_key,
)
from odds_client import TheOddsApiClient


def run_stream(args: argparse.Namespace) -> None:
    client = KalshiPublicClient()
    tickers = get_target_tickers(client, args.tickers, args.max_markets, include_settled=False)
    if not tickers:
        raise RuntimeError("No tradable baseball markets found. Try explicit --tickers.")

    algo_key = resolve_algorithm_key(args.algo)
    params = algorithm_params_from_args(args)
    algo_label = next((title for k, title in list_algorithm_choices() if k == algo_key), algo_key)
    create_algorithm(algo_key, params)
    algos: Dict[str, TradingAlgorithm] = {t: create_algorithm(algo_key, params) for t in tickers}

    print(f"Streaming {len(tickers)} markets: {', '.join(tickers)}")
    print(f"Algorithm: {algo_key} - {algo_label}\n")
    iteration = 0
    stat_arb_teams = _extract_yes_teams_for_tickers(client, tickers)
    odds_client = _build_odds_client(args)

    while True:
        snapshots = client.get_snapshots(tickers)
        fair_probs = _maybe_load_external_fair_probs(odds_client)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]")
        for snap in snapshots:
            if snap.mid is None:
                print(f"  {snap.ticker:22s} mid=NA spread=NA signal=HOLD")
                continue
            if snap.spread is not None and snap.spread > args.max_spread_cents:
                print(f"  {snap.ticker:22s} mid={snap.mid:6.2f} spread={snap.spread:6.2f} signal=HOLD (wide spread)")
                continue
            signal = algos[snap.ticker].on_price(snap.mid)
            stat_signal = _stat_arb_signal_for_snapshot(snap.ticker, snap.mid, stat_arb_teams, fair_probs, args.stat_arb_edge_cents)
            if stat_signal is not None:
                signal = stat_signal
            spread_text = f"{snap.spread:6.2f}" if snap.spread is not None else "   NA "
            print(f"  {snap.ticker:22s} mid={snap.mid:6.2f} spread={spread_text} signal={signal}")
        print()
        iteration += 1
        if args.iterations and iteration >= args.iterations:
            break
        time.sleep(args.interval_seconds)


def run_paper(args: argparse.Namespace) -> None:
    client = KalshiPublicClient()
    tickers = get_target_tickers(client, args.tickers, args.max_markets, include_settled=False)
    if not tickers:
        raise RuntimeError("No tradable baseball markets found. Try explicit --tickers.")

    algo_key = resolve_algorithm_key(args.algo)
    params = algorithm_params_from_args(args)
    algo_label = next((title for k, title in list_algorithm_choices() if k == algo_key), algo_key)
    create_algorithm(algo_key, params)
    algos: Dict[str, TradingAlgorithm] = {t: create_algorithm(algo_key, params) for t in tickers}
    books: Dict[str, PaperPosition] = {ticker: PaperPosition() for ticker in tickers}
    iteration = 0

    print(f"Paper trading {len(tickers)} markets: {', '.join(tickers)}")
    print(f"Algorithm: {algo_key} - {algo_label}\n")
    stat_arb_teams = _extract_yes_teams_for_tickers(client, tickers)
    odds_client = _build_odds_client(args)
    while True:
        snapshots = client.get_snapshots(tickers)
        fair_probs = _maybe_load_external_fair_probs(odds_client)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]")
        for snap in snapshots:
            if snap.mid is None:
                print(f"  {snap.ticker:22s} mid=NA signal=HOLD pos={books[snap.ticker].qty_yes:+d}")
                continue
            signal = algos[snap.ticker].on_price(snap.mid)
            stat_signal = _stat_arb_signal_for_snapshot(snap.ticker, snap.mid, stat_arb_teams, fair_probs, args.stat_arb_edge_cents)
            if stat_signal is not None:
                signal = stat_signal
            if signal != "HOLD":
                books[snap.ticker].apply_signal(signal, snap.mid, args.unit_size)
            unrealized = books[snap.ticker].mark_to_market(snap.mid)
            total = books[snap.ticker].realized_pnl + unrealized
            print(f"  {snap.ticker:22s} mid={snap.mid:6.2f} signal={signal:7s} pos={books[snap.ticker].qty_yes:+3d} pnl={total:8.2f}")
        print()
        iteration += 1
        if args.iterations and iteration >= args.iterations:
            break
        time.sleep(args.interval_seconds)

    _print_portfolio_summary(books, client, tickers)


def _print_portfolio_summary(books: Dict[str, PaperPosition], client: KalshiPublicClient, tickers: List[str]) -> None:
    snapshots = client.get_snapshots(tickers)
    snap_map = {snap.ticker: snap for snap in snapshots}
    total = 0.0
    print("Portfolio summary:")
    for ticker, book in books.items():
        snap = snap_map.get(ticker)
        mark = snap.mid if snap and snap.mid is not None else 50.0
        pnl = book.realized_pnl + book.mark_to_market(mark)
        total += pnl
        print(f"  {ticker:22s} pos={book.qty_yes:+3d} mark={mark:6.2f} pnl={pnl:8.2f}")
    print(f"  TOTAL PnL: {total:.2f}")


def _normalize_team_name(name: str) -> str:
    return " ".join(name.lower().replace(".", "").replace("-", " ").split())


def _extract_yes_team(market_title: str) -> Optional[str]:
    title = market_title.strip()
    patterns = [
        r"(?i)^will\s+(.+?)\s+beat\s+.+\?$",
        r"(?i)^will\s+(.+?)\s+win\s+",
        r"(?i)^(.+?)\s+vs\.?\s+.+$",
        r"(?i)^(.+?)\s+@\s+.+$",
    ]
    for pattern in patterns:
        match = re.match(pattern, title)
        if match:
            return _normalize_team_name(match.group(1))
    return None


def _extract_yes_teams_for_tickers(client: KalshiPublicClient, tickers: List[str]) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    for ticker in tickers:
        market = client.get_market(ticker)
        title = str(market.get("title", "")).strip()
        yes_team = _extract_yes_team(title)
        if yes_team:
            mapping[ticker] = yes_team
    return mapping


def _external_odds_enabled(provider: str) -> bool:
    return provider in ("the_odds_api", "draftkings")


def _build_odds_client(args: argparse.Namespace) -> Optional[TheOddsApiClient]:
    if not _external_odds_enabled(args.external_odds_provider):
        return None
    client = TheOddsApiClient(
        api_key=args.odds_api_key,
        sport_key=args.odds_sport_key,
        bookmaker=args.odds_bookmaker,
    )
    if client.api_key:
        print(
            f"[stat-arb] Odds API key source: {client.api_key_source}; "
            f"length={len(client.api_key)} chars (compare to key length in your Odds API dashboard)."
        )
    else:
        print("[stat-arb] No Odds API key found. Use .env ODDS_API_KEY=... or --odds-api-key.")
    return client


def _maybe_load_external_fair_probs(odds_client: Optional[TheOddsApiClient]) -> Optional[Dict[str, float]]:
    if odds_client is None:
        return None
    try:
        return odds_client.get_moneyline_probabilities()
    except Exception as exc:
        print(f"  [stat-arb] The Odds API fetch failed: {exc}")
        return None


def _stat_arb_signal_for_snapshot(
    ticker: str,
    kalshi_mid: float,
    ticker_to_yes_team: Dict[str, str],
    fair_probs: Optional[Dict[str, float]],
    edge_cents: float,
) -> Optional[str]:
    if not fair_probs:
        return None
    yes_team = ticker_to_yes_team.get(ticker)
    if not yes_team:
        return None
    fair_prob = fair_probs.get(yes_team)
    if fair_prob is None:
        return None
    fair_yes_cents = fair_prob * 100.0
    mispricing = fair_yes_cents - kalshi_mid
    if mispricing >= edge_cents:
        return "BUY_YES"
    if mispricing <= -edge_cents:
        return "BUY_NO"
    return "HOLD"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live stream and paper trading (plug-and-play algorithms).")
    parser.add_argument("--max-markets", type=int, default=5, help="Maximum markets to monitor.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated market tickers.")
    parser.add_argument("--lookback-samples", type=int, default=8, help="Rolling window length.")
    parser.add_argument("--threshold-cents", type=float, default=0.9, help="Threshold where applicable.")
    parser.add_argument("--algo", type=str, default=None, help="Algorithm key; if omitted, prompts in an interactive terminal.")
    parser.add_argument("--rsi-period", type=int, default=14, dest="rsi_period")
    parser.add_argument("--rsi-oversold", type=float, default=30.0, dest="rsi_oversold")
    parser.add_argument("--rsi-overbought", type=float, default=70.0, dest="rsi_overbought")
    parser.add_argument("--range-low", type=float, default=0.15, dest="range_low")
    parser.add_argument("--range-high", type=float, default=0.85, dest="range_high")
    parser.add_argument("--interval-seconds", type=float, default=15.0, help="Live loop polling interval.")
    parser.add_argument("--iterations", type=int, default=0, help="Stop after N loops (0 runs forever).")
    parser.add_argument("--max-spread-cents", type=float, default=10.0, help="Spread filter used in stream mode.")
    parser.add_argument("--unit-size", type=int, default=1, help="Contracts per non-hold signal in paper mode.")
    parser.add_argument(
        "--external-odds-provider",
        choices=["none", "the_odds_api", "draftkings"],
        default="none",
        help="Stat-arb fair value from The Odds API (the-odds-api.com). Use the_odds_api; draftkings is a legacy alias.",
    )
    parser.add_argument(
        "--odds-api-key",
        type=str,
        default="",
        help="API key from The Odds API (https://the-odds-api.com/#get-access); or set ODDS_API_KEY / .env.",
    )
    parser.add_argument("--odds-sport-key", type=str, default="baseball_mlb", help="Sport key for The Odds API (e.g. baseball_mlb).")
    parser.add_argument(
        "--odds-bookmaker",
        type=str,
        default="draftkings",
        help="Bookmaker key in The Odds API feed (e.g. draftkings, fanduel, betmgm). See their bookmaker list.",
    )
    parser.add_argument(
        "--stat-arb-edge-cents",
        type=float,
        default=3.0,
        help="Override signal if external fair value differs by this many cents.",
    )
    parser.add_argument("--mode", choices=["stream", "paper"], default="stream", help="Run live signal stream or paper trading.")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "stream":
        run_stream(args)
    else:
        run_paper(args)
