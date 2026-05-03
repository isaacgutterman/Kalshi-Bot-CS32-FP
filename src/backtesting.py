import argparse
import datetime as dt
from typing import List, Tuple

from api_client import (
    KalshiPublicClient,
    get_target_tickers,
    is_baseball_win_loss_market,
    parse_trade_time,
    parse_trade_yes_price_cents,
)
from algorithm import (
    PaperPosition,
    algorithm_params_from_args,
    create_algorithm,
    list_algorithm_choices,
    resolve_algorithm_key,
)


def run_backtest(args: argparse.Namespace) -> None:
    client = KalshiPublicClient()
    explicit = [ticker.strip() for ticker in args.tickers.split(",") if ticker.strip()] if args.tickers else []
    if explicit:
        tickers = explicit
    else:
        recent = client.get_recent_trades(limit=1000)
        strict_tickers: List[str] = []
        broad_tickers: List[str] = []
        for trade in recent:
            ticker = str(trade.get("ticker", ""))
            if not ticker:
                continue
            if ticker.startswith("KXMLB"):
                broad_tickers.append(ticker)
            market = client.get_market(ticker)
            if is_baseball_win_loss_market(market):
                strict_tickers.append(ticker)
            if len(strict_tickers) >= args.max_markets:
                break
        tickers = list(dict.fromkeys(strict_tickers))[: args.max_markets]
        if not tickers:
            tickers = list(dict.fromkeys(broad_tickers))[: args.max_markets]
    if not tickers:
        tickers = get_target_tickers(client, "", args.max_markets, include_settled=True)
    if not tickers:
        raise RuntimeError("No baseball markets found for backtest. Try explicit --tickers.")

    algo_key = resolve_algorithm_key(args.algo)
    params = algorithm_params_from_args(args)
    algo_label = next((title for k, title in list_algorithm_choices() if k == algo_key), algo_key)
    create_algorithm(algo_key, params)  # validate key early

    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=args.backtest_days)
    print(f"Backtesting {len(tickers)} markets from {since.isoformat()} UTC")
    print(f"Algorithm: {algo_key} - {algo_label}\n")

    portfolio_total = 0.0
    for ticker in tickers:
        trades = client.get_trades(ticker=ticker, limit=args.backtest_trade_limit)
        if not trades:
            print(f"  {ticker:22s} no trades in window")
            continue

        history: List[Tuple[dt.datetime, float]] = []
        for trade in trades:
            ts = parse_trade_time(trade)
            price = parse_trade_yes_price_cents(trade)
            if ts is None or price is None:
                continue
            if ts >= since:
                history.append((ts, price))
        history.sort(key=lambda item: item[0])
        series = [price for _, price in history]
        min_points = args.lookback_samples + 2
        if algo_key == "rsi":
            min_points = max(min_points, args.rsi_period + 3)
        if len(series) < min_points:
            print(f"  {ticker:22s} insufficient history ({len(series)} points)")
            continue

        algo = create_algorithm(algo_key, params)
        book = PaperPosition()
        for price in series:
            signal = algo.on_price(price)
            if signal != "HOLD":
                book.apply_signal(signal, price, args.unit_size)
        final_price = series[-1]
        pnl = book.realized_pnl + book.mark_to_market(final_price)
        portfolio_total += pnl
        print(
            f"  {ticker:22s} points={len(series):4d} final={final_price:6.2f} "
            f"pos={book.qty_yes:+3d} pnl={pnl:8.2f}"
        )

    print(f"\nBacktest portfolio PnL: {portfolio_total:.2f}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backtest Kalshi baseball strategies (plug-and-play algorithms).")
    parser.add_argument("--max-markets", type=int, default=8, help="How many markets to backtest.")
    parser.add_argument("--tickers", type=str, default="", help="Comma-separated tickers to backtest.")
    parser.add_argument("--lookback-samples", type=int, default=12, help="Rolling window length (momentum / range / breakout).")
    parser.add_argument("--threshold-cents", type=float, default=1.5, help="Distance trigger for momentum/mean-reversion/breakout.")
    parser.add_argument("--algo", type=str, default=None, help="Algorithm key; if omitted, prompts in an interactive terminal.")
    parser.add_argument("--rsi-period", type=int, default=14, dest="rsi_period", help="RSI lookback period.")
    parser.add_argument("--rsi-oversold", type=float, default=30.0, dest="rsi_oversold")
    parser.add_argument("--rsi-overbought", type=float, default=70.0, dest="rsi_overbought")
    parser.add_argument("--range-low", type=float, default=0.15, dest="range_low", help="Range strategy: buy YES below this fraction of window.")
    parser.add_argument("--range-high", type=float, default=0.85, dest="range_high", help="Range strategy: buy NO above this fraction of window.")
    parser.add_argument("--unit-size", type=int, default=1, help="Contracts per non-hold signal.")
    parser.add_argument("--backtest-days", type=int, default=30, help="Historical lookback window in days.")
    parser.add_argument("--backtest-trade-limit", type=int, default=1000, help="Max trade points per market.")
    return parser


if __name__ == "__main__":
    parser = build_parser()
    run_backtest(parser.parse_args())
