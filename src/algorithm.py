"""Plug-and-play trading algorithms (signals only; execution is PaperPosition elsewhere)."""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from typing import ClassVar, Deque, Dict, List, Optional, Type


Signal = str  # "BUY_YES" | "BUY_NO" | "HOLD"


@dataclass
class AlgorithmParams:
    """Shared knobs CLI passes into algorithms."""

    lookback_samples: int = 12
    threshold_cents: float = 1.5
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    # Stochastic-style: extremes of the rolling range (0–1 scale).
    range_low: float = 0.15
    range_high: float = 0.85


class TradingAlgorithm(ABC):
    """One instance per ticker so state stays isolated."""

    key: ClassVar[str] = ""
    display_name: ClassVar[str] = ""

    def __init__(self, params: AlgorithmParams) -> None:
        self.params = params

    @abstractmethod
    def reset(self) -> None:
        ...

    @abstractmethod
    def on_price(self, price: float) -> Signal:
        """Called once per new trade price (YES cents, 0–100 scale)."""


# --- Shared helpers ------------------------------------------------------------


class _RollingPrices:
    def __init__(self, maxlen: int) -> None:
        self._deque: Deque[float] = deque(maxlen=maxlen)

    def push(self, price: float) -> None:
        self._deque.append(price)

    def values(self) -> List[float]:
        return list(self._deque)

    def __len__(self) -> int:
        return len(self._deque)

    def sma(self) -> Optional[float]:
        if len(self._deque) < self._deque.maxlen:
            return None
        return sum(self._deque) / len(self._deque)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# --- Implementations ------------------------------------------------------------


class MomentumAlgorithm(TradingAlgorithm):
    key = "momentum"
    display_name = "Momentum (trend-following vs rolling average)"

    def __init__(self, params: AlgorithmParams) -> None:
        super().__init__(params)
        self._window = _RollingPrices(maxlen=params.lookback_samples)

    def reset(self) -> None:
        self._window = _RollingPrices(maxlen=self.params.lookback_samples)

    def on_price(self, price: float) -> Signal:
        self._window.push(price)
        avg = self._window.sma()
        if avg is None:
            return "HOLD"
        delta = price - avg
        if delta >= self.params.threshold_cents:
            return "BUY_YES"
        if delta <= -self.params.threshold_cents:
            return "BUY_NO"
        return "HOLD"


class MeanReversionAlgorithm(TradingAlgorithm):
    key = "mean_reversion"
    display_name = "Mean reversion (fade stretch from average)"

    def __init__(self, params: AlgorithmParams) -> None:
        super().__init__(params)
        self._window = _RollingPrices(maxlen=params.lookback_samples)

    def reset(self) -> None:
        self._window = _RollingPrices(maxlen=self.params.lookback_samples)

    def on_price(self, price: float) -> Signal:
        self._window.push(price)
        avg = self._window.sma()
        if avg is None:
            return "HOLD"
        delta = price - avg
        # High vs average: YES looks rich -> lean NO; low vs average -> lean YES.
        if delta >= self.params.threshold_cents:
            return "BUY_NO"
        if delta <= -self.params.threshold_cents:
            return "BUY_YES"
        return "HOLD"


class RsiAlgorithm(TradingAlgorithm):
    key = "rsi"
    display_name = "RSI-style (oversold/overbought on recent changes)"

    def __init__(self, params: AlgorithmParams) -> None:
        super().__init__(params)
        self._period = max(2, params.rsi_period)
        self._closes: Deque[float] = deque(maxlen=self._period + 1)

    def reset(self) -> None:
        self._closes.clear()

    def on_price(self, price: float) -> Signal:
        self._closes.append(price)
        if len(self._closes) < self._period + 1:
            return "HOLD"
        gains = 0.0
        losses = 0.0
        seq = list(self._closes)
        for i in range(1, len(seq)):
            d = seq[i] - seq[i - 1]
            if d >= 0:
                gains += d
            else:
                losses += -d
        period = float(self._period)
        avg_gain = gains / period
        avg_loss = losses / period
        if avg_loss == 0:
            rsi = 100.0 if avg_gain > 0 else 50.0
        else:
            rs = avg_gain / avg_loss
            rsi = 100.0 - (100.0 / (1.0 + rs))
        if rsi <= self.params.rsi_oversold:
            return "BUY_YES"
        if rsi >= self.params.rsi_overbought:
            return "BUY_NO"
        return "HOLD"


class RangePositionAlgorithm(TradingAlgorithm):
    key = "range"
    display_name = "Range position (stochastic-style min/max window)"

    def __init__(self, params: AlgorithmParams) -> None:
        super().__init__(params)
        self._window = _RollingPrices(maxlen=params.lookback_samples)

    def reset(self) -> None:
        self._window = _RollingPrices(maxlen=self.params.lookback_samples)

    def on_price(self, price: float) -> Signal:
        self._window.push(price)
        vals = self._window.values()
        if len(vals) < self.params.lookback_samples:
            return "HOLD"
        lo = min(vals)
        hi = max(vals)
        if hi - lo < 1e-6:
            return "HOLD"
        pos = (price - lo) / (hi - lo)
        pos = _clamp(pos, 0.0, 1.0)
        if pos <= self.params.range_low:
            return "BUY_YES"
        if pos >= self.params.range_high:
            return "BUY_NO"
        return "HOLD"


