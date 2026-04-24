from collections import deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass
class MomentumState:
    history: Deque[float] = field(default_factory=deque)

    def update(self, value: float, lookback: int) -> float:
        self.history.append(value)
        while len(self.history) > lookback:
            self.history.popleft()
        return sum(self.history) / len(self.history)


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


def momentum_signal(mid: float, moving_avg: float, threshold_cents: float) -> str:
    delta = mid - moving_avg
    if delta >= threshold_cents:
        return "BUY_YES"
    if delta <= -threshold_cents:
        return "BUY_NO"
    return "HOLD"
