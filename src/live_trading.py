import argparse
import time
from typing import Dict, List

from api_client import KalshiPublicClient, get_target_tickers
from algorithm import (
    PaperPosition,
    TradingAlgorithm,
    algorithm_params_from_args,
    create_algorithm,
    list_algorithm_choices,
    resolve_algorithm_key,
)


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

    while True:
        snapshots = client.get_snapshots(tickers)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]")
        for snap in snapshots:
            if snap.mid is None:
                print(f"  {snap.ticker:22s} mid=NA spread=NA signal=HOLD")
                continue
            if snap.spread is not None and snap.spread > args.max_spread_cents:
                print(f"  {snap.ticker:22s} mid={snap.mid:6.2f} spread={snap.spread:6.2f} signal=HOLD (wide spread)")
                continue
            signal = algos[snap.ticker].on_price(snap.mid)
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
    while True:
        snapshots = client.get_snapshots(tickers)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}]")
        for snap in snapshots:
            if snap.mid is None:
                print(f"  {snap.ticker:22s} mid=NA signal=HOLD pos={books[snap.ticker].qty_yes:+d}")
                continue
            signal = algos[snap.ticker].on_price(snap.mid)
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Live stream and paper trading (plug-and-play algorithms).")
    parser.add_argument("--max-markets", type=int, default=5, help="Maximum markets to monitor.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated market tickers.")
    parser.add_argument("--lookback-samples", type=int, default=12, help="Rolling window length.")
    parser.add_argument("--threshold-cents", type=float, default=1.5, help="Threshold where applicable.")
    parser.add_argument("--algo", type=str, default=None, help="Algorithm key; if omitted, prompts in an interactive terminal.")
    parser.add_argument("--rsi-period", type=int, default=14, dest="rsi_period")
    parser.add_argument("--rsi-oversold", type=float, default=30.0, dest="rsi_oversold")
    parser.add_argument("--rsi-overbought", type=float, default=70.0, dest="rsi_overbought")
    parser.add_argument("--range-low", type=float, default=0.15, dest="range_low")
    parser.add_argument("--range-high", type=float, default=0.85, dest="range_high")
    parser.add_argument("--interval-seconds", type=float, default=15.0, help="Live loop polling interval.")
    parser.add_argument("--iterations", type=int, default=0, help="Stop after N loops (0 runs forever).")
    parser.add_argument("--max-spread-cents", type=float, default=6.0, help="Spread filter used in stream mode.")
    parser.add_argument("--unit-size", type=int, default=1, help="Contracts per non-hold signal in paper mode.")
    parser.add_argument("--mode", choices=["stream", "paper"], default="stream", help="Run live signal stream or paper trading.")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    if args.mode == "stream":
        run_stream(args)
    else:
        run_paper(args)