class BreakoutAlgorithm(TradingAlgorithm):
    key = "breakout"
    display_name = "Breakout (close outside prior min/max band)"

    def __init__(self, params: AlgorithmParams) -> None:
        super().__init__(params)
        self._prev_maxlen = max(2, params.lookback_samples)
        self._history: Deque[float] = deque(maxlen=self._prev_maxlen)

    def reset(self) -> None:
        self._history.clear()

    def on_price(self, price: float) -> Signal:
        if len(self._history) < self._prev_maxlen:
            self._history.append(price)
            return "HOLD"
        window = list(self._history)
        lo = min(window)
        hi = max(window)
        signal: Signal = "HOLD"
        if price > hi + self.params.threshold_cents:
            signal = "BUY_YES"
        elif price < lo - self.params.threshold_cents:
            signal = "BUY_NO"
        self._history.append(price)
        return signal


# --- Registry & factory ------------------------------------------------------------

ALGORITHM_REGISTRY: Dict[str, Type[TradingAlgorithm]] = {
    cls.key: cls
    for cls in (
        MomentumAlgorithm,
        MeanReversionAlgorithm,
        RsiAlgorithm,
        RangePositionAlgorithm,
        BreakoutAlgorithm,
    )
}


def list_algorithm_choices() -> List[tuple[str, str]]:
    return sorted((cls.key, cls.display_name) for cls in ALGORITHM_REGISTRY.values())


def create_algorithm(key: str, params: AlgorithmParams) -> TradingAlgorithm:
    normalized = key.strip().lower().replace("-", "_")
    if normalized not in ALGORITHM_REGISTRY:
        known = ", ".join(sorted(ALGORITHM_REGISTRY))
        raise ValueError(f"Unknown algorithm '{key}'. Choose one of: {known}")
    algo = ALGORITHM_REGISTRY[normalized](params)
    algo.reset()
    return algo


def resolve_algorithm_key(cli_algo: Optional[str]) -> str:
    """Interactive pick if no --algo; non-interactive stdin defaults to momentum."""
    if cli_algo:
        return cli_algo.strip().lower().replace("-", "_")
    if not sys.stdin.isatty():
        return "momentum"
    print("Select algorithm:")
    for k, title in list_algorithm_choices():
        print(f"  [{k}] {title}")
    choice = input("Enter key (default: momentum): ").strip().lower().replace("-", "_")
    return choice or "momentum"


def algorithm_params_from_args(args: object) -> AlgorithmParams:
    return AlgorithmParams(
        lookback_samples=int(getattr(args, "lookback_samples", 12)),
        threshold_cents=float(getattr(args, "threshold_cents", 1.5)),
        rsi_period=int(getattr(args, "rsi_period", 14)),
        rsi_oversold=float(getattr(args, "rsi_oversold", 30.0)),
        rsi_overbought=float(getattr(args, "rsi_overbought", 70.0)),
        range_low=float(getattr(args, "range_low", 0.15)),
        range_high=float(getattr(args, "range_high", 0.85)),
    )


# --- Lightweight rolling helper (legacy / stateless combos) ----------------------


@dataclass
class MomentumState:
    """Rolling window for a simple moving average (used with momentum_signal())."""

    history: Deque[float] = field(default_factory=deque)

    def update(self, value: float, lookback: int) -> float:
        self.history.append(value)
        while len(self.history) > lookback:
            self.history.popleft()
        return sum(self.history) / len(self.history)


def momentum_signal(mid: float, moving_avg: float, threshold_cents: float) -> Signal:
    """Stateless momentum check (same rule as MomentumAlgorithm)."""

    delta = mid - moving_avg
    if delta >= threshold_cents:
        return "BUY_YES"
    if delta <= -threshold_cents:
        return "BUY_NO"
    return "HOLD"


@dataclass
class PaperPosition:
    qty_yes: int = 0
    avg_yes: float = 0.0
    realized_pnl: float = 0.0

    def apply_signal(self, signal: str, price: float, unit_size: int) -> None:
        if signal == "BUY_YES":
            self._buy_yes(price, unit_size)
        elif signal == "BUY_NO":
            self._buy_no(price, unit_size)

    def _buy_yes(self, price_yes: float, qty: int) -> None:
        if self.qty_yes < 0:
            close_qty = min(qty, abs(self.qty_yes))
            self.realized_pnl += (100.0 - price_yes - self.avg_yes) * close_qty
            self.qty_yes += close_qty
            qty -= close_qty
            if self.qty_yes == 0:
                self.avg_yes = 0.0

        if qty > 0:
            new_qty = self.qty_yes + qty
            self.avg_yes = ((self.avg_yes * self.qty_yes) + (price_yes * qty)) / new_qty if self.qty_yes > 0 else price_yes
            self.qty_yes = new_qty

    def _buy_no(self, price_yes: float, qty: int) -> None:
        no_price = 100.0 - price_yes
        if self.qty_yes > 0:
            close_qty = min(qty, self.qty_yes)
            self.realized_pnl += (price_yes - self.avg_yes) * close_qty
            self.qty_yes -= close_qty
            qty -= close_qty
            if self.qty_yes == 0:
                self.avg_yes = 0.0

        if qty > 0:
            short_yes_price = 100.0 - no_price
            new_abs = abs(self.qty_yes) + qty
            self.avg_yes = (
                ((self.avg_yes * abs(self.qty_yes)) + (short_yes_price * qty)) / new_abs if self.qty_yes < 0 else short_yes_price
            )
            self.qty_yes -= qty

    def mark_to_market(self, price_yes: float) -> float:
        if self.qty_yes > 0:
            return (price_yes - self.avg_yes) * self.qty_yes
        if self.qty_yes < 0:
            return ((100.0 - price_yes) - self.avg_yes) * abs(self.qty_yes)
        return 0.0
